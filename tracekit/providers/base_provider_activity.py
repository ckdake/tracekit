"""Base activity model for provider-specific activities.

This module defines the base class that all provider-specific activity models
should inherit from, providing common fields and functionality.
"""

import zoneinfo
from datetime import UTC, datetime

from peewee import (
    SQL,
    CharField,
    DateTimeField,
    DecimalField,
    IntegerField,
    Model,
    TextField,
)

from tracekit.db import db


class BaseProviderActivity(Model):
    """Base class for provider-specific activity models.

    This class defines the common fields that all provider activities should have.
    Each provider can extend this with their own specific fields.
    """

    # Core identification - each provider should override this
    provider_id = CharField(max_length=50, index=True)  # ID from the provider

    # Core activity data
    name = CharField(max_length=255, null=True)
    distance = DecimalField(max_digits=10, decimal_places=6, null=True)  # in miles
    start_time = IntegerField(null=True)  # Unix timestamp

    # Activity classification
    activity_type = CharField(max_length=50, null=True)
    duration_hms = CharField(max_length=20, null=True)
    equipment = CharField(max_length=255, null=True)

    # Location information
    location_name = CharField(max_length=255, null=True)
    city = CharField(max_length=100, null=True)
    state = CharField(max_length=50, null=True)

    # Performance metrics
    max_speed = DecimalField(max_digits=8, decimal_places=4, null=True)
    avg_heart_rate = IntegerField(null=True)
    max_heart_rate = IntegerField(null=True)
    calories = IntegerField(null=True)
    avg_cadence = IntegerField(null=True)

    # Elevation data
    max_elevation = DecimalField(max_digits=10, decimal_places=4, null=True)
    total_elevation_gain = DecimalField(max_digits=10, decimal_places=4, null=True)

    # Environmental conditions
    temperature = DecimalField(max_digits=6, decimal_places=2, null=True)

    # Additional information
    notes = TextField(null=True)

    # Raw data storage for provider-specific information
    raw_data = TextField(null=True)

    # Metadata timestamps
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])
    updated_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])

    # User association — 0 = CLI/unscoped, web users get their own ID
    user_id = IntegerField(default=0, index=True)

    class Meta:
        database = db
        abstract = True  # This is a base class, not a concrete table

    def get_correlation_key(self) -> str:
        """Generate a correlation key for matching activities across providers.

        This should be deterministic and slightly fuzzy to account for different
        distance calculations across providers. Uses date + rounded distance.
        """
        if not self.start_time or not self.distance:
            return ""

        try:
            # Convert timestamp to date string
            dt = datetime.fromtimestamp(self.start_time, UTC)
            date_str = dt.strftime("%Y-%m-%d")

            # Round distance to nearest 0.1 mile for fuzzy matching
            rounded_distance = round(float(self.distance) * 10) / 10

            return f"{date_str}_{rounded_distance}"
        except (ValueError, TypeError):
            return ""

    @property
    def date(self):
        """Get the date of the activity from start_time."""
        start_time_val = getattr(self, "start_time", None)
        if not start_time_val:
            return None
        try:
            return datetime.fromtimestamp(start_time_val, UTC).date()
        except (ValueError, TypeError):
            return None

    @property
    def local_time(self) -> str:
        """Get formatted local time string."""
        start_time_val = getattr(self, "start_time", None)
        if not start_time_val:
            return ""
        try:
            dt = datetime.fromtimestamp(start_time_val, UTC)
            # Default to US/Eastern if no timezone provided
            local_tz = zoneinfo.ZoneInfo("US/Eastern")
            local_dt = dt.astimezone(local_tz)
            return local_dt.strftime("%Y-%m-%d %H:%M %Z")
        except (ValueError, TypeError, Exception):
            return ""

    @property
    def duration(self):
        """Get duration in seconds from duration_hms."""
        duration_hms_val = getattr(self, "duration_hms", None)
        if not duration_hms_val:
            return None
        try:
            parts = str(duration_hms_val).split(":")
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, TypeError):
            pass
        return None

    @duration.setter
    def duration(self, value):
        """Set duration_hms from seconds value."""
        if value is None:
            self.duration_hms = None
        else:
            try:
                total_seconds = int(value)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                self.duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            except (ValueError, TypeError):
                self.duration_hms = None

    def __str__(self) -> str:
        """String representation of the activity."""
        return f"{self.__class__.__name__}({self.provider_id}: {self.name or 'Unnamed'})"
