from unittest.mock import MagicMock, patch

import pytest

from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
from tracekit.providers.spreadsheet.spreadsheet_provider import SpreadsheetProvider


@pytest.fixture(autouse=True)
def clean_spreadsheet_activities():
    """Clean SpreadsheetActivity table before each test to avoid conflicts."""
    SpreadsheetActivity.delete().execute()
    yield
    # Cleanup after test if needed


import datetime

from tracekit.providers.base_provider_activity import BaseProviderActivity


def seconds_to_hms(seconds):
    if seconds is None:
        return ""
    return str(datetime.timedelta(seconds=round(seconds)))


@pytest.fixture
def mock_sheet():
    # Simulate a sheet with a header and one data row
    header = [
        "start_time",
        "activity_type",
        "location_name",
        "city",
        "state",
        "temperature",
        "equipment",
        "duration_hms",
        "distance",
        "max_speed",
        "avg_heart_rate",
        "max_heart_rate",
        "calories",
        "max_elevation",
        "total_elevation_gain",
        "with_names",
        "avg_cadence",
        "strava_id",
        "garmin_id",
        "ridewithgps_id",
        "notes",
    ]
    data_row = [
        "2024-06-01T10:00:00Z",
        "Ride",
        "Park",
        "Atlanta",
        "GA",
        72,
        "Bike",
        "1:00:00",
        25.0,
        30.0,
        140,
        160,
        500,
        300,
        1000,
        "Alice,Bob",
        85,
        123,
        456,
        789,
        "Nice ride",
    ]
    # iter_rows returns an iterator of tuples, first header, then data
    return MagicMock(
        iter_rows=MagicMock(return_value=[header, data_row]),
        max_row=2,
        __getitem__=lambda self, idx: [MagicMock(value=v) for v in data_row],
    )


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_pull_activities(mock_path, mock_load_workbook, mock_sheet):
    """Test pull_activities method with proper database mocking."""
    mock_wb = MagicMock()
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Since the database is cleaned before each test, calling pull_activities
    # should process the mocked sheet data and create new activities
    activities = provider.pull_activities()

    # Should return list of SpreadsheetActivity objects
    assert isinstance(activities, list)
    assert len(activities) == 1  # One data row from mock_sheet
    assert isinstance(activities[0], SpreadsheetActivity)
    assert activities[0].equipment == "Bike"
    assert activities[0].spreadsheet_id == "2"  # Row 2 (first data row after header, as string)


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_get_activity_by_id(mock_path, mock_load_workbook, mock_sheet):
    mock_wb = MagicMock()
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})
    # Insert a mock activity into the test DB
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity

    SpreadsheetActivity.create(
        start_time="2024-06-01T10:00:00Z",
        activity_type="Ride",
        spreadsheet_id=3,
        equipment="Bike",
    )
    activity = provider.get_activity_by_id("3")
    assert isinstance(activity, BaseProviderActivity)
    assert activity.equipment == "Bike"
    assert activity.spreadsheet_id == "3"


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_create_activity(mock_path, mock_load_workbook):
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test with comprehensive activity data including all provider IDs
    activity_data = {
        "start_time": "2024-06-02",
        "activity_type": "Run",
        "location_name": "Central Park",
        "city": "New York",
        "state": "NY",
        "temperature": "68",
        "equipment": "Running Shoes",
        "duration": 3600,  # 1 hour in seconds
        "distance": 5.2,
        "max_speed": "8.5",
        "avg_heart_rate": "145",
        "max_heart_rate": "165",
        "calories": "450",
        "max_elevation": "150",
        "total_elevation_gain": "50",
        "with_names": "John Doe",
        "avg_cadence": "180",
        "strava_id": "12345",
        "garmin_id": "67890",
        "ridewithgps_id": "54321",
        "notes": "Great run in the park",
    }

    mock_sheet.max_row = 50  # Use a different row to avoid conflicts
    result = provider.create_activity(activity_data)

    # Verify that append was called with the correct row data
    mock_sheet.append.assert_called_once()
    call_args = mock_sheet.append.call_args[0][0]  # First argument to append()

    # Verify all fields are in the correct order and format
    expected_row = [
        "2024-06-02",  # start_time
        "Run",  # activity_type
        "Central Park",  # location_name
        "New York",  # city
        "NY",  # state
        "68",  # temperature
        "Running Shoes",  # equipment
        "1:00:00",  # duration_hms (converted from seconds)
        5.2,  # distance
        "8.5",  # max_speed
        "145",  # avg_heart_rate
        "165",  # max_heart_rate
        "450",  # calories
        "150",  # max_elevation
        "50",  # total_elevation_gain
        "John Doe",  # with_names
        "180",  # avg_cadence
        "12345",  # strava_id
        "67890",  # garmin_id
        "54321",  # ridewithgps_id
        "Great run in the park",  # notes
    ]

    assert call_args == expected_row
    mock_wb.save.assert_called_once()
    assert result == "51"  # max_row + 1 = 50 + 1 = 51


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_set_gear(mock_path, mock_load_workbook):
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 2
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})
    result = provider.set_gear("NewBike", "2")
    mock_sheet.cell.assert_called_with(row=2, column=7, value="NewBike")
    mock_wb.save.assert_called_once()
    assert result is True


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
@patch("tracekit.providers.spreadsheet.spreadsheet_activity.SpreadsheetActivity.get")
def test_update_activity(mock_get, mock_path, mock_load_workbook):
    """Test updating activity via provider update_activity method."""
    mock_activity = MagicMock()
    mock_get.return_value = mock_activity

    # Mock the Excel operations
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 10
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test with dictionary data (no Activity objects in providers!)
    activity_data = {
        "start_time": "2024-06-02",
        "activity_type": "Run",
        "spreadsheet_id": 2,
        "equipment": "Shoes",
        "notes": "Test run",
    }

    result = provider.update_activity(activity_data)

    # Verify the activity was retrieved, updated, and saved
    mock_get.assert_called_once()
    mock_activity.save.assert_called_once()
    assert result == mock_activity


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_get_all_gear(mock_path, mock_load_workbook, mock_sheet):
    mock_wb = MagicMock()
    # Simulate two rows with different equipment
    header = [
        "start_time",
        "activity_type",
        "location_name",
        "city",
        "state",
        "temperature",
        "equipment",
        "duration_hms",
        "distance",
        "max_speed",
        "avg_heart_rate",
        "max_heart_rate",
        "calories",
        "max_elevation",
        "total_elevation_gain",
        "with_names",
        "avg_cadence",
        "strava_id",
        "garmin_id",
        "ridewithgps_id",
        "notes",
    ]
    row1 = [
        "2024-06-01T10:00:00Z",
        "Ride",
        "Park",
        "Atlanta",
        "GA",
        72,
        "Bike",
        "1:00:00",
        25.0,
        30.0,
        140,
        160,
        500,
        300,
        1000,
        "Alice,Bob",
        85,
        123,
        456,
        789,
        "Nice ride",
    ]
    row2 = [
        "2024-06-02T10:00:00Z",
        "Run",
        "Trail",
        "Atlanta",
        "GA",
        70,
        "Shoes",
        "0:30:00",
        5.0,
        10.0,
        130,
        150,
        200,
        100,
        300,
        "Bob",
        80,
        124,
        457,
        790,
        "Morning run",
    ]
    mock_sheet = MagicMock(iter_rows=MagicMock(return_value=[header, row1, row2]))
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})
    gear = provider.get_all_gear()
    assert gear == {"Bike": "Bike", "Shoes": "Shoes"}


