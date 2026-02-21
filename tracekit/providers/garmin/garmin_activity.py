"""Garmin-specific activity model."""

from peewee import CharField

from tracekit.db import db
from tracekit.providers.base_provider_activity import BaseProviderActivity


class GarminActivity(BaseProviderActivity):
    """Garmin-specific activity data.

    Stores raw activity data pulled from the Garmin Connect API.
    """

    # Garmin-specific ID field
    garmin_id = CharField(max_length=50, unique=True, index=True)

    # Device that recorded this activity (e.g. "Forerunner 965")
    device_name = CharField(max_length=255, null=True)

    class Meta:  # type: ignore
        database = db
        table_name = "garmin_activities"

    @property
    def provider_id(self) -> str:
        """Return the Garmin ID as the provider ID."""
        return str(self.garmin_id) if self.garmin_id else ""

    @provider_id.setter
    def provider_id(self, value: str) -> None:
        """Set the Garmin ID when provider_id is set."""
        self.garmin_id = value
