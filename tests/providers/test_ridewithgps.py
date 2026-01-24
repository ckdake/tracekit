from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tracekit.providers.ridewithgps import RideWithGPSProvider


@pytest.fixture
def mock_user_info():
    """Mock user info with gear data from RideWithGPS API."""
    gear_data = [
        SimpleNamespace(id=275580, name="2020 Altra Kayenta"),
        SimpleNamespace(id=275581, name="2021 Commencal Meta AM HT 29"),
        SimpleNamespace(id=280513, name="2023 Canyon Ultimate CF SLX"),
        SimpleNamespace(id=287642, name="2024 Ibis Ripley AF"),
        SimpleNamespace(id=289126, name="2025 Altra Escalante 4"),
    ]
    return SimpleNamespace(id=3052056, gear=gear_data)


@pytest.fixture(autouse=True)
def patch_rwgps_activities(monkeypatch, mock_user_info):
    """Patch RideWithGPSProvider.__init__ to not require env vars and set mock client."""

    def fake_init(self, config=None):
        self.client = MagicMock()
        self.client.authenticate.return_value = mock_user_info
        self.userid = 3052056
        self.user_info = mock_user_info

    monkeypatch.setattr(RideWithGPSProvider, "__init__", fake_init)


@pytest.mark.skip(reason="RideWithGPS provider tests need updating for new API")
def test_fetch_activities(monkeypatch, mock_client):
    # This test needs to be updated to use pull_activities() instead of fetch_activities()
    pass


@pytest.mark.skip(reason="RideWithGPS provider tests need updating for new API")
def test_create_activity(mock_client):
    pass


@pytest.mark.skip(reason="RideWithGPS provider tests need updating for new API")
def test_get_activity_by_id(monkeypatch, mock_client):
    pass


def test_update_activity_name_success():
    """Test successful name update via RideWithGPS API."""
    provider = RideWithGPSProvider()

    # Mock successful API response
    provider.client.patch = MagicMock(return_value=SimpleNamespace())

    # Test data
    activity_data = {"ridewithgps_id": "12345", "name": "Updated Activity Name"}

    # Call update_activity
    result = provider.update_activity(activity_data)

    # Verify the result
    assert result is True

    # Verify the API was called correctly
    provider.client.patch.assert_called_once_with(
        path="/trips/12345.json", params={"trip": {"name": "Updated Activity Name"}}
    )


def test_update_activity_multiple_fields():
    """Test updating multiple fields via RideWithGPS API."""
    provider = RideWithGPSProvider()

    # Mock successful API response
    provider.client.patch = MagicMock(return_value=SimpleNamespace())

    # Test data with multiple fields
    activity_data = {
        "ridewithgps_id": "67890",
        "name": "New Name",
        "description": "New description",
        "visibility": 1,
    }

    # Call update_activity
    result = provider.update_activity(activity_data)

    # Verify the result
    assert result is True

    # Verify the API was called with all fields except ridewithgps_id
    provider.client.patch.assert_called_once_with(
        path="/trips/67890.json",
        params={
            "trip": {
                "name": "New Name",
                "description": "New description",
                "visibility": 1,
            }
        },
    )


def test_update_activity_api_failure():
    """Test handling of API failure during update."""
    provider = RideWithGPSProvider()

    # Mock API failure
    provider.client.patch = MagicMock(side_effect=Exception("API Error"))

    # Test data
    activity_data = {"ridewithgps_id": "12345", "name": "Updated Name"}

    # Call update_activity and expect it to handle the exception
    result = provider.update_activity(activity_data)

    # Verify the result is False due to the exception
    assert result is False

    # Verify the API was called
    provider.client.patch.assert_called_once()


def test_update_activity_api_error_response():
    """Test handling of API error response during update."""
    provider = RideWithGPSProvider()

    # Mock API response with error
    error_response = SimpleNamespace(error="Some API error")
    provider.client.patch = MagicMock(return_value=error_response)

    # Test data
    activity_data = {"ridewithgps_id": "12345", "name": "Updated Name"}

    # Call update_activity
    result = provider.update_activity(activity_data)

    # Verify the result is False due to the error response
    assert result is False


def test_update_activity_removes_provider_id():
    """Test that ridewithgps_id is removed from the data sent to API."""
    provider = RideWithGPSProvider()

    # Mock successful API response
    provider.client.patch = MagicMock(return_value=SimpleNamespace())

    # Test data
    activity_data = {
        "ridewithgps_id": "12345",
        "name": "Test Name",
        "some_other_field": "some_value",
    }

    # Call update_activity
    provider.update_activity(activity_data)

    # Verify that ridewithgps_id was not passed to the API
    # but other fields were passed
    provider.client.patch.assert_called_once_with(
        path="/trips/12345.json",
        params={"trip": {"name": "Test Name", "some_other_field": "some_value"}},
    )


def test_get_all_gear():
    """Test that get_all_gear returns the correct gear mapping."""
    provider = RideWithGPSProvider()
    gear = provider.get_all_gear()

    expected_gear = {
        "275580": "2020 Altra Kayenta",
        "275581": "2021 Commencal Meta AM HT 29",
        "280513": "2023 Canyon Ultimate CF SLX",
        "287642": "2024 Ibis Ripley AF",
        "289126": "2025 Altra Escalante 4",
    }

    assert gear == expected_gear


def test_set_gear():
    """Test that set_gear looks up gear_id by name and makes the correct API call."""
    provider = RideWithGPSProvider()

    # Mock the client.post method
    provider.client.patch = MagicMock(return_value=True)

    # Test setting gear by name
    result = provider.set_gear("2021 Commencal Meta AM HT 29", "315572559")

    # Verify the API call was made correctly with the looked-up gear_id
    provider.client.patch.assert_called_once_with(path="/trips/315572559.json", params={"trip": {"gear_id": 275581}})

    assert result is True


def test_set_gear_not_found():
    """Test that set_gear handles gear name not found gracefully."""
    provider = RideWithGPSProvider()

    # Mock the client.post method (should not be called)
    provider.client.post = MagicMock()

    # Test setting gear with name that doesn't exist
    result = provider.set_gear("Nonexistent Gear", "315572559")

    # Verify the API call was NOT made
    provider.client.post.assert_not_called()

    assert result is False


def test_set_gear_failure():
    """Test that set_gear handles API failures gracefully."""
    provider = RideWithGPSProvider()

    # Mock the client.post method to raise an exception
    provider.client.post = MagicMock(side_effect=Exception("API Error"))

    # Test setting gear with failure
    result = provider.set_gear("2021 Commencal Meta AM HT 29", "315572559")

    assert result is False
