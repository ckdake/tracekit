"""Intervals.icu webhook endpoint."""

import json
import logging

from flask import Blueprint, request

intervalsicu_webhook_bp = Blueprint("intervalsicu_webhook", __name__)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _notify_admin(message: str, category: str = "info") -> None:
    """Write a notification row for the admin user (user_id=1)."""
    try:
        from datetime import UTC, datetime

        from db_init import _init_db

        from tracekit.notification import Notification

        _init_db()
        Notification.create(
            message=message,
            category=category,
            created=int(datetime.now(UTC).timestamp()),
            expires=None,
            user_id=1,
        )
    except Exception as e:
        log.warning("_notify_admin failed: %s", e)


def _find_user(athlete_id) -> int | None:
    """Return the local user_id for an Intervals.icu athlete_id, or None."""
    from db_init import _init_db

    from tracekit.appconfig import find_user_id_by_intervalsicu_athlete_id

    try:
        _init_db()
        return find_user_id_by_intervalsicu_athlete_id(str(athlete_id))
    except Exception as e:
        log.error(
            "Intervals.icu webhook: error looking up user for athlete_id=%s: %s",
            athlete_id,
            e,
        )
        return None


# ---------------------------------------------------------------------------
# Webhook event handler (public — no auth required)
# ---------------------------------------------------------------------------


@intervalsicu_webhook_bp.route("/api/intervalsicu/webhook", methods=["POST"])
def webhook_event():
    """Handle incoming Intervals.icu webhook notifications."""
    try:
        payload = request.get_json(force=True)
    except Exception:
        return "", 400

    if not isinstance(payload, dict):
        return "", 400

    try:
        _handle_event(payload)
    except Exception as e:
        log.error("Intervals.icu webhook: unhandled error: %s", e)
        _notify_admin(f"Intervals.icu webhook: unhandled error: {e}", "error")

    return "", 200


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------


def _handle_event(payload: dict) -> None:
    """Route an Intervals.icu webhook event to the right handler."""
    from tracekit.user_context import set_user_id

    # Intervals.icu webhook payload shape:
    # { "athlete_id": "...", "id": "<activity_id>", "action": "created"|"updated"|"deleted" }
    athlete_id = payload.get("athlete_id")
    activity_id = payload.get("id")
    action = payload.get("action")

    log.info(
        "Intervals.icu webhook: action=%s activity_id=%s athlete_id=%s",
        action,
        activity_id,
        athlete_id,
    )

    if not athlete_id or not activity_id:
        log.debug("Intervals.icu webhook: missing athlete_id or activity_id — ignoring")
        return

    user_id = _find_user(athlete_id)
    if user_id is None:
        log.warning(
            "Intervals.icu webhook: no local user found for athlete_id=%s — ignoring",
            athlete_id,
        )
        _notify_admin(
            f"Intervals.icu webhook: {action} event for unknown athlete {athlete_id} (activity {activity_id})",
            "error",
        )
        return

    set_user_id(user_id)

    try:
        if action == "deleted":
            _delete_local_activity(activity_id, user_id)
        elif action in ("created", "updated"):
            _sync_local_activity(activity_id, user_id)
        else:
            log.debug("Intervals.icu webhook: no action taken for action=%s", action)
            return
        _notify_admin(f"Intervals.icu webhook: activity {action} — id={activity_id} user={user_id}")
    except Exception as e:
        log.error(
            "Intervals.icu webhook: error handling %s for activity %s: %s",
            action,
            activity_id,
            e,
        )
        _notify_admin(
            f"Intervals.icu webhook: error on activity {action} (id={activity_id}): {e}",
            "error",
        )


def _delete_local_activity(activity_id, user_id: int) -> None:
    from tracekit.providers.intervalsicu.intervalsicu_activity import (
        IntervalsICUActivity,
    )

    deleted = (
        IntervalsICUActivity.delete()
        .where((IntervalsICUActivity.intervalsicu_id == str(activity_id)) & (IntervalsICUActivity.user_id == user_id))
        .execute()
    )
    log.info(
        "Intervals.icu webhook: deleted %d local record(s) for activity_id=%s user_id=%d",
        deleted,
        activity_id,
        user_id,
    )


def _sync_local_activity(activity_id, user_id: int) -> None:
    from tracekit.appconfig import AppConfig
    from tracekit.providers.intervalsicu.intervalsicu_provider import (
        IntervalsICUProvider,
    )

    row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
    if row is None:
        log.warning("Intervals.icu webhook: no config for user_id=%d", user_id)
        _notify_admin(
            f"Intervals.icu webhook: no provider config for user {user_id} (activity {activity_id})",
            "error",
        )
        return

    icu_cfg = json.loads(row.value).get("intervalsicu", {})
    access_token = icu_cfg.get("access_token", "")
    if not access_token:
        log.warning("Intervals.icu webhook: no access token for user_id=%d", user_id)
        _notify_admin(
            f"Intervals.icu webhook: no access token for user {user_id} (activity {activity_id})",
            "error",
        )
        return

    provider = IntervalsICUProvider(config=icu_cfg)
    provider.sync_single_activity(str(activity_id))
