"""User identity context for scoped database access.

The CLI never calls ``set_user_id()`` so it always operates on ``user_id=0``
(the unscoped / CLI-owned data pool).  The web layer calls ``set_user_id()``
in a ``before_request`` hook so every downstream read and write automatically
targets the logged-in user's rows without any changes to function signatures.

Celery tasks receive ``user_id`` as an explicit parameter and call
``set_user_id()`` as their first line so worker processes are also scoped
correctly.
"""

from contextvars import ContextVar

_current_user_id: ContextVar[int] = ContextVar("current_user_id", default=0)


def get_user_id() -> int:
    """Return the current user ID (0 = CLI / unscoped)."""
    return _current_user_id.get()


def set_user_id(uid: int) -> None:
    """Set the current user ID for this execution context."""
    _current_user_id.set(uid)
