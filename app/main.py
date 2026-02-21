"""tracekit web application — entry point and blueprint registration."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Re-exports kept for backward-compatibility with the test suite
# ---------------------------------------------------------------------------
from calendar_data import get_sync_calendar_data  # noqa: F401
from db_init import (
    _init_db,  # noqa: F401
    load_tracekit_config,
)
from flask import Flask
from helpers import (
    get_current_date_in_timezone,  # noqa: F401
    get_database_info,  # noqa: F401
    sort_providers,  # noqa: F401
)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app_dir = Path(__file__).parent
app = Flask(__name__, template_folder=str(app_dir / "templates"), static_folder=str(app_dir / "static"))

# ---------------------------------------------------------------------------
# Blueprint registration
# ---------------------------------------------------------------------------

from routes.api import api_bp
from routes.auth_garmin import garmin_bp
from routes.auth_strava import strava_bp
from routes.calendar import calendar_bp
from routes.month import month_bp
from routes.notifications import notifications_bp
from routes.pages import pages_bp

app.register_blueprint(pages_bp)
app.register_blueprint(api_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(month_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(garmin_bp)
app.register_blueprint(strava_bp)

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting tracekit Web App...")

    config = load_tracekit_config()
    print(f"Config loaded: timezone={config.get('home_timezone')}, debug={config.get('debug')}")

    print("Server starting at: http://localhost:5000")
    print("  Dashboard:    http://localhost:5000")
    print("  Settings:     http://localhost:5000/settings")
    print("  Config API:   http://localhost:5000/api/config")
    print("  Database API: http://localhost:5000/api/database")
    print("  Health:       http://localhost:5000/health")
    print("\nPress Ctrl+C to stop")

    try:
        app.run(debug=config.get("debug", False), host="0.0.0.0", port=5000, threaded=True)
    except Exception as e:
        print(f"Server failed to start: {e}")
        exit(1)
