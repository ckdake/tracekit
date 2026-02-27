import os

# Prevent Sentry SDK from initialising during tests.
os.environ.pop("SENTRY_DSN", None)
os.environ.pop("SENTRY_ENV", None)
