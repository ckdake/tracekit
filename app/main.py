"""Simple Flask web application to view tracekit configuration and database status."""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime
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


def get_database_info(db_path: str) -> dict[str, Any]:
    """Get basic information about the SQLite database."""
    if not os.path.exists(db_path):
        return {"error": "Database file not found", "path": db_path}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get database file size
        file_size = os.path.getsize(db_path)

        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        # Get row counts for each table
        table_counts = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            table_counts[table] = cursor.fetchone()[0]

        conn.close()

        return {
            "path": db_path,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "tables": table_counts,
            "total_tables": len(tables),
        }
    except sqlite3.Error as e:
        return {"error": f"Database error: {e}", "path": db_path}


def get_sync_calendar_data(db_path: str, config: dict[str, Any]) -> dict[str, Any]:
    """Get sync calendar data from the providersync table with activity counts."""
    if not os.path.exists(db_path):
        return {"error": "Database file not found", "path": db_path}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all sync records
        cursor.execute("SELECT year_month, provider FROM providersync ORDER BY year_month, provider")
        records = cursor.fetchall()

        # Get date range
        cursor.execute("SELECT MIN(year_month), MAX(year_month) FROM providersync")
        date_range = cursor.fetchone()

        # Get unique providers
        cursor.execute("SELECT DISTINCT provider FROM providersync ORDER BY provider")
        providers = [row[0] for row in cursor.fetchall()]

        # Get activity counts per provider per month
        provider_tables = {
            "strava": "strava_activities",
            "garmin": "garmin_activities",
            "ridewithgps": "ridewithgps_activities",
            "spreadsheet": "spreadsheet_activities",
            "file": "file_activities",
        }

        activity_counts = {}
        for provider, table in provider_tables.items():
            try:
                # Get activity counts grouped by month (start_time is Unix timestamp)
                cursor.execute(f"""
                    SELECT
                        strftime('%Y-%m', datetime(start_time, 'unixepoch')) as year_month,
                        COUNT(*) as count
                    FROM {table}
                    WHERE start_time IS NOT NULL
                    GROUP BY strftime('%Y-%m', datetime(start_time, 'unixepoch'))
                """)

                provider_counts = cursor.fetchall()
                for year_month, count in provider_counts:
                    if year_month not in activity_counts:
                        activity_counts[year_month] = {}
                    activity_counts[year_month][provider] = count

            except Exception as e:
                print(f"Error getting activity counts for {provider}: {e}")

        conn.close()

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

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}", "path": db_path}


@app.route("/calendar")
def calendar():
    """Sync calendar page."""
    config = load_tracekit_config()

    calendar_data = {}
    if "metadata_db" in config and not config.get("error"):
        db_path = config["metadata_db"]
        calendar_data = get_sync_calendar_data(db_path, config)

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
    if "metadata_db" in config and not config.get("error"):
        db_path = config["metadata_db"]
        db_info = get_database_info(db_path)

    return render_template("index.html", config=config, sorted_providers=sorted_providers, db_info=db_info)


@app.route("/api/config")
def api_config():
    """API endpoint for configuration data."""
    return jsonify(load_tracekit_config())


@app.route("/api/database")
def api_database():
    """API endpoint for database information."""
    config = load_tracekit_config()
    if "metadata_db" in config and not config.get("error"):
        db_path = config["metadata_db"]
        return jsonify(get_database_info(db_path))
    return jsonify({"error": "No database configured or config error"})


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
        app.run(debug=False, host="127.0.0.1", port=5000, threaded=True)
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        exit(1)
