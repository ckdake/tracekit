"""Tests for calendar functionality in the tracekit web application."""

import contextlib
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import (
    app,
    get_current_date_in_timezone,
    get_sync_calendar_data,
)


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset DB initialisation state between tests to prevent leakage."""
    yield
    import db_init as db_init_module

    import tracekit.db as tdb

    db_init_module._db_initialized = False
    tdb._configured = False


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
def temp_database(monkeypatch):
    """Create a temporary database with test data using peewee models.

    Also seeds appconfig and blocks _FILE_PATHS so the real config file on disk
    cannot interfere via the file-sync logic.
    """
    import tracekit.appconfig as tcfg
    import tracekit.db as tdb
    from tracekit.appconfig import save_config
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db
    from tracekit.provider_sync import ProviderSync
    from tracekit.providers.file.file_activity import FileActivity
    from tracekit.providers.garmin.garmin_activity import GarminActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
    from tracekit.providers.strava.strava_activity import StravaActivity

    # Prevent real config file from overwriting test config
    monkeypatch.setattr(tcfg, "_FILE_PATHS", [])

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())

    # Seed default config so load_config() returns something sane
    save_config({"home_timezone": "US/Pacific", "debug": False, "providers": {}})

    # Insert ProviderSync records
    sync_records = [
        ("2024-01", "strava"),
        ("2024-01", "garmin"),
        ("2024-02", "strava"),
        ("2024-03", "garmin"),
        ("2024-03", "spreadsheet"),
    ]
    for year_month, provider in sync_records:
        ProviderSync.get_or_create(year_month=year_month, provider=provider)

    # Insert sample activities (Unix timestamps for 2024-01, 2024-02, 2024-03)
    timestamps = [
        1704067200,  # 2024-01-01
        1706745600,  # 2024-02-01
        1709251200,  # 2024-03-01
    ]
    for model in (
        StravaActivity,
        GarminActivity,
        RideWithGPSActivity,
        SpreadsheetActivity,
    ):
        for i, ts in enumerate(timestamps):
            model.create(provider_id=f"test-{model.__name__}-{i}", start_time=ts)

    # FileActivity requires file_path + file_checksum
    for i, ts in enumerate(timestamps):
        FileActivity.create(
            provider_id=f"test-file-{i}",
            start_time=ts,
            file_path=f"/fake/path/{i}.gpx",
            file_checksum=f"abc{i:061d}",
        )

    yield db_path

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    os.remove(db_path)


class TestSyncCalendar:
    """Test sync calendar functionality."""

    def test_get_sync_calendar_data_valid_db(self, temp_database):
        """Test getting sync calendar data from a valid database."""
        config = {"metadata_db": temp_database, "home_timezone": "UTC"}

        calendar_data = get_sync_calendar_data(config)

        assert "error" not in calendar_data
        assert "months" in calendar_data
        assert "providers" in calendar_data
        assert "date_range" in calendar_data

        assert set(calendar_data["providers"]) == {"strava", "garmin", "spreadsheet"}
        assert calendar_data["date_range"] == ("2024-01", "2024-03")

        months = calendar_data["months"]
        assert len(months) >= 3

        jan_2024 = next((m for m in months if m["year_month"] == "2024-01"), None)
        assert jan_2024 is not None
        assert jan_2024["year"] == 2024
        assert jan_2024["month"] == 1
        assert jan_2024["month_name"] == "January"
        assert jan_2024["provider_status"]["strava"] is True
        assert jan_2024["provider_status"]["garmin"] is True
        assert jan_2024["provider_status"]["spreadsheet"] is False
        assert "activity_counts" in jan_2024
        assert "total_activities" in jan_2024
        assert isinstance(jan_2024["activity_counts"], dict)
        assert isinstance(jan_2024["total_activities"], int)

    def test_get_sync_calendar_data_empty_db(self):
        """Test getting sync calendar data from an empty database."""
        import tracekit.db as tdb
        from tracekit.database import get_all_models, migrate_tables
        from tracekit.db import configure_db

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            tdb._configured = False
            configure_db(db_path)
            tdb.get_db().connect(reuse_if_open=True)
            migrate_tables(get_all_models())

            config = {"metadata_db": db_path, "home_timezone": "UTC"}
            calendar_data = get_sync_calendar_data(config)

            assert "error" not in calendar_data
            assert calendar_data["months"] == []
            assert calendar_data["providers"] == []
            assert calendar_data["date_range"] == (None, None)
            assert calendar_data["total_months"] == 0
        finally:
            tdb._configured = False
            os.remove(db_path)

    def test_calendar_activity_counts(self, temp_database):
        """Test that calendar includes activity counts per provider per month."""
        config = {"metadata_db": temp_database, "home_timezone": "UTC"}

        calendar_data = get_sync_calendar_data(config)

        assert "error" not in calendar_data
        assert "months" in calendar_data

        months_with_data = [m for m in calendar_data["months"] if m.get("total_activities", 0) > 0]
        assert len(months_with_data) > 0, "Should have months with activity data"

        month = months_with_data[0]
        assert "activity_counts" in month
        assert "total_activities" in month
        assert month["total_activities"] > 0

        activity_counts = month["activity_counts"]
        assert isinstance(activity_counts, dict)
        provider_counts = [count for count in activity_counts.values() if count > 0]
        assert len(provider_counts) > 0, "Should have at least one provider with activities"


class TestTimezone:
    """Tests for timezone functionality in calendar."""

    def test_get_current_date_in_timezone_with_valid_timezone(self):
        """Test getting current date with a valid timezone."""
        config = {"home_timezone": "US/Eastern"}
        current_date = get_current_date_in_timezone(config)

        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")
        assert 2020 <= current_date.year <= 2030

    def test_get_current_date_in_timezone_with_invalid_timezone(self):
        """Test getting current date with an invalid timezone falls back to UTC."""
        config = {"home_timezone": "Invalid/Timezone"}
        current_date = get_current_date_in_timezone(config)

        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")

    def test_get_current_date_in_timezone_without_timezone(self):
        """Test getting current date without timezone config falls back to UTC."""
        config = {}
        current_date = get_current_date_in_timezone(config)

        assert hasattr(current_date, "year")
        assert hasattr(current_date, "month")
        assert hasattr(current_date, "day")

    def test_calendar_uses_configured_timezone(self, temp_database):
        """Test that calendar functionality uses the configured timezone."""
        config = {"metadata_db": temp_database, "home_timezone": "US/Pacific"}

        calendar_data = get_sync_calendar_data(config)

        assert "error" not in calendar_data
        assert "months" in calendar_data
        assert "providers" in calendar_data
        assert isinstance(calendar_data["providers"], list)

        if calendar_data["months"]:
            month = calendar_data["months"][0]
            assert "year_month" in month
            assert "month_name" in month
            assert "activity_counts" in month
            assert "total_activities" in month


class TestCalendarIntegration:
    """Integration tests for calendar page."""

    def test_calendar_page_renders(self, client, temp_database):
        """Test that the calendar page renders successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"calendar-grid" in response.data
        assert b"load-more-btn" in response.data

    def test_calendar_page_with_timezone(self, client, temp_database):
        """Test calendar page with a specific timezone seeded in the DB."""
        from tracekit.appconfig import save_config

        save_config({"home_timezone": "US/Eastern", "debug": False, "providers": {}})

        response = client.get("/")
        assert response.status_code == 200

        content = response.data.decode()
        assert "calendar-grid" in content
        assert len(content) > 1000
