"""Shared helper functions for the tracekit web app."""

from datetime import datetime
from typing import Any

import pytz
from db_init import _init_db


def get_current_date_in_timezone(config: dict[str, Any]):
    """Get the current date in the configured timezone."""
    try:
        timezone_str = config.get("home_timezone", "UTC")
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        return now.date()
    except Exception:
        return datetime.now(pytz.UTC).date()


def get_database_info(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get basic information about the configured database."""
    if not _init_db():
        return {"error": "Database not available"}
    try:
        from tracekit.db import get_db
        from tracekit.stats import get_database_info as _get_database_info

        db = get_db()
        db.connect(reuse_if_open=True)
        return _get_database_info()
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_most_recent_activity(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the timestamp and timezone-formatted datetime of the most recent activity."""
    if not _init_db():
        return {"error": "Database not available"}
    try:
        from tracekit.db import get_db
        from tracekit.stats import get_most_recent_activity as _get_most_recent

        db = get_db()
        db.connect(reuse_if_open=True)
        tz_str = (config or {}).get("home_timezone", "UTC")
        return _get_most_recent(tz_str)
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_provider_activity_counts() -> dict[str, int]:
    """Return {provider_name: activity_count} for all known providers."""
    if not _init_db():
        return {}
    try:
        from tracekit.db import get_db
        from tracekit.stats import get_provider_activity_counts as _get_counts

        db = get_db()
        db.connect(reuse_if_open=True)
        return _get_counts()
    except Exception as e:
        return {"error": f"Database error: {e}"}  # type: ignore[return-value]


def sort_providers(providers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Sort providers by priority (lowest first) with disabled providers at the end."""
    from tracekit.utils import sort_providers as _sort_providers

    return _sort_providers(providers)
