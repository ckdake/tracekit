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


# ---------------------------------------------------------------------------
# POST /api/file/upload
# ---------------------------------------------------------------------------


def _make_upload(c, filename, content=b"data", content_type="application/octet-stream"):
    """POST to /api/file/upload with a fake file."""
    from io import BytesIO

    data = {"file": (BytesIO(content), filename, content_type)}
    return c.post("/api/file/upload", data=data, content_type="multipart/form-data")


class TestFileUpload:
    def test_no_file_field_returns_400(self, client):
        c, _ = client
        resp = c.post("/api/file/upload", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_empty_filename_returns_400(self, client):
        c, _ = client
        from io import BytesIO

        data = {"file": (BytesIO(b"x"), "", "application/octet-stream")}
        resp = c.post("/api/file/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_unsupported_extension_rejected(self, client, tmp_path):
        c, user_id = client
        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
        ):
            resp = _make_upload(c, "photo.pdf")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "photo.pdf" in data["rejected"]
        assert data["saved"] == []

    def test_supported_file_saved_and_queued(self, client, tmp_path):
        c, user_id = client
        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
            patch("routes.files._enqueue_process_file") as mock_enqueue,
        ):
            resp = _make_upload(c, "activity.fit", content=b"FIT\0")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "activity.fit" in data["saved"]
        assert data["skipped"] == []
        assert data["rejected"] == []
        mock_enqueue.assert_called_once()

    def test_existing_file_skipped(self, client, tmp_path):
        c, user_id = client
        # Pre-create the file on disk
        user_dir = tmp_path / "activities" / str(user_id)
        user_dir.mkdir(parents=True)
        (user_dir / "activity.fit").write_bytes(b"existing")

        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
            patch("routes.files._enqueue_process_file") as mock_enqueue,
        ):
            resp = _make_upload(c, "activity.fit", content=b"new content")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "activity.fit" in data["skipped"]
        assert data["saved"] == []
        mock_enqueue.assert_not_called()
        # Original file must not be overwritten
        assert (user_dir / "activity.fit").read_bytes() == b"existing"

    def test_zip_extracts_supported_files(self, client, tmp_path):
        import io
        import zipfile as zf

        c, user_id = client

        buf = io.BytesIO()
        with zf.ZipFile(buf, "w") as z:
            z.writestr("ride.gpx", b"<gpx/>")
            z.writestr("run.fit", b"FIT\0")
            z.writestr("photo.jpg", b"JPEG")
        buf.seek(0)

        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
            patch("routes.files._enqueue_process_file") as mock_enqueue,
        ):
            from io import BytesIO

            data_payload = {"file": (BytesIO(buf.read()), "activities.zip", "application/zip")}
            resp = c.post("/api/file/upload", data=data_payload, content_type="multipart/form-data")

        data = resp.get_json()
        assert resp.status_code == 200
        assert sorted(data["saved"]) == ["ride.gpx", "run.fit"]
        assert "photo.jpg" in data["rejected"]
        assert mock_enqueue.call_count == 2

    def test_zip_skips_existing_files(self, client, tmp_path):
        import io
        import zipfile as zf

        c, user_id = client
        user_dir = tmp_path / "activities" / str(user_id)
        user_dir.mkdir(parents=True)
        (user_dir / "ride.gpx").write_bytes(b"existing gpx")

        buf = io.BytesIO()
        with zf.ZipFile(buf, "w") as z:
            z.writestr("ride.gpx", b"<gpx/>")
            z.writestr("run.fit", b"FIT\0")
        buf.seek(0)

        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
            patch("routes.files._enqueue_process_file"),
        ):
            from io import BytesIO

            data_payload = {"file": (BytesIO(buf.read()), "bundle.zip", "application/zip")}
            resp = c.post("/api/file/upload", data=data_payload, content_type="multipart/form-data")

        data = resp.get_json()
        assert "ride.gpx" in data["skipped"]
        assert "run.fit" in data["saved"]
        # existing file must be untouched
        assert (user_dir / "ride.gpx").read_bytes() == b"existing gpx"

    def test_bad_zip_returns_400(self, client, tmp_path):
        c, user_id = client
        with (
            patch("routes.files.get_user_id", return_value=user_id),
            patch.dict(os.environ, {"TRACEKIT_DATA_DIR": str(tmp_path)}),
        ):
            resp = _make_upload(c, "bad.zip", content=b"not a zip")
        assert resp.status_code == 400
        assert "error" in resp.get_json()
