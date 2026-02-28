"""Tests for system-level API credential fallback (Strava + RideWithGPS)."""

import contextlib
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

# ---------------------------------------------------------------------------
# Fixtures (mirrors test_web_app.py patterns)
# ---------------------------------------------------------------------------

_STRAVA_CONFIG = {
    "home_timezone": "UTC",
    "debug": False,
    "providers": {
        "strava": {
            "enabled": True,
            "use_personal_credentials": False,
            "client_id": "",
            "client_secret": "",
            "access_token": "",
            "refresh_token": "",
            "token_expires": "0",
        },
    },
}


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset DB initialisation state between tests to prevent leakage."""
    yield
    import db_init as db_init_module

    import tracekit.db as tdb

    db_init_module._db_initialized = False
    tdb._configured = False


@pytest.fixture
def temp_database(monkeypatch):
    """Temporary SQLite database seeded with a minimal Strava config."""
    import tracekit.appconfig as tcfg
    import tracekit.db as tdb
    from tracekit.appconfig import save_config
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db

    monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("RIDEWITHGPS_KEY", raising=False)

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())
    save_config(_STRAVA_CONFIG)

    yield db_path

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client(temp_database):
    """Authenticated Flask test client."""
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


# ---------------------------------------------------------------------------
# Unit tests: _get_strava_client_credentials helper
# ---------------------------------------------------------------------------


class TestGetStravaClientCredentials:
    """Credential resolution logic in auth_strava."""

    def test_personal_creds_returned_when_flag_on(self):
        from routes.auth_strava import _get_strava_client_credentials

        cfg = {
            "use_personal_credentials": True,
            "client_id": "personal_id",
            "client_secret": "personal_secret",
        }
        cid, csec = _get_strava_client_credentials(cfg)
        assert cid == "personal_id"
        assert csec == "personal_secret"

    def test_system_env_creds_used_when_flag_off(self, monkeypatch):
        from routes.auth_strava import _get_strava_client_credentials

        monkeypatch.setenv("STRAVA_CLIENT_ID", "sys_id")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "sys_secret")
        cfg = {
            "use_personal_credentials": False,
            "client_id": "personal_id",
            "client_secret": "personal_secret",
        }
        cid, csec = _get_strava_client_credentials(cfg)
        assert cid == "sys_id"
        assert csec == "sys_secret"

    def test_falls_back_to_config_when_no_env_and_flag_off(self, monkeypatch):
        from routes.auth_strava import _get_strava_client_credentials

        monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
        monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
        cfg = {
            "use_personal_credentials": False,
            "client_id": "saved_id",
            "client_secret": "saved_secret",
        }
        cid, csec = _get_strava_client_credentials(cfg)
        assert cid == "saved_id"
        assert csec == "saved_secret"

    def test_returns_empty_when_nothing_configured(self, monkeypatch):
        from routes.auth_strava import _get_strava_client_credentials

        monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
        monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
        cfg = {"use_personal_credentials": False, "client_id": "", "client_secret": ""}
        cid, csec = _get_strava_client_credentials(cfg)
        assert cid == ""
        assert csec == ""


# ---------------------------------------------------------------------------
# Route tests: /api/auth/strava/authorize
# ---------------------------------------------------------------------------


class TestStravaAuthorizeRoute:
    """Tests for GET /api/auth/strava/authorize."""

    def test_returns_400_without_any_credentials(self, client, monkeypatch):
        """No system env vars and no personal creds → configuration error."""
        monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
        monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
        resp = client.get("/api/auth/strava/authorize")
        assert resp.status_code == 400
        body = resp.data.decode()
        assert "not configured" in body.lower() or "configuration error" in body.lower()

    def test_redirects_to_strava_with_system_credentials(self, client, monkeypatch):
        """Valid system credentials cause a redirect to Strava's OAuth endpoint."""
        monkeypatch.setenv("STRAVA_CLIENT_ID", "123456")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "sys_secret")
        resp = client.get("/api/auth/strava/authorize")
        assert resp.status_code == 302
        assert "strava.com" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Route tests: /api/auth/strava/callback
# ---------------------------------------------------------------------------


class TestStravaCallbackRoute:
    """Tests for GET /api/auth/strava/callback."""

    def test_error_param_shows_failure_page(self, client):
        """Strava returning error=access_denied is shown as a failure."""
        resp = client.get("/api/auth/strava/callback?error=access_denied")
        assert resp.status_code == 200
        assert b"authorization denied" in resp.data.lower()

    def test_missing_code_shows_failure_page(self, client):
        """No code param returns failure page."""
        resp = client.get("/api/auth/strava/callback")
        assert resp.status_code == 200
        assert b"no authorization code" in resp.data.lower()

    def test_callback_uses_system_credentials_for_token_exchange(self, client, monkeypatch):
        """Token exchange is performed with system client_id/secret when flag is off."""
        monkeypatch.setenv("STRAVA_CLIENT_ID", "123456")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "sys_secret")

        mock_token = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": 9999999999,
        }

        with patch("stravalib.client.Client") as mockclient:
            mock_instance = MagicMock()
            mock_instance.exchange_code_for_token.return_value = mock_token
            mockclient.return_value = mock_instance

            resp = client.get("/api/auth/strava/callback?code=test_code")

        assert resp.status_code == 200
        assert b"successful" in resp.data.lower()
        mock_instance.exchange_code_for_token.assert_called_once_with(
            client_id=123456,
            client_secret="sys_secret",
            code="test_code",
        )

    def test_callback_fails_without_any_credentials(self, client, monkeypatch):
        """Token exchange fails cleanly when no credentials are configured at all."""
        monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
        monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)

        resp = client.get("/api/auth/strava/callback?code=test_code")
        assert resp.status_code == 200
        assert b"not configured" in resp.data.lower()


# ---------------------------------------------------------------------------
# Settings page: system_credentials context variable
# ---------------------------------------------------------------------------


class TestSettingsSystemCredentialsContext:
    """The /settings page passes system_credentials booleans to the template."""

    def test_settings_shows_no_system_creds_when_env_absent(self, client, monkeypatch):
        """SYSTEM_CREDENTIALS is {strava: false, ridewithgps: false} when env absent."""
        monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
        monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("RIDEWITHGPS_KEY", raising=False)

        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.data.decode()
        # SYSTEM_CREDENTIALS is injected as a JSON literal in the page
        assert '"strava": false' in body or '"strava":false' in body

    def test_settings_shows_system_creds_when_env_present(self, client, monkeypatch):
        """SYSTEM_CREDENTIALS is {strava: true, ...} when env vars are set."""
        monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
        monkeypatch.setenv("STRAVA_CLIENT_SECRET", "abc")
        monkeypatch.setenv("RIDEWITHGPS_CLIENT_ID", "rwgps_client_id")
        monkeypatch.setenv("RIDEWITHGPS_CLIENT_SECRET", "rwgps_client_secret")

        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert '"strava": true' in body or '"strava":true' in body
        assert '"ridewithgps": true' in body or '"ridewithgps":true' in body
