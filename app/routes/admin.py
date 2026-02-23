"""Admin routes — user management for the admin (user id=1)."""

import json

from flask import Blueprint, abort, g, jsonify, render_template

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    """Abort with 403 if the current user is not the admin."""
    user = g.get("current_user")
    if not user or not user.is_admin:
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
                "providers": provider_info,
            }
        )

    return render_template("admin.html", page_name="Admin", user_data=user_data)


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
