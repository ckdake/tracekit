"""Celery worker for tracekit background tasks.

Start the worker:
    celery -A tracekit.worker worker --loglevel=info --concurrency=1

Start the scheduler:
    celery -A tracekit.worker beat --loglevel=info

Observe via Flower (runs as its own container in production):
    celery -A tracekit.worker flower
"""

import contextlib
import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("tracekit", broker=BROKER_URL, backend=RESULT_BACKEND)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Keep task results for 24 hours so the UI can poll status
    result_expires=86400,
    # Emit task events so Flower can display task history and details
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Store STARTED state in the result backend (visible in Flower)
    task_track_started=True,
    beat_schedule={
        "daily": {
            "task": "tracekit.worker.daily",
            # 3 AM UTC every day
            "schedule": crontab(hour=3, minute=0),
        },
    },
)


@celery_app.task(bind=True, name="tracekit.worker.pull_month")
def pull_month(self, year_month: str, user_id: int = 0):
    """Fan out per-provider pull jobs for *year_month*.

    Deletes existing data for the month so each provider starts with a clean
    slate, then enqueues one :func:`pull_provider_month` task per enabled
    provider so they can run (and fail) independently in parallel.
    """
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.core import tracekit as tracekit_class
        from tracekit.provider_status import PULL_STATUS_QUEUED, is_pull_active, set_pull_status

        with tracekit_class() as tk:
            tk.delete_month_activities(year_month)
            providers = tk.enabled_providers

        with contextlib.suppress(Exception):
            from tracekit.provider_status import MONTH_SYNC_UNKNOWN, set_month_sync_status

            set_month_sync_status(year_month, MONTH_SYNC_UNKNOWN)

        for provider_name in providers:
            if is_pull_active(year_month, provider_name):
                continue  # already queued or running — skip to avoid duplicates
            task = pull_provider_month.delay(year_month, provider_name, user_id=user_id)
            with contextlib.suppress(Exception):
                set_pull_status(year_month, provider_name, PULL_STATUS_QUEUED, job_id=task.id)
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Pull failed to start for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, max_retries=1, name="tracekit.worker.pull_provider_month")
def pull_provider_month(self, year_month: str, provider_name: str, user_id: int = 0):
    """Pull activities for *year_month* from a single named provider.

    Handles rate-limit errors from the provider: short-term limits trigger a
    retry after the cooldown; long-term (daily) limits fail immediately.
    """
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.provider_status import PULL_STATUS_STARTED, set_pull_status

        set_pull_status(year_month, provider_name, PULL_STATUS_STARTED, job_id=self.request.id)
    except Exception:
        pass

    with contextlib.suppress(Exception):
        from tracekit.provider_status import MONTH_SYNC_UNKNOWN, set_month_sync_status

        set_month_sync_status(year_month, MONTH_SYNC_UNKNOWN)

    try:
        from tracekit.core import tracekit as tracekit_class

        with tracekit_class() as tk:
            tk.pull_provider_activities(year_month, provider_name)

        try:
            from tracekit.provider_status import PULL_STATUS_SUCCESS, set_pull_status

            set_pull_status(year_month, provider_name, PULL_STATUS_SUCCESS)
        except Exception:
            pass
    except Exception as exc:
        from tracekit.provider_status import RATE_LIMIT_SHORT_TERM, ProviderRateLimitError

        if isinstance(exc, ProviderRateLimitError):
            if exc.limit_type == RATE_LIMIT_SHORT_TERM and exc.retry_after:
                # Short-term: re-queue status (same task ID on retry), notify, then retry
                try:
                    from tracekit.provider_status import PULL_STATUS_QUEUED, set_pull_status

                    set_pull_status(year_month, provider_name, PULL_STATUS_QUEUED, job_id=self.request.id)
                except Exception:
                    pass
                raise self.retry(countdown=exc.retry_after, exc=exc)
            else:
                # Long-term: fail immediately without retry
                try:
                    from tracekit.provider_status import PULL_STATUS_ERROR, record_rate_limit, set_pull_status

                    set_pull_status(year_month, provider_name, PULL_STATUS_ERROR, message=str(exc))
                    record_rate_limit(
                        provider=exc.provider,
                        limit_type=exc.limit_type,
                        reset_at=exc.reset_at,
                        operation="pull",
                        message=str(exc),
                    )
                except Exception:
                    pass
                try:
                    from tracekit.notification import create_notification

                    create_notification(
                        f"Strava daily rate limit exceeded — {provider_name} pull for {year_month} will not be retried. "
                        f"Limit resets at midnight UTC. See https://developers.strava.com/docs/rate-limits/",
                        category="error",
                    )
                except Exception:
                    pass
                raise

        try:
            from tracekit.provider_status import PULL_STATUS_ERROR, set_pull_status

            set_pull_status(year_month, provider_name, PULL_STATUS_ERROR, message=str(exc))
        except Exception:
            pass
        try:
            from tracekit.notification import create_notification

            create_notification(f"{provider_name} pull failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.reset_month")
