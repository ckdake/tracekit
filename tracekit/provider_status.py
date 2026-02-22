"""Per-provider operational status tracking and typed exceptions.

Stores the last operation attempted for each provider, whether it succeeded,
and any rate-limit information (short-term vs long-term, reset timestamp).

Also tracks per-(year_month, provider) pull job status so the UI can show
queued / started / success / error state for each calendar cell.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from peewee import BooleanField, CharField, IntegerField, Model

from tracekit.db import db

# ---- constants ---------------------------------------------------------------

RATE_LIMIT_SHORT_TERM = "short_term"  # 15-minute Strava window
RATE_LIMIT_LONG_TERM = "long_term"  # daily Strava window (resets midnight UTC)

PULL_STATUS_QUEUED = "queued"
PULL_STATUS_STARTED = "started"
PULL_STATUS_SUCCESS = "success"
PULL_STATUS_ERROR = "error"

_PULL_ACTIVE_STATUSES = {PULL_STATUS_QUEUED, PULL_STATUS_STARTED}


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


# ---- per-(year_month, provider) pull job status ------------------------------


class ProviderPullStatus(Model):
    """Tracks the current pull job status for each (year_month, provider) pair.

    Only one row per pair — represents current state, not history.
    """

    year_month = CharField()  # e.g. "2025-02"
    provider = CharField()  # e.g. "strava"
    status = CharField()  # queued | started | success | error
    job_id = CharField(null=True)  # Celery task ID; cleared on finish
    message = CharField(null=True, max_length=1024)  # error detail on failure
    updated_at = IntegerField(null=True)  # Unix timestamp of last update

    class Meta:
        database = db
        table_name = "provider_pull_status"
        indexes = ((("year_month", "provider"), True),)  # unique together


def set_pull_status(
    year_month: str,
    provider: str,
    status: str,
    job_id: str | None = None,
    message: str | None = None,
) -> None:
    """Upsert the pull status for (year_month, provider).

    Clears job_id automatically when status is success or error.
    Safe to call from anywhere; never raises.
    """
    try:
        _ensure_connected()
        now = int(datetime.now(UTC).timestamp())
        row, _ = ProviderPullStatus.get_or_create(
            year_month=year_month,
            provider=provider,
            defaults={"status": status, "updated_at": now},
        )
        row.status = status
        row.updated_at = now
        if status in (PULL_STATUS_SUCCESS, PULL_STATUS_ERROR):
            row.job_id = None  # done — no need to track the job any more
        elif job_id is not None:
            row.job_id = job_id
        row.message = message[:1024] if message else None
        row.save()
    except Exception as exc:
        print(f"[provider_status] failed to set pull status: {exc}")


def get_month_pull_statuses(year_month: str) -> dict[str, dict]:
    """Return {provider: status_dict} for all pull status rows in *year_month*."""
    try:
        _ensure_connected()
        rows = ProviderPullStatus.select().where(ProviderPullStatus.year_month == year_month)
        return {
            row.provider: {
                "status": row.status,
                "job_id": row.job_id,
                "message": row.message,
                "updated_at": row.updated_at,
            }
            for row in rows
        }
    except Exception as exc:
        print(f"[provider_status] failed to get month pull statuses: {exc}")
        return {}


def is_pull_active(year_month: str, provider: str) -> bool:
    """Return True if a pull is currently queued or in-progress for (year_month, provider).

    Returns False on any exception so a DB error never permanently blocks enqueuing.
    """
    try:
        _ensure_connected()
        row = ProviderPullStatus.get_or_none(
            (ProviderPullStatus.year_month == year_month) & (ProviderPullStatus.provider == provider)
        )
        return row is not None and row.status in _PULL_ACTIVE_STATUSES
    except Exception as exc:
        print(f"[provider_status] failed to check pull active: {exc}")
        return False


# ---- per-month sync review status --------------------------------------------

MONTH_SYNC_UNKNOWN = "unknown"  # not yet computed (or invalidated)
MONTH_SYNC_SYNCED = "synced"  # computed — no changes needed
MONTH_SYNC_REQUIRES_ACTION = "requires_action"  # computed — changes pending


class MonthSyncStatus(Model):
    """Stores the computed sync-review result for each year_month.

    Written when the sync-review page is visited; reset to 'unknown' whenever
    activity data for the month changes (pull started or change applied).
    """

    year_month = CharField(unique=True)  # e.g. "2025-02"
    status = CharField(default=MONTH_SYNC_UNKNOWN)  # unknown | synced | requires_action
    updated_at = IntegerField(null=True)  # Unix timestamp of last update

    class Meta:
        database = db
        table_name = "month_sync_status"


def set_month_sync_status(year_month: str, status: str) -> None:
    """Upsert the sync-review status for *year_month*.

    Safe to call from anywhere; never raises.
    """
    try:
        _ensure_connected()
        now = int(datetime.now(UTC).timestamp())
        row, _ = MonthSyncStatus.get_or_create(
            year_month=year_month,
            defaults={"status": status, "updated_at": now},
        )
        row.status = status
        row.updated_at = now
        row.save()
    except Exception as exc:
        print(f"[provider_status] failed to set month sync status: {exc}")


def get_month_sync_status(year_month: str) -> str:
    """Return the stored sync-review status for *year_month*, defaulting to 'unknown'."""
    try:
        _ensure_connected()
        row = MonthSyncStatus.get_or_none(MonthSyncStatus.year_month == year_month)
        return row.status if row else MONTH_SYNC_UNKNOWN
    except Exception as exc:
        print(f"[provider_status] failed to get month sync status: {exc}")
        return MONTH_SYNC_UNKNOWN
