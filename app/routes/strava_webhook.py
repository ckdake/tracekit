"""Strava webhook endpoint and subscription management (admin)."""

import logging
import os

import requests
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

strava_webhook_bp = Blueprint("strava_webhook", __name__)

STRAVA_PUSH_SUBSCRIPTIONS_URL = "https://www.strava.com/api/v3/push_subscriptions"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _notify_admin(message: str, category: str = "info") -> None:
    """Write a notification row for the admin user (user_id=1).

    Uses a direct Notification.create rather than create_notification so that
    the webhook's own user_id context doesn't interfere.
    """
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


def _require_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def _get_strava_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env vars or admin user (id=1) config."""
    client_id = os.environ.get("STRAVA_CLIENT_ID", "").strip()
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        try:
            import json

            from tracekit.appconfig import AppConfig

            row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == 1))
            if row:
                strava_cfg = json.loads(row.value).get("strava", {})
                client_id = client_id or strava_cfg.get("client_id", "").strip()
                client_secret = client_secret or strava_cfg.get("client_secret", "").strip()
        except Exception:
            pass

    return client_id, client_secret


# ---------------------------------------------------------------------------
# Webhook verification + event handling (public — no auth required)
# ---------------------------------------------------------------------------


@strava_webhook_bp.route("/api/strava/webhook", methods=["GET"])
def webhook_verify():
    """Respond to Strava's hub challenge during subscription creation."""
    from tracekit.appconfig import get_strava_webhook_config

    hub_mode = request.args.get("hub.mode")
    hub_challenge = request.args.get("hub.challenge")
    hub_verify_token = request.args.get("hub.verify_token")

    if hub_mode != "subscribe":
        return jsonify({"error": "Invalid hub.mode"}), 400

    cfg = get_strava_webhook_config()
    expected_token = cfg.get("verify_token", "")

    if not expected_token or hub_verify_token != expected_token:
        log.warning("Strava webhook: invalid verify_token in hub challenge")
        return jsonify({"error": "Invalid verify_token"}), 403

    return jsonify({"hub.challenge": hub_challenge})


@strava_webhook_bp.route("/api/strava/webhook", methods=["POST"])
def webhook_event():
    """Handle incoming Strava webhook events."""
    try:
        event = request.get_json(force=True)
    except Exception:
        return "", 400

    if not isinstance(event, dict):
        return "", 400

    object_type = event.get("object_type")
    aspect_type = event.get("aspect_type")
    object_id = event.get("object_id")
    owner_id = event.get("owner_id")
    updates = event.get("updates", {})

    log.info(
        "Strava webhook event: object_type=%s aspect_type=%s object_id=%s owner_id=%s",
        object_type,
        aspect_type,
        object_id,
        owner_id,
    )

    if object_type == "activity":
        _handle_activity_event(aspect_type, object_id, owner_id)
    elif object_type == "athlete" and aspect_type == "update" and updates.get("authorized") == "false":
        _handle_deauthorize(owner_id)

    # Always return 200 quickly so Strava doesn't retry.
    return "", 200


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _find_user(owner_id) -> int | None:
    """Return the local user_id for a Strava athlete_id, or None."""
    from db_init import _init_db

    from tracekit.appconfig import find_user_id_by_strava_athlete_id

    try:
        _init_db()
        return find_user_id_by_strava_athlete_id(str(owner_id))
    except Exception as e:
        log.error("Strava webhook: error looking up user for owner_id=%s: %s", owner_id, e)
        return None


def _handle_activity_event(aspect_type: str, activity_id, owner_id):
    """Route activity create/update/delete to the right handler."""
    from tracekit.user_context import set_user_id

    user_id = _find_user(owner_id)
    if user_id is None:
        log.warning("Strava webhook: no user found for athlete_id=%s — ignoring", owner_id)
        _notify_admin(
            f"Strava webhook: {aspect_type} event for unknown athlete {owner_id} (activity {activity_id})", "error"
        )
        return

    set_user_id(user_id)

    try:
        if aspect_type == "delete":
            _delete_local_activity(activity_id, user_id)
        elif aspect_type in ("create", "update"):
            _sync_local_activity(activity_id, user_id)
        _notify_admin(f"Strava webhook: activity {aspect_type} — id={activity_id} user={user_id}")
    except Exception as e:
        log.error("Strava webhook: error handling %s event for activity %s: %s", aspect_type, activity_id, e)
        _notify_admin(f"Strava webhook: error on activity {aspect_type} (id={activity_id}): {e}", "error")


def _delete_local_activity(activity_id, user_id: int):
    from tracekit.providers.strava.strava_activity import StravaActivity

    deleted = (
        StravaActivity.delete()
        .where((StravaActivity.strava_id == str(activity_id)) & (StravaActivity.user_id == user_id))
        .execute()
    )
    log.info("Strava webhook: deleted %d local record(s) for strava_id=%s user_id=%d", deleted, activity_id, user_id)


