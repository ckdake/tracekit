"""Strava JSON provider for tracekit.

This module defines the StravaJsonProvider class, which provides an interface
for interacting with locally cached Strava activity data stored as JSON files.
It supports fetching activities from a folder of JSON files, but does not support
uploading, creating, updating, or managing gear.
"""

from typing import Any

from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity


class StravaJsonProvider(FitnessProvider):
    """Provider for reading Strava activity data from JSON files."""

    def __init__(self, folder: str, config: dict[str, Any] | None = None):
        """Initialize with folder containing JSON files."""
        super().__init__(config)
        self.folder = folder

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return "stravajson"

    def pull_activities(self, date_filter: str | None = None) -> list[StravaJsonActivity]:
        """Pull activities from JSON files - not yet implemented."""
        print("StravaJSON provider: pulling activities not implemented yet")
        return []

    def get_activity_by_id(self, activity_id: str) -> StravaJsonActivity | None:
        """Get activity by ID - not supported for JSON files."""
        raise NotImplementedError("StravaJsonProvider does not support fetching by ID.")

    def update_activity(self, activity_id: str, activity: StravaJsonActivity) -> bool:
        """Update activity - not supported for JSON files."""
        raise NotImplementedError("StravaJsonProvider does not support updating activities.")

    def get_all_gear(self) -> dict[str, str]:
        """Get gear - not supported for JSON files."""
        raise NotImplementedError("StravaJsonProvider does not support gear.")

    def create_activity(self, activity: StravaJsonActivity) -> str:
        """Create activity - not supported for JSON files."""
        raise NotImplementedError("StravaJsonProvider does not support creating activities.")

    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set gear - not supported for JSON files."""
        raise NotImplementedError("StravaJsonProvider does not support setting gear.")

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Reset (delete) StravaJSON activities from local database."""
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )

            return (
                StravaJsonActivity.delete()
                .where(
                    (StravaJsonActivity.start_time >= start_timestamp)
                    & (StravaJsonActivity.start_time <= end_timestamp)
                )
                .execute()
            )
        else:
            return StravaJsonActivity.delete().execute()
