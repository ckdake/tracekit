"""Tests for the system-level provider visibility feature."""

import contextlib
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

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
def db(monkeypatch):
    """Temporary SQLite DB with all tables created."""
    import tracekit.appconfig as tcfg
    import tracekit.db as tdb
    from tracekit.appconfig import save_config
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db

    monkeypatch.setattr(tcfg, "_FILE_PATHS", [])

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    database = tdb.get_db()
    database.connect(reuse_if_open=True)
    migrate_tables(get_all_models())

    from models.user import User

    database.create_tables([User])
    save_config({"home_timezone": "UTC", "debug": False, "providers": {}})

    yield database

    with contextlib.suppress(Exception):
        database.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def users(db):
    """Seed admin (id=1) and a regular user (id=2). Returns (admin, user)."""
    from models.user import User
    from werkzeug.security import generate_password_hash

    admin = User.create(
        email="admin@example.com",
        password_hash=generate_password_hash("adminpass"),
        status="active",
    )
    regular = User.create(
        email="user@example.com",
        password_hash=generate_password_hash("userpass"),
        status="active",
    )
    return admin, regular


@pytest.fixture
def admin_client(users):
    """Flask test client authenticated as admin."""
    admin, _ = users
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(admin.id)
            sess["_fresh"] = True
        yield c


@pytest.fixture
def user_client(users):
    """Flask test client authenticated as the regular user."""
    _, regular = users
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(regular.id)
            sess["_fresh"] = True
        yield c


# ---------------------------------------------------------------------------
# TestGetSystemProviders — model-level defaults and persistence
# ---------------------------------------------------------------------------


class TestGetSystemProviders:
    """get_system_providers() returns correct defaults and reads persisted data."""

    def test_defaults_all_providers_enabled(self, db):
        from tracekit.appconfig import ALL_PROVIDERS, get_system_providers

        result = get_system_providers()
        for provider in ALL_PROVIDERS:
            assert result[provider] is True

    def test_returns_all_known_providers(self, db):
        from tracekit.appconfig import ALL_PROVIDERS, get_system_providers

        result = get_system_providers()
        assert set(result.keys()) == set(ALL_PROVIDERS)

    def test_persisted_disabled_state_is_read_back(self, db):
        from tracekit.appconfig import get_system_providers, save_system_providers

        save_system_providers(
            {
                "strava": False,
                "garmin": True,
                "ridewithgps": True,
                "spreadsheet": False,
                "file": True,
                "stravajson": False,
            }
        )
        result = get_system_providers()
        assert result["strava"] is False
        assert result["garmin"] is True
        assert result["spreadsheet"] is False
        assert result["stravajson"] is False

    def test_providers_absent_from_stored_value_default_to_enabled(self, db):
        from tracekit.appconfig import get_system_providers, save_system_providers

        # Only persist a subset — missing providers should default to True
        save_system_providers({"strava": False})
        result = get_system_providers()
        assert result["strava"] is False
        assert result["garmin"] is True
        assert result["ridewithgps"] is True


# ---------------------------------------------------------------------------
# TestSaveSystemProviders — persistence
# ---------------------------------------------------------------------------


class TestSaveSystemProviders:
    """save_system_providers() persists values and is idempotent."""

    def test_save_and_reload(self, db):
        from tracekit.appconfig import get_system_providers, save_system_providers

        payload = {p: False for p in ["strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"]}
        save_system_providers(payload)
        result = get_system_providers()
        for p in payload:
            assert result[p] is False

    def test_second_save_overwrites_first(self, db):
        from tracekit.appconfig import get_system_providers, save_system_providers

        save_system_providers(
            {
                "strava": False,
                "garmin": True,
                "ridewithgps": True,
                "spreadsheet": True,
                "file": True,
                "stravajson": True,
            }
        )
        save_system_providers(
            {
                "strava": True,
                "garmin": False,
                "ridewithgps": True,
                "spreadsheet": True,
                "file": True,
                "stravajson": True,
            }
        )
        result = get_system_providers()
        assert result["strava"] is True
        assert result["garmin"] is False


# ---------------------------------------------------------------------------
# TestToggleProviderEndpoint — POST /admin/providers/<provider>/toggle
# ---------------------------------------------------------------------------


