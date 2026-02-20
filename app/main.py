"""Simple Flask web application to view tracekit configuration and database status."""

import json
from collections import defaultdict
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
    """Get sync calendar data from the providersync table with activity counts."""
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

        # Get all sync records using the ORM
        rows = ProviderSync.select(ProviderSync.year_month, ProviderSync.provider).order_by(
            ProviderSync.year_month, ProviderSync.provider
        )
        records = [(r.year_month, r.provider) for r in rows]

        if not records:
            date_range = (None, None)
        else:
            year_months = [r[0] for r in records]
            date_range = (min(year_months), max(year_months))

        providers = sorted({r[1] for r in records})

        # Count activities per provider per month — fetch start_time and group in Python
        # so this works on both SQLite and Postgres without SQL dialect differences.
        provider_models = {
            "strava": StravaActivity,
            "garmin": GarminActivity,
            "ridewithgps": RideWithGPSActivity,
            "spreadsheet": SpreadsheetActivity,
            "file": FileActivity,
            "stravajson": StravaJsonActivity,
        }

        activity_counts: dict[str, dict[str, int]] = {}
        for provider, model in provider_models.items():
            try:
                for activity in model.select(model.start_time).where(model.start_time.is_null(False)):
                    ym = datetime.fromtimestamp(activity.start_time, tz=UTC).strftime("%Y-%m")
                    activity_counts.setdefault(ym, {})
                    activity_counts[ym][provider] = activity_counts[ym].get(provider, 0) + 1
            except Exception as e:
                print(f"Error getting activity counts for {provider}: {e}")

        # Organize data by month
        sync_data = defaultdict(set)
        for year_month, provider in records:
            sync_data[year_month].add(provider)

        # Generate all months from start to current month
        if date_range[0] and date_range[1]:
            start_year, start_month = map(int, date_range[0].split("-"))
            end_year, end_month = map(int, date_range[1].split("-"))
            current_date = get_current_date_in_timezone(config)
            current_year_month = f"{current_date.year:04d}-{current_date.month:02d}"

            # If current month is later than last sync, extend to current month
            if current_year_month > date_range[1]:
                end_year, end_month = current_date.year, current_date.month

            # Also consider months that have activities but no sync data
            activity_months = set(activity_counts.keys())
            if activity_months:
                for activity_month in activity_months:
                    activity_year, activity_month_num = map(int, activity_month.split("-"))
                    if activity_year < start_year or (activity_year == start_year and activity_month_num < start_month):
                        start_year, start_month = activity_year, activity_month_num
                    if activity_year > end_year or (activity_year == end_year and activity_month_num > end_month):
                        end_year, end_month = activity_year, activity_month_num

            all_months = []
            year, month = start_year, start_month
            while year < end_year or (year == end_year and month <= end_month):
                year_month = f"{year:04d}-{month:02d}"

                # Build provider activity counts for this month
                provider_activity_counts = {}
                if year_month in activity_counts:
                    provider_activity_counts = activity_counts[year_month]

                all_months.append(
                    {
                        "year_month": year_month,
                        "year": year,
                        "month": month,
                        "month_name": datetime(year, month, 1).strftime("%B"),
                        "synced_providers": list(sync_data[year_month]),
                        "provider_status": {provider: provider in sync_data[year_month] for provider in providers},
                        "activity_counts": provider_activity_counts,
                        "total_activities": sum(provider_activity_counts.values()) if provider_activity_counts else 0,
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
        else:
            return {"months": [], "providers": providers, "date_range": (None, None), "total_months": 0}

    except Exception as e:
        return {"error": f"Database error: {e}"}


@app.route("/calendar")
def calendar():
    """Sync calendar page."""
    config = load_tracekit_config()

    calendar_data = {}
    if not config.get("error"):
        calendar_data = get_sync_calendar_data(config)

    # Add current month for highlighting (using configured timezone)
    current_date = get_current_date_in_timezone(config)
    current_month = f"{current_date.year:04d}-{current_date.month:02d}"

    return render_template("calendar.html", config=config, calendar_data=calendar_data, current_month=current_month)


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
