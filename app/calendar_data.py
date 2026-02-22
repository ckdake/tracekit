"""Calendar data helpers for the tracekit web app.

Business logic lives in ``tracekit.calendar``; this module is a thin shim
that handles web-layer concerns (database availability checks, config
extraction) before delegating to the package functions.
"""

from typing import Any

from db_init import _init_db


def _sort_providers_by_priority(providers: list[str], config: dict[str, Any] | None) -> list[str]:
    """Sort a list of provider names by their configured priority (lowest = first)."""
    pconf = (config or {}).get("providers", {})
    return sorted(providers, key=lambda p: (pconf.get(p, {}).get("priority", 999), p))


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
        from tracekit.calendar import get_calendar_shell as _get_calendar_shell
        from tracekit.db import get_db

        db = get_db()
        db.connect(reuse_if_open=True)

        tz_str = (config or {}).get("home_timezone", "UTC")
        result = _get_calendar_shell(tz_str)
        if "providers" in result:
            result["providers"] = _sort_providers_by_priority(result["providers"], config)
        return result
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_single_month_data(config: dict[str, Any] | None, year_month: str) -> dict[str, Any]:
    """Return sync status and activity counts for one month."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.calendar import get_single_month_data as _get_single_month_data
        from tracekit.db import get_db

        db = get_db()
        db.connect(reuse_if_open=True)

        tz_str = (config or {}).get("home_timezone", "UTC")
        result = _get_single_month_data(year_month, tz_str)
        if "providers" in result:
            result["providers"] = _sort_providers_by_priority(result["providers"], config)
        return result
    except Exception as e:
        return {"error": f"Database error: {e}"}
