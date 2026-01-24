from peewee import CharField, Model

from tracekit.db import db


class ProviderSync(Model):
    """Tracks which months have been synced for each provider."""

    year_month = CharField()  # Format: YYYY-MM
    provider = CharField()  # e.g., 'strava', 'spreadsheet', 'ridewithgps'

    class Meta:
        database = db
        indexes = ((("year_month", "provider"), True),)  # unique together

    @classmethod
    def get_or_none(cls, year_month: str, provider: str) -> "ProviderSync":
        """Get the sync record for a specific year-month and provider."""
        return cls.select().where((cls.year_month == year_month) & (cls.provider == provider)).first()
