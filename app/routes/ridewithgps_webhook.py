"""RideWithGPS webhook endpoint."""

import hashlib
import hmac
import json
import logging
import os

from flask import Blueprint, request

ridewithgps_webhook_bp = Blueprint("ridewithgps_webhook", __name__)

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


def _get_rwgps_client_secret() -> str:
    """Return the RideWithGPS client secret used for HMAC signature verification.

    Checks env var first, then falls back to the admin user's (id=1) saved config.
    """
    secret = os.environ.get("RIDEWITHGPS_CLIENT_SECRET", "").strip()
    if not secret:
        try:
            from tracekit.appconfig import AppConfig

            row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == 1))
            if row:
                rwgps_cfg = json.loads(row.value).get("ridewithgps", {})
                secret = rwgps_cfg.get("client_secret", "").strip()
        except Exception:
            pass
    return secret


def _verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Validate the x-rwgps-signature HMAC-SHA256 header."""
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _find_user(rwgps_user_id) -> int | None:
    """Return the local user_id for a RideWithGPS user_id, or None."""
    from db_init import _init_db

    from tracekit.appconfig import find_user_id_by_rwgps_user_id

    try:
        _init_db()
        return find_user_id_by_rwgps_user_id(str(rwgps_user_id))
    except Exception as e:
        log.error("RideWithGPS webhook: error looking up user for rwgps_user_id=%s: %s", rwgps_user_id, e)
        return None


# ---------------------------------------------------------------------------
# Webhook event handler (public — no auth required)
# ---------------------------------------------------------------------------


@ridewithgps_webhook_bp.route("/api/ridewithgps/webhook", methods=["POST"])
def webhook_event():
    """Handle incoming RideWithGPS webhook notifications."""
    raw_body = request.get_data()

    # Verify HMAC-SHA256 signature when a client secret is configured.
    secret = _get_rwgps_client_secret()
    if secret:
        signature = request.headers.get("x-rwgps-signature", "")
        if not signature or not _verify_signature(raw_body, signature, secret):
            log.warning("RideWithGPS webhook: invalid or missing signature — rejected")
            return "", 403
    else:
        log.warning("RideWithGPS webhook: no client secret configured, skipping signature verification")

    try:
        payload = json.loads(raw_body)
    except Exception:
        return "", 400

    notifications = payload.get("notifications", [])
    if not isinstance(notifications, list):
        return "", 400

    for notification in notifications:
        try:
            _handle_notification(notification)
        except Exception as e:
            log.error("RideWithGPS webhook: unhandled error for notification %s: %s", notification, e)

    # Always return 200 quickly — RWGPS has no retry mechanism.
    return "", 200


# ---------------------------------------------------------------------------
# Notification handlers
# ---------------------------------------------------------------------------


def _handle_notification(notification: dict) -> None:
    """Route a single RideWithGPS notification to the right handler."""
    from tracekit.user_context import set_user_id

    item_type = notification.get("item_type")
    item_id = notification.get("item_id")
    action = notification.get("action")
    rwgps_user_id = notification.get("user_id")

    log.info(
        "RideWithGPS webhook: item_type=%s action=%s item_id=%s rwgps_user_id=%s",
        item_type,
        action,
        item_id,
        rwgps_user_id,
    )

    # Only trip events are meaningful for activity sync.
    if item_type != "trip":
        log.debug("RideWithGPS webhook: ignoring non-trip item_type=%s", item_type)
        return

    user_id = _find_user(rwgps_user_id)
    if user_id is None:
        log.warning("RideWithGPS webhook: no local user found for rwgps_user_id=%s — ignoring", rwgps_user_id)
        _notify_admin(
            f"RideWithGPS webhook: {action} event for unknown RWGPS user {rwgps_user_id} (trip {item_id})",
            "error",
        )
        return

    set_user_id(user_id)

    try:
        if action == "deleted":
            _delete_local_trip(item_id, user_id)
        elif action in ("created", "updated"):
            _sync_local_trip(item_id, user_id)
        else:
            log.debug("RideWithGPS webhook: no action taken for action=%s", action)
            return
        _notify_admin(f"RideWithGPS webhook: trip {action} — id={item_id} user={user_id}")
    except Exception as e:
        log.error("RideWithGPS webhook: error handling %s event for trip %s: %s", action, item_id, e)
        _notify_admin(f"RideWithGPS webhook: error on trip {action} (id={item_id}): {e}", "error")


def _delete_local_trip(trip_id, user_id: int) -> None:
    from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity

    deleted = (
        RideWithGPSActivity.delete()
        .where((RideWithGPSActivity.ridewithgps_id == str(trip_id)) & (RideWithGPSActivity.user_id == user_id))
        .execute()
    )
    log.info("RideWithGPS webhook: deleted %d local record(s) for trip_id=%s user_id=%d", deleted, trip_id, user_id)


def _sync_local_trip(trip_id, user_id: int) -> None:
    from tracekit.appconfig import AppConfig
    from tracekit.providers.ridewithgps.ridewithgps_provider import RideWithGPSProvider

    row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
    if row is None:
        log.warning("RideWithGPS webhook: no config for user_id=%d", user_id)
        return

    rwgps_cfg = json.loads(row.value).get("ridewithgps", {})
    access_token = rwgps_cfg.get("access_token", "")
    if not access_token:
        log.warning("RideWithGPS webhook: no access token for user_id=%d", user_id)
        return

    provider = RideWithGPSProvider(config=rwgps_cfg)
    provider.sync_single_activity(str(trip_id))
