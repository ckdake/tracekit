"""Shared helper functions for the tracekit web app."""

from datetime import UTC, datetime
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
        from tracekit.database import get_all_models
        from tracekit.db import get_db

        db = get_db()
        db.connect(reuse_if_open=True)

        models = get_all_models()
        table_counts = {}
        for model in models:
            table_name = model._meta.table_name
            table_counts[table_name] = model.select().count()

        return {
            "tables": table_counts,
            "total_tables": len(table_counts),
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_most_recent_activity(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the timestamp and timezone-formatted datetime of the most recent activity."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import (
            RideWithGPSActivity,
        )
        from tracekit.providers.spreadsheet.spreadsheet_activity import (
            SpreadsheetActivity,
        )
        from tracekit.providers.strava.strava_activity import StravaActivity
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        models = [
            StravaActivity,
            GarminActivity,
            RideWithGPSActivity,
            SpreadsheetActivity,
            FileActivity,
            StravaJsonActivity,
        ]

        max_ts: int | None = None
        for model in models:
            try:
                row = (
                    model.select(model.start_time)
                    .where(model.start_time.is_null(False))
                    .order_by(model.start_time.desc())
                    .first()
                )
                if row and row.start_time:
                    ts = int(row.start_time)
                    if max_ts is None or ts > max_ts:
                        max_ts = ts
            except Exception:
                pass

        if max_ts is None:
            return {"timestamp": None, "formatted": None}

        tz_str = (config or {}).get("home_timezone", "UTC")
        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            tz = pytz.UTC

        dt = datetime.fromtimestamp(max_ts, tz=UTC).astimezone(tz)
        formatted = dt.strftime("%-d %b %Y, %H:%M %Z")
        return {"timestamp": max_ts, "formatted": formatted}
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_provider_activity_counts() -> dict[str, int]:
    """Return {provider_name: activity_count} for all known providers."""
    if not _init_db():
        return {}

    try:
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import (
            RideWithGPSActivity,
        )
        from tracekit.providers.spreadsheet.spreadsheet_activity import (
            SpreadsheetActivity,
        )
        from tracekit.providers.strava.strava_activity import StravaActivity
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        models: dict[str, Any] = {
            "strava": StravaActivity,
            "garmin": GarminActivity,
            "ridewithgps": RideWithGPSActivity,
            "spreadsheet": SpreadsheetActivity,
            "file": FileActivity,
            "stravajson": StravaJsonActivity,
        }

        return {name: model.select().count() for name, model in models.items()}
    except Exception as e:
        return {"error": f"Database error: {e}"}  # type: ignore[return-value]


def sort_providers(providers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Sort providers by priority (lowest first) with disabled providers at the end."""
    enabled: list[tuple[int, str, dict[str, Any]]] = []
    disabled: list[tuple[str, dict[str, Any]]] = []
    for name, cfg in providers.items():
        if cfg.get("enabled", False):
            enabled.append((cfg.get("priority", 999), name, cfg))
        else:
            disabled.append((name, cfg))
    enabled.sort(key=lambda x: x[0])
    result = [(name, cfg) for _, name, cfg in enabled]
    result.extend(disabled)
    return result
