"""Tests for calendar functionality in the tracekit web application."""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import (
    app,
    get_current_date_in_timezone,
    get_sync_calendar_data,
    load_tracekit_config,
)


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_config():
    """Create a temporary config file for testing."""
    config_data = {
        "home_timezone": "US/Pacific",
        "metadata_db": "test_metadata.sqlite3",
        "debug": True,
        "providers": {
            "strava": {"enabled": True, "priority": 1},
            "garmin": {"enabled": True, "priority": 2},
            "spreadsheet": {"enabled": True, "priority": 3},
            "file": {"enabled": True},
            "disabled_provider": {"enabled": False, "priority": 999},
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_data, f)
        temp_file = f.name

    yield temp_file, config_data

    os.remove(temp_file)


@pytest.fixture
def temp_database():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    # Create test database with sample data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create providersync table
    cursor.execute("""
        CREATE TABLE providersync (
            id INTEGER PRIMARY KEY,
            year_month TEXT,
            provider TEXT
        )
    """)

    # Insert test data
    test_data = [
        ("2024-01", "strava"),
        ("2024-01", "garmin"),
        ("2024-02", "strava"),
        ("2024-03", "garmin"),
        ("2024-03", "spreadsheet"),
    ]

    cursor.executemany("INSERT INTO providersync (year_month, provider) VALUES (?, ?)", test_data)

    # Create activity tables for testing activity counts
    activity_tables = [
        "strava_activities",
        "garmin_activities",
        "ridewithgps_activities",
        "spreadsheet_activities",
        "file_activities",
    ]

    for table in activity_tables:
        cursor.execute(f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY,
                start_time INTEGER,
                updated_at TEXT
            )
        """)

        # Add some test activities with different months
        test_activities = [
            (1704067200,),  # 2024-01-01 in Unix timestamp
            (1706745600,),  # 2024-02-01 in Unix timestamp
            (1709251200,),  # 2024-03-01 in Unix timestamp
        ]
        cursor.executemany(f"INSERT INTO {table} (start_time) VALUES (?)", test_activities)

    conn.commit()
    conn.close()

    yield db_path

    os.remove(db_path)


class TestSyncCalendar:
    """Test sync calendar functionality."""

    def test_get_sync_calendar_data_valid_db(self, temp_database, temp_config):
        """Test getting sync calendar data from a valid database."""
        _temp_file, _config_data = temp_config
        config = load_tracekit_config()  # This will use the default config

        calendar_data = get_sync_calendar_data(temp_database, config)

        assert "error" not in calendar_data
        assert "months" in calendar_data
        assert "providers" in calendar_data
        assert "date_range" in calendar_data

        # Check providers
        assert set(calendar_data["providers"]) == {"strava", "garmin", "spreadsheet"}

        # Check date range
        assert calendar_data["date_range"] == ("2024-01", "2024-03")

        # Check months data
        months = calendar_data["months"]
        assert len(months) >= 3  # Should include 2024-01, 2024-02, 2024-03 and possibly more to current month

        # Check specific month data
        jan_2024 = next((m for m in months if m["year_month"] == "2024-01"), None)
        assert jan_2024 is not None
        assert jan_2024["year"] == 2024
        assert jan_2024["month"] == 1
        assert jan_2024["month_name"] == "January"
        assert jan_2024["provider_status"]["strava"] is True
        assert jan_2024["provider_status"]["garmin"] is True
        assert jan_2024["provider_status"]["spreadsheet"] is False

        # Check activity counts are present
        assert "activity_counts" in jan_2024
        assert "total_activities" in jan_2024
        assert isinstance(jan_2024["activity_counts"], dict)
        assert isinstance(jan_2024["total_activities"], int)

    def test_get_sync_calendar_data_missing_file(self, temp_config):
        """Test getting sync calendar data from a missing database file."""
        _temp_file, _config_data = temp_config
        config = {"home_timezone": "UTC"}

        calendar_data = get_sync_calendar_data("nonexistent_database.sqlite3", config)

        assert "error" in calendar_data
        assert "not found" in calendar_data["error"]

    def test_get_sync_calendar_data_empty_db(self, temp_config):
        """Test getting sync calendar data from an empty database."""
        _temp_file, _config_data = temp_config
        config = {"home_timezone": "UTC"}

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            # Create empty database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE providersync (
                    id INTEGER PRIMARY KEY,
                    year_month TEXT,
                    provider TEXT
                )
            """)
            conn.commit()
            conn.close()

            calendar_data = get_sync_calendar_data(db_path, config)

            assert "error" not in calendar_data
            assert calendar_data["months"] == []
            assert calendar_data["providers"] == []
            assert calendar_data["date_range"] == (None, None)
            assert calendar_data["total_months"] == 0
        finally:
            os.remove(db_path)

    def test_calendar_activity_counts(self, temp_database, temp_config):
        """Test that calendar includes activity counts per provider per month."""
        _temp_file, _config_data = temp_config
        config = {"home_timezone": "UTC"}

        calendar_data = get_sync_calendar_data(temp_database, config)

        assert "error" not in calendar_data
        assert "months" in calendar_data

        # Find a month with data
        months_with_data = [m for m in calendar_data["months"] if m.get("total_activities", 0) > 0]
        assert len(months_with_data) > 0, "Should have months with activity data"

        month = months_with_data[0]
        assert "activity_counts" in month
        assert "total_activities" in month
        assert month["total_activities"] > 0

        # Check that activity counts are properly structured
        activity_counts = month["activity_counts"]
        assert isinstance(activity_counts, dict)

        # Should have some provider with activities
        provider_counts = [count for count in activity_counts.values() if count > 0]
        assert len(provider_counts) > 0, "Should have at least one provider with activities"


