"""Gunicorn configuration for tracekit.

The critical piece here is post_fork: Sentry's background transport thread
does not survive a fork(). Without this, each worker inherits the SDK state
from the master process but has no live thread to flush transactions, so
traces are silently dropped (errors may still appear via fallback sync sends).
Calling sentry_sdk.init() again in post_fork gives each worker a fresh thread.
"""

import os


def post_fork(server, worker):
    if _sentry_dsn := os.environ.get("SENTRY_DSN"):
        import sentry_sdk

        def _traces_sampler(sampling_context):
            wsgi_environ = sampling_context.get("wsgi_environ") or {}
            path = wsgi_environ.get("PATH_INFO", "")
            if path == "/health":
                return 0.0
            return 1.0

        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            traces_sampler=_traces_sampler,
            profile_lifecycle="trace",
            profile_session_sample_rate=1.0,
            enable_logs=True,
            send_default_pii=True,
        )
