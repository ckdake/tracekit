from peewee import CharField, IntegerField, Model

from tracekit.db import db
from tracekit.user_context import get_user_id


class ProviderSync(Model):
    """Tracks which months have been synced for each provider."""

    year_month = CharField()  # Format: YYYY-MM
    provider = CharField()  # e.g., 'strava', 'spreadsheet', 'ridewithgps'
    user_id = IntegerField(default=0)

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
