"""Core Activity model for tracekit."""

from peewee import (
    SQL,
    CharField,
    DateField,
    DateTimeField,
    DecimalField,
    FloatField,
    IntegerField,
    Model,
    TextField,
)

from tracekit.db import db


class Activity(Model):
    """
    Central logical representation of an activity in tracekit.

    This represents the "source of truth" activity that can be linked to
    multiple provider-specific activity records. Each Activity represents
    a single logical workout/ride/activity.
    """

    # Core activity data - the authoritative/computed values
    start_time = CharField(null=True, index=True)  # Stored as Unix timestamp string
    date = DateField(null=True, index=True)
    distance = FloatField(null=True)  # in miles

    # Authoritative names and descriptions
    name = CharField(null=True)  # The canonical name for the activity
    notes = TextField(null=True)  # Additional notes/description

    # Equipment and conditions (authoritative)
    equipment = CharField(null=True)
    activity_type = CharField(null=True)
    temperature = DecimalField(null=True)

    # Location data (authoritative)
    location_name = CharField(null=True)
    city = CharField(null=True)
    state = CharField(null=True)

    # Performance metrics (authoritative)
    duration_hms = CharField(null=True)
    max_speed = DecimalField(null=True)
    avg_heart_rate = IntegerField(null=True)
    max_heart_rate = IntegerField(null=True)
    calories = IntegerField(null=True)
    max_elevation = IntegerField(null=True)
    total_elevation_gain = IntegerField(null=True)
    avg_cadence = IntegerField(null=True)

    # Links to provider-specific activity records
    # These are the IDs from each provider for correlation
    spreadsheet_id = CharField(null=True, index=True)  # Row number or custom ID
    strava_id = CharField(null=True, index=True)
    garmin_id = CharField(null=True, index=True)
    ridewithgps_id = CharField(null=True, index=True)

    # Provider-specific data (stored as JSON) - kept for compatibility
    strava_data = TextField(null=True)  # JSON blob of raw Strava data
    ridewithgps_data = TextField(null=True)  # JSON blob of raw RWGPS data
    garmin_data = TextField(null=True)  # JSON blob of raw Garmin data
    spreadsheet_data = TextField(null=True)  # JSON blob of spreadsheet data

    # Metadata for correlation and tracking
    correlation_key = CharField(null=True, index=True)  # For deterministic matching
    last_updated = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])
    original_filename = CharField(null=True)  # For imported files
    source = CharField(default="tracekit")  # Source of truth indicator

    # User association — 0 = CLI/unscoped, web users get their own ID
    user_id = IntegerField(default=0, index=True)

    class Meta:
        database = db
