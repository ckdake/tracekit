import json
import os
from unittest.mock import MagicMock, patch

from tracekit.core import tracekit as tracekit_class


class TesttracekitCore:
    """Test the core tracekit class functionality."""

    def test_tracekit_init_loads_config(self, tmp_path):
        """Test that tracekit initializes and loads config correctly."""
        # Create a temporary config file with new format
        config_data = {
            "home_timezone": "US/Pacific",
            "debug": False,
            "provider_priority": "spreadsheet,strava",
            "providers": {
                "spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"},
                "strava": {"enabled": True},
                "file": {"enabled": True, "glob": "./test/*"},
            },
        }

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db

                tracekit = tracekit_class()

                assert tracekit.config["home_timezone"] == "US/Pacific"
                assert not tracekit.config["debug"]

    def test_tracekit_config_defaults(self, tmp_path):
        """Test that tracekit sets default config values."""
        # Create minimal config
        config_data = {"spreadsheet_path": "/tmp/test.xlsx"}

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db

                tracekit = tracekit_class()

                # Should set defaults but NOT create providers section
                assert not tracekit.config["debug"]
                assert tracekit.config["provider_priority"] == "spreadsheet,ridewithgps,strava,garmin"
                # No longer creates providers section automatically
                assert "providers" not in tracekit.config

    def test_enabled_providers_empty(self, tmp_path):
        """Test enabled_providers when no providers are enabled."""
        config_data = {
            "providers": {
                "spreadsheet": {"enabled": False},
                "strava": {"enabled": False},
                "ridewithgps": {"enabled": False},
                "garmin": {"enabled": False},
                "file": {"enabled": False},
                "stravajson": {"enabled": False},
            }
        }

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db

                tracekit = tracekit_class()

                # No providers should be enabled
                assert tracekit.enabled_providers == []

    def test_enabled_providers_with_spreadsheet(self, tmp_path):
        """Test enabled_providers when spreadsheet is configured and enabled."""
        config_data = {
            "providers": {
                "spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"},
                "strava": {"enabled": False},
                "ridewithgps": {"enabled": False},
                "garmin": {"enabled": False},
                "file": {"enabled": False},
                "stravajson": {"enabled": False},
            }
        }

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db

                tracekit = tracekit_class()

                # Should detect spreadsheet provider
                assert "spreadsheet" in tracekit.enabled_providers

    @patch.dict(
        os.environ,
        {
            "STRAVA_ACCESS_TOKEN": "test_token",
            "STRAVA_REFRESH_TOKEN": "12345",
            "STRAVA_TOKEN_EXPIRES": "1738568400",
        },
    )
    def test_enabled_providers_with_strava_env(self, tmp_path):
        """Test enabled_providers when Strava env vars are set and provider is enabled."""
        config_data = {
            "providers": {
                "spreadsheet": {"enabled": False},
                "strava": {"enabled": True},
                "ridewithgps": {"enabled": False},
                "garmin": {"enabled": False},
                "file": {"enabled": False},
                "stravajson": {"enabled": False},
            }
        }

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db
            mock_db.connect.return_value = None
            mock_db.is_connection_usable.return_value = True

            tracekit = tracekit_class()

            # Should detect strava provider due to env vars and enabled config
            assert "strava" in tracekit.enabled_providers

    @patch.dict(
        os.environ,
        {
            "STRAVA_ACCESS_TOKEN": "test_token",
            "STRAVA_CLIENT_ID": "12345",
            "STRAVA_CLIENT_SECRET": "secret",
        },
    )
    def test_enabled_providers_with_strava_disabled(self, tmp_path):
        """Test enabled_providers when Strava env vars are set but provider is disabled."""
        config_data = {
            "providers": {
                "spreadsheet": {"enabled": False},
                "strava": {"enabled": False},  # Disabled in config
                "ridewithgps": {"enabled": False},
                "garmin": {"enabled": False},
                "file": {"enabled": False},
                "stravajson": {"enabled": False},
            }
        }

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db
            mock_db.connect.return_value = None
            mock_db.is_connection_usable.return_value = True

            tracekit = tracekit_class()

            # Should NOT detect strava provider because it's disabled in config
            assert "strava" not in tracekit.enabled_providers

    def test_cleanup_closes_db(self, tmp_path):
        """Test that cleanup properly closes database connection."""
        config_data = {}

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_db.close.return_value = None
                mock_get_db.return_value = mock_db

                tracekit = tracekit_class()

                # Test cleanup directly
                with patch("tracekit.core.get_db", return_value=mock_db):
                    tracekit.cleanup()

                mock_db.close.assert_called_once()

    def test_context_manager(self, tmp_path):
        """Test that tracekit works as a context manager."""
        config_data = {}

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_db.close.return_value = None
                mock_get_db.return_value = mock_db

                with patch("tracekit.core.get_db", return_value=mock_db):
                    with tracekit_class() as tracekit:
                        assert tracekit is not None

                    # Should have called cleanup
                    mock_db.close.assert_called_once()

    def test_pull_activities_error_handling(self, tmp_path):
        """Test that pull_activities handles provider errors gracefully."""
        config_data = {"providers": {"spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"}}}

        config_file = tmp_path / "tracekit_config.json"
        config_file.write_text(json.dumps(config_data))

        with patch("tracekit.core.CONFIG_PATH", config_file), patch("tracekit.db.configure_db"):
            with patch("tracekit.db.get_db") as mock_get_db:
                mock_db = MagicMock()
                mock_db.connect.return_value = None
                mock_db.is_connection_usable.return_value = True
                mock_get_db.return_value = mock_db
            mock_db.connect.return_value = None
            mock_db.is_connection_usable.return_value = True

            tracekit = tracekit_class()

            # Mock a provider that raises an exception
            mock_provider = MagicMock()
            mock_provider.pull_activities.side_effect = Exception("Test error")
            tracekit._spreadsheet = mock_provider

            result = tracekit.pull_activities("2024-01")

            # Should handle error gracefully and return empty list
            assert result["spreadsheet"] == []
