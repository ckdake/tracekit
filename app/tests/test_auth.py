"""Tests for authentication routes — signup, login, logout."""

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
def auth_database(monkeypatch):
    """Temporary SQLite database with all core tables plus the User table."""
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

    yield db_path

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signup(client, email="user@example.com", password="secret", confirm=None, follow_redirects=True):
    """POST /signup and return the response."""
    return client.post(
        "/signup",
        data={"email": email, "password": password, "confirm": confirm or password},
        follow_redirects=follow_redirects,
    )


def _login(client, email="user@example.com", password="secret", follow_redirects=True):
    """POST /login and return the response."""
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=follow_redirects,
    )


def _logout(client):
    return client.post("/logout")


def _create_and_logout(client, email="user@example.com", password="secret"):
    """Create a user via signup then immediately log out."""
    _signup(client, email=email, password=password)
    _logout(client)


# ---------------------------------------------------------------------------
# TestSignupPage
# ---------------------------------------------------------------------------


class TestSignupPage:
    """GET /signup page rendering."""

    def test_signup_get_returns_200(self, client, auth_database):
        assert client.get("/signup").status_code == 200

    def test_signup_page_has_title(self, client, auth_database):
        assert b"Sign Up" in client.get("/signup").data

    def test_signup_page_has_email_field(self, client, auth_database):
        assert b'name="email"' in client.get("/signup").data

    def test_signup_page_has_password_field(self, client, auth_database):
        assert b'name="password"' in client.get("/signup").data

    def test_signup_page_has_confirm_field(self, client, auth_database):
        assert b'name="confirm"' in client.get("/signup").data

    def test_signup_page_has_link_to_login(self, client, auth_database):
        assert b'href="/login"' in client.get("/signup").data


# ---------------------------------------------------------------------------
# TestSignupPost
# ---------------------------------------------------------------------------


