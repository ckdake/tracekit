"""Root conftest for the app test suite.

Sets required environment variables before any test module imports main.py,
which reads SESSION_KEY at module load time.
"""

import os

os.environ.setdefault("SESSION_KEY", "test-session-key-not-for-production")
