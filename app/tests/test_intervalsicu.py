"""Tests for Intervals.icu OAuth routes and webhook endpoint."""

import contextlib
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ICU_CONFIG = {
    "home_timezone": "UTC",
    "debug": False,
    "providers": {
        "intervalsicu": {
            "enabled": True,
            "use_personal_credentials": False,
            "client_id": "",
            "client_secret": "",
            "access_token": "",
            "athlete_id": "",
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
    """Temporary SQLite database seeded with a minimal Intervals.icu config."""
    import tracekit.appconfig as tcfg
    import tracekit.db as tdb
    from tracekit.appconfig import save_config
    from tracekit.database import get_all_models, migrate_tables
    from tracekit.db import configure_db

    monkeypatch.setattr(tcfg, "_FILE_PATHS", [])
    monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
    monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)

    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        db_path = f.name

    tdb._configured = False
    configure_db(db_path)
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())
    save_config(_ICU_CONFIG)

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
# Unit tests: _get_intervalsicu_client_credentials helper
# ---------------------------------------------------------------------------


class TestGetIntervalsICUClientCredentials:
    """Credential resolution logic in auth_intervalsicu."""

    def test_personal_creds_returned_when_flag_on(self):
        from routes.auth_intervalsicu import _get_intervalsicu_client_credentials

        cfg = {
            "use_personal_credentials": True,
            "client_id": "personal_id",
            "client_secret": "personal_secret",
        }
        cid, csec = _get_intervalsicu_client_credentials(cfg)
        assert cid == "personal_id"
        assert csec == "personal_secret"

    def test_system_env_creds_used_when_flag_off(self, monkeypatch):
        from routes.auth_intervalsicu import _get_intervalsicu_client_credentials

        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")
        cfg = {
            "use_personal_credentials": False,
            "client_id": "personal_id",
            "client_secret": "personal_secret",
        }
        cid, csec = _get_intervalsicu_client_credentials(cfg)
        assert cid == "sys_id"
        assert csec == "sys_secret"

    def test_falls_back_to_config_when_no_env_and_flag_off(self, monkeypatch):
        from routes.auth_intervalsicu import _get_intervalsicu_client_credentials

        monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
        monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)
        cfg = {
            "use_personal_credentials": False,
            "client_id": "saved_id",
            "client_secret": "saved_secret",
        }
        cid, csec = _get_intervalsicu_client_credentials(cfg)
        assert cid == "saved_id"
        assert csec == "saved_secret"

    def test_returns_empty_when_nothing_configured(self, monkeypatch):
        from routes.auth_intervalsicu import _get_intervalsicu_client_credentials

        monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
        monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)
        cfg = {"use_personal_credentials": False, "client_id": "", "client_secret": ""}
        cid, csec = _get_intervalsicu_client_credentials(cfg)
        assert cid == ""
        assert csec == ""


# ---------------------------------------------------------------------------
# Route tests: /api/auth/intervalsicu/authorize
# ---------------------------------------------------------------------------


