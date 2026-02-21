"""RideWithGPS provider for tracekit.

This module defines the RideWithGPSProvider class, which provides an interface
for interacting with RideWithGPS activity data, including fetching, creating,
updating activities, and managing gear.
"""

import datetime
from decimal import Decimal
from typing import Any

from dateutil import parser as dt_parser
from pyrwgps import RideWithGPS

from tracekit.provider_sync import ProviderSync
from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity


class RideWithGPSProvider(FitnessProvider):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.username = (self.config or {}).get("email", "")
        self.password = (self.config or {}).get("password", "")
        self.apikey = (self.config or {}).get("apikey", "")

        self.client = RideWithGPS(apikey=self.apikey, cache=True)

        user_info = self.client.authenticate(self.username, self.password)
        self.userid = getattr(user_info, "id", None)
        self.user_info = user_info

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return "ridewithgps"

    @staticmethod
    def _parse_iso8601(dt_val):
        if not dt_val:
            return None

        try:
            return dt_parser.parse(str(dt_val))
        except Exception:
            return None

    def pull_activities(self, date_filter: str | None = None) -> list[RideWithGPSActivity]:
        """
        Pull activities from RideWithGPS for a given month (YYYY-MM).
        Only activities for the specified month are fetched and persisted.
        """
        if date_filter is None:
            print("RideWithGPS provider: pulling all activities not implemented yet")
            return []

        year, month = map(int, date_filter.split("-"))

        if not ProviderSync.get_or_none(date_filter, self.provider_name):
            trip_summaries = list(self.client.list(f"/users/{self.userid}/trips.json"))
            print(f"Found {len(trip_summaries)} RideWithGPS trip summaries")

            for trip_summary in trip_summaries:
                try:
                    trip_id = trip_summary.id
                    departed_at = trip_summary.departed_at
                    if not trip_id or not departed_at:
                        continue
                    # Parse date string to datetime
                    dt = self._parse_iso8601(departed_at)
                    if not dt:
                        continue
                    dt_utc = dt.astimezone(datetime.UTC)
                    if dt_utc.year != year or dt_utc.month != month:
                        continue
                    timestamp = int(dt_utc.timestamp())

                    trip = self.client.get(path=f"/trips/{trip_id}.json").trip

                    rwgps_activity = RideWithGPSActivity()

                    rwgps_activity.ridewithgps_id = str(trip.id)
                    rwgps_activity.name = str(trip.name)
                    if hasattr(trip, "distance") and trip.distance is not None:
                        # Convert meters to miles
                        miles = float(trip.distance) / 1609.34
                        rwgps_activity.distance = Decimal(str(miles))
                    rwgps_activity.start_time = timestamp
                    if hasattr(trip, "locality") and trip.locality:
                        rwgps_activity.city = str(trip.locality)
                    if hasattr(trip, "administrative_area") and trip.administrative_area:
                        rwgps_activity.state = str(trip.administrative_area)
                    if hasattr(trip, "gear") and trip.gear and hasattr(trip.gear, "name"):
                        rwgps_activity.equipment = str(trip.gear.name)
                    existing = RideWithGPSActivity.get_or_none(RideWithGPSActivity.ridewithgps_id == str(trip.id))
                    if existing:
                        continue
                    try:
                        rwgps_activity.save()
                    except Exception as e:
                        print(f"Error saving RideWithGPS activity {trip.id}: {e}")
                except Exception as e:
                    print(f"Error processing RideWithGPS activity: {e}")
                    continue

            ProviderSync.create(year_month=date_filter, provider=self.provider_name)
            print(f"RideWithGPS Sync complete for {date_filter}")

        # Always return all activities for this month from the database
        start = datetime.datetime(year, month, 1, tzinfo=datetime.UTC)
        if month == 12:
            end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.UTC)
        else:
            end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.UTC)
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        activities = list(
            RideWithGPSActivity.select().where(
                (RideWithGPSActivity.start_time >= start_ts) & (RideWithGPSActivity.start_time < end_ts)
            )
        )
        return activities

    # Abstract method implementations
    def create_activity(self, activity_data: dict) -> RideWithGPSActivity:
        """Create a new RideWithGPSActivity from activity data."""
        # Create new activity
        return RideWithGPSActivity.create(**activity_data)

    def get_activity_by_id(self, activity_id: str) -> RideWithGPSActivity | None:
        """Get a RideWithGPSActivity by its provider ID."""
        return RideWithGPSActivity.get_or_none(RideWithGPSActivity.ridewithgps_id == activity_id)

    # TODO: "pull" the activity again after setting gear to update our local copy.
    def update_activity(self, activity_data: dict) -> bool:
        """Update an existing RideWithGPS trip via API."""
        provider_id = activity_data["ridewithgps_id"]

        try:
            trip_data = {k: v for k, v in activity_data.items() if k != "ridewithgps_id"}

            response = self.client.patch(path=f"/trips/{provider_id}.json", params={"trip": trip_data})

            # Check if there's an error in the response
            if hasattr(response, "error"):
                raise RuntimeError(f"RideWithGPS API error: {response.error}")

            return True

        except Exception as e:
            print(f"Error updating RideWithGPS trip {provider_id}: {e}")
            raise

    def get_all_gear(self) -> dict[str, str]:
        """Get gear from RideWithGPS user info."""
        gear_dict = {}
        if hasattr(self, "user_info") and hasattr(self.user_info, "gear"):
            for gear_item in self.user_info.gear:
                gear_id = str(gear_item.id)
                gear_name = gear_item.name
                gear_dict[gear_id] = gear_name
        return gear_dict

    # TODO: "pull" the activity again after setting gear to update our local copy.
    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set gear for a RideWithGPS trip by gear name."""
        try:
            all_gear = self.get_all_gear()
            gear_id = None
            for gid, gname in all_gear.items():
                if gname == gear_name:
                    gear_id = gid
                    break

            if gear_id is None:
                print(f"Gear '{gear_name}' not found in RideWithGPS gear list")
                return False

            response = self.client.patch(
                path=f"/trips/{activity_id}.json",
                params={
                    "trip": {
                        "gear_id": int(gear_id),
                    }
                },
            )

            if hasattr(response, "error"):
                print(f"API returned error: {response.error}")
                return False

            return True

        except Exception as e:
            print(f"Error setting gear for RideWithGPS trip {activity_id}: {e}")
            return False

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Reset (delete) RideWithGPS activities from local database."""
        from tracekit.providers.ridewithgps.ridewithgps_activity import (
            RideWithGPSActivity,
        )

        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )

            deleted_count = (
                RideWithGPSActivity.delete()
                .where(
                    (RideWithGPSActivity.start_time >= start_timestamp)
                    & (RideWithGPSActivity.start_time <= end_timestamp)
                )
                .execute()
            )
            return deleted_count
        else:
            return RideWithGPSActivity.delete().execute()
