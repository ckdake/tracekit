"""Gunicorn configuration for the tracekit web app."""

import os
import sys

bind = "0.0.0.0:5000"
workers = 2
timeout = 120

# Load the app in the master process before forking workers so that
# _db_initialized is True in all workers (inherited via fork) and
# migrations never run inside a worker.
preload_app = True


def on_starting(server):
    """Run DB migrations exactly once, in the master process before workers fork."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from db_init import _init_db

    _init_db()


def post_fork(server, worker):
    """Close the master-process DB connection so each worker opens its own."""
    try:
        from tracekit.db import get_db

        db = get_db()
        if not db.is_closed():
            db.close()
    except Exception:
        pass