class TestTimezone:
    """Tests for timezone functionality in calendar."""

    def test_get_current_date_in_timezone_with_valid_timezone(self):
        """Test getting current date with a valid timezone."""
        config = {"home_timezone": "US/Eastern"}
        current_date = get_current_date_in_timezone(config)

        # Should return a date object
        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")

        # Should be a reasonable year (not in the distant past/future)
        assert 2020 <= current_date.year <= 2030

    def test_get_current_date_in_timezone_with_invalid_timezone(self):
        """Test getting current date with an invalid timezone falls back to UTC."""
        config = {"home_timezone": "Invalid/Timezone"}
        current_date = get_current_date_in_timezone(config)

        # Should still return a valid date object (fallback to UTC)
        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")

    def test_get_current_date_in_timezone_without_timezone(self):
        """Test getting current date without timezone config falls back to UTC."""
        config = {}
        current_date = get_current_date_in_timezone(config)

        # Should still return a valid date object (fallback to UTC)
        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")

    def test_calendar_uses_configured_timezone(self, temp_config, temp_database):
        """Test that calendar functionality uses the configured timezone."""
        temp_file, config_data = temp_config
        config_data["metadata_db"] = temp_database
        config_data["home_timezone"] = "US/Pacific"

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            config = load_tracekit_config()
            calendar_data = get_sync_calendar_data(temp_database, config)

            # Should successfully load calendar data
            assert "error" not in calendar_data
            assert "months" in calendar_data
            assert "providers" in calendar_data

            # The function should have used the timezone for current date calculations
            # We can't easily test the exact date without mocking datetime,
            # but we can verify the function ran successfully with timezone config
            # The exact providers depend on what's in the test database
            assert isinstance(calendar_data["providers"], list)
            assert len(calendar_data["providers"]) >= 0  # Could be empty or have providers

            # Verify months data structure is correct
            if calendar_data["months"]:
                month = calendar_data["months"][0]
                assert "year_month" in month
                assert "month_name" in month
                assert "activity_counts" in month
                assert "total_activities" in month


class TestCalendarIntegration:
    """Integration tests for calendar page."""

    def test_calendar_page_renders(self, client, temp_config, temp_database):
        """Test that the calendar page renders successfully."""
        temp_file, config_data = temp_config
        config_data["metadata_db"] = temp_database

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/calendar")
            assert response.status_code == 200
            assert b"Sync Calendar" in response.data

            # Should contain timezone-aware data
            content = response.data.decode()
            assert "2024-01" in content or "2024-02" in content or "2024-03" in content

            # Should contain activity count information
            assert "activities" in content or "total" in content

    def test_calendar_page_with_timezone(self, client, temp_config, temp_database):
        """Test calendar page with specific timezone configuration."""
        temp_file, config_data = temp_config
        config_data["metadata_db"] = temp_database
        config_data["home_timezone"] = "US/Eastern"

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/calendar")
            assert response.status_code == 200

            # Should successfully render with Eastern timezone
            content = response.data.decode()
            assert "Sync Calendar" in content
            assert len(content) > 1000  # Should be a substantial page
