"""Intervals.icu-specific activity model."""

from peewee import CharField

from tracekit.db import db
from tracekit.providers.base_provider_activity import BaseProviderActivity


class IntervalsICUActivity(BaseProviderActivity):
    """Intervals.icu-specific activity data.

    Stores raw activity data pulled from the Intervals.icu API.
    """

    intervalsicu_id = CharField(max_length=50, unique=True, index=True)
    # Top-level "source" field from the API (e.g. "STRAVA", "GARMIN", "MANUAL").
    # Used to skip file download offers for activities imported from Strava.
    source = CharField(max_length=64, null=True)

    class Meta:
        database = db
        table_name = "intervalsicu_activities"

    @property
    def provider_id(self) -> str:
        """Return the Intervals.icu ID as the provider ID."""
        return str(self.intervalsicu_id) if self.intervalsicu_id else ""

    @provider_id.setter
    def provider_id(self, value: str) -> None:
        """Set the Intervals.icu ID when provider_id is set."""
        self.intervalsicu_id = value
