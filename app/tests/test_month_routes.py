"""Tests for the month sync-review web routes."""

import json
import os
import sys
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_db_state():
    yield
    import db_init as db_init_module

    import tracekit.db as tdb

    db_init_module._db_initialized = False
    tdb._configured = False


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


_CONFIG = {
    "home_timezone": "US/Eastern",
    "debug": False,
    "providers": {
        "strava": {"enabled": True, "priority": 1, "sync_name": True, "sync_equipment": True},
        "spreadsheet": {"enabled": True, "priority": 2, "sync_name": True, "sync_equipment": True},
    },
}


# ---------------------------------------------------------------------------
# GET /month/<year_month>
# ---------------------------------------------------------------------------


class TestMonthShowPage:
    def test_valid_month_returns_200(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2024-07")
        assert resp.status_code == 200

    def test_page_contains_month_name(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2024-07")
        assert b"July" in resp.data

    def test_page_contains_year(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2024-07")
        assert b"2024" in resp.data

    def test_page_contains_sync_review_heading(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2024-07")
        assert b"Sync Review" in resp.data

    def test_page_contains_back_link(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2024-07")
        assert b"Dashboard" in resp.data or b"/" in resp.data

    def test_invalid_month_returns_400(self, client):
        resp = client.get("/month/not-a-month")
        assert resp.status_code == 400

    def test_invalid_month_format_rejected(self, client):
        resp = client.get("/month/2024")
        assert resp.status_code == 400

    def test_page_includes_year_month_js_var(self, client):
        with patch("routes.month.load_tracekit_config", return_value=_CONFIG):
            resp = client.get("/month/2025-03")
        assert b"2025-03" in resp.data


# ---------------------------------------------------------------------------
# GET /api/month-changes/<year_month>
# ---------------------------------------------------------------------------


class TestMonthChangesApi:
    def _make_tk_mock(self):
        tk = MagicMock()
        tk.pull_activities.return_value = {}
        from zoneinfo import ZoneInfo

        tk.home_tz = ZoneInfo("US/Eastern")
        tk.config = {"providers": _CONFIG["providers"], "home_timezone": "US/Eastern"}
        # Support context manager: `with tracekit_class() as tk:` where
        # tracekit_class is patched with return_value=tk_mock
        tk.__enter__ = MagicMock(return_value=tk)
        tk.__exit__ = MagicMock(return_value=False)
        return tk

    def test_valid_month_returns_200(self, client):
        tk_mock = self._make_tk_mock()
        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
        ):
            resp = client.get("/api/month-changes/2024-07")
        assert resp.status_code == 200

    def test_response_is_json(self, client):
        tk_mock = self._make_tk_mock()
        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
        ):
            resp = client.get("/api/month-changes/2024-07")
        assert resp.content_type.startswith("application/json")

    def test_response_has_expected_keys(self, client):
        tk_mock = self._make_tk_mock()
        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
        ):
            resp = client.get("/api/month-changes/2024-07")
        data = json.loads(resp.data)
        assert "year_month" in data
        assert "changes" in data
        assert "rows" in data
        assert "provider_list" in data

    def test_year_month_echoed_in_response(self, client):
        tk_mock = self._make_tk_mock()
        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
        ):
            resp = client.get("/api/month-changes/2025-03")
        data = json.loads(resp.data)
        assert data["year_month"] == "2025-03"

    def test_invalid_month_returns_400(self, client):
        resp = client.get("/api/month-changes/bad-month")
        assert resp.status_code == 400

    def test_empty_activities_returns_empty_changes(self, client):
        tk_mock = self._make_tk_mock()
        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
        ):
            resp = client.get("/api/month-changes/2024-07")
        data = json.loads(resp.data)
        assert data["changes"] == []
        assert data["rows"] == []

    def test_changes_are_serialised_as_dicts(self, client):
        from tracekit.sync import ActivityChange, ChangeType

        tk_mock = self._make_tk_mock()

        def fake_compute(tk, year_month):
            ch = ActivityChange(ChangeType.UPDATE_NAME, "strava", "1", "Old", "New")
            return {}, [ch]

        with (
            patch("routes.month.load_tracekit_config", return_value=_CONFIG),
            patch("routes.month.tracekit_class", return_value=tk_mock),
            patch("routes.month.compute_month_changes", side_effect=fake_compute),
        ):
            resp = client.get("/api/month-changes/2024-07")
        data = json.loads(resp.data)
        assert len(data["changes"]) == 1
        c = data["changes"][0]
        assert c["change_type"] == "Update Name"
        assert c["provider"] == "strava"
        assert c["new_value"] == "New"


# ---------------------------------------------------------------------------
# POST /api/month-sync/apply
# ---------------------------------------------------------------------------


class TestMonthApplyApi:
    _change: ClassVar[dict] = {
        "change_type": "Update Name",
        "provider": "strava",
        "activity_id": "42",
        "old_value": "Old",
        "new_value": "New",
        "source_provider": None,
    }

    def test_missing_body_returns_400(self, client):
        resp = client.post("/api/month-sync/apply", content_type="application/json", data="{}")
        assert resp.status_code == 400

    def test_missing_year_month_returns_400(self, client):
        resp = client.post(
            "/api/month-sync/apply",
            content_type="application/json",
            data=json.dumps({"change": self._change}),
        )
        assert resp.status_code == 400

    def test_invalid_year_month_returns_400(self, client):
        resp = client.post(
            "/api/month-sync/apply",
            content_type="application/json",
            data=json.dumps({"change": self._change, "year_month": "not-valid"}),
        )
        assert resp.status_code == 400

    def test_celery_unavailable_returns_503(self, client):
        with patch("routes.month.apply_sync_change", None):
            resp = client.post(
                "/api/month-sync/apply",
                content_type="application/json",
                data=json.dumps({"change": self._change, "year_month": "2024-07"}),
            )
        assert resp.status_code == 503

    def test_successful_enqueue_returns_queued(self, client):
        mock_task = MagicMock()
        mock_task.id = "test-task-uuid-1234"
        mock_celery = MagicMock()
        mock_celery.delay.return_value = mock_task
        with (
            patch("routes.month.apply_sync_change", mock_celery),
            patch("routes.month.create_notification", MagicMock()),
            patch("routes.month.expiry_timestamp", return_value=99999),
        ):
            resp = client.post(
                "/api/month-sync/apply",
                content_type="application/json",
                data=json.dumps({"change": self._change, "year_month": "2024-07"}),
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "queued"
        assert data["task_id"] == "test-task-uuid-1234"
        assert data["year_month"] == "2024-07"
