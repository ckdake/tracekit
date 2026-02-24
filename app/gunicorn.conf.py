"""
Gunicorn configuration for Tracekit — production-safe Sentry + structured JSON logging.

Key points:
1. post_fork ensures each worker has a fresh Sentry SDK background thread.
2. Clears root handlers so our JSON logs are clean and not prefixed by Gunicorn.
3. Adds user_id to Sentry breadcrumbs.
4. Skips /health endpoints for traces, transactions, and profiling.
"""

import logging
import os

# -------------------------
# Gunicorn access log
# -------------------------
# We emit our own JSON logs in main.py's _log_request, so disable Gunicorn's default.
accesslog = None


# -------------------------
# Worker post-fork hook
# -------------------------
def post_fork(server, worker):
    """
    Called after each Gunicorn worker is forked.
    Sets up Sentry and logging correctly in the worker.
    """
    # 1. Clean and configure root logger for JSON logs
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))  # bare JSON lines
    root.addHandler(handler)

    # 2. Initialize Sentry in the worker
    if _sentry_dsn := os.environ.get("SENTRY_DSN"):
        import sentry_sdk
        from flask import has_request_context
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        from app import app
        from tracekit.user_context import get_user_id

        # Logging integration: breadcrumbs for INFO, errors as events
        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # capture log breadcrumbs
            event_level=logging.ERROR,  # errors are sent as events
        )

        # Attach user_id to all breadcrumbs
        def before_breadcrumb(breadcrumb, hint):
            try:
                if has_request_context():
                    breadcrumb["data"] = breadcrumb.get("data", {})
                    breadcrumb["data"]["user_id"] = get_user_id()
            except Exception:
                pass
            return breadcrumb

        # Skip traces/profiling for /health
        def traces_sampler(sampling_context):
            wsgi_environ = sampling_context.get("wsgi_environ") or {}
            path = wsgi_environ.get("PATH_INFO", "")
            if path == "/health":
                return 0.0
            return 1.0

        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            integrations=[sentry_logging],
            traces_sampler=traces_sampler,
            before_breadcrumb=before_breadcrumb,
            enable_logs=True,
            send_default_pii=True,
            profile_session_sample_rate=1.0,
            profile_lifecycle="trace",
            debug=True,  # optional, remove in high-volume production
        )

        app.wsgi_app = FlaskIntegration().wsgi_middleware(app.wsgi_app)

    logging.info("Worker post_fork: Sentry initialized and logging configured")
