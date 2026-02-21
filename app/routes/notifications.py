"""Notification API routes for the tracekit web app."""

from db_init import _init_db
from flask import Blueprint, jsonify

notifications_bp = Blueprint("notifications", __name__)


def _get_notifications_list() -> list[dict]:
    """Return all notifications ordered newest-first."""
    if not _init_db():
        return []
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        rows = Notification.select().order_by(Notification.created.desc())
        return [r.to_dict() for r in rows]
    except Exception as e:
        print(f"notifications list error: {e}")
        return []


@notifications_bp.route("/api/notifications")
def api_notifications():
    """Return all notifications ordered newest-first."""
    return jsonify(_get_notifications_list())


@notifications_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def api_notification_read(notification_id: int):
    """Mark a single notification as read."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        n = Notification.get_by_id(notification_id)
        n.read = True
        n.save()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
def api_notifications_read_all():
    """Mark all notifications as read."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        Notification.update(read=True).where(Notification.read == False).execute()  # noqa: E712
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@notifications_bp.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
def api_notification_delete(notification_id: int):
    """Delete a single notification."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        n = Notification.get_by_id(notification_id)
        n.delete_instance()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 404
