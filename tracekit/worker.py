"""Celery worker for tracekit background tasks.

Start the worker:
    celery -A tracekit.worker worker --loglevel=info --concurrency=1

Start the scheduler:
    celery -A tracekit.worker beat --loglevel=info

Observe via Flower (runs as its own container in production):
    celery -A tracekit.worker flower
"""

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
def pull_month(self, year_month: str):
    """Pull activities for a given YYYY-MM from all enabled providers."""
    try:
        from tracekit.notification import create_notification, expiry_timestamp

        create_notification(
            f"Pull started for {year_month}",
            category="info",
            expires=expiry_timestamp(24),
        )
    except Exception:
        pass

    try:
        from tracekit.commands.pull import run
        from tracekit.core import tracekit as tracekit_class

        # Delete existing data for the month so we get a clean re-pull
        with tracekit_class() as tk:
            tk.delete_month_activities(year_month)

        run(["--date", year_month])

        try:
            from tracekit.notification import create_notification, expiry_timestamp

            create_notification(
                f"Pull finished for {year_month}",
                category="info",
                expires=expiry_timestamp(24),
            )
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Pull failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.reset_month")
def reset_month(self, year_month: str):
    """Reset (delete) all activities and sync records for a given YYYY-MM."""
    try:
        from tracekit.notification import create_notification

        create_notification(f"Reset started for {year_month}", category="info")
    except Exception:
        pass

    try:
        from tracekit.commands.reset import run

        run(["--date", year_month])

        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset finished for {year_month}", category="info")
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.reset_all")
def reset_all(self):
    """Reset (delete) ALL activities and sync records."""
    try:
        from tracekit.notification import create_notification

        create_notification("Reset all started", category="info")
    except Exception:
        pass

    try:
        from tracekit.commands.reset import run

        run(["--force"])

        try:
            from tracekit.notification import create_notification

            create_notification("Reset all finished", category="info")
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Reset all failed: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(bind=True, name="tracekit.worker.apply_sync_change")
def apply_sync_change(self, change_dict: dict, year_month: str):
    """Apply a single ActivityChange for *year_month*.

    *change_dict* is the dict produced by ``ActivityChange.to_dict()``.
    For ADD_ACTIVITY changes the grouped activity data is re-computed by
    re-pulling the month from all providers (no network calls if the data
    is already cached in the local DB).
    """
    try:
        from tracekit.notification import create_notification

        create_notification(
            f"Applying sync change ({change_dict.get('change_type')}) for {year_month}",
            category="info",
        )
    except Exception:
        pass

    try:
        from tracekit.core import tracekit as tracekit_class
        from tracekit.sync import ActivityChange, apply_change, compute_month_changes

        change = ActivityChange.from_dict(change_dict)

        with tracekit_class() as tk:
            # For ADD_ACTIVITY we need the grouped activity data.
            # We always compute it; for other change types the grouped arg is ignored.
            grouped, _ = compute_month_changes(tk, year_month)
            success, msg = apply_change(change, tk, grouped=grouped)

        if success:
            try:
                from tracekit.notification import create_notification

                create_notification(f"Sync change applied: {msg}", category="info")
            except Exception:
                pass
            return {"success": True, "message": msg}
        else:
            try:
                from tracekit.notification import create_notification

                create_notification(f"Sync change failed: {msg}", category="error")
            except Exception:
                pass
            raise RuntimeError(msg)

    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Sync change error for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(name="tracekit.worker.daily")
def daily():
    """Daily heartbeat — pull current month and notify."""
    from datetime import UTC, datetime

    year_month = datetime.now(UTC).strftime("%Y-%m")
    try:
        from tracekit.notification import create_notification, expiry_timestamp

        create_notification(
            f"Daily sync running for {year_month}",
            category="info",
            expires=expiry_timestamp(24),
        )
    except Exception:
        pass

    try:
        from tracekit.commands.pull import run

        run(["--date", year_month])

        try:
            from tracekit.notification import create_notification, expiry_timestamp

            create_notification(
                f"Daily sync finished for {year_month}",
                category="info",
                expires=expiry_timestamp(24),
            )
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Daily sync failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise
