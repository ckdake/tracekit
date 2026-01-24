"""Core tracekit functionality and provider management."""

import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
        # Load config first
        self.config = self._load_config()
        self.home_tz = ZoneInfo(self.config.get("home_timezone", "US/Eastern"))

        # Configure database with path from config
        metadata_db_path = self.config.get("metadata_db", "metadata.sqlite3")
        configure_db(metadata_db_path)

        # Initialize database
        db = get_db()
        db.connect(reuse_if_open=True)

        # Always migrate tables on startup
        migrate_tables(get_all_models())

        # Initialize providers
        self._spreadsheet = None
        self._strava = None
        self._ridewithgps = None
        self._garmin = None
        self._file = None
        self._stravajson = None

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from tracekit_config.json."""
        with open(CONFIG_PATH) as f:
            config = json.load(f)

        # Set defaults if not present
        if "debug" not in config:
            config["debug"] = False
        if "provider_priority" not in config:
            config["provider_priority"] = "spreadsheet,ridewithgps,strava,garmin"

        return config

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
            token = os.environ.get("STRAVA_ACCESS_TOKEN")
            if token:
                # Add home_timezone to provider config
                enhanced_config = provider_config.copy()
                enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
                self._strava = StravaProvider(
                    token,
                    refresh_token=os.environ.get("STRAVA_REFRESH_TOKEN"),
                    token_expires=os.environ.get("STRAVA_TOKEN_EXPIRES"),
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
            and all(
                os.environ.get(env)
                for env in [
                    "RIDEWITHGPS_EMAIL",
                    "RIDEWITHGPS_PASSWORD",
                    "RIDEWITHGPS_KEY",
                ]
            )
        ):
            # Add home_timezone to provider config
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
            glob_pattern = provider_config.get("glob")
            if glob_pattern:
                # Add home_timezone to provider config
                enhanced_config = provider_config.copy()
                enhanced_config["home_timezone"] = self.config.get("home_timezone", "US/Eastern")
                self._file = FileProvider(glob_pattern, config=enhanced_config)
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

    def pull_activities(self, year_month: str) -> dict[str, list[BaseProviderActivity]]:
        """Pull activities from all enabled providers for the given month.

        This is the main entry point for fetching data from providers.
        Each provider handles its own API interaction and database updates.

        Returns:
            Dict mapping provider names to lists of BaseProviderActivity objects
        """
        activities = {}

        # Get the list of enabled providers from the config
        enabled_providers = self.enabled_providers

        # Pull from each enabled provider
        for provider_name in enabled_providers:
            provider = getattr(self, provider_name)
            if provider:
                try:
                    provider_activities = provider.pull_activities(year_month)
                    activities[provider_name] = provider_activities
                    print(f"Pulled {len(provider_activities)} activities from {provider_name}")
                except Exception as e:
                    print(f"Error pulling from {provider_name}: {e}")
                    activities[provider_name] = []
            else:
                activities[provider_name] = []

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