# New tests for config parameter functionality
def test_spreadsheet_provider_with_config():
    """Test that SpreadsheetProvider accepts and stores config parameter."""
    config = {"home_timezone": "US/Pacific", "enabled": True, "path": "/test/path.xlsx"}

    provider = SpreadsheetProvider("/test/path.xlsx", config=config)

    # Test that config is stored
    assert provider.config == config
    assert provider.config["home_timezone"] == "US/Pacific"
    assert provider.config["enabled"]


def test_spreadsheet_provider_without_config():
    """Test that SpreadsheetProvider works without config parameter (backward compatibility)."""
    provider = SpreadsheetProvider("/test/path.xlsx")

    # Should have empty config dict
    assert provider.config == {}
    assert provider.path == "/test/path.xlsx"


def test_spreadsheet_provider_with_none_config():
    """Test that SpreadsheetProvider handles None config parameter."""
    provider = SpreadsheetProvider("/test/path.xlsx", config=None)

    # Should have empty config dict when None is passed
    assert provider.config == {}
    assert provider.path == "/test/path.xlsx"


def test_spreadsheet_provider_config_access():
    """Test accessing config values from the provider."""
    config = {
        "home_timezone": "Europe/London",
        "debug": True,
        "custom_setting": "test_value",
    }

    provider = SpreadsheetProvider("/test/path.xlsx", config=config)

    # Test accessing various config values
    assert provider.config.get("home_timezone") == "Europe/London"
    assert provider.config.get("debug")
    assert provider.config.get("custom_setting") == "test_value"
    assert provider.config.get("nonexistent", "default") == "default"


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.FitnessProvider.__init__")
def test_spreadsheet_provider_calls_super_with_config(mock_super_init):
    """Test that SpreadsheetProvider calls super().__init__(config)."""
    config = {"home_timezone": "US/Pacific", "enabled": True}

    # Make the mock return None to avoid issues
    mock_super_init.return_value = None

    SpreadsheetProvider("/test/path.xlsx", config=config)

    # Verify super().__init__ was called with the config
    mock_super_init.assert_called_once_with(config)


