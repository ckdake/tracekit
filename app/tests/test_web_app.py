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

from db_init import load_tracekit_config
from helpers import get_database_info, sort_providers
from main import app

# ---------------------------------------------------------------------------
# Shared config data used across fixtures
# ---------------------------------------------------------------------------

_CONFIG_DATA = {
    "home_timezone": "US/Pacific",
    "debug": True,
    "providers": {
        "strava": {"enabled": True, "priority": 1},
        "garmin": {"enabled": True, "priority": 2},
        "spreadsheet": {"enabled": True, "priority": 3},
        "file": {"enabled": True},
        "disabled_provider": {"enabled": False, "priority": 999},
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset DB initialisation state between tests to prevent leakage."""
    yield
    import db_init as db_init_module

    import tracekit.db as tdb

    db_init_module._db_initialized = False
    tdb._configured = False


@pytest.fixture
def client(temp_database):
    """Create an authenticated test client with a seeded admin user."""
    from models.user import User
    from werkzeug.security import generate_password_hash

    from tracekit.db import get_db

    db = get_db()
    db.create_tables([User])
    user = User.create(
        email="testadmin@example.com",
        password_hash=generate_password_hash("testpass"),
        status="active",
    )

    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        yield c


@pytest.fixture
def temp_config_file():
    """Write _CONFIG_DATA to a temporary JSON file; yield its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_CONFIG_DATA, f)
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_database(monkeypatch):
    """Create a temporary database seeded with sync rows *and* appconfig.

    Also patches _FILE_PATHS to [] so the real tracekit_config.json on disk
    can't interfere with the test DB via the file-sync logic.
    """
    import tracekit.appconfig as tcfg
    import tracekit.db as tdb
    from tracekit.appconfig import save_config
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db
    from tracekit.provider_sync import ProviderSync

    # Prevent the real config file from overwriting the test-seeded config
    monkeypatch.setattr(tcfg, "_FILE_PATHS", [])

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())

    # Seed config into appconfig table
    save_config(_CONFIG_DATA)

    # Seed sync rows
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

    yield db_path

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


# ---------------------------------------------------------------------------
# TestConfigLoading
# ---------------------------------------------------------------------------


class TestConfigLoading:
    """Config is always stored in the DB; the JSON file syncs *into* the DB."""

    def test_config_loads_from_db(self, temp_database):
        """Config seeded in DB is returned by load_tracekit_config()."""
        config = load_tracekit_config()

        assert config["home_timezone"] == "US/Pacific"
        assert config["debug"] is True
        assert "providers" in config
        assert len(config["providers"]) == 5

    def test_config_file_synced_to_db_on_boot(self, temp_database, temp_config_file):
        """If a JSON config file differs from the DB, the DB is updated to match."""
        import tracekit.appconfig as tcfg
        from tracekit.appconfig import _load_from_db, save_config

        # Overwrite DB with a different timezone so we can detect the sync
        save_config({**_CONFIG_DATA, "home_timezone": "UTC"})

        # Point _FILE_PATHS at our temp file (which has "US/Pacific")
        with patch.object(tcfg, "_FILE_PATHS", [Path(temp_config_file)]):
            config = load_tracekit_config()

        assert config["home_timezone"] == "US/Pacific"

        # DB should now reflect the file value
        db_cfg = _load_from_db()
        assert db_cfg is not None
        assert db_cfg["home_timezone"] == "US/Pacific"

    def test_defaults_seeded_when_db_empty(self):
        """First boot with empty DB and no file seeds built-in defaults."""
        import tracekit.appconfig as tcfg
        import tracekit.db as tdb
        from tracekit.database import get_all_models, migrate_tables
        from tracekit.db import configure_db

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        try:
            tdb._configured = False
            configure_db(db_path)
            db = tdb.get_db()
            db.connect(reuse_if_open=True)
            migrate_tables(get_all_models())

            with patch.object(tcfg, "_FILE_PATHS", []):
                config = load_tracekit_config()

            assert config["home_timezone"] == "UTC"  # built-in default
            assert isinstance(config.get("providers"), dict)
        finally:
            tdb._configured = False
            with contextlib.suppress(Exception):
                db.close()
            if os.path.exists(db_path):
                os.remove(db_path)


# ---------------------------------------------------------------------------
# TestDatabaseInfo
# ---------------------------------------------------------------------------


class TestDatabaseInfo:
    """Test database information functionality."""

    def test_get_database_info_valid_db(self, temp_database):
        """Returns table row counts when the DB is configured and populated."""
        db_info = get_database_info()

        assert "error" not in db_info
        assert "tables" in db_info
        assert "providersync" in db_info["tables"]
        assert "activity" in db_info["tables"]
        assert db_info["tables"]["providersync"] == 6
        assert db_info["total_tables"] > 0

    def test_get_database_info_unavailable(self):
        """Returns a dict gracefully when DB cannot be initialised."""
        import db_init as db_init_module

        db_init_module._db_initialized = False
        with patch.dict(os.environ, {"DATABASE_URL": "", "METADATA_DB": "/no/such/path.db"}):
            db_info = get_database_info()

        assert isinstance(db_info, dict)