def reset_month(self, year_month: str, user_id: int = 0):
    """Reset (delete) all activities and sync records for a given YYYY-MM."""
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.commands.reset import run

        run(["--date", year_month])
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.reset_all")
def reset_all(self, user_id: int = 0):
    """Reset (delete) ALL activities and sync records."""
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.commands.reset import run

        run(["--force"])
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset all failed: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, max_retries=1, name="tracekit.worker.apply_sync_change")
def apply_sync_change(self, change_dict: dict, year_month: str, user_id: int = 0):
    """Apply a single ActivityChange for *year_month*.

    *change_dict* is the dict produced by ``ActivityChange.to_dict()``.
    For ADD_ACTIVITY changes the grouped activity data is re-computed by
    re-pulling the month from all providers (no network calls if the data
    is already cached in the local DB).
    """
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.core import tracekit as tracekit_class
        from tracekit.sync import ActivityChange, apply_change, compute_month_changes

        change = ActivityChange.from_dict(change_dict)

        with tracekit_class() as tk:
            # For ADD_ACTIVITY we need the grouped activity data.
            # We always compute it; for other change types the grouped arg is ignored.
            grouped, _ = compute_month_changes(tk, year_month)
            success, msg = apply_change(change, tk, grouped=grouped)

        provider = change_dict.get("provider", "unknown")
        if success:
            try:
                from tracekit.provider_status import record_operation

                record_operation(provider, change_dict.get("change_type", "apply_change"), True, msg)
            except Exception:
                pass
            with contextlib.suppress(Exception):
                from tracekit.provider_status import MONTH_SYNC_UNKNOWN, set_month_sync_status

                set_month_sync_status(year_month, MONTH_SYNC_UNKNOWN)
            return {"success": True, "message": msg}
        else:
            try:
                from tracekit.notification import create_notification
                from tracekit.provider_status import record_operation

                record_operation(provider, change_dict.get("change_type", "apply_change"), False, msg)
                create_notification(f"Sync change failed: {msg}", category="error")
            except Exception:
                pass
            return {"success": False, "message": msg}

    except Exception as exc:
        from tracekit.provider_status import RATE_LIMIT_SHORT_TERM, ProviderRateLimitError

        if isinstance(exc, ProviderRateLimitError):
            if exc.limit_type == RATE_LIMIT_SHORT_TERM and exc.retry_after:
                raise self.retry(countdown=exc.retry_after, exc=exc)
            else:
                try:
                    from tracekit.notification import create_notification

                    create_notification(
                        "Strava daily rate limit exceeded — sync change not applied. "
                        "Resets at midnight UTC. See https://developers.strava.com/docs/rate-limits/",
                        category="error",
                    )
                except Exception:
                    pass
                raise

        msg = str(exc)
        try:
            from tracekit.notification import create_notification
            from tracekit.provider_status import record_operation

            provider = change_dict.get("provider", "unknown")
            record_operation(provider, change_dict.get("change_type", "apply_change"), False, msg)
            create_notification(f"Sync change error for {year_month}: {msg}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.pull_file")
def pull_file(self, user_id: int = 0):
    """Scan the activities data folder and enqueue one process_file task per new file.

    Files already in the database (matched by basename + checksum) are skipped
    immediately — no parse work is queued for them.  This task is a lightweight
    fan-out; the actual parsing happens in process_file.
    """
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.core import tracekit as tracekit_class

        with tracekit_class() as tk:
            if not tk.file:
                return {"queued": 0, "reason": "file provider not enabled"}
            unprocessed = tk.file.list_unprocessed_files()

        count = len(unprocessed)
        for file_path in unprocessed:
            process_file.delay(file_path, user_id=user_id)

        return {"queued": count}
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"File pull scan failed: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.process_file")
def process_file(self, file_path: str, user_id: int = 0):
    """Parse and ingest a single activity file.

    Idempotent: if the file has already been processed (matched by checksum)
    this task exits without writing to the database.
    """
    import os as _os

    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.core import tracekit as tracekit_class

        with tracekit_class() as tk:
            if not tk.file:
                return {"status": "skipped", "reason": "file provider not enabled"}
            result = tk.file.process_single_file(file_path)

        return result
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(
                f"Failed to process file {_os.path.basename(file_path)}: {exc}",
                category="error",
            )
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.reset_provider")
def reset_provider(self, provider_name: str, user_id: int = 0):
    """Delete all activities and sync records for a single named provider.

    Does not touch any files on disk — only removes this tracekit\'s stored
    copy of the provider\'s activities and the associated sync records.
    """
    from tracekit.user_context import set_user_id

    set_user_id(user_id)

    try:
        from tracekit.core import tracekit as tracekit_class
        from tracekit.provider_sync import ProviderSync

        with tracekit_class() as tk:
            provider = tk.get_provider(provider_name)
            if provider is None:
                raise ValueError(f"Provider not found or not enabled: {provider_name}")
            deleted = provider.reset_activities(date_filter=None)

        sync_deleted = (
            ProviderSync.delete()
            .where((ProviderSync.provider == provider_name) & (ProviderSync.user_id == user_id))
            .execute()
        )
        return {"provider": provider_name, "activities_deleted": deleted, "sync_records_deleted": sync_deleted}
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset {provider_name} failed: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(name="tracekit.worker.daily")
def daily():
    """Daily heartbeat — pull the relevant month for every known user.

    On the 1st of the month the previous month is pulled (activities from the
    last day of the prior month haven't been pulled yet).  All other days pull
    the current month.

    Fan-out: one pull_month task per distinct user_id that has ProviderSync
    rows (covers user_id=0 / CLI and all web users).  user_id=0 is always
    included even if no rows exist yet.
    """
    from datetime import UTC, datetime, timedelta

    from tracekit.provider_sync import ProviderSync

    now = datetime.now(UTC)
    if now.day == 1:
        prev = now.replace(day=1) - timedelta(days=1)
        year_month = prev.strftime("%Y-%m")
    else:
        year_month = now.strftime("%Y-%m")

    try:
        user_ids = {row.user_id for row in ProviderSync.select(ProviderSync.user_id).distinct()}
    except Exception:
        user_ids = set()
    user_ids.add(0)  # always include CLI/unscoped user

    for uid in user_ids:
        pull_month.delay(year_month, user_id=uid)

    pull_file.delay(user_id=0)  # file scanning is always unscoped
