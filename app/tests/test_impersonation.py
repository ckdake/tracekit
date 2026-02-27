"""Tests for the admin impersonation feature."""

import contextlib
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
def db_with_users(monkeypatch):
    """Temp SQLite DB with all tables created, no users seeded."""
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
    db = tdb.get_db()
    db.connect(reuse_if_open=True)
    migrate_tables(get_all_models())

    from models.user import User

    db.create_tables([User])
    save_config({"home_timezone": "UTC", "debug": False, "providers": {}})

    yield db

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def users(db_with_users):
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
    """Flask test client authenticated as admin (user id=1)."""
    admin, _ = users
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(admin.id)
            sess["_fresh"] = True
        yield c


@pytest.fixture
def user_client(users):
    """Flask test client authenticated as the regular (non-admin) user."""
    _, regular = users
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(regular.id)
            sess["_fresh"] = True
        yield c


# ---------------------------------------------------------------------------
# TestAllowImpersonationModel
# ---------------------------------------------------------------------------


class TestAllowImpersonationModel:
    """User.allow_impersonation defaults and persistence."""

    def test_defaults_to_false(self, users):
        _, regular = users
        assert regular.allow_impersonation is False

    def test_can_be_set_true(self, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        regular_refreshed = User.get_by_id(regular.id)
        assert regular_refreshed.allow_impersonation is True


# ---------------------------------------------------------------------------
# TestAllowImpersonationAPI
# ---------------------------------------------------------------------------


class TestAllowImpersonationAPI:
    """POST /api/user/allow-impersonation endpoint."""

    def test_enable_sets_flag(self, user_client, users):
        from models.user import User

        _, regular = users
        user_client.post(
            "/api/user/allow-impersonation",
            json={"enabled": True},
            content_type="application/json",
        )
        assert User.get_by_id(regular.id).allow_impersonation is True

    def test_disable_clears_flag(self, user_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        user_client.post(
            "/api/user/allow-impersonation",
            json={"enabled": False},
            content_type="application/json",
        )
        assert User.get_by_id(regular.id).allow_impersonation is False

    def test_returns_enabled_value(self, user_client):
        resp = user_client.post(
            "/api/user/allow-impersonation",
            json={"enabled": True},
            content_type="application/json",
        )
        import json

        assert json.loads(resp.data)["enabled"] is True

    def test_missing_enabled_field_returns_400(self, user_client):
        resp = user_client.post(
            "/api/user/allow-impersonation",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_no_body_returns_400(self, user_client):
        resp = user_client.post("/api/user/allow-impersonation")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestSettingsPageToggle
# ---------------------------------------------------------------------------


class TestSettingsPageToggle:
    """Settings page renders the allow-impersonation toggle."""

    def test_toggle_present_on_settings_page(self, user_client):
        resp = user_client.get("/settings")
        assert b"allow-impersonation-toggle" in resp.data

    def test_toggle_unchecked_by_default(self, user_client):
        resp = user_client.get("/settings")
        # The checked attribute should not be present on this toggle
        html = resp.data.decode()
        idx = html.index("allow-impersonation-toggle")
        snippet = html[idx : idx + 200]
        assert "checked" not in snippet

    def test_toggle_checked_when_enabled(self, user_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        resp = user_client.get("/settings")
        html = resp.data.decode()
        idx = html.index("allow-impersonation-toggle")
        snippet = html[idx : idx + 200]
        assert "checked" in snippet


# ---------------------------------------------------------------------------
# TestImpersonateRoute
# ---------------------------------------------------------------------------


class TestImpersonateRoute:
    """POST /admin/users/<id>/impersonate."""

    def test_requires_admin(self, user_client, users):
        _, regular = users
        resp = user_client.post(f"/admin/users/{regular.id}/impersonate")
        assert resp.status_code == 403

    def test_requires_target_opt_in(self, admin_client, users):
        _, regular = users
        # allow_impersonation is False by default
        resp = admin_client.post(f"/admin/users/{regular.id}/impersonate")
        assert resp.status_code == 403

    def test_nonexistent_user_returns_404(self, admin_client):
        resp = admin_client.post("/admin/users/99999/impersonate")
        assert resp.status_code == 404

    def test_sets_is_impersonating_in_session(self, admin_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        admin_client.post(f"/admin/users/{regular.id}/impersonate")
        with admin_client.session_transaction() as sess:
            assert sess.get("is_impersonating") is True

    def test_stores_original_user_id_in_session(self, admin_client, users):
        from models.user import User

        admin, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        admin_client.post(f"/admin/users/{regular.id}/impersonate")
        with admin_client.session_transaction() as sess:
            assert sess.get("original_user_id") == admin.id

    def test_redirects_to_index(self, admin_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        resp = admin_client.post(f"/admin/users/{regular.id}/impersonate")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"

    def test_subsequent_requests_use_target_identity(self, admin_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        admin_client.post(f"/admin/users/{regular.id}/impersonate")
        resp = admin_client.get("/", follow_redirects=True)
        assert b"user@example.com" in resp.data
        assert b"admin@example.com" not in resp.data


# ---------------------------------------------------------------------------
# TestEndImpersonation
# ---------------------------------------------------------------------------


class TestEndImpersonation:
    """POST /admin/impersonation/end."""

    def _start_impersonation(self, admin_client, users):
        """Helper: enable opt-in and kick off impersonation."""
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        admin_client.post(f"/admin/users/{regular.id}/impersonate")

    def test_without_impersonation_session_returns_400(self, user_client):
        resp = user_client.post("/admin/impersonation/end")
        assert resp.status_code == 400

    def test_redirects_to_admin(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        resp = admin_client.post("/admin/impersonation/end")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/admin"

    def test_clears_is_impersonating_from_session(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        admin_client.post("/admin/impersonation/end")
        with admin_client.session_transaction() as sess:
            assert "is_impersonating" not in sess

    def test_clears_original_user_id_from_session(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        admin_client.post("/admin/impersonation/end")
        with admin_client.session_transaction() as sess:
            assert "original_user_id" not in sess

    def test_restores_admin_identity(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        admin_client.post("/admin/impersonation/end")
        resp = admin_client.get("/", follow_redirects=True)
        assert b"admin@example.com" in resp.data

    def test_admin_can_access_admin_page_after_end(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        admin_client.post("/admin/impersonation/end")
        resp = admin_client.get("/admin")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestImpersonationHeader
# ---------------------------------------------------------------------------


class TestImpersonationHeader:
    """Header behaviour during and outside of impersonation."""

    def _start_impersonation(self, admin_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        admin_client.post(f"/admin/users/{regular.id}/impersonate")

    def test_badge_shown_during_impersonation(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        resp = admin_client.get("/", follow_redirects=True)
        assert b"impersonation-badge" in resp.data

    def test_badge_not_shown_normally(self, admin_client):
        resp = admin_client.get("/", follow_redirects=True)
        assert b"impersonation-badge" not in resp.data

    def test_end_impersonation_form_shown_during_impersonation(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        resp = admin_client.get("/", follow_redirects=True)
        assert b'action="/admin/impersonation/end"' in resp.data

    def test_normal_logout_form_shown_when_not_impersonating(self, admin_client):
        resp = admin_client.get("/", follow_redirects=True)
        assert b'action="/logout"' in resp.data

    def test_normal_logout_form_absent_during_impersonation(self, admin_client, users):
        self._start_impersonation(admin_client, users)
        resp = admin_client.get("/", follow_redirects=True)
        assert b'action="/logout"' not in resp.data


# ---------------------------------------------------------------------------
# TestAdminPageImpersonateButton
# ---------------------------------------------------------------------------


class TestAdminPageImpersonateButton:
    """Impersonate button visibility on the /admin user table."""

    def test_button_shown_when_user_opted_in(self, admin_client, users):
        from models.user import User

        _, regular = users
        User.update(allow_impersonation=True).where(User.id == regular.id).execute()
        resp = admin_client.get("/admin")
        assert b"Impersonate" in resp.data

    def test_button_not_shown_without_opt_in(self, admin_client, users):
        # allow_impersonation is False by default
        resp = admin_client.get("/admin")
        assert b"Impersonate" not in resp.data

    def test_button_not_shown_for_admin_even_if_opted_in(self, admin_client, users):
        from models.user import User

        admin, _ = users
        # Force allow_impersonation=True on the admin user itself
        User.update(allow_impersonation=True).where(User.id == admin.id).execute()
        # Ensure the regular user has NOT opted in so any "Impersonate" text is from admin
        resp = admin_client.get("/admin")
        assert b"Impersonate" not in resp.data