class TestToggleProviderEndpoint:
    """POST /admin/providers/<provider>/toggle requires admin, toggles state."""

    def test_requires_admin(self, user_client):
        resp = user_client.post("/admin/providers/strava/toggle")
        assert resp.status_code == 403

    def test_unauthenticated_is_rejected(self, db):
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post("/admin/providers/strava/toggle")
        assert resp.status_code in (302, 403)

    def test_unknown_provider_returns_400(self, admin_client):
        resp = admin_client.post("/admin/providers/notreal/toggle")
        assert resp.status_code == 400

    def test_toggle_disables_enabled_provider(self, admin_client, db):
        from tracekit.appconfig import get_system_providers

        # Strava defaults to enabled — toggling should disable it
        resp = admin_client.post("/admin/providers/strava/toggle")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["enabled"] is False
        assert get_system_providers()["strava"] is False

    def test_toggle_enables_disabled_provider(self, admin_client, db):
        from tracekit.appconfig import get_system_providers, save_system_providers

        save_system_providers(
            {p: (p != "strava") for p in ["strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"]}
        )
        resp = admin_client.post("/admin/providers/strava/toggle")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["enabled"] is True
        assert get_system_providers()["strava"] is True

    def test_response_contains_provider_name(self, admin_client):
        resp = admin_client.post("/admin/providers/garmin/toggle")
        data = json.loads(resp.data)
        assert data["provider"] == "garmin"

    def test_toggle_is_idempotent_over_two_calls(self, admin_client, db):
        from tracekit.appconfig import get_system_providers

        admin_client.post("/admin/providers/strava/toggle")  # disable
        admin_client.post("/admin/providers/strava/toggle")  # re-enable
        assert get_system_providers()["strava"] is True


# ---------------------------------------------------------------------------
# TestAdminPageProviderCard — GET /admin renders providers card
# ---------------------------------------------------------------------------


class TestAdminPageProviderCard:
    """Admin page shows the provider visibility card."""

    def test_providers_card_present(self, admin_client):
        resp = admin_client.get("/admin")
        assert b"provider-toggle-strava" in resp.data

    def test_all_providers_shown(self, admin_client):
        from tracekit.appconfig import ALL_PROVIDERS

        resp = admin_client.get("/admin")
        for provider in ALL_PROVIDERS:
            assert provider.encode() in resp.data

    def test_enabled_provider_has_checked_attribute(self, admin_client):
        resp = admin_client.get("/admin")
        html = resp.data.decode()
        idx = html.index("provider-toggle-strava")
        snippet = html[idx : idx + 200]
        assert "checked" in snippet

    def test_disabled_provider_lacks_checked_attribute(self, admin_client, db):
        from tracekit.appconfig import save_system_providers

        save_system_providers(
            {p: (p != "strava") for p in ["strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"]}
        )
        resp = admin_client.get("/admin")
        html = resp.data.decode()
        idx = html.index("provider-toggle-strava")
        snippet = html[idx : idx + 200]
        assert "checked" not in snippet

    def test_non_admin_cannot_access_admin_page(self, user_client):
        resp = user_client.get("/admin")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestSettingsPageEnabledProviders — ENABLED_PROVIDERS injected into page
# ---------------------------------------------------------------------------


class TestSettingsPageEnabledProviders:
    """Settings page receives the correct ENABLED_PROVIDERS list."""

    def test_enabled_providers_var_present(self, user_client):
        resp = user_client.get("/settings")
        assert b"ENABLED_PROVIDERS" in resp.data

    def test_all_providers_visible_by_default(self, user_client):
        from tracekit.appconfig import ALL_PROVIDERS

        resp = user_client.get("/settings")
        html = resp.data.decode()
        # Find the ENABLED_PROVIDERS JS array
        start = html.index("ENABLED_PROVIDERS")
        snippet = html[start : start + 300]
        for provider in ALL_PROVIDERS:
            assert provider in snippet

    def test_disabled_provider_excluded_from_enabled_providers(self, user_client, db):
        from tracekit.appconfig import save_system_providers

        save_system_providers(
            {p: (p != "spreadsheet") for p in ["strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"]}
        )
        resp = user_client.get("/settings")
        html = resp.data.decode()
        start = html.index("ENABLED_PROVIDERS")
        # The JS array ends at the first semicolon after the variable declaration
        end = html.index(";", start)
        snippet = html[start:end]
        assert "spreadsheet" not in snippet
        assert "strava" in snippet
