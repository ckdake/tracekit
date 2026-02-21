"""Per-provider operational status tracking and typed exceptions.

Stores the last operation attempted for each provider, whether it succeeded,
and any rate-limit information (short-term vs long-term, reset timestamp).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from peewee import BooleanField, CharField, IntegerField, Model

from tracekit.db import db

# ---- constants ---------------------------------------------------------------

RATE_LIMIT_SHORT_TERM = "short_term"  # 15-minute Strava window
RATE_LIMIT_LONG_TERM = "long_term"  # daily Strava window (resets midnight UTC)


# ---- typed exception ---------------------------------------------------------


class ProviderRateLimitError(RuntimeError):
    """Raised by providers when an API rate limit is hit.

    Carries enough context for the Celery worker to decide whether to retry
    (short-term) or fail immediately (long-term) and what to record.
    """

    def __init__(
        self,
        message: str,
        provider: str,
        limit_type: str,
        reset_at: int,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.limit_type = limit_type
        self.reset_at = reset_at
        self.retry_after = retry_after  # seconds; only set for short-term


# ---- model -------------------------------------------------------------------


class ProviderStatus(Model):
    """Tracks the most recent operation result for each provider."""

    provider = CharField(unique=True)  # e.g. "strava", "ridewithgps"
    last_operation = CharField(null=True)  # e.g. "pull", "sync_name", "apply_change"
    last_operation_at = IntegerField(null=True)  # Unix timestamp
    last_success = BooleanField(null=True)  # True / False / None (never run)
    last_message = CharField(null=True, max_length=1024)
    # Rate-limit fields (Strava-specific but generic enough for others)
    rate_limit_type = CharField(null=True)  # RATE_LIMIT_SHORT_TERM | RATE_LIMIT_LONG_TERM
    rate_limit_reset_at = IntegerField(null=True)  # Unix timestamp when limit clears

    class Meta:
        database = db
        table_name = "provider_status"

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "last_operation": self.last_operation,
            "last_operation_at": self.last_operation_at,
            "last_success": self.last_success,
            "last_message": self.last_message,
            "rate_limit_type": self.rate_limit_type,
            "rate_limit_reset_at": self.rate_limit_reset_at,
        }


# ---- helpers -----------------------------------------------------------------


def _ensure_connected() -> None:
    from tracekit.db import get_db

    get_db().connect(reuse_if_open=True)


def record_operation(
    provider: str,
    operation: str,
    success: bool,
    message: str | None = None,
) -> None:
    """Upsert the status row for *provider* with the outcome of *operation*.

    Clears any stored rate-limit information on a successful call.
    Safe to call from anywhere; never raises.
    """
    try:
        _ensure_connected()
        now = int(datetime.now(UTC).timestamp())
        row, _ = ProviderStatus.get_or_create(provider=provider)
        row.last_operation = operation
        row.last_operation_at = now
        row.last_success = success
        row.last_message = (message or "")[:1024]
        if success:
            row.rate_limit_type = None
            row.rate_limit_reset_at = None
        row.save()
    except Exception as exc:
        print(f"[provider_status] failed to record operation: {exc}")


def record_rate_limit(
    provider: str,
    limit_type: str,
    reset_at: int,
    operation: str | None = None,
    message: str | None = None,
) -> None:
    """Record that *provider* hit a rate limit of *limit_type*.

    *reset_at* is the Unix timestamp when the limit clears.
    Safe to call from anywhere; never raises.
    """
    try:
        _ensure_connected()
        now = int(datetime.now(UTC).timestamp())
        row, _ = ProviderStatus.get_or_create(provider=provider)
        if operation:
            row.last_operation = operation
        row.last_operation_at = now
        row.last_success = False
        row.last_message = (message or "")[:1024]
        row.rate_limit_type = limit_type
        row.rate_limit_reset_at = reset_at
        row.save()
    except Exception as exc:
        print(f"[provider_status] failed to record rate limit: {exc}")


def get_all_statuses() -> dict[str, dict]:
    """Return {provider: status_dict} for all rows in the table."""
    try:
        _ensure_connected()
        return {row.provider: row.to_dict() for row in ProviderStatus.select()}
    except Exception as exc:
        print(f"[provider_status] failed to read statuses: {exc}")
        return {}


def next_midnight_utc() -> int:
    """Unix timestamp of the next midnight UTC (long-term rate limit reset)."""
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())