def test_spreadsheet_provider_with_enhanced_config():
    """Test SpreadsheetProvider with enhanced config including home_timezone."""
    enhanced_config = {
        "enabled": True,
        "path": "/test/spreadsheet.xlsx",
        "home_timezone": "America/New_York",
        "debug": False,
    }

    provider = SpreadsheetProvider("/test/spreadsheet.xlsx", config=enhanced_config)

    # Verify all config values are accessible
    assert provider.config["home_timezone"] == "America/New_York"
    assert provider.config["enabled"]
    assert not provider.config["debug"]
    assert provider.path == "/test/spreadsheet.xlsx"


def test_spreadsheet_provider_mimics_core_behavior():
    """Test that SpreadsheetProvider works with config structure from core.py."""
    # Simulate the enhanced_config that core.py creates
    provider_config = {"enabled": True, "path": "/test/spreadsheet.xlsx"}

    # This is what core.py does - creates enhanced_config
    enhanced_config = provider_config.copy()
    enhanced_config["home_timezone"] = "US/Eastern"

    # This is how core.py calls the provider
    provider = SpreadsheetProvider("/test/spreadsheet.xlsx", config=enhanced_config)

    # Verify that the provider has access to both the provider config and home_timezone
    assert provider.config["enabled"]
    assert provider.config["path"] == "/test/spreadsheet.xlsx"
    assert provider.config["home_timezone"] == "US/Eastern"
    assert provider.path == "/test/spreadsheet.xlsx"


def test_spreadsheet_provider_timezone_access():
    """Test that provider can access home_timezone for timezone conversion."""
    config = {"home_timezone": "America/Los_Angeles", "enabled": True}
    provider = SpreadsheetProvider("/test/path.xlsx", config=config)

    # Provider should be able to access the timezone setting
    timezone = provider.config.get("home_timezone", "UTC")
    assert timezone == "America/Los_Angeles"

    # This would be useful for timezone conversions in the provider
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(timezone)
    assert str(tz) == "America/Los_Angeles"


