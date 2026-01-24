"""Base provider interface for fitness data providers.

This module defines the abstract base class that all provider implementations
should inherit from, ensuring a consistent interface across different fitness
data sources.
"""

import calendar
import datetime
from abc import ABC, abstractmethod
from typing import Any

import pytz


class FitnessProvider(ABC):
    """Abstract base class for fitness data providers.

    All providers must implement this interface to ensure consistent
    behavior across different fitness data sources.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the provider with configuration."""
        self.config = config or {}

    @staticmethod
    def _YYYY_MM_to_unixtime_range(year_month: str, timezone: str) -> tuple[int, int]:
        """Convert YYYY-MM date string to unix timestamp range for the month.

        Args:
            year_month: Date string in YYYY-MM format
            timezone: Timezone string (default: US/Eastern)

        Returns:
            Tuple of (start_timestamp, end_timestamp) for the month in UTC
        """

        year, month = map(int, year_month.split("-"))
        tz = pytz.timezone(timezone)

        # First day of the month at 00:00:00
        start_dt = tz.localize(datetime.datetime(year, month, 1))
        start_timestamp = int(start_dt.astimezone(pytz.UTC).timestamp())

        # Last day of the month at 23:59:59
        last_day = calendar.monthrange(year, month)[1]
        end_dt = tz.localize(datetime.datetime(year, month, last_day, 23, 59, 59))
        end_timestamp = int(end_dt.astimezone(pytz.UTC).timestamp())

        return start_timestamp, end_timestamp

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider."""

    @abstractmethod
    def pull_activities(self, date_filter: str | None = None) -> list:
        """
        Pull activities from the provider for a given date filter.
        If date_filter is None, pulls all activities.
        Fetches from provider API/source and persists to database.
        Returns a list of provider-specific activity objects.
        """

    @abstractmethod
    def create_activity(self, activity_data: dict[str, Any]) -> Any:
        """Create a new activity from activity data. Returns provider-specific activity object."""

    @abstractmethod
    def get_activity_by_id(self, activity_id: str) -> Any | None:
        """Fetch a single activity by its provider-specific ID."""

    @abstractmethod
    def update_activity(self, activity_data: dict[str, Any]) -> Any:
        """Update an existing activity on the provider."""

    @abstractmethod
    def get_all_gear(self) -> dict[str, str]:
        """Fetch gear/equipment from the provider, if supported."""

    @abstractmethod
    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set the gear/equipment for a specific activity on the provider."""

    @abstractmethod
    def reset_activities(self, date_filter: str | None = None) -> int:
        """Reset (delete) activities from local database.

        Args:
            date_filter: Optional date filter in YYYY-MM format.
                        If None, deletes all activities.

        Returns:
            Number of activities deleted.
        """
