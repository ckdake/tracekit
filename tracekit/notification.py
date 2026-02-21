"""Notification model — lightweight in-DB bell-icon notifications."""

from datetime import UTC, datetime

from peewee import BooleanField, CharField, IntegerField, Model

from tracekit.db import db


class Notification(Model):
    """A single notification shown in the UI bell-icon dropdown."""

    message = CharField()
    category = CharField(default="info")  # "info" | "error"
    read = BooleanField(default=False)
    created = IntegerField()  # Unix timestamp

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
        }


def create_notification(message: str, category: str = "info") -> Notification:
    """Insert a new notification row.  Safe to call from anywhere."""
    try:
        from tracekit.db import get_db

        db_instance = get_db()
        db_instance.connect(reuse_if_open=True)
        return Notification.create(
            message=message,
            category=category,
            created=int(datetime.now(UTC).timestamp()),
        )
    except Exception as e:
        # Never let notification creation crash the caller
        print(f"[notification] failed to create: {e}")
        return None  # type: ignore[return-value]