class TestIntervalsICUAuthorizeRoute:
    """Tests for GET /api/auth/intervalsicu/authorize."""

    def test_returns_400_without_any_credentials(self, client, monkeypatch):
        """No system env vars and no personal creds → configuration error."""
        monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
        monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)
        resp = client.get("/api/auth/intervalsicu/authorize")
        assert resp.status_code == 400
        body = resp.data.decode()
        assert "not configured" in body.lower() or "configuration error" in body.lower()

    def test_redirects_to_intervalsicu_with_system_credentials(self, client, monkeypatch):
        """Valid system credentials cause a redirect to Intervals.icu OAuth endpoint."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")
        resp = client.get("/api/auth/intervalsicu/authorize")
        assert resp.status_code == 302
        assert "intervals.icu" in resp.headers["Location"]

    def test_authorize_url_contains_client_id(self, client, monkeypatch):
        """The redirect URL contains the client_id."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "myapp123")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "secret")
        resp = client.get("/api/auth/intervalsicu/authorize")
        assert "myapp123" in resp.headers["Location"]

    def test_authorize_url_contains_scope(self, client, monkeypatch):
        """The redirect URL contains the required scopes."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sec")
        resp = client.get("/api/auth/intervalsicu/authorize")
        assert "ACTIVITY" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Route tests: /api/auth/intervalsicu/callback
# ---------------------------------------------------------------------------


class TestIntervalsICUCallbackRoute:
    """Tests for GET /api/auth/intervalsicu/callback."""

    def test_error_param_shows_failure_page(self, client):
        """Intervals.icu returning error=access_denied is shown as a failure."""
        resp = client.get("/api/auth/intervalsicu/callback?error=access_denied")
        assert resp.status_code == 200
        assert b"authorization denied" in resp.data.lower()

    def test_missing_code_shows_failure_page(self, client):
        """No code param returns failure page."""
        resp = client.get("/api/auth/intervalsicu/callback")
        assert resp.status_code == 200
        assert b"no authorization code" in resp.data.lower()

    def test_callback_fails_without_any_credentials(self, client, monkeypatch):
        """Token exchange fails cleanly when no credentials are configured at all."""
        monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
        monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)
        resp = client.get("/api/auth/intervalsicu/callback?code=test_code")
        assert resp.status_code == 200
        assert b"not configured" in resp.data.lower()

    def test_callback_success_with_token_exchange(self, client, monkeypatch):
        """Successful token exchange saves tokens and shows success page."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "athlete": {"id": "12345"},
        }

        with patch("requests.post", return_value=mock_response):
            resp = client.get("/api/auth/intervalsicu/callback?code=test_code")

        assert resp.status_code == 200
        assert b"successful" in resp.data.lower()

    def test_callback_handles_failed_token_exchange(self, client, monkeypatch):
        """Non-OK token exchange response shows failure page."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.text = "invalid_grant"

        with patch("requests.post", return_value=mock_response):
            resp = client.get("/api/auth/intervalsicu/callback?code=bad_code")

        assert resp.status_code == 200
        body = resp.data.decode()
        assert "failed" in body.lower() or "error" in body.lower()

    def test_callback_handles_missing_access_token(self, client, monkeypatch):
        """Token exchange response with no access_token shows failure page."""
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {}  # no access_token

        with patch("requests.post", return_value=mock_response):
            resp = client.get("/api/auth/intervalsicu/callback?code=test_code")

        assert resp.status_code == 200
        assert b"no access token" in resp.data.lower()


# ---------------------------------------------------------------------------
# Webhook endpoint tests: /api/intervalsicu/webhook
# ---------------------------------------------------------------------------


class TestIntervalsICUWebhook:
    """Tests for POST /api/intervalsicu/webhook."""

    def test_webhook_returns_200_for_valid_payload(self, client):
        """A valid payload always returns 200 (webhook must not retry on app errors)."""
        with patch("routes.intervalsicu_webhook._handle_event"):
            resp = client.post(
                "/api/intervalsicu/webhook",
                json={"athlete_id": "123", "id": "456", "action": "created"},
            )
        assert resp.status_code == 200

    def test_webhook_returns_400_for_invalid_json(self, client):
        """Non-JSON body returns 400."""
        resp = client.post(
            "/api/intervalsicu/webhook",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_webhook_returns_400_for_non_dict_payload(self, client):
        """JSON array body returns 400."""
        resp = client.post(
            "/api/intervalsicu/webhook",
            json=["not", "a", "dict"],
        )
        assert resp.status_code == 400

    def test_webhook_is_publicly_accessible(self, temp_database):
        """Webhook endpoint must not require authentication."""
        app.config["TESTING"] = True
        with app.test_client() as c:
            with patch("routes.intervalsicu_webhook._handle_event"):
                resp = c.post(
                    "/api/intervalsicu/webhook",
                    json={"athlete_id": "99", "id": "77", "action": "deleted"},
                )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Settings page: system_credentials includes intervalsicu
# ---------------------------------------------------------------------------


class TestSettingsIntervalsICUSystemCredentials:
    """The /settings page passes system_credentials.intervalsicu boolean."""

    def test_settings_shows_no_system_creds_when_env_absent(self, client, monkeypatch):
        monkeypatch.delenv("INTERVALSICU_CLIENT_ID", raising=False)
        monkeypatch.delenv("INTERVALSICU_CLIENT_SECRET", raising=False)

        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert '"intervalsicu": false' in body or '"intervalsicu":false' in body

    def test_settings_shows_system_creds_when_env_present(self, client, monkeypatch):
        monkeypatch.setenv("INTERVALSICU_CLIENT_ID", "sys_id")
        monkeypatch.setenv("INTERVALSICU_CLIENT_SECRET", "sys_secret")

        resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert '"intervalsicu": true' in body or '"intervalsicu":true' in body
