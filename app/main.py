"""tracekit web application — entry point and blueprint registration."""

import json
import logging
import os
import sys
from pathlib import Path

from db_init import _ensure_db_connected, load_tracekit_config
from flask import Flask, abort, redirect, request, url_for
from flask_login import LoginManager, current_user

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(message)s",
)

if _sentry_dsn := os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    def _traces_sampler(sampling_context):
        wsgi_environ = sampling_context.get("wsgi_environ") or {}
        path = wsgi_environ.get("PATH_INFO", "")
        if path == "/health":
            return 0.0  # do not sample
        return 1.0  # sample everything else

    sentry_sdk.init(
        dsn=_sentry_dsn,
        release=os.getenv("SENTRY_RELEASE"),
        environment=os.getenv("SENTRY_ENV", "production"),
        traces_sampler=_traces_sampler,
        profile_lifecycle="trace",
        profile_session_sample_rate=1.0,
        enable_logs=True,
        send_default_pii=True,
        debug=os.getenv("SENTRY_DEBUG", "false").lower() == "true",
    )

    from tracekit.db import patch_peewee_for_sentry

    patch_peewee_for_sentry()

app_dir = Path(__file__).parent
app = Flask(
    __name__,
    template_folder=str(app_dir / "templates"),
    static_folder=str(app_dir / "static"),
)

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 900  # 15 minutes
app.secret_key = os.environ["SESSION_KEY"]

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)


@login_manager.user_loader
def _load_user(user_id: str):
    from models.user import User

    try:
        return User.get_by_id(int(user_id))
    except Exception:
        return None


_PUBLIC_ENDPOINTS = frozenset(
    {
        "auth.login",
        "auth.signup",
        "auth.logout",
        "api.health",
        "stripe.webhook",
        "static",
    }
)


@app.before_request
def _setup_request():
    """Connect DB, set tracekit user context, enforce authentication."""
    from tracekit.user_context import set_user_id

    # Connect DB for all endpoints that may need it (skip health + static)
    if request.endpoint not in {"api.health", "static"}:
        try:
            _ensure_db_connected()
        except Exception:
            abort(503)

    # Set tracekit user context (accessing current_user triggers user_loader)
    uid = current_user.id if current_user.is_authenticated else 0
    set_user_id(uid)

    if uid and _sentry_dsn:
        import sentry_sdk

        sentry_sdk.set_user({"id": str(uid), "email": current_user.email})

    # Enforce authentication for protected endpoints
    if request.endpoint not in _PUBLIC_ENDPOINTS and (not current_user.is_authenticated or not current_user.is_active):
        return redirect(url_for("auth.login"))


@app.context_processor
def inject_sentry():
    return {
        "sentry_dsn": _sentry_dsn,
        "sentry_release": os.getenv("SENTRY_RELEASE"),
        "sentry_env": os.getenv("SENTRY_ENV", "production"),
    }


@app.after_request
def _log_request(response):
    if request.path != "/health":
        from tracekit.user_context import get_user_id

        log_record = {
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "user_id": get_user_id(),
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
        }
        logging.info(json.dumps(log_record))
    return response


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
