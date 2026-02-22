"""Database query helpers for activity statistics.

These functions are intentionally free of web/Flask dependencies so they can
be used by both the CLI commands and the web application.  Callers are
responsible for ensuring the database is initialised before calling these.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def get_provider_activity_counts() -> dict[str, int]:
    """Return {provider_name: total_activity_count} for all known providers."""
    from tracekit.providers.file.file_activity import FileActivity
    from tracekit.providers.garmin.garmin_activity import GarminActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
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


def get_most_recent_activity(home_timezone: str = "UTC") -> dict[str, Any]:
    """Return the timestamp and formatted datetime of the most recent activity.

    Args:
        home_timezone: IANA timezone string used for display formatting.

    Returns:
        {"timestamp": int | None, "formatted": str | None}
    """
    import pytz

    from tracekit.providers.file.file_activity import FileActivity
    from tracekit.providers.garmin.garmin_activity import GarminActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
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

    try:
        tz = pytz.timezone(home_timezone)
    except Exception:
        tz = pytz.UTC

    dt = datetime.fromtimestamp(max_ts, tz=UTC).astimezone(tz)
    formatted = dt.strftime("%-d %b %Y, %H:%M %Z")
    return {"timestamp": max_ts, "formatted": formatted}


def get_database_info() -> dict[str, Any]:
    """Return {table_name: row_count} for every model in the database."""
    from tracekit.database import get_all_models

    models = get_all_models()
    table_counts = {}
    for model in models:
        table_name = model._meta.table_name
        table_counts[table_name] = model.select().count()

    return {
        "tables": table_counts,
        "total_tables": len(table_counts),
    }
