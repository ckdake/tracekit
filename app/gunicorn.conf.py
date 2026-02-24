import logging
import os

from flask import has_request_context

accesslog = None
errorlog = "-"


def post_fork(server, worker):
    """
    Re-initialize Sentry in each Gunicorn worker.
    Adds structured logging, user_id in breadcrumbs, and filters health checks.
    """
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    from tracekit.user_context import get_user_id  # your ContextVar accessor

    # Fix root logger to emit bare JSON lines
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))

    if _sentry_dsn := os.environ.get("SENTRY_DSN"):
        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # breadcrumbs for INFO+
            event_level=logging.ERROR,  # only errors as events
        )

        # Add user_id to every breadcrumb
        def before_breadcrumb(breadcrumb, hint):
            try:
                # Only attach user_id if in request context
                if has_request_context():
                    breadcrumb["data"] = breadcrumb.get("data", {})
                    breadcrumb["data"]["user_id"] = get_user_id()
            except Exception:
                pass
            return breadcrumb

        # Filter /health from traces
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
            profile_lifecycle="trace",
            profile_session_sample_rate=1.0,
            send_default_pii=True,
        )
