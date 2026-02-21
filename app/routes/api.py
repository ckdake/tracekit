"""General API routes (config, database, health) for the tracekit web app."""

from db_init import _init_db, load_tracekit_config
from flask import Blueprint, jsonify, request
from helpers import get_database_info, get_most_recent_activity, get_provider_activity_counts

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/config", methods=["GET"])
def api_config():
    """Return the current configuration as JSON."""
    return jsonify(load_tracekit_config())


@api_bp.route("/api/config", methods=["PUT"])
def api_config_save():
    """Persist a new configuration to the DB."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    _init_db()
    from tracekit.appconfig import save_config

    save_config(data)
    return jsonify({"status": "saved"})


@api_bp.route("/api/database")
def api_database():
    """API endpoint for database information."""
    return jsonify(get_database_info())


@api_bp.route("/api/recent-activity")
def api_recent_activity():
    """Return the most recent activity timestamp and formatted datetime."""
    config = load_tracekit_config()
    return jsonify(get_most_recent_activity(config))


@api_bp.route("/api/provider-status")
def api_provider_status():
    """Return per-provider operational status (last op, success, rate limits)."""
    try:
        from tracekit.provider_status import get_all_statuses

        statuses = get_all_statuses()
        counts = get_provider_activity_counts()

        # Merge activity counts into each provider's status dict
        all_providers = set(statuses.keys()) | set(counts.keys())
        merged: dict = {}
        for provider in all_providers:
            entry = dict(statuses.get(provider) or {})
            entry["activity_count"] = counts.get(provider, 0)
            merged[provider] = entry

        return jsonify(merged)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "app": "tracekit-web"})
