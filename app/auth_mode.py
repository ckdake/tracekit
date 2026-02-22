"""Single-user mode detection.

Set the ``SINGLE_USER_MODE`` environment variable to ``true``, ``1``, or ``yes``
to run the web app as a single-user instance.  In this mode:
- Login / signup / logout UI is hidden.
- All requests use ``user_id=0`` (the same pool as the CLI).
- No authentication is required to access any page.
"""

import os


def is_single_user_mode() -> bool:
    """Return True when SINGLE_USER_MODE env var is set to a truthy value."""
    return os.environ.get("SINGLE_USER_MODE", "").lower() in ("1", "true", "yes")
