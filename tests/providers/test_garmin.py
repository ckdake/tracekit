from unittest.mock import Mock, patch

import pytest
from garminconnect import GarminConnectConnectionError

from tracekit.providers.garmin.garmin_provider import GarminProvider


class TestGarminProviderCore:
    """Test core Garmin provider functionality."""

    def test_provider_name(self):
        """Test provider name property."""
        provider = GarminProvider()
        assert provider.provider_name == "garmin"

    def test_initialization_with_config(self):
        """Test provider initialization with config."""
        config = {"custom_setting": "value"}
        provider = GarminProvider(config=config)
        assert provider.config == config

    def test_initialization_without_config(self):
        """Test provider initialization without config."""
        provider = GarminProvider()
        assert provider.config == {}

    def test_initialization_with_config_credentials(self):
        """Test provider initialization with config credentials."""
        config = {"email": "test@example.com", "garth_tokens": "somebase64tokens"}
        provider = GarminProvider(config=config)
        assert provider.email == "test@example.com"
        assert provider.garth_tokens == "somebase64tokens"

    def test_initialization_without_config_credentials(self):
        """Test provider initialization without credentials defaults to empty strings."""
        provider = GarminProvider()
        assert provider.email == ""
        assert provider.garth_tokens == ""


class TestGarminProviderAuthentication:
    """Test Garmin provider authentication."""

    @patch("garminconnect.Garmin")
    def test_get_client_success(self, mock_garmin_class):
        """Test successful client authentication."""
        mock_client = Mock()
        mock_garmin_class.return_value = mock_client
        mock_client.login = Mock()

        garth_tokens = "x" * 600  # simulate a long base64 token string
        provider = GarminProvider(config={"garth_tokens": garth_tokens})

        result = provider._get_client()

        assert result == mock_client
        assert provider.client == mock_client
        mock_client.login.assert_called_once_with(garth_tokens)

    @patch("garminconnect.Garmin")
    def test_get_client_cached(self, mock_garmin_class):
        """Test that client is cached after first call."""
        mock_client = Mock()
        provider = GarminProvider()
        provider.client = mock_client

        result = provider._get_client()

        # Should return cached client without creating new one
        assert result == mock_client
        mock_garmin_class.assert_not_called()

    @patch("garminconnect.Garmin")
    def test_get_client_authentication_failure(self, mock_garmin_class):
        """Test client authentication failure when login raises an exception."""
        mock_client = Mock()
        mock_garmin_class.return_value = mock_client
        mock_client.login = Mock(side_effect=Exception("Auth failed"))

        garth_tokens = "x" * 600
        provider = GarminProvider(config={"garth_tokens": garth_tokens})

        with pytest.raises(Exception) as exc_info:
            provider._get_client()

        assert "Garmin authentication failed" in str(exc_info.value)
        assert "Please run 'python -m tracekit auth-garmin' first" in str(exc_info.value)

    def test_get_client_no_tokens(self):
        """Test that _get_client raises when no garth_tokens are configured."""
        provider = GarminProvider()

        with pytest.raises(Exception) as exc_info:
            provider._get_client()

        assert "Garmin tokens not found" in str(exc_info.value)


