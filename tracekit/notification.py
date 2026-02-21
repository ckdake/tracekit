"""Notification model — lightweight in-DB bell-icon notifications."""

from datetime import UTC, datetime, timedelta

from peewee import BooleanField, CharField, IntegerField, Model

from tracekit.db import db

EXPIRY_24H = int(timedelta(hours=24).total_seconds())


class Notification(Model):
    """A single notification shown in the UI bell-icon dropdown."""

    message = CharField()
    category = CharField(default="info")  # "info" | "error"
    read = BooleanField(default=False)
    created = IntegerField()  # Unix timestamp
    expires = IntegerField(null=True, default=None)  # Unix timestamp; NULL = never expires

    class Meta:
        database = db
        table_name = "notification"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "category": self.category,
            "read": self.read,
            "created": self.created,
            "expires": self.expires,
        }


def create_notification(
    message: str,
    category: str = "info",
    expires: int | None = None,
) -> Notification:
    """Insert a new notification row.  Safe to call from anywhere.

    Pass ``expires`` as a Unix timestamp to automatically hide the notification
    after that time.  Use ``expiry_timestamp()`` for convenience.
    """
    try:
        from tracekit.db import _configured, get_db

        if not _configured:
            # DB not yet configured in this worker process — skip silently.
            # The API route already creates a "scheduled" notification when
            # the task is enqueued, so this pre-task ping is non-essential.
            return None  # type: ignore[return-value]

        db_instance = get_db()
        db_instance.connect(reuse_if_open=True)
        return Notification.create(
            message=message,
            category=category,
            created=int(datetime.now(UTC).timestamp()),
            expires=expires,
        )
    except Exception as e:
        # Never let notification creation crash the caller
        print(f"[notification] failed to create: {e}")
        return None  # type: ignore[return-value]


def expiry_timestamp(hours: int = 24) -> int:
    """Return a Unix timestamp ``hours`` from now."""
    return int((datetime.now(UTC) + timedelta(hours=hours)).timestamp())
