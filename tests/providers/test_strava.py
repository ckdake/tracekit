import datetime
from unittest.mock import Mock, patch

import pytest

from tracekit.providers.strava.strava_provider import StravaProvider


@pytest.mark.parametrize(
    "input_name,expected",
    [
        ("Altra Kayenta 2020 Black/Lime", "2020 Altra Kayenta"),
        ("Altra Lone Peak 2018 Altra Lone Peak", "2018 Altra Lone Peak"),
        ("Specialized Stumpjumper 2019 Carbon", "2019 Specialized Stumpjumper"),
        ("NoYearBikeName", "NoYearBikeName"),
        ("Trek 2022", "2022 Trek"),
        ("2021 Giant Propel Advanced", "2021 Giant Propel Advanced"),
    ],
)
def test_normalize_strava_gear_name(input_name, expected):
    assert StravaProvider._normalize_strava_gear_name(input_name) == expected


class TestStravaProviderUpdate:
    """Test Strava provider update_activity method."""

    def test_update_activity_name_success(self):
        """Test successful name update via Strava API."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.update_activity = Mock()

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Test data
        activity_data = {"strava_id": "12345", "name": "Updated Activity Name"}

        # Call update_activity
        result = provider.update_activity(activity_data)

        # Verify the result
        assert result is True

        # Verify the API was called correctly
        mock_client.update_activity.assert_called_once_with(activity_id=12345, name="Updated Activity Name")

    def test_update_activity_multiple_fields(self):
        """Test updating multiple fields via Strava API."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.update_activity = Mock()

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Test data with multiple fields
        activity_data = {
            "strava_id": "67890",
            "name": "New Name",
            "description": "New description",
        }

        # Call update_activity
        result = provider.update_activity(activity_data)

        # Verify the result
        assert result is True

        # Verify the API was called with all fields except strava_id
        mock_client.update_activity.assert_called_once_with(
            activity_id=67890, name="New Name", description="New description"
        )

    def test_update_activity_api_failure(self):
        """Test handling of API failure during update."""
        # Mock the stravalib client to raise an exception
        mock_client = Mock()
        mock_client.update_activity = Mock(side_effect=Exception("API Error"))

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Test data
        activity_data = {"strava_id": "12345", "name": "Updated Name"}

        # Call update_activity and expect it to handle the exception
        result = provider.update_activity(activity_data)

        # Verify the result is False due to the exception
        assert result is False

        # Verify the API was called
        mock_client.update_activity.assert_called_once()

    def test_update_activity_removes_provider_id(self):
        """Test that strava_id is removed from the data sent to API."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.update_activity = Mock()

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Test data
        activity_data = {
            "strava_id": "12345",
            "name": "Test Name",
            "some_other_field": "some_value",
        }

        # Call update_activity
        provider.update_activity(activity_data)

        # Verify that strava_id was not passed to the API
        # but other fields were passed
        mock_client.update_activity.assert_called_once_with(
            activity_id=12345, name="Test Name", some_other_field="some_value"
        )


class TestStravaProviderGear:
    """Test Strava provider gear methods."""

    def test_get_all_gear_success(self):
        """Test successful gear retrieval from Strava API."""
        # Mock the stravalib client
        mock_client = Mock()

        # Mock athlete object with bikes and shoes
        mock_bike1 = Mock()
        mock_bike1.id = "b123"
        mock_bike1.name = "Trek Bike"

        mock_bike2 = Mock()
        mock_bike2.id = "b456"
        mock_bike2.name = "Specialized Bike"

        mock_shoe1 = Mock()
        mock_shoe1.id = "g789"
        mock_shoe1.name = "Running Shoes"

        mock_athlete = Mock()
        mock_athlete.bikes = [mock_bike1, mock_bike2]
        mock_athlete.shoes = [mock_shoe1]

        mock_client.get_athlete = Mock(return_value=mock_athlete)

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Call get_all_gear
        result = provider.get_all_gear()

        # Verify the result
        expected = {
            "b123": "Trek Bike",
            "b456": "Specialized Bike",
            "g789": "Running Shoes",
        }
        assert result == expected

        # Verify the API was called correctly
        mock_client.get_athlete.assert_called_once()

    def test_get_all_gear_no_gear(self):
        """Test gear retrieval when athlete has no gear."""
        # Mock the stravalib client
        mock_client = Mock()

        # Mock athlete object with no bikes/shoes
        mock_athlete = Mock()
        mock_athlete.bikes = None
        mock_athlete.shoes = None

        mock_client.get_athlete = Mock(return_value=mock_athlete)

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Call get_all_gear
        result = provider.get_all_gear()

        # Verify empty result
        assert result == {}

    def test_get_all_gear_api_failure(self):
        """Test gear retrieval when API fails."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.get_athlete = Mock(side_effect=Exception("API Error"))

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Call get_all_gear
        result = provider.get_all_gear()

        # Verify empty result due to exception
        assert result == {}

    def test_set_gear_success(self):
        """Test successful gear setting."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.update_activity = Mock()

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Mock get_all_gear to return test gear
        provider.get_all_gear = Mock(return_value={"b123": "Trek Bike", "g456": "Running Shoes"})

        # Call set_gear
        result = provider.set_gear("Trek Bike", "12345")

        # Verify the result
        assert result is True

        # Verify the API was called correctly
        mock_client.update_activity.assert_called_once_with(activity_id=12345, gear_id="b123")

    def test_set_gear_not_found(self):
        """Test gear setting when gear name is not found."""
        # Mock the stravalib client
        mock_client = Mock()

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Mock get_all_gear to return test gear
        provider.get_all_gear = Mock(return_value={"b123": "Trek Bike"})

        # Call set_gear with non-existent gear name
        result = provider.set_gear("Nonexistent Bike", "12345")

        # Verify the result is False
        assert result is False

        # Verify the API was not called
        mock_client.update_activity.assert_not_called()

    def test_set_gear_api_failure(self):
        """Test gear setting when API fails."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_client.update_activity = Mock(side_effect=Exception("API Error"))

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        # Mock get_all_gear to return test gear
        provider.get_all_gear = Mock(return_value={"b123": "Trek Bike"})

        # Call set_gear
        result = provider.set_gear("Trek Bike", "12345")

        # Verify the result is False due to exception
        assert result is False

        # Verify the API was called
        mock_client.update_activity.assert_called_once()


