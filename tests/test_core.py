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

    def test_enabled_providers_with_strava_env(self, monkeypatch):
        """Test enabled_providers when Strava credentials are in config and provider is enabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": False},
                    "strava": {
                        "enabled": True,
                        "access_token": "test_token",
                        "refresh_token": "12345",
                        "token_expires": "1738568400",
                    },
                    "ridewithgps": {"enabled": False},
                    "garmin": {"enabled": False},
                    "file": {"enabled": False},
                    "stravajson": {"enabled": False},
                },
            }
        )

        tracekit = tracekit_class()

        # Should detect strava provider due to credentials in config and enabled flag
        assert "strava" in tracekit.enabled_providers

    def test_enabled_providers_with_strava_disabled(self, monkeypatch):
        """Test enabled_providers when Strava credentials present but provider is disabled."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "spreadsheet": {"enabled": False},
                    "strava": {
                        "enabled": False,  # Disabled in config
                        "access_token": "test_token",
                        "client_id": "12345",
                        "client_secret": "secret",
                    },
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

    # ── System credential fallback ────────────────────────────────────────────

    def test_strava_uses_system_client_creds_when_personal_off(self, monkeypatch):
        """When use_personal_credentials is False, env vars override config creds."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        monkeypatch.setenv("STRAVA_CLIENT_ID", "sys_id")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "sys_secret")
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "strava": {
                        "enabled": True,
                        "use_personal_credentials": False,
                        "client_id": "personal_id",
                        "client_secret": "personal_secret",
                        "access_token": "tok",
                        "refresh_token": "ref",
                        "token_expires": "9999999999",
                    },
                },
            }
        )

        tk = tracekit_class()
        provider = tk.strava

        assert provider is not None
        assert provider.config["client_id"] == "sys_id"
        assert provider.config["client_secret"] == "sys_secret"

    def test_strava_uses_personal_creds_when_flag_on(self, monkeypatch):
        """When use_personal_credentials is True, config values are kept as-is."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        monkeypatch.setenv("STRAVA_CLIENT_ID", "sys_id")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "sys_secret")
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "strava": {
                        "enabled": True,
                        "use_personal_credentials": True,
                        "client_id": "personal_id",
                        "client_secret": "personal_secret",
                        "access_token": "tok",
                        "refresh_token": "ref",
                        "token_expires": "9999999999",
                    },
                },
            }
        )

        tk = tracekit_class()
        provider = tk.strava

        assert provider is not None
        assert provider.config["client_id"] == "personal_id"
        assert provider.config["client_secret"] == "personal_secret"

    def test_ridewithgps_uses_system_apikey_when_personal_off(self, monkeypatch):
        """When use_personal_credentials is False, RIDEWITHGPS_KEY env var is used."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        monkeypatch.setenv("RIDEWITHGPS_KEY", "sys_apikey")
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "ridewithgps": {
                        "enabled": True,
                        "use_personal_credentials": False,
                        "email": "user@example.com",
                        "password": "pass",
                        "apikey": "",
                    },
                },
            }
        )

        tk = tracekit_class()
        provider = tk.ridewithgps

        assert provider is not None
        assert provider.apikey == "sys_apikey"

    def test_ridewithgps_uses_personal_apikey_when_flag_on(self, monkeypatch):
        """When use_personal_credentials is True, the user's apikey is used."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        monkeypatch.setenv("RIDEWITHGPS_KEY", "sys_apikey")
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "ridewithgps": {
                        "enabled": True,
                        "use_personal_credentials": True,
                        "email": "user@example.com",
                        "password": "pass",
                        "apikey": "personal_key",
                    },
                },
            }
        )

        tk = tracekit_class()
        provider = tk.ridewithgps

        assert provider is not None
        assert provider.apikey == "personal_key"

    def test_ridewithgps_returns_none_without_any_apikey(self, monkeypatch):
        """RideWithGPS returns None when no apikey is available from any source."""
        monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
        monkeypatch.delenv("RIDEWITHGPS_KEY", raising=False)
        AppConfig.delete().execute()
        save_config(
            {
                "home_timezone": "UTC",
                "debug": False,
                "providers": {
                    "ridewithgps": {
                        "enabled": True,
                        "use_personal_credentials": False,
                        "email": "user@example.com",
                        "password": "pass",
                        "apikey": "",
                    },
                },
            }
        )

        tk = tracekit_class()
        assert tk.ridewithgps is None

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
