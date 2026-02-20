"""Simple Flask web application to view tracekit configuration and database status."""

import calendar as _cal
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytz
from flask import Flask, jsonify, render_template

# Get the directory where this script is located
app_dir = Path(__file__).parent
app = Flask(__name__, template_folder=str(app_dir / "templates"))

# Look for config file in current directory, then parent directory
CONFIG_PATH = Path("tracekit_config.json")
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("../tracekit_config.json")

# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

_db_initialized = False


def _init_db(config: dict[str, Any]) -> bool:
    """Lazily initialise the tracekit DB (honours DATABASE_URL for Postgres)."""
    global _db_initialized
    if not _db_initialized:
        try:
            from tracekit.db import configure_db

            db_path = config.get("metadata_db", "metadata.sqlite3")
            configure_db(db_path)
            _db_initialized = True
        except Exception as e:
            print(f"DB init failed: {e}")
            return False
    return True


def load_tracekit_config() -> dict[str, Any]:
    """Load tracekit configuration from tracekit_config.json."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "tracekit_config.json not found"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}


def get_current_date_in_timezone(config: dict[str, Any]) -> date:
    """Get the current date in the configured timezone."""
    try:
        timezone_str = config.get("home_timezone", "UTC")
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        return now.date()
    except Exception:
        # Fallback to UTC if timezone is invalid
        return datetime.now(pytz.UTC).date()


def get_database_info(config: dict[str, Any]) -> dict[str, Any]:
    """Get basic information about the configured database."""
    if not _init_db(config):
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


def get_calendar_shell(config: dict[str, Any]) -> dict[str, Any]:
    """Return month stubs and providers list — no activity table scans."""
    if not _init_db(config):
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
            return {"months": [], "providers": [], "date_range": (None, None), "total_months": 0}

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


def get_single_month_data(config: dict[str, Any], year_month: str) -> dict[str, Any]:
    """Return sync status and activity counts for one month.

    Activity queries are scoped to the month's timestamp range so this is
    fast even for large databases.
    """
    if not _init_db(config):
        return {"error": "Database not available"}

    try:
        from tracekit.db import get_db
        from tracekit.provider_sync import ProviderSync
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
        from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
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
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


@app.route("/calendar")
def calendar():
    """Sync calendar page — renders card shells; each card loads via /api/calendar/<ym>."""
    config = load_tracekit_config()

    shell_data: dict[str, Any] = {}
    if not config.get("error"):
        shell_data = get_calendar_shell(config)

    current_date = get_current_date_in_timezone(config)
    current_month = f"{current_date.year:04d}-{current_date.month:02d}"

    return render_template("calendar.html", config=config, shell_data=shell_data, current_month=current_month)


def sort_providers(providers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Sort providers by priority (lowest to highest) with disabled providers at the end."""
    enabled_providers = []
    disabled_providers = []

    for name, config in providers.items():
        if config.get("enabled", False):
            # Get priority, default to 999 if not specified
            priority = config.get("priority", 999)
            enabled_providers.append((priority, name, config))
        else:
            disabled_providers.append((name, config))

    # Sort enabled providers by priority (lowest first)
    enabled_providers.sort(key=lambda x: x[0])

    # Convert to list of (name, config) tuples
    result = [(name, config) for _, name, config in enabled_providers]
    result.extend(disabled_providers)

    return result


@app.route("/")
def index():
    """Main dashboard page."""
    config = load_tracekit_config()

    # Sort providers if they exist
    sorted_providers = []
    if "providers" in config and not config.get("error"):
        sorted_providers = sort_providers(config["providers"])

    db_info = {}
    if not config.get("error"):
        db_info = get_database_info(config)

    return render_template("index.html", config=config, sorted_providers=sorted_providers, db_info=db_info)


@app.route("/api/config")
def api_config():
    """API endpoint for configuration data."""
    return jsonify(load_tracekit_config())


@app.route("/api/database")
def api_database():
    """API endpoint for database information."""
    config = load_tracekit_config()
    if not config.get("error"):
        return jsonify(get_database_info(config))
    return jsonify({"error": "Config error"})


@app.route("/api/calendar/<year_month>")
def api_calendar_month(year_month: str):
    """Return sync status and activity counts for a single month."""
    import re

    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    config = load_tracekit_config()
    if config.get("error"):
        return jsonify({"error": "Config error"}), 503
    return jsonify(get_single_month_data(config, year_month))


@app.route("/api/sync/<year_month>", methods=["POST"])
def sync_month(year_month: str):
    """Enqueue a pull job for the given YYYY-MM month."""
    import re

    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    try:
        from tracekit.worker import pull_month

        task = pull_month.delay(year_month)
        return jsonify({"task_id": task.id, "year_month": year_month, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@app.route("/api/sync/status/<task_id>")
def sync_status(task_id: str):
    """Return the current state of a Celery task."""
    try:
        from celery.result import AsyncResult

        from tracekit.worker import celery_app

        result = AsyncResult(task_id, app=celery_app)
        info = None
        if result.failed():
            info = str(result.info)
        return jsonify({"task_id": task_id, "state": result.state, "info": info})
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "app": "tracekit-web"})


if __name__ == "__main__":
    print("🚀 Starting tracekit Web App...")

    # Test that everything works before starting server
    print("� Testing configuration...")
    config = load_tracekit_config()
    if config.get("error"):
        print(f"❌ Config error: {config['error']}")
        exit(1)
    else:
        print(f"✅ Config loaded: {config.get('home_timezone')}")

    print("📋 Testing template rendering...")
    with app.test_client() as client:
        response = client.get("/")
        if response.status_code == 200:
            print("✅ Template rendering works")
        else:
            print("❌ Template rendering failed")
            exit(1)

    print("�📍 Server starting at: http://localhost:5000")
    print("🔧 Dashboard: http://localhost:5000")
    print("🔧 Config API: http://localhost:5000/api/config")
    print("💾 Database API: http://localhost:5000/api/database")
    print("❤️  Health Check: http://localhost:5000/health")
    print("\nPress Ctrl+C to stop")

    try:
        app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        exit(1)
