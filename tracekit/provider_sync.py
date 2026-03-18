from enum import StrEnum

from peewee import CharField, IntegerField, Model

from tracekit.db import db
from tracekit.user_context import get_user_id


class SyncStatus(StrEnum):
    ENQUEUED = "enqueued"
    STARTED = "started"
    DONE = "done"


class ProviderSync(Model):
    """Tracks which months have been synced for each provider."""

    year_month = CharField()  # Format: YYYY-MM
    provider = CharField()  # e.g., 'strava', 'spreadsheet', 'ridewithgps'
    user_id = IntegerField(default=0)
    status = CharField(default=SyncStatus.DONE)  # enqueued | started | done

    class Meta:
        database = db
        indexes = ((("year_month", "provider", "user_id"), True),)  # unique together

    @classmethod
    def get_or_none(cls, year_month: str, provider: str) -> "ProviderSync":
        """Get the sync record for a specific year-month and provider."""
        return (
            cls.select()
            .where((cls.year_month == year_month) & (cls.provider == provider) & (cls.user_id == get_user_id()))
            .first()
        )

    @classmethod
    def is_done(cls, year_month: str, provider: str) -> bool:
        """Return True if this month has been fully synced (status=done)."""
        return (
            cls.select()
            .where(
                (cls.year_month == year_month)
                & (cls.provider == provider)
                & (cls.user_id == get_user_id())
                & (cls.status == SyncStatus.DONE)
            )
            .exists()
        )

    @classmethod
    def upsert_status(cls, year_month: str, provider: str, status: SyncStatus) -> None:
        """Create or replace the sync record with the given status."""
        uid = get_user_id()
        cls.delete().where((cls.year_month == year_month) & (cls.provider == provider) & (cls.user_id == uid)).execute()
        cls.create(year_month=year_month, provider=provider, user_id=uid, status=status)
