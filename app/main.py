"""tracekit web application — entry point and blueprint registration."""

import os
import secrets
from pathlib import Path

# ---------------------------------------------------------------------------
# Re-exports kept for backward-compatibility with the test suite
# ---------------------------------------------------------------------------
from calendar_data import get_sync_calendar_data  # noqa: F401
from db_init import (
    _init_db,  # noqa: F401
    load_tracekit_config,
)
from flask import Flask, session
from helpers import (
    get_current_date_in_timezone,  # noqa: F401
    get_database_info,  # noqa: F401
    sort_providers,  # noqa: F401
)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app_dir = Path(__file__).parent
app = Flask(
    __name__,
    template_folder=str(app_dir / "templates"),
    static_folder=str(app_dir / "static"),
)

app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ---------------------------------------------------------------------------
# Template context — inject current_user into every template
# ---------------------------------------------------------------------------


@app.before_request
def _set_user_context():
    from auth_mode import is_single_user_mode

    from tracekit.user_context import set_user_id

    if is_single_user_mode():
        set_user_id(0)
        return
    uid = session.get("user_id")
    if uid:
        try:
            from models.user import User

            user = User.get_by_id(uid)
            set_user_id(user.id)
        except Exception:
            session.pop("user_id", None)
            set_user_id(0)
    else:
        set_user_id(0)


@app.context_processor
def inject_current_user():
    from auth_mode import is_single_user_mode

    single_user_mode = is_single_user_mode()
    if single_user_mode:
        return {"current_user": None, "single_user_mode": True}
    user_id = session.get("user_id")
    if user_id:
        try:
            from models.user import User

            return {"current_user": User.get_by_id(user_id), "single_user_mode": False}
        except Exception:
            session.pop("user_id", None)
    return {"current_user": None, "single_user_mode": False}


# ---------------------------------------------------------------------------
# Blueprint registration
# ---------------------------------------------------------------------------

from routes.api import api_bp
from routes.auth import auth_bp
from routes.auth_garmin import garmin_bp
from routes.auth_strava import strava_bp
from routes.calendar import calendar_bp
from routes.month import month_bp
from routes.notifications import notifications_bp
from routes.pages import pages_bp

app.register_blueprint(pages_bp)
app.register_blueprint(auth_bp)
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
