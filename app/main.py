"""tracekit web application — entry point and blueprint registration."""

import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Sentry — initialise before anything else so all errors are captured
# ---------------------------------------------------------------------------
if _sentry_dsn := os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    def _traces_sampler(sampling_context: dict) -> float:
        if sampling_context.get("wsgi_environ", {}).get("PATH_INFO") == "/health":
            return 0.0
        return 1.0

    sentry_sdk.init(
        dsn=_sentry_dsn,
        send_default_pii=True,
        traces_sampler=_traces_sampler,
        enable_logs=True,
        profile_session_sample_rate=1.0,
        profile_lifecycle="trace",
    )

# ---------------------------------------------------------------------------
# Re-exports kept for backward-compatibility with the test suite
# ---------------------------------------------------------------------------
from calendar_data import get_sync_calendar_data  # noqa: F401
from db_init import (
    _init_db,  # noqa: F401
    load_tracekit_config,
)
from flask import Flask, abort, g, redirect, request, session, url_for

_access_log = logging.getLogger("tracekit.access")
from helpers import (
    get_current_date_in_timezone,  # noqa: F401
    get_database_info,  # noqa: F401
    sort_providers,  # noqa: F401
)

# ---------------------------------------------------------------------------
# Logging — inject user_id into every record produced by the web process
# ---------------------------------------------------------------------------


class _UserIdFilter(logging.Filter):
    """Adds ``user_id`` to every log record.

    Prefers ``g.uid`` (set per-request by ``_set_user_context``) when inside a
    Flask request context so concurrent requests on different threads each get
    their own value.  Falls back to the ContextVar for log lines emitted outside
    of a request (e.g. Celery workers, startup).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from flask import g as flask_g
            from flask import has_request_context

            if has_request_context():
                record.user_id = flask_g.get("uid", 0)
            else:
                from tracekit.user_context import get_user_id

                record.user_id = get_user_id()
        except Exception:
            record.user_id = "?"
        return True


def _configure_logging() -> None:
    """Attach the user_id filter + formatter to the root logger."""
    handler = logging.StreamHandler()
    handler.addFilter(_UserIdFilter())
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s uid=%(user_id)s %(name)s: %(message)s"))
    root = logging.getLogger()
    # Avoid duplicate handlers when the module is reloaded in tests.
    if not any(isinstance(h, logging.StreamHandler) and hasattr(h, "stream") for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_logging()


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
# Template context — inject current_user into every template
# ---------------------------------------------------------------------------


@app.before_request
def _set_user_context():
    from auth_mode import is_single_user_mode

    from tracekit.user_context import set_user_id

    # Initialise g.uid so the log filter always has a value for this request,
    # even if we return early or abort below.
    g.uid = 0

    if is_single_user_mode():
        set_user_id(0)
        return

    # Ensure the DB is initialised and connected before any route that may query
    # it — including unauthenticated routes like /login and /signup.  This
    # matters for fresh Gunicorn worker processes where _db_initialized is still
    # False.  If the DB is genuinely unavailable, abort with 503.
    try:
        from db_init import _init_db

        from tracekit.db import get_db

        _init_db()
        get_db().connect(reuse_if_open=True)
    except Exception:
        abort(503)

    uid = session.get("user_id")
    if not uid:
        # Unauthenticated request — explicitly reset to 0.  ContextVars are not
        # reset between requests in a single-threaded WSGI process, so without
        # this a previous authenticated request's user_id would bleed through.
        set_user_id(0)
        return

    try:
        import peewee
        from models.user import User

        user = User.get_by_id(uid)
        set_user_id(user.id)
        g.uid = user.id
        # Cache on g so the context processor never needs to re-query the DB.
        # Tracekit.cleanup() closes the connection before templates render, so a
        # second DB round-trip in inject_current_user() would intermittently fail.
        g.current_user = user
    except Exception as exc:
        import peewee

        if isinstance(exc, peewee.DoesNotExist):
            # The user row was deleted — log out cleanly.
            session.pop("user_id", None)
        else:
            # Any other DB error: abort rather than writing data under user_id=0.
            abort(503)


@app.context_processor
def inject_current_user():
    from auth_mode import is_single_user_mode

    single_user_mode = is_single_user_mode()
    if single_user_mode:
        return {"current_user": None, "single_user_mode": True}

    # Use the user cached by before_request — no additional DB query needed.
    current_user = g.get("current_user")
    return {"current_user": current_user, "single_user_mode": False}


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
    """Redirect unauthenticated users to /login in multi-user mode."""
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
    if request.endpoint != "api.health":
        _access_log.info("%s %s %s", request.method, request.path, response.status_code)
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