def _sync_local_activity(activity_id, user_id: int):
    import json

    from tracekit.appconfig import AppConfig
    from tracekit.providers.strava.strava_provider import StravaProvider

    # Load the user's strava config directly (bypasses user_context scoping in load_config).
    row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
    if row is None:
        log.warning("Strava webhook: no config for user_id=%d", user_id)
        return

    strava_cfg = json.loads(row.value).get("strava", {})
    access_token = strava_cfg.get("access_token", "")
    if not access_token:
        log.warning("Strava webhook: no access token for user_id=%d", user_id)
        return

    provider = StravaProvider(
        token=access_token,
        refresh_token=strava_cfg.get("refresh_token", ""),
        token_expires=strava_cfg.get("token_expires", "0"),
        config=strava_cfg,
    )
    provider.sync_single_activity(str(activity_id))


def _handle_deauthorize(owner_id):
    """Disable Strava and clear tokens for the user who revoked access."""
    import json

    from tracekit.appconfig import AppConfig
    from tracekit.user_context import set_user_id

    user_id = _find_user(owner_id)
    if user_id is None:
        log.warning("Strava deauth webhook: no user found for athlete_id=%s — ignoring", owner_id)
        return

    set_user_id(user_id)

    try:
        row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
        if row is None:
            return

        providers = json.loads(row.value)
        strava_cfg = providers.get("strava", {}).copy()
        strava_cfg["enabled"] = False
        strava_cfg["access_token"] = ""
        strava_cfg["refresh_token"] = ""
        strava_cfg["token_expires"] = "0"
        providers["strava"] = strava_cfg

        (
            AppConfig.update({AppConfig.value: json.dumps(providers)})
            .where((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
            .execute()
        )
        log.info("Strava deauth: disabled provider for user_id=%d", user_id)
        _notify_admin(f"Strava webhook: user {user_id} (athlete {owner_id}) deauthorized — provider disabled", "error")
    except Exception as e:
        log.error("Strava deauth: error disabling provider for user_id=%d: %s", user_id, e)
        _notify_admin(f"Strava webhook: deauth error for user {user_id}: {e}", "error")


# ---------------------------------------------------------------------------
# Admin routes — subscription management
# ---------------------------------------------------------------------------


@strava_webhook_bp.route("/admin/strava/webhook/status")
def webhook_status():
    """Return current webhook subscription info as JSON."""
    _require_admin()

    from tracekit.appconfig import get_strava_webhook_config

    cfg = get_strava_webhook_config()
    local_sub_id = cfg.get("subscription_id")

    client_id, client_secret = _get_strava_credentials()
    strava_sub = None
    if client_id and client_secret:
        try:
            resp = requests.get(
                STRAVA_PUSH_SUBSCRIPTIONS_URL,
                params={"client_id": client_id, "client_secret": client_secret},
                timeout=10,
            )
            if resp.ok:
                subs = resp.json()
                strava_sub = subs[0] if subs else None
        except Exception as e:
            log.warning("Could not fetch Strava subscriptions from API: %s", e)

    return jsonify({"subscription_id": local_sub_id, "strava_subscription": strava_sub})


@strava_webhook_bp.route("/admin/strava/webhook/subscribe", methods=["POST"])
def webhook_subscribe():
    """Create a Strava webhook subscription for this app."""
    _require_admin()

    from tracekit.appconfig import get_or_create_strava_webhook_verify_token, save_strava_webhook_subscription_id

    client_id, client_secret = _get_strava_credentials()
    if not client_id or not client_secret:
        return jsonify({"error": "Strava client_id and client_secret not configured"}), 400

    verify_token = get_or_create_strava_webhook_verify_token()
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    callback_url = f"{scheme}://{request.host}/api/strava/webhook"

    try:
        resp = requests.post(
            STRAVA_PUSH_SUBSCRIPTIONS_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "callback_url": callback_url,
                "verify_token": verify_token,
            },
            timeout=30,
        )
        if resp.ok:
            sub_id = resp.json().get("id")
            save_strava_webhook_subscription_id(sub_id)
            return jsonify({"success": True, "subscription_id": sub_id})
        else:
            return jsonify({"error": resp.text}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@strava_webhook_bp.route("/admin/strava/webhook/unsubscribe", methods=["POST"])
def webhook_unsubscribe():
    """Delete the active Strava webhook subscription."""
    _require_admin()

    from tracekit.appconfig import get_strava_webhook_config, save_strava_webhook_subscription_id

    client_id, client_secret = _get_strava_credentials()
    if not client_id or not client_secret:
        return jsonify({"error": "Strava client_id and client_secret not configured"}), 400

    cfg = get_strava_webhook_config()
    sub_id = cfg.get("subscription_id")
    if not sub_id:
        return jsonify({"error": "No active subscription found locally"}), 400

    try:
        resp = requests.delete(
            f"{STRAVA_PUSH_SUBSCRIPTIONS_URL}/{sub_id}",
            params={"client_id": client_id, "client_secret": client_secret},
            timeout=30,
        )
        if resp.ok or resp.status_code == 404:
            save_strava_webhook_subscription_id(None)
            return jsonify({"success": True})
        else:
            return jsonify({"error": resp.text}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
