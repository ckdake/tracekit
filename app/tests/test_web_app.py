"""Tests for the tracekit web application."""

import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import (
    app,
    get_database_info,
    load_tracekit_config,
    sort_providers,
)


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset DB initialisation state between tests to prevent leakage."""
    yield
    import main as main_module

    import tracekit.db as tdb

    main_module._db_initialized = False
    tdb._configured = False


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_config():
    """Create a temporary config file for testing."""
    config_data = {
        "home_timezone": "US/Pacific",
        "metadata_db": "test_metadata.sqlite3",
        "debug": True,
        "providers": {
            "strava": {"enabled": True, "priority": 1},
            "garmin": {"enabled": True, "priority": 2},
            "spreadsheet": {"enabled": True, "priority": 3},
            "file": {"enabled": True},
            "disabled_provider": {"enabled": False, "priority": 999},
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_data, f)
        temp_file = f.name

    yield temp_file, config_data

    if os.path.exists(temp_file):
        os.remove(temp_file)


@pytest.fixture
def temp_database():
    """Create a temporary database with test data using peewee models."""
    import tracekit.db as tdb
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db
    from tracekit.provider_sync import ProviderSync

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())

    sync_data = [
        ("2024-01", "strava"),
        ("2024-01", "garmin"),
        ("2024-02", "strava"),
        ("2024-02", "garmin"),
        ("2024-02", "spreadsheet"),
        ("2024-03", "strava"),
    ]
    for year_month, provider in sync_data:
        ProviderSync.get_or_create(year_month=year_month, provider=provider)

    config = {"metadata_db": db_path, "home_timezone": "US/Pacific"}
    yield db_path, config

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


class TestConfigLoading:
    """Test configuration loading functionality."""

    def test_load_valid_config(self, temp_config):
        """Test loading a valid configuration file."""
        temp_file, _expected_data = temp_config

        with patch("main.CONFIG_PATH", Path(temp_file)):
            config = load_tracekit_config()

        assert config["home_timezone"] == "US/Pacific"
        assert config["metadata_db"] == "test_metadata.sqlite3"
        assert config["debug"] is True
        assert "providers" in config
        assert len(config["providers"]) == 5

    def test_load_missing_config(self):
        """Test loading when config file is missing."""
        with patch("main.CONFIG_PATH", Path("nonexistent_file.json")):
            config = load_tracekit_config()

        assert "error" in config
        assert "not found" in config["error"]

    def test_load_invalid_json(self):
        """Test loading an invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_file = f.name

        try:
            with patch("main.CONFIG_PATH", Path(temp_file)):
                config = load_tracekit_config()

            assert "error" in config
            assert "Invalid JSON" in config["error"]
        finally:
            os.remove(temp_file)


class TestDatabaseInfo:
    """Test database information functionality."""

    def test_get_database_info_valid_db(self, temp_database):
        """Test getting info from a valid database."""
        _db_path, config = temp_database
        db_info = get_database_info(config)

        assert "error" not in db_info
        assert "tables" in db_info
        assert "providersync" in db_info["tables"]
        assert "activity" in db_info["tables"]
        assert db_info["tables"]["providersync"] == 6
        assert db_info["total_tables"] > 0

    def test_get_database_info_empty_db(self):
        """Test getting info from an empty (unconfigured) DB gracefully."""
        import tracekit.db as tdb

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            empty_path = f.name

        try:
            # empty DB — tables haven't been created, queries should error gracefully
            tdb._configured = False
            config = {"metadata_db": empty_path, "home_timezone": "UTC"}
            db_info = get_database_info(config)
            assert isinstance(db_info, dict)
        finally:
            tdb._configured = False
            os.remove(empty_path)


