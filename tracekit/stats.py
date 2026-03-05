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
    from tracekit.providers.intervalsicu.intervalsicu_activity import IntervalsICUActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
    from tracekit.providers.strava.strava_activity import StravaActivity
    from tracekit.user_context import get_user_id

    models: dict[str, Any] = {
        "strava": StravaActivity,
        "garmin": GarminActivity,
        "ridewithgps": RideWithGPSActivity,
        "intervalsicu": IntervalsICUActivity,
        "spreadsheet": SpreadsheetActivity,
        "file": FileActivity,
    }
    uid = get_user_id()
    return {name: model.select().where(model.user_id == uid).count() for name, model in models.items()}


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
    from tracekit.providers.intervalsicu.intervalsicu_activity import IntervalsICUActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
    from tracekit.providers.strava.strava_activity import StravaActivity

    models = [
        StravaActivity,
        GarminActivity,
        RideWithGPSActivity,
        IntervalsICUActivity,
        SpreadsheetActivity,
        FileActivity,
    ]

    from tracekit.user_context import get_user_id

    uid = get_user_id()
    max_ts: int | None = None
    for model in models:
        try:
            row = (
                model.select(model.start_time)
                .where(model.start_time.is_null(False) & (model.user_id == uid))
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


def get_gear_summary() -> list[dict[str, Any]]:
    """Return per-gear mileage summary, sorted by most-recently used.

    Each entry contains:
      - name: gear name (from provider equipment field)
      - total_distance: deduplicated total across providers (miles)
      - last_used: ISO date string of most recent activity, or None
      - providers: {provider_name: distance_sum} for each provider
    """
    from zoneinfo import ZoneInfo

    from tracekit.providers.file.file_activity import FileActivity
    from tracekit.providers.garmin.garmin_activity import GarminActivity
    from tracekit.providers.intervalsicu.intervalsicu_activity import IntervalsICUActivity
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
    from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
    from tracekit.providers.strava.strava_activity import StravaActivity
    from tracekit.user_context import get_user_id

    uid = get_user_id()

    # Fixed provider list; ordering here doesn't affect correctness (dedup is per-gear).
    all_providers: list[tuple[str, Any]] = [
        ("strava", StravaActivity),
        ("garmin", GarminActivity),
        ("ridewithgps", RideWithGPSActivity),
        ("spreadsheet", SpreadsheetActivity),
        ("file", FileActivity),
        ("intervalsicu", IntervalsICUActivity),
    ]
    provider_names = [p for p, _ in all_providers]

    gear_map: dict[str, dict[str, Any]] = {}
    # Per-gear set of correlation keys already counted in the total (dedup).
    gear_seen: dict[str, set[str]] = {}

    def _corr_key(ts: int, dist: float) -> str:
        if not ts or not dist:
            return ""
        try:
            dt = datetime.fromtimestamp(ts, ZoneInfo("US/Eastern"))
            bucket = round(dist * 2) / 2
            return f"{dt.strftime('%Y-%m-%d')}_{bucket:.1f}"
        except Exception:
            return ""

    for provider_name, model_cls in all_providers:
        try:
            rows = (
                model_cls.select()
                .where(model_cls.user_id == uid)
                .where(model_cls.equipment.is_null(False))
                .where(model_cls.equipment != "")
            )
            for row in rows:
                name = (row.equipment or "").strip()
                if not name:
                    continue
                if name not in gear_map:
                    gear_map[name] = {
                        "name": name,
                        "total_distance": 0.0,
                        "last_used": None,
                        "providers": {p: 0.0 for p in provider_names},
                    }
                    gear_seen[name] = set()

                dist = float(row.distance or 0)
                gear_map[name]["providers"][provider_name] += dist

                # Deduplicate totals via correlation key (date + distance bucket).
                key = _corr_key(int(row.start_time or 0), dist)
                if not key or key not in gear_seen[name]:
                    gear_map[name]["total_distance"] += dist
                    if key:
                        gear_seen[name].add(key)

                if row.start_time:
                    try:
                        d = datetime.fromtimestamp(int(row.start_time), UTC).strftime("%Y-%m-%d")
                        if gear_map[name]["last_used"] is None or d > gear_map[name]["last_used"]:
                            gear_map[name]["last_used"] = d
                    except (ValueError, TypeError, OSError):
                        pass
        except Exception:
            pass

    result = sorted(
        gear_map.values(),
        key=lambda x: (x["last_used"] or "", x["name"]),
        reverse=True,
    )
    return result


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
