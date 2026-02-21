"""Calendar data helpers for the tracekit web app."""

import calendar as _cal
from datetime import UTC, datetime
from typing import Any

from db_init import _init_db
from helpers import get_current_date_in_timezone


def get_sync_calendar_data(config: dict[str, Any]) -> dict[str, Any]:
    """Compatibility shim — returns full calendar data (used by tests).

    In production the page uses get_calendar_shell + get_single_month_data
    so that each month loads independently.  This function still works for
    the test suite which imports it directly.
    """
    shell = get_calendar_shell(config)
    if shell.get("error"):
        return shell

    months_with_data = []
    for stub in shell["months"]:
        month_data = get_single_month_data(config, stub["year_month"])
        if month_data.get("error"):
            months_with_data.append(stub)
        else:
            months_with_data.append(month_data)

    return {
        "months": months_with_data,
        "providers": shell["providers"],
        "date_range": shell["date_range"],
        "total_months": shell["total_months"],
    }


def get_calendar_shell(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return month stubs and providers list — no activity table scans."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.db import get_db
        from tracekit.provider_sync import ProviderSync

        db = get_db()
        db.connect(reuse_if_open=True)

        rows = ProviderSync.select(ProviderSync.year_month, ProviderSync.provider).order_by(
            ProviderSync.year_month, ProviderSync.provider
        )
        records = [(r.year_month, r.provider) for r in rows]

        if not records:
            return {
                "months": [],
                "providers": [],
                "date_range": (None, None),
                "total_months": 0,
            }

        year_months_all = [r[0] for r in records]
        date_range = (min(year_months_all), max(year_months_all))
        providers = sorted({r[1] for r in records})

        start_year, start_month = map(int, date_range[0].split("-"))
        end_year, end_month = map(int, date_range[1].split("-"))

        current_date = get_current_date_in_timezone(config)
        current_ym = f"{current_date.year:04d}-{current_date.month:02d}"
        if current_ym > date_range[1]:
            end_year, end_month = current_date.year, current_date.month

        all_months = []
        year, month = start_year, start_month
        while year < end_year or (year == end_year and month <= end_month):
            ym = f"{year:04d}-{month:02d}"
            all_months.append(
                {
                    "year_month": ym,
                    "year": year,
                    "month": month,
                    "month_name": datetime(year, month, 1).strftime("%B"),
                }
            )
            month += 1
            if month > 12:
                month = 1
                year += 1

        return {
            "months": all_months,
            "providers": providers,
            "date_range": date_range,
            "total_months": len(all_months),
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_single_month_data(config: dict[str, Any] | None, year_month: str) -> dict[str, Any]:
    """Return sync status and activity counts for one month.

    Activity queries are scoped to the month's timestamp range so this is
    fast even for large databases.
    """
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.db import get_db
        from tracekit.provider_sync import ProviderSync
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

        db = get_db()
        db.connect(reuse_if_open=True)

        synced_rows = ProviderSync.select(ProviderSync.provider).where(ProviderSync.year_month == year_month)
        synced_providers = [r.provider for r in synced_rows]

        all_rows = ProviderSync.select(ProviderSync.provider).distinct()
        providers = sorted({r.provider for r in all_rows})

        provider_status = {p: p in synced_providers for p in providers}

        year_int, month_int = map(int, year_month.split("-"))
        start_ts = int(datetime(year_int, month_int, 1, tzinfo=UTC).timestamp())
        last_day = _cal.monthrange(year_int, month_int)[1]
        end_ts = int(datetime(year_int, month_int, last_day, 23, 59, 59, tzinfo=UTC).timestamp())

        provider_models = {
            "strava": StravaActivity,
            "garmin": GarminActivity,
            "ridewithgps": RideWithGPSActivity,
            "spreadsheet": SpreadsheetActivity,
            "file": FileActivity,
            "stravajson": StravaJsonActivity,
        }

        activity_counts: dict[str, int] = {}
        for provider, model in provider_models.items():
            try:
                count = (
                    model.select()
                    .where(
                        model.start_time.is_null(False) & (model.start_time >= start_ts) & (model.start_time <= end_ts)
                    )
                    .count()
                )
                if count > 0:
                    activity_counts[provider] = count
            except Exception as e:
                print(f"Error counting {provider} activities for {year_month}: {e}")

        total_activities = sum(activity_counts.values())

        # Per-provider list of day-of-month numbers that have ≥1 activity,
        # converted to the configured home timezone so dots match the user's calendar.
        tz_str = (config or {}).get("home_timezone", "UTC")
        try:
            import pytz

            local_tz = pytz.timezone(tz_str)
        except Exception:
            import pytz

            local_tz = pytz.utc

        activity_days: dict[str, list[int]] = {}
        for provider, model in provider_models.items():
            if provider not in activity_counts:
                continue
            try:
                rows_ts = model.select(model.start_time).where(
                    model.start_time.is_null(False) & (model.start_time >= start_ts) & (model.start_time <= end_ts)
                )
                days = sorted({datetime.fromtimestamp(r.start_time, tz=UTC).astimezone(local_tz).day for r in rows_ts})
                if days:
                    activity_days[provider] = days
            except Exception as e:
                print(f"Error getting activity days for {provider}/{year_month}: {e}")

        # Collect Garmin device names used in this month (non-null, distinct)
        garmin_devices: list[str] = []
        try:
            rows = (
                GarminActivity.select(GarminActivity.device_name)
                .where(
                    GarminActivity.start_time.is_null(False)
                    & (GarminActivity.start_time >= start_ts)
                    & (GarminActivity.start_time <= end_ts)
                    & GarminActivity.device_name.is_null(False)
                )
                .distinct()
            )
            garmin_devices = sorted({r.device_name for r in rows if r.device_name})
        except Exception:
            pass

        provider_metadata: dict[str, dict] = {}
        if garmin_devices:
            provider_metadata["garmin"] = {"devices": garmin_devices}

        return {
            "year_month": year_month,
            "year": year_int,
            "month": month_int,
            "month_name": datetime(year_int, month_int, 1).strftime("%B"),
            "providers": providers,
            "synced_providers": synced_providers,
            "provider_status": provider_status,
            "activity_counts": activity_counts,
            "total_activities": total_activities,
            "provider_metadata": provider_metadata,
            "activity_days": activity_days,
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}