class TestProviderSorting:
    """Test provider sorting functionality."""

    def test_sort_providers_by_priority(self):
        """Test sorting providers by priority."""
        providers = {
            "strava": {"enabled": True, "priority": 3},
            "garmin": {"enabled": True, "priority": 1},
            "spreadsheet": {"enabled": True, "priority": 2},
            "file": {"enabled": True},
            "disabled": {"enabled": False, "priority": 1},
        }

        sorted_providers = sort_providers(providers)

        assert len(sorted_providers) == 5
        assert sorted_providers[0][0] == "garmin"
        assert sorted_providers[1][0] == "spreadsheet"
        assert sorted_providers[2][0] == "strava"
        assert sorted_providers[3][0] == "file"
        assert sorted_providers[4][0] == "disabled"

    def test_sort_providers_all_disabled(self):
        """Test sorting when all providers are disabled."""
        providers = {
            "strava": {"enabled": False},
            "garmin": {"enabled": False},
        }

        sorted_providers = sort_providers(providers)

        assert len(sorted_providers) == 2
        assert sorted_providers[0][0] in ["strava", "garmin"]
        assert sorted_providers[1][0] in ["strava", "garmin"]

    def test_sort_providers_empty(self):
        """Test sorting empty providers dict."""
        sorted_providers = sort_providers({})
        assert sorted_providers == []


class TestWebRoutes:
    """Test Flask web routes."""

    def test_index_route_success(self, client, temp_config, temp_database):
        """Test the index route with valid config and database."""
        temp_file, config_data = temp_config
        _db_path, db_config = temp_database
        config_data["metadata_db"] = db_config["metadata_db"]

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/")

        assert response.status_code == 200
        assert b"tracekit Dashboard" in response.data
        assert b"US/Pacific" in response.data

    def test_index_route_config_error(self, client):
        """Test the index route with config error."""
        with patch("main.CONFIG_PATH", Path("nonexistent.json")):
            response = client.get("/")

        assert response.status_code == 200
        assert b"Configuration Error" in response.data

    def test_calendar_route_success(self, client, temp_config, temp_database):
        """Test the calendar route with valid data."""
        temp_file, config_data = temp_config
        _db_path, db_config = temp_database
        config_data["metadata_db"] = db_config["metadata_db"]

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/calendar")

        assert response.status_code == 200
        assert b"tracekit Sync Calendar" in response.data
        assert b"strava" in response.data
        assert b"garmin" in response.data

    def test_api_config_route(self, client, temp_config):
        """Test the API config route."""
        temp_file, _config_data = temp_config

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/api/config")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert data["home_timezone"] == "US/Pacific"
        assert "providers" in data

    def test_api_database_route(self, client, temp_config, temp_database):
        """Test the API database route."""
        temp_file, config_data = temp_config
        _db_path, db_config = temp_database
        config_data["metadata_db"] = db_config["metadata_db"]

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/api/database")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert "tables" in data
        assert "providersync" in data["tables"]

    def test_api_database_route_no_config(self, client):
        """Test the API database route with no valid config."""
        with patch("main.CONFIG_PATH", Path("nonexistent.json")):
            response = client.get("/api/database")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert "error" in data

    def test_health_route(self, client):
        """Test the health check route."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["app"] == "tracekit-web"

    def test_404_route(self, client):
        """Test a non-existent route returns 404."""
        response = client.get("/nonexistent")
        assert response.status_code == 404


class TestIntegration:
    """Integration tests for the web application."""

    def test_full_application_flow(self, client, temp_config, temp_database):
        """Test a complete flow through the application."""
        temp_file, config_data = temp_config
        _db_path, db_config = temp_database
        config_data["metadata_db"] = db_config["metadata_db"]

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/")
            assert response.status_code == 200
            assert b"tracekit Dashboard" in response.data

            response = client.get("/api/config")
            assert response.status_code == 200
            api_config = response.get_json()
            assert "providers" in api_config

            response = client.get("/api/database")
            assert response.status_code == 200
            db_data = response.get_json()
            assert "tables" in db_data

            response = client.get("/health")
            assert response.status_code == 200
            health_data = response.get_json()
            assert health_data["status"] == "healthy"
