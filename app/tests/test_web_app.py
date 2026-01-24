"""Tests for the tracekit web application."""

import json
import os
import sqlite3

# Import from the parent app module
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

    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)


@pytest.fixture
def temp_database():
    """Create a temporary database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    # Create database with test data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create test tables
    cursor.execute("""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            name TEXT,
            date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE providersync (
            id INTEGER PRIMARY KEY,
            year_month TEXT,
            provider TEXT
        )
    """)

    # Insert test data
    cursor.execute("INSERT INTO activities (name, date) VALUES (?, ?)", ("Test Activity 1", "2024-01-01"))
    cursor.execute("INSERT INTO activities (name, date) VALUES (?, ?)", ("Test Activity 2", "2024-01-02"))

    # Insert sync data
    sync_data = [
        ("2024-01", "strava"),
        ("2024-01", "garmin"),
        ("2024-02", "strava"),
        ("2024-02", "garmin"),
        ("2024-02", "spreadsheet"),
        ("2024-03", "strava"),
    ]

    for year_month, provider in sync_data:
        cursor.execute("INSERT INTO providersync (year_month, provider) VALUES (?, ?)", (year_month, provider))

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
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
        db_info = get_database_info(temp_database)

        assert "error" not in db_info
        assert db_info["path"] == temp_database
        assert db_info["file_size_bytes"] > 0
        assert db_info["file_size_mb"] > 0
        assert "tables" in db_info
        assert "activities" in db_info["tables"]
        assert "providersync" in db_info["tables"]
        assert db_info["tables"]["activities"] == 2
        assert db_info["tables"]["providersync"] == 6
        assert db_info["total_tables"] == 2

    def test_get_database_info_missing_file(self):
        """Test getting info from a missing database file."""
        db_info = get_database_info("nonexistent_database.sqlite3")

        assert "error" in db_info
        assert "not found" in db_info["error"]
        assert db_info["path"] == "nonexistent_database.sqlite3"

    def test_get_database_info_invalid_file(self):
        """Test getting info from an invalid database file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sqlite3", delete=False) as f:
            f.write("not a database")
            temp_file = f.name

        try:
            db_info = get_database_info(temp_file)
            assert "error" in db_info
            assert "Database error" in db_info["error"]
        finally:
            os.remove(temp_file)


class TestProviderSorting:
    """Test provider sorting functionality."""

    def test_sort_providers_by_priority(self):
        """Test sorting providers by priority."""
        providers = {
            "strava": {"enabled": True, "priority": 3},
            "garmin": {"enabled": True, "priority": 1},
            "spreadsheet": {"enabled": True, "priority": 2},
            "file": {"enabled": True},  # No priority
            "disabled": {"enabled": False, "priority": 1},
        }

        sorted_providers = sort_providers(providers)

        # Check order: enabled by priority first, then enabled without priority, then disabled
        assert len(sorted_providers) == 5
        assert sorted_providers[0][0] == "garmin"  # priority 1
        assert sorted_providers[1][0] == "spreadsheet"  # priority 2
        assert sorted_providers[2][0] == "strava"  # priority 3
        assert sorted_providers[3][0] == "file"  # no priority (gets 999)
        assert sorted_providers[4][0] == "disabled"  # disabled

    def test_sort_providers_all_disabled(self):
        """Test sorting when all providers are disabled."""
        providers = {
            "strava": {"enabled": False},
            "garmin": {"enabled": False},
        }

        sorted_providers = sort_providers(providers)

        assert len(sorted_providers) == 2
        # Order should be preserved for disabled providers
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
        config_data["metadata_db"] = temp_database

        # Update config file with correct database path
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
        config_data["metadata_db"] = temp_database

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
        config_data["metadata_db"] = temp_database

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            response = client.get("/api/database")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert "tables" in data
        assert "activities" in data["tables"]

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
        config_data["metadata_db"] = temp_database

        with open(temp_file, "w") as f:
            json.dump(config_data, f)

        with patch("main.CONFIG_PATH", Path(temp_file)):
            # Test index page
            response = client.get("/")
            assert response.status_code == 200
            assert b"tracekit Dashboard" in response.data

            # Test config API
            response = client.get("/api/config")
            assert response.status_code == 200
            config_data = response.get_json()
            assert "providers" in config_data

            # Test database API
            response = client.get("/api/database")
            assert response.status_code == 200
            db_data = response.get_json()
            assert "tables" in db_data

            # Test health check
            response = client.get("/health")
            assert response.status_code == 200
            health_data = response.get_json()
            assert health_data["status"] == "healthy"
