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
        from tracekit.notification import create_notification

        create_notification(f"Pull started for {year_month}", category="info")
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
            from tracekit.notification import create_notification

            create_notification(f"Pull finished for {year_month}", category="info")
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Pull failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise


@celery_app.task(name="tracekit.worker.daily")
def daily():
    """Daily heartbeat — pull current month and notify."""
    from datetime import UTC, datetime

    year_month = datetime.now(UTC).strftime("%Y-%m")
    try:
        from tracekit.notification import create_notification

        create_notification(f"Daily sync running for {year_month}", category="info")
    except Exception:
        pass

    try:
        from tracekit.commands.pull import run

        run(["--date", year_month])

        try:
            from tracekit.notification import create_notification

            create_notification(f"Daily sync finished for {year_month}", category="info")
        except Exception:
            pass
    except Exception as exc:
        try:
            from tracekit.notification import create_notification

            create_notification(f"Daily sync failed for {year_month}: {exc}", category="error")
        except Exception:
            pass
        raise