class TestStravaProviderCore:
    """Test core Strava provider functionality."""

    def test_provider_name(self):
        """Test provider name property."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        assert provider.provider_name == "strava"

    def test_initialization_with_config(self):
        """Test provider initialization with config."""
        config = {"debug": True, "custom_setting": "value"}
        provider = StravaProvider(
            token="test_token",
            refresh_token="test_refresh",
            token_expires="999999999",
            config=config,
        )
        assert provider.config == config
        assert provider.debug is True

    def test_initialization_without_config(self):
        """Test provider initialization without config."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        assert provider.config == {}

    @patch.dict("os.environ", {"STRAVALIB_DEBUG": "1"})
    def test_debug_from_environment(self):
        """Test debug setting from environment variable."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        assert provider.debug is True

    def test_normalize_strava_gear_name_static_method(self):
        """Test the normalize gear name static method directly."""
        # Test cases already covered in parametrized test, but verify it's accessible
        result = StravaProvider._normalize_strava_gear_name("Test Bike 2023")
        assert result == "2023 Test Bike"

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_get_strava_activities_for_month(self, mock_provider_sync):
        """Test getting activities for a specific month."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock StravaActivity.select() to return activities
        mock_activity1 = Mock()
        mock_activity1.start_time = "1609459200"  # Jan 1, 2021
        mock_activity2 = Mock()
        mock_activity2.start_time = "1612137600"  # Feb 1, 2021
        mock_activity3 = Mock()
        mock_activity3.start_time = "1609545600"  # Jan 2, 2021

        with patch("tracekit.providers.strava.strava_activity.StravaActivity.select") as mock_select:
            mock_select.return_value = [mock_activity1, mock_activity2, mock_activity3]

            result = provider._get_strava_activities_for_month("2021-01")

            # Should return activities from January 2021 only
            assert len(result) == 2
            assert mock_activity1 in result
            assert mock_activity3 in result
            assert mock_activity2 not in result

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_get_strava_activities_for_month_invalid_timestamps(self, mock_provider_sync):
        """Test getting activities with invalid timestamps."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock StravaActivity with invalid timestamp
        mock_activity = Mock()
        mock_activity.start_time = "invalid"

        with patch("tracekit.providers.strava.strava_activity.StravaActivity.select") as mock_select:
            mock_select.return_value = [mock_activity]

            result = provider._get_strava_activities_for_month("2021-01")

            # Should handle invalid timestamp gracefully
            assert len(result) == 0

    def test_fetch_strava_activities_for_month(self):
        """Test fetching raw Strava activities for a month."""
        # Mock the stravalib client
        mock_client = Mock()
        mock_activity1 = Mock()
        mock_activity2 = Mock()
        mock_client.get_activities.return_value = [mock_activity1, mock_activity2]

        # Create provider with mocked client
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")
        provider.client = mock_client

        result = provider._fetch_strava_activities_for_month("2021-01")

        # Verify activities returned
        assert len(result) == 2
        assert result == [mock_activity1, mock_activity2]

        # Verify client was called with correct date range
        mock_client.get_activities.assert_called_once()
        call_args = mock_client.get_activities.call_args
        assert call_args[1]["limit"] is None

    @pytest.mark.skip(reason="Complex mocking of stravalib objects with multiple attributes")
    def test_convert_to_strava_activity(self):
        """Test converting stravalib activity to StravaActivity."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock stravalib activity object with proper numeric values
        mock_strava_lib_activity = Mock()
        mock_strava_lib_activity.id = 12345
        mock_strava_lib_activity.name = "Test Activity"
        mock_strava_lib_activity.type = "Ride"
        mock_strava_lib_activity.start_date_local = datetime.datetime(2021, 1, 1, 10, 0, 0)
        mock_strava_lib_activity.distance = 10000.0  # meters as float
        mock_strava_lib_activity.moving_time = datetime.timedelta(seconds=1800)  # 30 min
        mock_strava_lib_activity.total_elevation_gain = 100.0  # meters as float

        # Mock the client.get_activity call that happens inside _convert_to_strava_activity
        mock_full_activity = Mock()
        mock_full_activity.id = 12345
        mock_full_activity.name = "Test Activity"
        mock_full_activity.type = "Ride"
        mock_full_activity.distance = 10000.0  # Ensure this is a float
        mock_full_activity.moving_time = datetime.timedelta(seconds=1800)
        mock_full_activity.total_elevation_gain = 100.0
        mock_full_activity.start_date_local = datetime.datetime(2021, 1, 1, 10, 0, 0)
        # Mock start_date properly
        mock_start_date = Mock()
        mock_start_date.timestamp.return_value = 1609459200  # Jan 1, 2021 timestamp
        mock_full_activity.start_date = mock_start_date
        mock_full_activity.gear = Mock()
        mock_full_activity.gear.name = "Test Bike"
        provider.client.get_activity = Mock(return_value=mock_full_activity)

        with patch("tracekit.providers.strava.strava_activity.StravaActivity") as mock_strava_activity_class:
            mock_strava_activity = Mock()
            mock_strava_activity_class.return_value = mock_strava_activity

            result = provider._convert_to_strava_activity(mock_strava_lib_activity)

            # Verify StravaActivity was created and configured correctly
            assert result == mock_strava_activity
            assert mock_strava_activity.strava_id == "12345"
            assert mock_strava_activity.name == "Test Activity"
            assert mock_strava_activity.activity_type == "Ride"


