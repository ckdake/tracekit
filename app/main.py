"""tracekit web application — entry point and blueprint registration."""

import json
import logging
import os
import sys
from pathlib import Path

from db_init import _init_db, load_tracekit_config
from flask import Flask, abort, g, has_request_context, redirect, request, session, url_for

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(message)s",
)

if _sentry_dsn := os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    def _traces_sampler(sampling_context):
        """
        sampling_context is a dict with keys like:
            "wsgi_environ": Flask WSGI environ
            "parent_sampled": bool
            "transaction_context": dict
        """
        wsgi_environ = sampling_context.get("wsgi_environ") or {}
        path = wsgi_environ.get("PATH_INFO", "")
        if path == "/health":
            return 0.0  # do not sample
        return 1.0  # sample everything else

    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        traces_sampler=_traces_sampler,
        profile_lifecycle="trace",
        profile_session_sample_rate=1.0,
        enable_logs=True,
        send_default_pii=True,
    )

app_dir = Path(__file__).parent
app = Flask(
    __name__,
    template_folder=str(app_dir / "templates"),
    static_folder=str(app_dir / "static"),
)

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 900  # 15 minutes
app.secret_key = os.environ["SESSION_KEY"]


@app.before_request
def _set_user_context():
    from auth_mode import is_single_user_mode

    from tracekit.user_context import set_user_id

    if is_single_user_mode():
        from types import SimpleNamespace

        set_user_id(0)
        g.current_user = SimpleNamespace(id=0, is_admin=True)
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
        return {"current_user": g.get("current_user"), "single_user_mode": True}

    return {
        "current_user": g.get("current_user"),
        "single_user_mode": False,
    }


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
def _require_auth():
    from auth_mode import is_single_user_mode

    if is_single_user_mode():
        return
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if g.get("current_user"):
        return

    return redirect(url_for("auth.login"))


@app.after_request
def _log_request(response):
    if request.path != "/health":
        log_record = {
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "user_id": g.get("uid", 0) if has_request_context() else 0,
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