def test_convert_to_gmt_timestamp_date_only_eastern():
    """Test _convert_to_gmt_timestamp with date-only string and US/Eastern timezone."""

    from tracekit.providers.spreadsheet.spreadsheet_provider import SpreadsheetProvider

    # Feb 3, 2025 in US/Eastern should be 2025-02-03 00:00:00-05:00
    # Which is 2025-02-03 05:00:00 UTC
    dt_str = "2025-02-03"  # How this appears in the spreadsheet
    tz = "US/Eastern"  # Where the activity was recorded
    ts = SpreadsheetProvider._convert_to_gmt_timestamp(dt_str, tz)
    assert ts == 1738558800  # 2025-02-03 05:00:00 UTC = 1738568400

    dt_str = "2025-02-03 00:00:00"  # How this appears in the spreadsheet
    tz = "US/Eastern"  # Where the activity was recorded
    ts = SpreadsheetProvider._convert_to_gmt_timestamp(dt_str, tz)
    assert ts == 1738558800  # 2025-02-03 05:00:00 UTC = 1738568400


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_create_activity_with_duration_hms(mock_path, mock_load_workbook):
    """Test that create_activity correctly converts duration to HH:MM:SS format."""
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 10  # Use different row to avoid conflicts
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test with duration in seconds
    activity_data = {
        "start_time": "2024-06-01T10:00:00Z",
        "activity_type": "Ride",
        "location_name": "Test Location",
        "duration": 3661,  # 1 hour, 1 minute, 1 second
        "distance": 25.0,
        "notes": "Test ride",
    }

    result = provider.create_activity(activity_data)

    # Verify the activity was created with correct row number
    assert result == "11"  # Next row after max_row=10

    # Verify sheet.append was called with correct data including duration_hms
    mock_sheet.append.assert_called_once()
    append_args = mock_sheet.append.call_args[0][0]

    # Duration should be converted to HH:MM:SS format
    assert append_args[7] == "1:01:01"  # duration_hms column (index 7)
    assert append_args[0] == "2024-06-01T10:00:00Z"  # start_time
    assert append_args[20] == "Test ride"  # notes


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_create_activity_with_zero_duration(mock_path, mock_load_workbook):
    """Test that create_activity handles zero duration correctly."""
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 11  # Use different row to avoid conflicts
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    activity_data = {
        "start_time": "2024-06-01T10:00:00Z",
        "activity_type": "Ride",
        "duration": 0,
        "distance": 25.0,
    }

    provider.create_activity(activity_data)

    append_args = mock_sheet.append.call_args[0][0]
    assert append_args[7] == "0:00:00"  # Zero duration


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_create_activity_with_no_duration(mock_path, mock_load_workbook):
    """Test that create_activity handles missing duration correctly."""
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 12  # Use different row to avoid conflicts
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    activity_data = {
        "start_time": "2024-06-01T10:00:00Z",
        "activity_type": "Ride",
        "distance": 25.0,
        # No duration field
    }

    provider.create_activity(activity_data)

    append_args = mock_sheet.append.call_args[0][0]
    assert append_args[7] == ""  # Empty string for missing duration


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
@patch("tracekit.providers.spreadsheet.spreadsheet_activity.SpreadsheetActivity.get")
def test_update_activity_with_duration_hms(mock_get, mock_path, mock_load_workbook):
    """Test that update_activity correctly updates duration_hms in Excel file."""
    mock_activity = MagicMock()
    mock_get.return_value = mock_activity

    # Mock the Excel operations
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 10
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test updating duration_hms
    activity_data = {
        "spreadsheet_id": 3,
        "duration_hms": "2:30:45",  # 2 hours, 30 minutes, 45 seconds
    }

    result = provider.update_activity(activity_data)

    # Verify the activity was retrieved and saved
    mock_get.assert_called_once()
    mock_activity.save.assert_called_once()
    assert result == mock_activity

    # Verify Excel file was updated with duration_hms in column 8
    mock_sheet.cell.assert_called_with(row=3, column=8, value="2:30:45")
    mock_wb.save.assert_called_once()


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
@patch("tracekit.providers.spreadsheet.spreadsheet_activity.SpreadsheetActivity.get")
def test_update_activity_with_notes_and_duration_hms(mock_get, mock_path, mock_load_workbook):
    """Test that update_activity correctly updates both notes and duration_hms."""
    mock_activity = MagicMock()
    mock_get.return_value = mock_activity

    # Mock the Excel operations
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 10
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test updating both notes and duration_hms
    activity_data = {
        "spreadsheet_id": 5,
        "notes": "Updated activity name",
        "duration_hms": "1:15:30",
    }

    result = provider.update_activity(activity_data)

    # Verify the activity was retrieved and saved
    mock_get.assert_called_once()
    mock_activity.save.assert_called_once()
    assert result == mock_activity

    # Verify Excel file was updated with both fields
    expected_calls = [
        (5, 21, "Updated activity name"),  # notes in column 21
        (5, 8, "1:15:30"),  # duration_hms in column 8
    ]

    # Check that both cell updates were made
    assert mock_sheet.cell.call_count == 2

    # The cell method is called with keyword arguments
    call_details = []
    for call in mock_sheet.cell.call_args_list:
        _args, kwargs = call
        if "row" in kwargs and "column" in kwargs and "value" in kwargs:
            call_details.append((kwargs["row"], kwargs["column"], kwargs["value"]))

    expected_calls = [
        (5, 21, "Updated activity name"),  # notes in column 21
        (5, 8, "1:15:30"),  # duration_hms in column 8
    ]

    # Sort both lists to handle order independence
    expected_calls.sort()
    call_details.sort()
    assert call_details == expected_calls

    mock_wb.save.assert_called_once()


def test_seconds_to_hms_conversion():
    """Test the _seconds_to_hms static method."""
    from tracekit.providers.spreadsheet.spreadsheet_provider import SpreadsheetProvider

    # Test various durations
    assert SpreadsheetProvider._seconds_to_hms(3661) == "1:01:01"
    assert SpreadsheetProvider._seconds_to_hms(3600) == "1:00:00"
    assert SpreadsheetProvider._seconds_to_hms(61) == "0:01:01"
    assert SpreadsheetProvider._seconds_to_hms(0) == "0:00:00"
    assert SpreadsheetProvider._seconds_to_hms(None) == ""

    # Test with float values
    assert SpreadsheetProvider._seconds_to_hms(3661.7) == "1:01:02"  # Rounds to nearest second


