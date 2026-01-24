from unittest.mock import Mock

import pytest

from tracekit.commands.sync_month import (
    convert_activity_to_spreadsheet_format,
    generate_correlation_key,
)


@pytest.mark.parametrize(
    "timestamp1,distance1,timestamp2,distance2",
    [
        (1746504000, 30.55, 1746570520, 30.546996425),
        (1748491200, 15.0, 1748559503, 15.00241904),
        (1748559503, 14.99832225, 1748559503, 15.00241904),
        (1743546548, 15.551244, 1743480000, 15.55),
        (1720411200, 2.5, 1720475888, 2.5043798),
        (1741642895, 2.4997, 1741579200, 2.5),
    ],
)
def test_generate_correlation_key(timestamp1, distance1, timestamp2, distance2):
    assert generate_correlation_key(timestamp1, distance1) == generate_correlation_key(timestamp2, distance2)


def test_convert_activity_to_spreadsheet_format():
    """Test conversion of activity to spreadsheet format."""
    # Mock activity object
    mock_activity = Mock()
    mock_activity.activity_type = "Ride"
    mock_activity.location_name = "Test Location"
    mock_activity.city = "Test City"
    mock_activity.state = "Test State"
    mock_activity.temperature = "65"
    mock_activity.duration = 3600  # 1 hour in seconds
    mock_activity.max_speed = "25.0"
    mock_activity.avg_heart_rate = "150"
    mock_activity.max_heart_rate = "180"
    mock_activity.calories = "500"
    mock_activity.max_elevation = "1000"
    mock_activity.total_elevation_gain = "500"
    mock_activity.with_names = "John Doe"
    mock_activity.avg_cadence = "80"
    mock_activity.notes = "Test notes"

    # Source activity data
    source_activity = {
        "provider": "strava",
        "id": "12345",
        "timestamp": 1720411200,  # 2024-07-08
        "distance": 15.5,
        "obj": mock_activity,
        "name": "Test Activity",
        "equipment": "Test Bike",
    }

    # Mock grouped activities with correlated activities
    correlation_key = generate_correlation_key(1720411200, 15.5)
    grouped_activities = {
        correlation_key: [
            {
                "provider": "strava",
                "id": "12345",
                "timestamp": 1720411200,
                "distance": 15.5,
            },
            {
                "provider": "garmin",
                "id": "67890",
                "timestamp": 1720411200,
                "distance": 15.5,
            },
            {
                "provider": "ridewithgps",
                "id": "54321",
                "timestamp": 1720411200,
                "distance": 15.5,
            },
        ]
    }

    result = convert_activity_to_spreadsheet_format(source_activity, grouped_activities)

    # Verify the conversion
    assert result["start_time"] == "2024-07-08"
    assert result["activity_type"] == "Ride"
    assert result["location_name"] == "Test Location"
    assert result["city"] == "Test City"
    assert result["state"] == "Test State"
    assert result["equipment"] == "Test Bike"
    assert result["distance"] == 15.5
    assert result["strava_id"] == "12345"
    assert result["garmin_id"] == "67890"
    assert result["ridewithgps_id"] == "54321"
    assert result["notes"] == "Test Activity"  # Activity name maps to notes field
    assert result["duration_hms"] == "01:00:00"  # Duration formatted as HH:MM:SS (3600 seconds = 1 hour)