class TestSignupPost:
    """POST /signup behaviour."""

    def test_successful_signup_redirects_to_home(self, client, auth_database):
        response = _signup(client, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_successful_signup_logs_user_in(self, client, auth_database):
        _signup(client, email="logged@example.com")
        assert b"logged@example.com" in client.get("/").data

    def test_signup_stores_hashed_password(self, client, auth_database):
        """The stored password_hash must not equal the plain-text password."""
        from models.user import User

        _signup(client, email="hash@example.com", password="plaintext")
        user = User.get(User.email == "hash@example.com")
        assert user.password_hash != "plaintext"
        assert len(user.password_hash) > 10

    def test_signup_missing_email_shows_error(self, client, auth_database):
        response = client.post("/signup", data={"email": "", "password": "pw", "confirm": "pw"})
        assert response.status_code == 200
        assert b"required" in response.data.lower()

    def test_signup_missing_password_shows_error(self, client, auth_database):
        response = client.post("/signup", data={"email": "a@b.com", "password": "", "confirm": ""})
        assert response.status_code == 200
        assert b"required" in response.data.lower()

    def test_signup_mismatched_passwords_shows_error(self, client, auth_database):
        response = _signup(client, password="abc", confirm="xyz")
        assert response.status_code == 200
        assert b"do not match" in response.data.lower()

    def test_signup_duplicate_email_shows_error(self, client, auth_database):
        _create_and_logout(client, email="dupe@example.com")
        response = _signup(client, email="dupe@example.com")
        assert response.status_code == 200
        assert b"already exists" in response.data.lower()

    def test_signup_preserves_email_in_form_on_error(self, client, auth_database):
        response = _signup(client, email="kept@example.com", password="a", confirm="b")
        assert b"kept@example.com" in response.data

    def test_signup_email_normalised_to_lowercase(self, client, auth_database):
        from models.user import User

        _signup(client, email="Upper@Example.COM")
        assert User.select().where(User.email == "upper@example.com").exists()


# ---------------------------------------------------------------------------
# TestLoginPage
# ---------------------------------------------------------------------------


class TestLoginPage:
    """GET /login page rendering."""

    def test_login_get_returns_200(self, client, auth_database):
        assert client.get("/login").status_code == 200

    def test_login_page_has_title(self, client, auth_database):
        assert b"Log In" in client.get("/login").data

    def test_login_page_has_email_field(self, client, auth_database):
        assert b'name="email"' in client.get("/login").data

    def test_login_page_has_password_field(self, client, auth_database):
        assert b'name="password"' in client.get("/login").data

    def test_login_page_has_link_to_signup(self, client, auth_database):
        assert b'href="/signup"' in client.get("/login").data


# ---------------------------------------------------------------------------
# TestLoginPost
# ---------------------------------------------------------------------------


class TestLoginPost:
    """POST /login behaviour."""

    def test_successful_login_redirects_to_home(self, client, auth_database):
        _create_and_logout(client)
        response = _login(client, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_successful_login_shows_email_in_header(self, client, auth_database):
        _create_and_logout(client, email="visible@example.com")
        _login(client, email="visible@example.com")
        assert b"visible@example.com" in client.get("/").data

    def test_login_wrong_password_shows_error(self, client, auth_database):
        _create_and_logout(client)
        response = _login(client, password="wrong")
        assert response.status_code == 200
        assert b"Invalid" in response.data

    def test_login_nonexistent_email_shows_error(self, client, auth_database):
        response = _login(client, email="ghost@example.com")
        assert response.status_code == 200
        assert b"Invalid" in response.data

    def test_login_empty_fields_shows_error(self, client, auth_database):
        response = client.post("/login", data={"email": "", "password": ""})
        assert response.status_code == 200
        assert b"required" in response.data.lower()

    def test_login_preserves_email_in_form_on_error(self, client, auth_database):
        response = _login(client, email="kept@example.com", password="bad")
        assert b"kept@example.com" in response.data

    def test_login_email_is_case_insensitive(self, client, auth_database):
        _create_and_logout(client, email="mixed@example.com")
        response = _login(client, email="MIXED@EXAMPLE.COM", follow_redirects=False)
        assert response.status_code == 302

    def test_login_nonexistent_user_does_not_reveal_which_field_is_wrong(self, client, auth_database):
        """Both bad email and bad password return the same generic error."""
        _create_and_logout(client)
        bad_email_resp = _login(client, email="nobody@example.com")
        bad_pass_resp = _login(client, password="wrongpassword")
        assert b"Invalid" in bad_email_resp.data
        assert b"Invalid" in bad_pass_resp.data


# ---------------------------------------------------------------------------
# TestLogout
# ---------------------------------------------------------------------------


class TestLogout:
    """POST /logout behaviour."""

    def test_logout_redirects_to_home(self, client, auth_database):
        _signup(client)
        response = _logout(client)
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_logout_clears_user_from_header(self, client, auth_database):
        _signup(client, email="bye@example.com")
        _logout(client)
        assert b"bye@example.com" not in client.get("/").data

    def test_logout_shows_login_and_signup_links_again(self, client, auth_database):
        _signup(client)
        _logout(client)
        # Unauthenticated GET / redirects to /login; follow it so we land on the
        # full login page which renders the header with login + signup links.
        response = client.get("/", follow_redirects=True)
        assert b'href="/login"' in response.data
        assert b'href="/signup"' in response.data

    def test_logout_when_not_logged_in_still_redirects(self, client, auth_database):
        response = _logout(client)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# TestHeaderAuthIcons
# ---------------------------------------------------------------------------


class TestHeaderAuthIcons:
    """Auth-related elements rendered in the shared header."""

    def test_logged_out_shows_login_link(self, client, auth_database):
        assert b'href="/login"' in client.get("/").data

    def test_logged_out_shows_signup_link(self, client, auth_database):
        # GET / redirects to /login; the login page header contains the signup link.
        assert b'href="/signup"' in client.get("/", follow_redirects=True).data

    def test_logged_out_no_logout_form(self, client, auth_database):
        assert b'action="/logout"' not in client.get("/").data

    def test_logged_in_shows_logout_form(self, client, auth_database):
        _signup(client)
        assert b'action="/logout"' in client.get("/").data

    def test_logged_in_hides_login_link(self, client, auth_database):
        _signup(client)
        assert b'href="/login"' not in client.get("/").data

    def test_logged_in_hides_signup_link(self, client, auth_database):
        _signup(client)
        assert b'href="/signup"' not in client.get("/").data

    def test_logged_in_shows_email_in_header(self, client, auth_database):
        _signup(client, email="shown@example.com")
        assert b"shown@example.com" in client.get("/").data

    def test_auth_icons_present_on_settings_page(self, client, auth_database):
        assert b'href="/login"' in client.get("/settings").data

    def test_auth_icons_present_on_privacy_page(self, client, auth_database):
        assert b'href="/login"' in client.get("/privacy").data
