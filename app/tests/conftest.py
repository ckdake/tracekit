import os

# Prevent Sentry SDK from initialising during tests.
os.environ.pop("SENTRY_DSN", None)
os.environ.pop("SENTRY_ENV", None)

# Default to multi-user mode; individual fixtures set it explicitly when needed.
os.environ.pop("SINGLE_USER_MODE", None)