def test_hms_to_seconds_conversion():
    """Test the _hms_to_seconds static method."""
    from tracekit.providers.spreadsheet.spreadsheet_provider import SpreadsheetProvider

    # Test various HMS formats
    assert SpreadsheetProvider._hms_to_seconds("1:01:01") == 3661
    assert SpreadsheetProvider._hms_to_seconds("1:00:00") == 3600
    assert SpreadsheetProvider._hms_to_seconds("0:01:01") == 61
    assert SpreadsheetProvider._hms_to_seconds("0:00:00") == 0
    assert SpreadsheetProvider._hms_to_seconds("") is None
    assert SpreadsheetProvider._hms_to_seconds(None) is None

    # Test MM:SS format
    assert SpreadsheetProvider._hms_to_seconds("01:30") == 90

    # Test numeric inputs
    assert SpreadsheetProvider._hms_to_seconds(3661) == 3661.0
    assert SpreadsheetProvider._hms_to_seconds(3661.5) == 3661.5


@patch("tracekit.providers.spreadsheet.spreadsheet_provider.openpyxl.load_workbook")
@patch("tracekit.providers.spreadsheet.spreadsheet_provider.Path")
def test_create_activity_stores_duration_hms_in_database(mock_path, mock_load_workbook):
    """Test that create_activity stores duration_hms in the database record."""
    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.max_row = 2
    mock_wb.active = mock_sheet
    mock_load_workbook.return_value = mock_wb
    mock_path.return_value = "fake.xlsx"

    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test with duration_hms field provided directly
    activity_data = {
        "start_time": "2024-06-01T10:00:00Z",
        "activity_type": "Ride",
        "duration": 3661,  # 1 hour, 1 minute, 1 second
        "duration_hms": "1:01:01",  # Explicit HMS format
        "distance": 25.0,
        "notes": "Test ride with duration",
    }

    # Mock the database operations
    with patch("tracekit.providers.spreadsheet.spreadsheet_activity.SpreadsheetActivity.create") as mock_create:
        mock_activity = MagicMock()
        mock_create.return_value = mock_activity

        provider.create_activity(activity_data)

        # Verify create was called with duration_hms field
        mock_create.assert_called_once()
        create_args = mock_create.call_args[1]  # keyword arguments
        assert "duration_hms" in create_args
        assert create_args["duration_hms"] == "1:01:01"
        assert create_args["duration"] == 3661


def test_spreadsheet_activity_parsing_with_duration_hms():
    """Test that _process_parsed_data correctly sets duration_hms from spreadsheet."""
    provider = SpreadsheetProvider("fake.xlsx", config={"home_timezone": "US/Eastern", "test_mode": True})

    # Mock spreadsheet row data with duration_hms in column 7
    parsed_data = {
        "file_name": "test.xlsx",
        "spreadsheet_id": 15,  # Use a unique ID to avoid conflicts
        "row": [
            "2024-06-01T10:00:00",  # start_time (0)
            "Ride",  # activity_type (1)
            "Park",  # location_name (2)
            "Atlanta",  # city (3)
            "GA",  # state (4)
            "72",  # temperature (5)
            "Bike",  # equipment (6)
            "1:01:01",  # duration_hms (7) - This is what we're testing
            "25.0",  # distance (8)
            "",  # max_speed (9)
            "",  # avg_heart_rate (10)
            "",  # max_heart_rate (11)
            "",  # calories (12)
            "",  # max_elevation (13)
            "",  # total_elevation_gain (14)
            "",  # with_names (15)
            "",  # avg_cadence (16)
            "",  # strava_id (17)
            "",  # garmin_id (18)
            "",  # ridewithgps_id (19)
            "Test activity",  # notes (20)
        ],
    }

    # With clean database, this should create a new activity
    result = provider._process_parsed_data(parsed_data)

    # Verify the activity was created with the correct duration_hms
    assert result is not None
    assert result.duration_hms == "01:01:01"  # Gets normalized to 01:01:01 format
    assert result.duration == 3661  # 1:01:01 in seconds
    assert result.equipment == "Bike"
    assert result.spreadsheet_id == 15  # Stored as integer