class TestGarminProviderPullActivities:
    """Test Garmin provider pull_activities method."""

    def test_pull_activities_none_date_filter(self):
        """Test pull_activities with None date_filter."""
        provider = GarminProvider()

        result = provider.pull_activities(date_filter=None)

        # Should return empty list for None date_filter
        assert result == []

    @patch("tracekit.providers.garmin.garmin_provider.ProviderSync")
    def test_pull_activities_already_synced(self, mock_provider_sync):
        """Test pull_activities when month is already synced."""
        provider = GarminProvider()

        # Mock existing sync record
        mock_sync = Mock()
        mock_provider_sync.get_or_none.return_value = mock_sync

        # Mock the _get_garmin_activities_for_month method
        mock_activities = [Mock(), Mock()]
        provider._get_garmin_activities_for_month = Mock(return_value=mock_activities)

        result = provider.pull_activities(date_filter="2021-01")

        # Should return activities from database without fetching new ones
        assert result == mock_activities
        mock_provider_sync.get_or_none.assert_called_once_with("2021-01", "garmin")
        provider._get_garmin_activities_for_month.assert_called_once_with("2021-01")

    @pytest.mark.skip(reason="Complex mocking of GarminActivity instantiation in real execution flow")
    @patch("tracekit.providers.garmin.garmin_provider.ProviderSync")
    def test_pull_activities_new_month(self, mock_provider_sync):
        """Test pull_activities for a new month."""
        provider = GarminProvider()

        # Mock no existing sync record
        mock_provider_sync.get_or_none.return_value = None

        # Mock fetching raw activities
        mock_raw_activities = [
            {
                "activityId": 12345,
                "activityName": "Test Activity",
                "activityType": {"typeKey": "running"},
            },
        ]
        provider.fetch_activities_for_month = Mock(return_value=mock_raw_activities)

        # Mock final database query
        mock_final_activities = [Mock()]
        provider._get_garmin_activities_for_month = Mock(return_value=mock_final_activities)

        # Mock GarminActivity.get_or_none to return None (no duplicates)
        with patch("tracekit.providers.garmin.garmin_activity.GarminActivity.get_or_none") as mock_get_or_none:
            mock_get_or_none.return_value = None

            # Mock GarminActivity constructor and save
            with patch("tracekit.providers.garmin.garmin_activity.GarminActivity") as mock_garmin_activity_class:
                mock_activity = Mock()
                mock_garmin_activity_class.return_value = mock_activity

                result = provider.pull_activities(date_filter="2021-01")

                # Verify the flow - just check that the main flow worked
                assert result == mock_final_activities
                mock_provider_sync.get_or_none.assert_called_once_with("2021-01", "garmin")
                provider.fetch_activities_for_month.assert_called_once_with("2021-01")
                mock_provider_sync.create.assert_called_once_with(year_month="2021-01", provider="garmin")

                # Check that GarminActivity was instantiated
                mock_garmin_activity_class.assert_called_once()

    @patch("tracekit.providers.garmin.garmin_provider.ProviderSync")
    def test_pull_activities_with_duplicate_activity(self, mock_provider_sync):
        """Test pull_activities when encountering duplicate activity."""
        provider = GarminProvider()

        # Mock no existing sync record
        mock_provider_sync.get_or_none.return_value = None

        # Mock fetching raw activities
        mock_raw_activity = {"activityId": 12345, "activityName": "Test Activity"}
        provider.fetch_activities_for_month = Mock(return_value=[mock_raw_activity])

        # Mock final database query
        mock_final_activities = []
        provider._get_garmin_activities_for_month = Mock(return_value=mock_final_activities)

        # Mock GarminActivity.get_or_none to return existing activity (duplicate)
        with patch("tracekit.providers.garmin.garmin_activity.GarminActivity.get_or_none") as mock_get_or_none:
            mock_existing_activity = Mock()
            mock_get_or_none.return_value = mock_existing_activity

            # Mock GarminActivity constructor
            with patch("tracekit.providers.garmin.garmin_activity.GarminActivity") as mock_garmin_activity_class:
                mock_activity = Mock()
                mock_garmin_activity_class.return_value = mock_activity

                provider.pull_activities(date_filter="2021-01")

                # Verify duplicate was skipped (save not called)
                mock_activity.save.assert_not_called()
                mock_provider_sync.create.assert_called_once_with(year_month="2021-01", provider="garmin")


class TestGarminProviderFetchActivities:
    """Test Garmin provider fetch_activities_for_month method."""

    def test_fetch_activities_for_month(self):
        """Test fetching activities for a specific month."""
        provider = GarminProvider()

        # Mock client
        mock_client = Mock()
        mock_activities = [{"activityId": 1}, {"activityId": 2}]
        mock_client.get_activities_by_date.return_value = mock_activities
        provider._get_client = Mock(return_value=mock_client)

        result = provider.fetch_activities_for_month("2021-01")

        # Verify correct date range was used
        assert result == mock_activities
        mock_client.get_activities_by_date.assert_called_once_with("2021-01-01", "2021-01-31")

    def test_fetch_activities_for_month_december(self):
        """Test fetching activities for December (year boundary)."""
        provider = GarminProvider()

        # Mock client
        mock_client = Mock()
        mock_activities = [{"activityId": 1}]
        mock_client.get_activities_by_date.return_value = mock_activities
        provider._get_client = Mock(return_value=mock_client)

        result = provider.fetch_activities_for_month("2021-12")

        # Verify correct date range was used for December
        assert result == mock_activities
        mock_client.get_activities_by_date.assert_called_once_with("2021-12-01", "2021-12-31")

    def test_fetch_activities_api_error(self):
        """Test handling of API errors during fetch."""
        provider = GarminProvider()

        # Mock client to raise a Garmin-specific exception
        mock_client = Mock()
        mock_client.get_activities_by_date.side_effect = GarminConnectConnectionError("API Error")
        provider._get_client = Mock(return_value=mock_client)

        result = provider.fetch_activities_for_month("2021-01")

        # Should return empty list on error
        assert result == []


