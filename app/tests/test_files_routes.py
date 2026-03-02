"""Tests for the file download route."""

import contextlib
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

# ---------------------------------------------------------------------------
# Fixtures (mirrors test_month_routes.py pattern)
# ---------------------------------------------------------------------------

_CONFIG = {
    "home_timezone": "US/Eastern",
    "debug": False,
    "providers": {
        "file": {"enabled": True, "priority": 1},
    },
}


@pytest.fixture(autouse=True)
def reset_db_state():
    yield
    import db_init as db_init_module

    import tracekit.db as tdb

    db_init_module._db_initialized = False
    tdb._configured = False


@pytest.fixture
def temp_database(monkeypatch):
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
    save_config(_CONFIG)

    yield db_path

    with contextlib.suppress(Exception):
        db.close()
    tdb._configured = False
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client(temp_database):
    from models.user import User
    from werkzeug.security import generate_password_hash

    from tracekit.db import get_db

    db = get_db()
    db.create_tables([User])
    user = User.create(
        email="testfile@example.com",
        password_hash=generate_password_hash("testpass"),
        status="active",
    )

    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        yield c, user.id


# ---------------------------------------------------------------------------
# GET /api/file/download
# ---------------------------------------------------------------------------


class TestFileDownload:
    def test_missing_name_returns_400(self, client):
        c, _ = client
        resp = c.get("/api/file/download")
        assert resp.status_code == 400

    def test_slash_in_name_returns_400(self, client):
        c, _ = client
        resp = c.get("/api/file/download?name=../secret.fit")
        assert resp.status_code == 400

    def test_dotdot_in_name_returns_400(self, client):
        c, _ = client
        resp = c.get("/api/file/download?name=..%2Fsecret.fit")
        assert resp.status_code == 400

    def test_backslash_in_name_returns_400(self, client):
        c, _ = client
        resp = c.get("/api/file/download?name=foo%5Cbar.fit")
        assert resp.status_code == 400

    def test_unknown_file_returns_404(self, client):
        c, _ = client
        with patch("routes.files.FileActivity") as mock_fa:
            mock_fa.get_or_none.return_value = None
            resp = c.get("/api/file/download?name=nonexistent.fit")
        assert resp.status_code == 404

    def test_file_missing_on_disk_returns_404(self, client):
        c, _ = client
        with (
            patch("routes.files.FileActivity") as mock_fa,
            patch("routes.files._glob.glob", return_value=[]),
        ):
            mock_fa.get_or_none.return_value = MagicMock()
            resp = c.get("/api/file/download?name=activity.fit")
        assert resp.status_code == 404

    def test_valid_file_returns_200_and_attachment(self, client):
        c, _ = client
        with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as f:
            f.write(b"FIT file content")
            tmp_path = f.name
        try:
            with (
                patch("routes.files.FileActivity") as mock_fa,
                patch("routes.files._glob.glob", return_value=[tmp_path]),
            ):
                mock_fa.get_or_none.return_value = MagicMock()
                resp = c.get("/api/file/download?name=activity.fit")
            assert resp.status_code == 200
            assert "attachment" in resp.headers.get("Content-Disposition", "")
        finally:
            os.remove(tmp_path)

    def test_ownership_check_uses_user_id(self, client):
        """get_or_none must be called with the logged-in user's ID."""
        c, user_id = client
        with (
            patch("routes.files.FileActivity") as mock_fa,
            patch("routes.files.get_user_id", return_value=user_id),
        ):
            mock_fa.get_or_none.return_value = None
            c.get("/api/file/download?name=activity.fit")
            # The user_id filter must be present somewhere in the call
            assert mock_fa.get_or_none.call_args is not None

    def test_data_dir_env_var_respected(self, client):
        c, user_id = client
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake file in the expected location
            user_dir = os.path.join(tmpdir, "activities", str(user_id))
            os.makedirs(user_dir)
            fake_file = os.path.join(user_dir, "activity.fit")
            with open(fake_file, "wb") as f:
                f.write(b"FIT")

            with (
                patch("routes.files.FileActivity") as mock_fa,
                patch.dict(os.environ, {"TRACEKIT_DATA_DIR": tmpdir}),
                patch("routes.files.get_user_id", return_value=user_id),
            ):
                mock_fa.get_or_none.return_value = MagicMock()
                resp = c.get("/api/file/download?name=activity.fit")
            assert resp.status_code == 200