# ---------------------------------------------------------------------------
# TestProviderSorting
# ---------------------------------------------------------------------------


class TestProviderSorting:
    """Test provider sorting functionality."""

    def test_sort_providers_by_priority(self):
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
        providers = {
            "strava": {"enabled": False},
            "garmin": {"enabled": False},
        }

        sorted_providers = sort_providers(providers)

        assert len(sorted_providers) == 2
        assert sorted_providers[0][0] in ["strava", "garmin"]
        assert sorted_providers[1][0] in ["strava", "garmin"]

    def test_sort_providers_empty(self):
        assert sort_providers({}) == []


# ---------------------------------------------------------------------------
# TestWebRoutes
# ---------------------------------------------------------------------------


class TestWebRoutes:
    """Test Flask web routes."""

    def test_index_route_success(self, client, temp_database):
        """Index renders the calendar/status page."""
        response = client.get("/")

        assert response.status_code == 200
        assert b"calendar-grid" in response.data
        assert b"Status" in response.data
        assert b"load-more-btn" in response.data

    def test_index_route_no_db_still_serves(self, client):
        """Index always responds 200 even with no external config — uses defaults."""
        import tracekit.appconfig as tcfg

        with patch.object(tcfg, "_FILE_PATHS", []):
            response = client.get("/")

        assert response.status_code == 200

    def test_calendar_route_success(self, client, temp_database):
        """/calendar redirects to /."""
        response = client.get("/calendar")

        assert response.status_code == 301
        assert response.headers["Location"] == "/"

    def test_api_config_route(self, client, temp_database):
        """GET /api/config returns the config stored in the DB."""
        response = client.get("/api/config")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert data["home_timezone"] == "US/Pacific"
        assert "providers" in data

    def test_api_config_put(self, client, temp_database):
        """PUT /api/config persists a new config and subsequent GET reflects it."""
        new_cfg = {**_CONFIG_DATA, "home_timezone": "US/Mountain"}

        response = client.put(
            "/api/config",
            data=json.dumps(new_cfg),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.get_json()["status"] == "saved"

        resp2 = client.get("/api/config")
        assert resp2.get_json()["home_timezone"] == "US/Mountain"

    def test_api_database_route(self, client, temp_database):
        """GET /api/database returns table counts."""
        response = client.get("/api/database")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert "tables" in data
        assert "providersync" in data["tables"]

    def test_api_recent_activity_route(self, client, temp_database):
        """GET /api/recent-activity returns a JSON object with timestamp and formatted keys."""
        response = client.get("/api/recent-activity")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert "timestamp" in data
        assert "formatted" in data
        # With the seeded test DB there may or may not be activities;
        # either None/None or a real ts + formatted string are both valid.
        if data["timestamp"] is not None:
            assert isinstance(data["timestamp"], int)
            assert isinstance(data["formatted"], str)
            assert len(data["formatted"]) > 5

    def test_health_route(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.is_json
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["app"] == "tracekit-web"

    def test_404_route(self, client):
        response = client.get("/nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestSettingsRoute
# ---------------------------------------------------------------------------


class TestSettingsRoute:
    """Tests for GET /settings and the PUT /api/config round-trip it relies on."""

    def test_settings_route_returns_200(self, client, temp_database):
        response = client.get("/settings")
        assert response.status_code == 200

    def test_settings_route_without_db_still_serves(self, client):
        """Settings page renders even when no external database is configured."""
        import tracekit.appconfig as tcfg

        with patch.object(tcfg, "_FILE_PATHS", []):
            response = client.get("/settings")
        assert response.status_code == 200

    def test_settings_has_timezone_select(self, client, temp_database):
        response = client.get("/settings")
        assert b'<select id="timezone">' in response.data

    def test_settings_timezone_preselected(self, client, temp_database):
        """The current timezone from config is pre-selected in the <select>."""
        response = client.get("/settings")
        # _CONFIG_DATA sets home_timezone = "US/Pacific"
        assert b'value="US/Pacific" selected' in response.data

    def test_settings_has_debug_toggle(self, client, temp_database):
        response = client.get("/settings")
        assert b'id="debug-toggle"' in response.data

    def test_settings_debug_toggle_reflects_config(self, client, temp_database):
        """debug=True in config → checkbox rendered as checked."""
        # _CONFIG_DATA has debug=True
        response = client.get("/settings")
        assert b'id="debug-toggle" checked' in response.data

    def test_settings_debug_unchecked_when_false(self, client, temp_database):
        """debug=False in config → checkbox rendered without checked attribute."""
        import tracekit.appconfig as tcfg
        from tracekit.appconfig import save_config

        save_config({**_CONFIG_DATA, "debug": False})
        tcfg._FILE_PATHS = []
        response = client.get("/settings")
        body = response.data.decode()
        # The checked attribute should not appear on the debug toggle
        assert 'id="debug-toggle" checked' not in body
        assert 'id="debug-toggle"' in body

    def test_settings_has_provider_list(self, client, temp_database):
        response = client.get("/settings")
        assert b'id="provider-list"' in response.data

    def test_settings_has_status_toast(self, client, temp_database):
        response = client.get("/settings")
        assert b'id="status-msg"' in response.data

    def test_settings_has_back_link_to_dashboard(self, client, temp_database):
        response = client.get("/settings")
        assert b'href="/"' in response.data

    def test_settings_providers_injected_into_page(self, client, temp_database):
        """Provider names from config are embedded as JS data in the page."""
        response = client.get("/settings")
        body = response.data.decode()
        # INITIAL_CONFIG is serialised into the page via tojson
        assert "strava" in body
        assert "garmin" in body

    def test_settings_explains_enabled_field(self, client, temp_database):
        """Page contains copy explaining what the Enabled toggle does."""
        response = client.get("/settings")
        body = response.data.decode().lower()
        assert "pull" in body and "push" in body

    def test_settings_explains_sync_equipment(self, client, temp_database):
        """Page contains copy explaining what sync_equipment does."""
        response = client.get("/settings")
        body = response.data.decode().lower()
        assert "equipment" in body

    def test_settings_explains_sync_name(self, client, temp_database):
        """Page contains copy explaining what sync_name does."""
        response = client.get("/settings")
        body = response.data.decode().lower()
        assert "name" in body

    def test_settings_explains_priority(self, client, temp_database):
        """Page contains copy explaining how priority ordering works."""
        response = client.get("/settings")
        body = response.data.decode().lower()
        assert "priority" in body and "override" in body

    def test_settings_page_includes_timezone_options(self, client, temp_database):
        """Timezone select is populated with multiple options."""
        response = client.get("/settings")
        # There should be at least ~400 timezones; check for some well-known ones
        body = response.data.decode()
        assert "US/Pacific" in body
        assert "US/Eastern" in body
        assert "Europe/London" in body

    def test_api_config_put_roundtrip(self, client, temp_database):
        """PUT /api/config persists; subsequent GET /api/config reflects the change."""
        new_cfg = {
            **_CONFIG_DATA,
            "home_timezone": "US/Mountain",
            "debug": False,
        }
        put_resp = client.put(
            "/api/config",
            data=json.dumps(new_cfg),
            content_type="application/json",
        )
        assert put_resp.status_code == 200
        assert put_resp.get_json()["status"] == "saved"

        get_resp = client.get("/api/config")
        saved = get_resp.get_json()
        assert saved["home_timezone"] == "US/Mountain"
        assert saved["debug"] is False

    def test_api_config_put_updates_providers(self, client, temp_database):
        """PUT /api/config with changed provider priority is persisted."""
        updated = {
            **_CONFIG_DATA,
            "providers": {
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_equipment": True,
                    "sync_name": True,
                },
                "garmin": {
                    "enabled": False,
                    "priority": 2,
                    "sync_equipment": False,
                    "sync_name": True,
                },
            },
        }
        client.put("/api/config", data=json.dumps(updated), content_type="application/json")

        resp = client.get("/api/config")
        providers = resp.get_json()["providers"]
        assert providers["garmin"]["enabled"] is False
        assert providers["strava"]["priority"] == 1

    def test_api_config_put_invalid_body_returns_400(self, client, temp_database):
        """PUT /api/config with non-JSON body returns 400."""
        resp = client.put("/api/config", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_api_config_put_empty_body_returns_400(self, client, temp_database):
        """PUT /api/config with a JSON array (not object) returns 400."""
        resp = client.put("/api/config", data="[]", content_type="application/json")
        assert resp.status_code == 400

    def test_settings_page_reflects_updated_config(self, client, temp_database):
        """After a PUT /api/config, GET /settings shows the new timezone pre-selected."""
        new_cfg = {**_CONFIG_DATA, "home_timezone": "Asia/Tokyo"}
        client.put("/api/config", data=json.dumps(new_cfg), content_type="application/json")

        # Force reload (new request picks up fresh load_config() call)
        import db_init as db_init_module

        db_init_module._db_initialized = False  # allow re-init against same DB

        # Re-init against the same temp DB
        import tracekit.db as tdb

        tdb._configured = False
        from tracekit.db import configure_db

        configure_db(temp_database)
        db_init_module._db_initialized = True

        response = client.get("/settings")
        body = response.data.decode()
        assert 'value="Asia/Tokyo" selected' in body


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests for the web application."""

    def test_full_application_flow(self, client, temp_database):
        """Full request flow: status page, config API, database API, health."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"calendar-grid" in response.data

        response = client.get("/api/config")
        assert response.status_code == 200
        api_cfg = response.get_json()
        assert "providers" in api_cfg
        assert api_cfg["home_timezone"] == "US/Pacific"

        response = client.get("/api/database")
        assert response.status_code == 200
        db_data = response.get_json()
        assert "tables" in db_data

        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"