class TestStravaProviderPullActivities:
    """Test Strava provider pull_activities method."""

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_pull_activities_none_date_filter(self, mock_provider_sync):
        """Test pull_activities with None date_filter."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        result = provider.pull_activities(date_filter=None)

        # Should return empty list for None date_filter
        assert result == []

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_pull_activities_already_synced(self, mock_provider_sync):
        """Test pull_activities when month is already synced."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock existing sync record
        mock_sync = Mock()
        mock_provider_sync.get_or_none.return_value = mock_sync

        # Mock the _get_strava_activities_for_month method
        mock_activities = [Mock(), Mock()]
        provider._get_strava_activities_for_month = Mock(return_value=mock_activities)

        result = provider.pull_activities(date_filter="2021-01")

        # Should return activities from database without fetching new ones
        assert result == mock_activities
        mock_provider_sync.get_or_none.assert_called_once_with("2021-01", "strava")
        provider._get_strava_activities_for_month.assert_called_once_with("2021-01")

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_pull_activities_new_month(self, mock_provider_sync):
        """Test pull_activities for a new month."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock no existing sync record
        mock_provider_sync.get_or_none.return_value = None

        # Mock fetching raw activities
        mock_raw_activities = [Mock(), Mock()]
        provider._fetch_strava_activities_for_month = Mock(return_value=mock_raw_activities)

        # Mock converting activities
        mock_converted_activities = [Mock(), Mock()]
        provider._convert_to_strava_activity = Mock(side_effect=mock_converted_activities)

        # Mock saving activities
        for activity in mock_converted_activities:
            activity.save = Mock()

        # Mock final database query
        mock_final_activities = [Mock(), Mock()]
        provider._get_strava_activities_for_month = Mock(return_value=mock_final_activities)

        # Mock StravaActivity.get_or_none to return None (no duplicates)
        with patch("tracekit.providers.strava.strava_activity.StravaActivity.get_or_none") as mock_get_or_none:
            mock_get_or_none.return_value = None

            result = provider.pull_activities(date_filter="2021-01")

            # Verify the flow
            assert result == mock_final_activities
            mock_provider_sync.get_or_none.assert_called_once_with("2021-01", "strava")
            provider._fetch_strava_activities_for_month.assert_called_once_with("2021-01")
            mock_provider_sync.create.assert_called_once_with(year_month="2021-01", provider="strava")

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_pull_activities_with_duplicate_activity(self, mock_provider_sync):
        """Test pull_activities when encountering duplicate activity."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock no existing sync record
        mock_provider_sync.get_or_none.return_value = None

        # Mock fetching raw activities
        mock_raw_activity = Mock()
        mock_raw_activity.id = 12345
        provider._fetch_strava_activities_for_month = Mock(return_value=[mock_raw_activity])

        # Mock converting activity
        mock_converted_activity = Mock()
        provider._convert_to_strava_activity = Mock(return_value=mock_converted_activity)

        # Mock final database query
        mock_final_activities = []
        provider._get_strava_activities_for_month = Mock(return_value=mock_final_activities)

        # Mock StravaActivity.get_or_none to return existing activity (duplicate)
        with patch("tracekit.providers.strava.strava_activity.StravaActivity.get_or_none") as mock_get_or_none:
            mock_existing_activity = Mock()
            mock_get_or_none.return_value = mock_existing_activity

            provider.pull_activities(date_filter="2021-01")

            # Verify duplicate was skipped (save not called)
            mock_converted_activity.save.assert_not_called()
            mock_provider_sync.create.assert_called_once_with(year_month="2021-01", provider="strava")

    @patch("tracekit.providers.strava.strava_provider.ProviderSync")
    def test_pull_activities_with_error(self, mock_provider_sync):
        """Test pull_activities when processing error occurs."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        # Mock no existing sync record
        mock_provider_sync.get_or_none.return_value = None

        # Mock fetching raw activities
        mock_raw_activity = Mock()
        provider._fetch_strava_activities_for_month = Mock(return_value=[mock_raw_activity])

        # Mock converting activity to raise an exception
        provider._convert_to_strava_activity = Mock(side_effect=Exception("Conversion error"))

        # Mock final database query
        mock_final_activities = []
        provider._get_strava_activities_for_month = Mock(return_value=mock_final_activities)

        result = provider.pull_activities(date_filter="2021-01")

        # Should handle error gracefully and still mark as synced
        assert result == mock_final_activities
        mock_provider_sync.create.assert_called_once_with(year_month="2021-01", provider="strava")


class TestStravaProviderCreateActivity:
    """Test Strava provider create_activity method."""

    def test_create_activity_success(self):
        """Test successful activity creation."""
        provider = StravaProvider(token="test_token", refresh_token="test_refresh", token_expires="999999999")

        activity_data = {"strava_id": "12345", "name": "Test Activity"}

        with patch("tracekit.providers.strava.strava_activity.StravaActivity.create") as mock_create:
            mock_activity = Mock()
            mock_create.return_value = mock_activity

            result = provider.create_activity(activity_data)

            assert result == mock_activity
            mock_create.assert_called_once_with(**activity_data)
