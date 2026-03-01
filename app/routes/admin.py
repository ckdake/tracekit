"""Admin routes — user management for the admin (user id=1)."""

import json

from flask import Blueprint, abort, jsonify, redirect, render_template, session, url_for
from flask_login import current_user, login_user

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    """Abort with 403 if the current user is not the admin."""
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def _get_user_providers(user_id: int) -> dict:
    """Return {provider_name: enabled} for a given user from their AppConfig."""
    try:
        from tracekit.appconfig import AppConfig

        row = AppConfig.get_or_none((AppConfig.key == "providers") & (AppConfig.user_id == user_id))
        if row:
            return {name: cfg.get("enabled", False) for name, cfg in json.loads(row.value).items()}
    except Exception:
        pass
    return {}


def _get_user_activity_counts(user_id: int) -> dict:
    """Return {provider_name: count} for a given user across all provider tables."""
    try:
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
        from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
        from tracekit.providers.strava.strava_activity import StravaActivity
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        models = {
            "strava": StravaActivity,
            "garmin": GarminActivity,
            "ridewithgps": RideWithGPSActivity,
            "spreadsheet": SpreadsheetActivity,
            "file": FileActivity,
            "stravajson": StravaJsonActivity,
        }
        return {name: model.select().where(model.user_id == user_id).count() for name, model in models.items()}
    except Exception:
        return {}


@admin_bp.route("/admin")
def index():
    """Admin dashboard — list all users."""
    _require_admin()

    from models.user import User

    users = list(User.select().order_by(User.id))
    user_data = []
    for u in users:
        providers = _get_user_providers(u.id)
        counts = _get_user_activity_counts(u.id)
        # Merge: only show providers that are enabled or have activities
        provider_info = {}
        for name in set(list(providers.keys()) + list(counts.keys())):
            provider_info[name] = {
                "enabled": providers.get(name, False),
                "count": counts.get(name, 0),
            }
        user_data.append(
            {
                "id": u.id,
                "email": u.email,
                "status": u.status,
                "is_admin": u.is_admin,
                "allow_impersonation": u.allow_impersonation,
                "providers": provider_info,
                "subscription_status": u.stripe_subscription_status,
            }
        )

    from flask import request

    from tracekit.appconfig import get_strava_webhook_config, get_system_providers

    system_providers = get_system_providers()
    strava_webhook_cfg = get_strava_webhook_config()

    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    base_url = f"{scheme}://{request.host}"

    return render_template(
        "admin.html",
        page_name="Admin",
        user_data=user_data,
        system_providers=system_providers,
        strava_webhook_subscription_id=strava_webhook_cfg.get("subscription_id"),
        strava_webhook_url=f"{base_url}/api/strava/webhook",
        rwgps_webhook_url=f"{base_url}/api/ridewithgps/webhook",
    )


@admin_bp.route("/admin/providers/<provider>/toggle", methods=["POST"])
def toggle_provider(provider: str):
    """Toggle global visibility of a provider. Returns JSON."""
    _require_admin()

    from tracekit.appconfig import ALL_PROVIDERS, get_system_providers, save_system_providers

    if provider not in ALL_PROVIDERS:
        return jsonify({"error": "Unknown provider"}), 400

    providers = get_system_providers()
    providers[provider] = not providers.get(provider, True)
    save_system_providers(providers)
    return jsonify({"provider": provider, "enabled": providers[provider]})


@admin_bp.route("/admin/sentry-test")
def sentry_test():
    """Deliberately raise an exception to verify Sentry is wired up correctly."""
    _require_admin()
    raise RuntimeError("Sentry test error triggered from admin page")


@admin_bp.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
def toggle_user(user_id: int):
    """Toggle a user's status between active and blocked. Returns JSON."""
    _require_admin()

    from models.user import User

    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify({"error": "User not found"}), 404

    if user.is_admin:
        return jsonify({"error": "Cannot change admin status"}), 400

    user.status = "blocked" if user.status == "active" else "active"
    user.save()
    return jsonify({"status": user.status})


@admin_bp.route("/admin/users/<int:user_id>/impersonate", methods=["POST"])
def impersonate_user(user_id: int):
    """Begin impersonating a user. Stores admin's ID in session and switches login."""
    _require_admin()

    from models.user import User

    try:
        target = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)

    if not target.allow_impersonation:
        abort(403)

    session["original_user_id"] = current_user.id
    session["is_impersonating"] = True
    login_user(target)
    return redirect(url_for("pages.index"))


@admin_bp.route("/admin/impersonation/end", methods=["POST"])
def end_impersonation():
    """End an active impersonation session and return to the admin account."""
    if not session.get("is_impersonating"):
        abort(400)

    from models.user import User

    original_id = session.pop("original_user_id", None)
    session.pop("is_impersonating", None)

    if original_id:
        try:
            admin = User.get_by_id(original_id)
            login_user(admin)
        except User.DoesNotExist:
            pass

    return redirect(url_for("admin.index"))
