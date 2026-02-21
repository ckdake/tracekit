import os
from unittest.mock import MagicMock, patch

import tracekit.appconfig as tcfg
from tracekit.appconfig import AppConfig, save_config
from tracekit.core import tracekit as tracekit_class


class TesttracekitCore:
    """Test the core tracekit class functionality."""

    def test_tracekit_init_loads_config(self, monkeypatch):
        """Test that tracekit initializes and loads config correctly."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "US/Pacific",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"},
                    "strava": {"enabled": True},
                    "file": {"enabled": True, "glob": "./test/*"},
                },
            }
        )

        tracekit = tracekit_class()

        assert tracekit.config["home_timezone"] == "US/Pacific"
        assert not tracekit.config["debug"]

    def test_tracekit_config_defaults(self, monkeypatch):
        """Test that tracekit seeds DEFAULT_CONFIG into DB when DB is empty."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()

        tracekit = tracekit_class()

        # Defaults should always include debug=False and home_timezone
        assert not tracekit.config["debug"]
        assert "home_timezone" in tracekit.config
        assert "providers" in tracekit.config

    def test_enabled_providers_empty(self, monkeypatch):
        """Test enabled_providers when no providers are enabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": False},
                    "strava": {"enabled": False},
                    "ridewithgps": {"enabled": False},
                    "garmin": {"enabled": False},
                    "file": {"enabled": False},
                    "stravajson": {"enabled": False},
                },
            }
        )

        tracekit = tracekit_class()

        # No providers should be enabled
        assert tracekit.enabled_providers == []

    def test_enabled_providers_with_spreadsheet(self, monkeypatch):
        """Test enabled_providers when spreadsheet is configured and enabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"},
                    "strava": {"enabled": False},
                    "ridewithgps": {"enabled": False},
                    "garmin": {"enabled": False},
                    "file": {"enabled": False},
                    "stravajson": {"enabled": False},
                },
            }
        )

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
    def test_enabled_providers_with_strava_env(self, monkeypatch):
        """Test enabled_providers when Strava env vars are set and provider is enabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": False},
                    "strava": {"enabled": True},
                    "ridewithgps": {"enabled": False},
                    "garmin": {"enabled": False},
                    "file": {"enabled": False},
                    "stravajson": {"enabled": False},
                },
            }
        )

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
    def test_enabled_providers_with_strava_disabled(self, monkeypatch):
        """Test enabled_providers when Strava env vars are set but provider is disabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": False},
                    "strava": {"enabled": False},  # Disabled in config
                    "ridewithgps": {"enabled": False},
                    "garmin": {"enabled": False},
                    "file": {"enabled": False},
                    "stravajson": {"enabled": False},
                },
            }
        )

        tracekit = tracekit_class()

        # Should NOT detect strava provider because it's disabled in config
        assert "strava" not in tracekit.enabled_providers

    def test_cleanup_closes_db(self, monkeypatch):
        """Test that cleanup properly closes database connection."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()

        mock_db = MagicMock()
        mock_db.close.return_value = None

        tracekit = tracekit_class()

        # Test cleanup directly
        with patch("tracekit.core.get_db", return_value=mock_db):
            tracekit.cleanup()

        mock_db.close.assert_called_once()

    def test_context_manager(self, monkeypatch):
        """Test that tracekit works as a context manager."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()

        mock_db = MagicMock()
        mock_db.close.return_value = None

        with patch("tracekit.core.get_db", return_value=mock_db):
            with tracekit_class() as tracekit:
                assert tracekit is not None

            # Should have called cleanup
            mock_db.close.assert_called_once()

    def test_pull_activities_error_handling(self, monkeypatch):
        """Test that pull_activities handles provider errors gracefully."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": True, "path": "/tmp/test.xlsx"},
                },
            }
        )

        tracekit = tracekit_class()

        # Mock a provider that raises an exception
        mock_provider = MagicMock()
        mock_provider.pull_activities.side_effect = Exception("Test error")
        tracekit._spreadsheet = mock_provider

        result = tracekit.pull_activities("2024-01")

        # Should handle error gracefully and return empty list
        assert result["spreadsheet"] == []