class TestGarminProviderGear:
    """Test Garmin provider gear functionality."""

    def test_get_all_gear_success(self):
        """Test successful gear retrieval."""
        provider = GarminProvider()

        # Mock client
        mock_client = Mock()
        mock_client.get_device_last_used.return_value = {"userProfileNumber": "12345"}
        mock_client.get_gear.return_value = [
            {"displayName": "Trek Bike"},
            {"displayName": "Running Shoes"},
            {"displayName": ""},  # Empty name should be ignored
        ]
        provider._get_client = Mock(return_value=mock_client)

        result = provider.get_all_gear()

        # Verify gear mapping
        expected = {"Trek Bike": "Trek Bike", "Running Shoes": "Running Shoes"}
        assert result == expected
        mock_client.get_device_last_used.assert_called_once()
        mock_client.get_gear.assert_called_once_with("12345")

    def test_get_all_gear_api_error(self):
        """Test gear retrieval when API fails."""
        provider = GarminProvider()

        # Mock client to raise exception
        mock_client = Mock()
        mock_client.get_gear.side_effect = Exception("API Error")
        provider._get_client = Mock(return_value=mock_client)

        result = provider.get_all_gear()

        # Should return empty dict on error
        assert result == {}

    def test_set_gear_not_supported(self):
        """Test that set_gear is not supported."""
        provider = GarminProvider()

        result = provider.set_gear("Trek Bike", "12345")

        # Should return False as not supported
        assert result is False


class TestGarminProviderCreateActivity:
    """Test Garmin provider create_activity method."""

    def test_create_activity_not_implemented(self):
        """Test that create_activity raises NotImplementedError."""
        provider = GarminProvider()

        with pytest.raises(NotImplementedError):
            provider.create_activity({"name": "Test Activity"})


class TestGarminProviderGetActivitiesForMonth:
    """Test Garmin provider _get_garmin_activities_for_month method."""

    @patch("tracekit.providers.garmin.garmin_provider.GarminActivity")
    def test_get_garmin_activities_for_month(self, mock_garmin_activity_class):
        """Test getting activities for a specific month."""
        provider = GarminProvider()

        # Mock activities with different timestamps
        mock_activity1 = Mock()
        mock_activity1.start_time = "1609459200"  # Jan 1, 2021
        mock_activity2 = Mock()
        mock_activity2.start_time = "1612137600"  # Feb 1, 2021
        mock_activity3 = Mock()
        mock_activity3.start_time = "1609545600"  # Jan 2, 2021

        mock_garmin_activity_class.select.return_value = [
            mock_activity1,
            mock_activity2,
            mock_activity3,
        ]

        result = provider._get_garmin_activities_for_month("2021-01")

        # Should return activities from January 2021 only
        assert len(result) == 2
        assert mock_activity1 in result
        assert mock_activity3 in result
        assert mock_activity2 not in result

    @patch("tracekit.providers.garmin.garmin_provider.GarminActivity")
    def test_get_garmin_activities_for_month_invalid_timestamps(self, mock_garmin_activity_class):
        """Test getting activities with invalid timestamps."""
        provider = GarminProvider()

        # Mock activity with invalid timestamp
        mock_activity = Mock()
        mock_activity.start_time = "invalid"

        mock_garmin_activity_class.select.return_value = [mock_activity]

        result = provider._get_garmin_activities_for_month("2021-01")

        # Should handle invalid timestamp gracefully
        assert len(result) == 0


class TestGarminProviderUpdateActivity:
    """Test Garmin provider update_activity method."""

    def test_update_activity_success(self):
        """Test successful activity update."""
        provider = GarminProvider()

        # Mock client
        mock_client = Mock()
        mock_client.set_activity_name.return_value = {"success": True}
        provider._get_client = Mock(return_value=mock_client)

        activity_data = {"garmin_id": "12345", "name": "New Activity Name"}
        result = provider.update_activity(activity_data)

        # Verify update was successful
        assert result is True
        mock_client.set_activity_name.assert_called_once_with("12345", "New Activity Name")

    def test_update_activity_no_garmin_id(self):
        """Test update activity without garmin_id."""
        provider = GarminProvider()

        activity_data = {"name": "New Activity Name"}

        # This should raise a KeyError since garmin_id is required
        with pytest.raises(KeyError):
            provider.update_activity(activity_data)

    def test_update_activity_api_error(self):
        """Test update activity when API fails."""
        provider = GarminProvider()

        # Mock client to raise exception
        mock_client = Mock()
        mock_client.set_activity_name.side_effect = Exception("API Error")
        provider._get_client = Mock(return_value=mock_client)

        activity_data = {"garmin_id": "12345", "name": "New Activity Name"}

        # The method re-raises the exception
        with pytest.raises(Exception) as exc_info:
            provider.update_activity(activity_data)

        assert "API Error" in str(exc_info.value)

    def test_update_activity_multiple_fields_only_name_supported(self):
        """Test that only name updates are supported."""
        provider = GarminProvider()

        # Mock client
        mock_client = Mock()
        mock_client.set_activity_name.return_value = {"success": True}
        provider._get_client = Mock(return_value=mock_client)

        activity_data = {
            "garmin_id": "12345",
            "name": "New Name",
            "description": "New Description",  # Should be ignored
        }
        result = provider.update_activity(activity_data)

        # Should only update name
        assert result is True
        mock_client.set_activity_name.assert_called_once_with("12345", "New Name")
