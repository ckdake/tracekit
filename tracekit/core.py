"""Core tracekit functionality and provider management."""

import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .appconfig import DEFAULT_CONFIG, load_config
from .database import get_all_models, migrate_tables
from .db import configure_db, get_db
from .providers.base_provider_activity import BaseProviderActivity
from .providers.file import FileProvider
from .providers.garmin import GarminProvider
from .providers.ridewithgps import RideWithGPSProvider
from .providers.spreadsheet import SpreadsheetProvider
from .providers.strava import StravaProvider
from .providers.stravajson import StravaJsonProvider

CONFIG_PATH = Path("tracekit_config.json")


class Tracekit:
    """Main tracekit class that handles configuration and provider management."""

    def __init__(self):
        # Determine the SQLite path before the DB is configured.
        # Priority: DATABASE_URL env (Postgres), METADATA_DB env, JSON file, default.
        db_path = self._resolve_db_path()
        configure_db(db_path)

        # Ensure schema exists before load_config() tries to read appconfig.
        db = get_db()
        db.connect(reuse_if_open=True)
        migrate_tables(get_all_models())

        # load_config() syncs JSON file -> DB if they differ, then returns DB.
        self.config = load_config()
        self.home_tz = ZoneInfo(self.config.get("home_timezone", "US/Eastern"))

        # Initialize providers
        self._spreadsheet = None
        self._strava = None
        self._ridewithgps = None
        self._garmin = None
        self._file = None
        self._stravajson = None

    @staticmethod
    def _resolve_db_path() -> str:
        """Return the SQLite path to use when DATABASE_URL is not set."""
        import os

        # Explicit env override
        env_path = os.environ.get("METADATA_DB")
        if env_path:
            return env_path

        # Fall back to JSON file's metadata_db key if the file exists
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    raw = json.load(f)
                file_path = raw.get("metadata_db")
                if file_path:
                    return file_path
            except Exception:
                pass

        return DEFAULT_CONFIG.get("metadata_db", "metadata.sqlite3")

    @property
    def spreadsheet(self) -> SpreadsheetProvider | None:
        """Get the spreadsheet provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("spreadsheet", {})

        if not self._spreadsheet and provider_config.get("enabled", False):
            path = provider_config.get("path")
            if path:
                # Add home_timezone to provider config
                enhanced_config = provider_config.copy()
                enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
                self._spreadsheet = SpreadsheetProvider(path, config=enhanced_config)
        return self._spreadsheet

    @property
    def strava(self) -> StravaProvider | None:
        """Get the Strava provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("strava", {})

        if not self._strava and provider_config.get("enabled", False):
            token = provider_config.get("access_token", "").strip()
            if token:
                enhanced_config = provider_config.copy()
                enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
                self._strava = StravaProvider(
                    token,
                    refresh_token=provider_config.get("refresh_token") or None,
                    token_expires=provider_config.get("token_expires", "0"),
                    config=enhanced_config,
                )
        return self._strava

    @property
    def ridewithgps(self) -> RideWithGPSProvider | None:
        """Get the RideWithGPS provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("ridewithgps", {})

        if (
            not self._ridewithgps
            and provider_config.get("enabled", False)
            and provider_config.get("email", "").strip()
            and provider_config.get("password", "").strip()
            and provider_config.get("apikey", "").strip()
        ):
            enhanced_config = provider_config.copy()
            enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
            self._ridewithgps = RideWithGPSProvider(config=enhanced_config)
        return self._ridewithgps

    @property
    def garmin(self) -> GarminProvider | None:
        """Get the Garmin provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("garmin", {})

        if not self._garmin and provider_config.get("enabled", False) and os.environ.get("GARMINTOKENS"):
            # Add home_timezone to provider config
            enhanced_config = provider_config.copy()
            enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
            self._garmin = GarminProvider(config=enhanced_config)
        return self._garmin

    @property
    def file(self) -> FileProvider | None:
        """Get the File provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("file", {})

        if not self._file and provider_config.get("enabled", False):
            # The data folder is fixed: $TRACEKIT_DATA_DIR/activities (or the
            # default /opt/tracekit/data/activities used in production).  There
            # is no user-configurable glob — all supported files in the folder
            # are picked up automatically.
            data_dir = os.environ.get("TRACEKIT_DATA_DIR", "/opt/tracekit/data")
            data_folder = os.path.join(data_dir, "activities")
            enhanced_config = provider_config.copy()
            enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
            self._file = FileProvider(data_folder, config=enhanced_config)
        return self._file

    @property
    def stravajson(self) -> StravaJsonProvider | None:
        """Get the StravaJSON provider, initializing it if needed."""
        provider_config = self.config.get("providers", {}).get("stravajson", {})

        if not self._stravajson and provider_config.get("enabled", False):
            folder = provider_config.get("folder")
            if folder:
                # Add home_timezone to provider config
                enhanced_config = provider_config.copy()
                enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
                self._stravajson = StravaJsonProvider(folder, config=enhanced_config)
        return self._stravajson

    @property
    def enabled_providers(self) -> list[str]:
        """Get list of enabled providers based on config."""
        providers = []
        providers_config = self.config.get("providers", {})

        for provider_name in [
            "spreadsheet",
            "strava",
            "ridewithgps",
            "garmin",
            "file",
            "stravajson",
        ]:
            if providers_config.get(provider_name, {}).get("enabled", False):
                # Only add if required credentials/paths are available
                provider = getattr(self, provider_name)
                if provider:
                    providers.append(provider_name)

        return providers

    def get_provider(self, provider_name: str):
        """Get a provider by name, returning None if not available or enabled."""
        return getattr(self, provider_name, None)

    def delete_month_activities(self, year_month: str) -> None:
        """Delete all activity records and sync state for the given YYYY-MM month.

        Called before re-pulling so stale data doesn't linger.
        Removes:
          - Activity rows whose date falls within the month
          - All BaseProviderActivity subclass rows whose start_time falls in the month
          - ProviderSync rows for the month
        """
        import calendar as _calendar

        from .activity import Activity
        from .provider_sync import ProviderSync
        from .providers.base_provider import FitnessProvider

        home_tz = self.config.get("home_timezone", "US/Eastern")
        start_ts, end_ts = FitnessProvider._YYYY_MM_to_unixtime_range(year_month, home_tz)

        year_int, month_int = (int(p) for p in year_month.split("-"))
        last_day = _calendar.monthrange(year_int, month_int)[1]
        date_start = f"{year_month}-01"
        date_end = f"{year_month}-{last_day:02d}"

        # Delete core Activity rows for the month
        Activity.delete().where((Activity.date >= date_start) & (Activity.date <= date_end)).execute()

        # Delete every provider-specific activity table for the month
        for model_cls in BaseProviderActivity.__subclasses__():
            model_cls.delete().where((model_cls.start_time >= start_ts) & (model_cls.start_time <= end_ts)).execute()

        # Clear sync-state so the month is treated as never-synced
        ProviderSync.delete().where(ProviderSync.year_month == year_month).execute()

    def pull_provider_activities(self, year_month: str, provider_name: str) -> list[BaseProviderActivity]:
        """Pull activities for *year_month* from a single named provider.

        Raises ValueError if the provider is unknown or not available/enabled.
        Propagates ProviderRateLimitError directly so the Celery worker can
        decide whether to retry or fail without extra wrapping.
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider '{provider_name}' is not available or not enabled")

        try:
            activities = provider.pull_activities(year_month)
            print(f"Pulled {len(activities)} activities from {provider_name}")
            try:
                from tracekit.provider_status import record_operation

                record_operation(
                    provider_name,
                    "pull",
                    True,
                    f"Pulled {len(activities)} activities for {year_month}",
                )
            except Exception:
                pass
            return activities
        except Exception as e:
            from tracekit.provider_status import ProviderRateLimitError

            if isinstance(e, ProviderRateLimitError):
                try:
                    from tracekit.provider_status import record_rate_limit

                    record_rate_limit(e.provider, e.limit_type, e.reset_at, "pull", str(e))
                except Exception:
                    pass
            else:
                try:
                    from tracekit.provider_status import record_operation

                    record_operation(provider_name, "pull", False, str(e))
                except Exception:
                    pass
            raise

    def pull_activities(self, year_month: str) -> dict[str, list[BaseProviderActivity]]:
        """Pull activities from all enabled providers for the given month.

        This is the main entry point for fetching data from providers.
        Each provider handles its own API interaction and database updates.

        Returns:
            Dict mapping provider names to lists of BaseProviderActivity objects
        """
        activities = {}

        for provider_name in self.enabled_providers:
            try:
                activities[provider_name] = self.pull_provider_activities(year_month, provider_name)
            except Exception as e:
                from tracekit.provider_status import ProviderRateLimitError

                # Rate limit errors must propagate so the worker can retry/fail cleanly
                if isinstance(e, ProviderRateLimitError):
                    raise
                print(f"Error pulling from {provider_name}: {e}")
                activities[provider_name] = []
                try:
                    from tracekit.notification import create_notification

                    create_notification(
                        f"{provider_name} error pulling {year_month}: {e}",
                        category="error",
                    )
                except Exception:
                    pass

        return activities

    def cleanup(self):
        """Clean up resources, close connections etc."""
        try:
            db = get_db()
            if db.is_connection_usable():
                db.close()
        except RuntimeError:
            # Database not configured, nothing to clean up
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()


# Backwards compatible alias: many files import `tracekit` from this module
# expecting a class/constructor. Keep `tracekit` pointing to the class
# but use `Tracekit` as the proper CapWords class name to satisfy Ruff.
tracekit = Tracekit
