"""tracekit web application — entry point and blueprint registration."""

import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging — configure first
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

_access_log = logging.getLogger("tracekit.access")

# ---------------------------------------------------------------------------
# Sentry — modern SDK 2.x setup (Flask + Gunicorn safe)
# ---------------------------------------------------------------------------

if _sentry_dsn := os.environ.get("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    def _traces_sampler(sampling_context: dict) -> float:
        """
        Drop healthcheck traces.
        Sample everything else at 100%.
        """
        tx_ctx = sampling_context.get("transaction_context") or {}
        name = tx_ctx.get("name")

        if name == "api.health":
            return 0.0

        return 1.0

    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        # Performance
        traces_sampler=_traces_sampler,
        profile_lifecycle="trace",
        profile_session_sample_rate=1.0,
        # Logs (new 2.x logs product)
        enable_logs=True,
        # Flask integration
        integrations=[FlaskIntegration()],
        # Attach user + request info automatically
        send_default_pii=True,
    )

# ---------------------------------------------------------------------------
# Re-exports kept for backward-compatibility with the test suite
# ---------------------------------------------------------------------------

from calendar_data import get_sync_calendar_data  # noqa: F401
from db_init import (
    _init_db,
    load_tracekit_config,
)
from flask import Flask, abort, g, redirect, request, session, url_for
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

app.secret_key = os.environ["SESSION_KEY"]

# ---------------------------------------------------------------------------
# User context + DB initialization
# ---------------------------------------------------------------------------


@app.before_request
def _set_user_context():
    from auth_mode import is_single_user_mode

    from tracekit.user_context import set_user_id

    if is_single_user_mode():
        set_user_id(0)
        return

    try:
        from tracekit.db import get_db

        _init_db()
        get_db().connect(reuse_if_open=True)
    except Exception:
        abort(503)

    uid = session.get("user_id")
    if not uid:
        set_user_id(0)
        return

    try:
        import peewee
        from models.user import User

        user = User.get_by_id(uid)
        set_user_id(user.id)
        g.current_user = user
    except Exception as exc:
        import peewee

        if isinstance(exc, peewee.DoesNotExist):
            session.pop("user_id", None)
        else:
            abort(503)


@app.context_processor
def inject_current_user():
    from auth_mode import is_single_user_mode

    if is_single_user_mode():
        return {"current_user": None, "single_user_mode": True}

    return {
        "current_user": g.get("current_user"),
        "single_user_mode": False,
    }


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

_PUBLIC_ENDPOINTS = frozenset(
    {
        "auth.login",
        "auth.signup",
        "auth.logout",
        "api.health",
        "pages.privacy",
        "stripe.webhook",
        "static",
    }
)


@app.before_request
def _require_auth():
    from auth_mode import is_single_user_mode

    if is_single_user_mode():
        return
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if g.get("current_user"):
        return

    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------


@app.after_request
def _log_request(response):
    if request.endpoint != "api.health":
        _access_log.info(
            "%s %s %s",
            request.method,
            request.path,
            response.status_code,
        )
    return response


# ---------------------------------------------------------------------------
# Blueprint registration
# ---------------------------------------------------------------------------

from routes.admin import admin_bp
from routes.api import api_bp
from routes.auth import auth_bp
from routes.auth_garmin import garmin_bp
from routes.auth_strava import strava_bp
from routes.calendar import calendar_bp
from routes.month import month_bp
from routes.notifications import notifications_bp
from routes.pages import pages_bp
from routes.stripe_bp import stripe_bp

app.register_blueprint(pages_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(month_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(garmin_bp)
app.register_blueprint(strava_bp)
app.register_blueprint(stripe_bp)

# ---------------------------------------------------------------------------
# CLI entry point (dev only)
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

    app.run(
        debug=config.get("debug", False),
        host="0.0.0.0",
        port=5000,
        threaded=True,
    )
