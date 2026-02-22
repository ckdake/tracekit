"""Garmin provider for tracekit.

This module defines the GarminProvider class, which provides an interface
for interacting with Garmin Connect activity data, including fetching,
creating, updating activities, and managing gear.
"""

import datetime
import json
from decimal import Decimal
from typing import Any

import dateutil.parser
import garminconnect
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garth.exc import GarthHTTPError

from tracekit.provider_sync import ProviderSync
from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.garmin.garmin_activity import GarminActivity
from tracekit.user_context import get_user_id


class GarminProvider(FitnessProvider):
    """Provider for Garmin Connect activities."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize GarminProvider with config credentials."""
        super().__init__(config)
        self.email = (self.config or {}).get("email", "")
        self.garth_tokens = (self.config or {}).get("garth_tokens", "")
        self.client = None

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return "garmin"

    def _get_client(self):
        """Get authenticated Garmin client."""
        if self.client is None:
            if not self.garth_tokens:
                raise Exception("Garmin tokens not found. Please run 'python -m tracekit auth-garmin' first.")
            try:
                self.client = garminconnect.Garmin()
                self.client.login(self.garth_tokens)
            except Exception as e:
                raise Exception(
                    f"Garmin authentication failed: {e}. Please run 'python -m tracekit auth-garmin' first."
                )
        return self.client

    def _get_device_map(self) -> dict[int, str]:
        """Return a mapping of Garmin deviceId → human-readable product name.

        Calls get_devices() once per sync.  Returns an empty dict on failure
        so that the sync continues even if device info is unavailable.
        """
        try:
            client = self._get_client()
            devices = client.get_devices()
            device_map: dict[int, str] = {}
            for dev in devices or []:
                device_id = dev.get("deviceId")
                # Prefer productDisplayName, fall back to displayName
                name = dev.get("productDisplayName") or dev.get("displayName") or ""
                if device_id and name:
                    device_map[int(device_id)] = name
            return device_map
        except Exception as e:
            print(f"Could not fetch Garmin device list: {e}")
            return {}

    def pull_activities(self, date_filter: str | None = None) -> list[GarminActivity]:
        """
        Sync activities for a given month filter in YYYY-MM format.
        If date_filter is None, pulls all activities (not implemented yet).
        Returns a list of synced GarminActivity objects that have been persisted to the database.
        """
        # For now, require date_filter
        if date_filter is None:
            print("Garmin provider: pulling all activities not implemented yet")
            return []

        # Check if this month has already been synced for this provider
        existing_sync = ProviderSync.get_or_none(date_filter, self.provider_name)
        if existing_sync:
            print(f"Month {date_filter} already synced for {self.provider_name}")
            # Always return activities for the requested month from database
            return self._get_garmin_activities_for_month(date_filter)

        # Build device ID → name map once for this sync
        device_map = self._get_device_map()

        # Get the raw activity data for the month
        raw_activities = self.fetch_activities_for_month(date_filter)
        print(f"Found {len(raw_activities)} Garmin activities for {date_filter}")

        persisted_activities = []

        for raw_activity in raw_activities:
            try:
                # Create GarminActivity from raw data
                garmin_activity = GarminActivity()

                # Set basic activity data (raw_activity is a dict from Garmin API)
                garmin_activity.garmin_id = str(raw_activity.get("activityId", ""))
                garmin_activity.name = str(raw_activity.get("activityName", ""))

                # Activity type
                activity_type_info = raw_activity.get("activityType", {})
                if isinstance(activity_type_info, dict):
                    garmin_activity.activity_type = str(activity_type_info.get("typeKey", ""))
                else:
                    garmin_activity.activity_type = str(activity_type_info or "")

                # Distance conversion from meters to miles
                if raw_activity.get("distance"):
                    distance_meters = float(raw_activity.get("distance", 0))
                    garmin_activity.distance = Decimal(str(distance_meters * 0.000621371))

                # Start time
                if raw_activity.get("startTimeGMT"):
                    start_time_str = raw_activity.get("startTimeGMT")
                    dt = dateutil.parser.parse(start_time_str)
                    garmin_activity.start_time = int(dt.timestamp())

                # Duration
                if raw_activity.get("duration"):
                    total_seconds = int(raw_activity.get("duration", 0))
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    garmin_activity.duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                # Location data
                if raw_activity.get("locationName"):
                    garmin_activity.location_name = str(raw_activity.get("locationName", ""))

                # Performance metrics
                if raw_activity.get("maxSpeed"):
                    # Convert m/s to mph
                    max_speed_ms = float(raw_activity.get("maxSpeed", 0))
                    garmin_activity.max_speed = Decimal(str(max_speed_ms * 2.237))

                if raw_activity.get("averageHR"):
                    garmin_activity.avg_heart_rate = int(raw_activity.get("averageHR", 0))

                if raw_activity.get("maxHR"):
                    garmin_activity.max_heart_rate = int(raw_activity.get("maxHR", 0))

                if raw_activity.get("calories"):
                    garmin_activity.calories = int(raw_activity.get("calories", 0))

                # Device name
                raw_device_id = raw_activity.get("deviceId")
                if raw_device_id is not None:
                    garmin_activity.device_name = device_map.get(int(raw_device_id), "") or None

                # Store raw data as JSON
                garmin_activity.raw_data = json.dumps(raw_activity)

                # Check for duplicates based on garmin_id
                existing = GarminActivity.get_or_none(
                    (GarminActivity.garmin_id == str(raw_activity.get("activityId", "")))
                    & (GarminActivity.user_id == get_user_id())
                )
                if existing:
                    print(f"Skipping duplicate Garmin activity {raw_activity.get('activityId')}")
                    continue

                # Save to garmin_activities table
                garmin_activity.user_id = get_user_id()
                garmin_activity.save()
                persisted_activities.append(garmin_activity)

            except Exception as e:
                print(f"Error processing Garmin activity: {e}")
                continue

        # Mark this month as synced
        ProviderSync.create(year_month=date_filter, provider=self.provider_name, user_id=get_user_id())

        print(f"Synced {len(persisted_activities)} Garmin activities to garmin_activities table")

        # Always return activities for the requested month from database
        return self._get_garmin_activities_for_month(date_filter)

    def fetch_activities_for_month(self, year_month: str) -> list[dict]:
        """
        Return activities for the given year_month (YYYY-MM) using Garmin Connect API.
        """
        client = self._get_client()

        # Parse year and month
        year, month = map(int, year_month.split("-"))

        # Get start and end dates for the month
        start_date = datetime.date(year, month, 1)
        if month == 12:
            end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

        try:
            # Get activities for the date range
            activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())

            print(f"Found {len(activities)} activities from Garmin Connect for {year_month}")
            return activities

        except (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
            GarthHTTPError,
        ) as err:
            print(f"Error fetching activities from Garmin: {err}")
            return []

    def get_activity_by_id(self, activity_id: str) -> GarminActivity | None:
        """Get a GarminActivity by its provider ID."""
        return GarminActivity.get_or_none(
            (GarminActivity.garmin_id == activity_id) & (GarminActivity.user_id == get_user_id())
        )

    def update_activity(self, activity_data: dict[str, Any]) -> Any:
        """Update an existing GarminActivity with new data."""
        provider_id = activity_data["garmin_id"]

        # Get the client for API updates
        client = self._get_client()

        # Update name in Garmin Connect if provided
        if "name" in activity_data:
            try:
                client.set_activity_name(provider_id, activity_data["name"])
                print(f"Updated activity name in Garmin Connect: {activity_data['name']}")

                # Sync our local copy with the value we just successfully pushed upstream
                local = GarminActivity.get_or_none(
                    (GarminActivity.garmin_id == str(provider_id)) & (GarminActivity.user_id == get_user_id())
                )
                if local:
                    local.name = activity_data["name"]
                    local.save()

                return True

            except Exception as e:
                print(f"Failed to update activity name in Garmin Connect: {e}")
                raise

    def get_all_gear(self) -> dict[str, str]:
        """Get all gear from Garmin Connect."""
        try:
            client = self._get_client()

            # Get the user's device info to get profile number
            device_last_used = client.get_device_last_used()
            user_profile_number = device_last_used["userProfileNumber"]

            # Get gear list
            gear_list = client.get_gear(user_profile_number)

            # Convert to name -> name mapping (like other providers)
            gear_dict = {}
            for gear_item in gear_list:
                display_name = gear_item.get("displayName", "")
                if display_name:
                    gear_dict[display_name] = display_name

            return gear_dict

        except Exception as e:
            print(f"Error getting gear from Garmin Connect: {e}")
            return {}

    def create_activity(self, activity_data: dict) -> GarminActivity:
        """Create a new GarminActivity from activity data."""
        raise NotImplementedError("GarminActivity does not support creating activities. yet")

    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set gear for an activity - not yet supported by Garmin Connect API."""
        print("Setting gear for individual activities is not supported by Garmin Connect API")
        print("Gear can only be set as defaults for activity types through the Garmin Connect website")
        return False

    def _get_garmin_activities_for_month(self, date_filter: str) -> list["GarminActivity"]:
        """Get GarminActivity objects for a specific month."""
        year, month = map(int, date_filter.split("-"))
        garmin_activities = []

        for activity in GarminActivity.select().where(GarminActivity.user_id == get_user_id()):
            if hasattr(activity, "start_time") and activity.start_time:
                try:
                    # Convert timestamp to datetime for comparison
                    dt = datetime.datetime.fromtimestamp(int(activity.start_time))
                    if dt.year == year and dt.month == month:
                        garmin_activities.append(activity)
                except (ValueError, TypeError):
                    continue

        return garmin_activities

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Delete activities for a specific month or all activities."""
        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )

            deleted_count = (
                GarminActivity.delete()
                .where(
                    (GarminActivity.start_time >= start_timestamp)
                    & (GarminActivity.start_time <= end_timestamp)
                    & (GarminActivity.user_id == get_user_id())
                )
                .execute()
            )
            return deleted_count
        else:
            return GarminActivity.delete().where(GarminActivity.user_id == get_user_id()).execute()
