"""Calendar and sync API routes for the tracekit web app."""

import re

from calendar_data import get_single_month_data
from db_init import load_tracekit_config
from flask import Blueprint, jsonify, request

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/api/calendar")
def api_calendar_months():
    """Return sync status and activity counts for a range of months (max 12).

    Query params:
      from- start month, inclusive, YYYY-MM
      to- end month,   inclusive, YYYY-MM
    """
    from_month = request.args.get("from")
    to_month = request.args.get("to")
    if not from_month or not to_month:
        return jsonify({"error": "Required query params: from, to (YYYY-MM)"}), 400
    if not re.fullmatch(r"\d{4}-\d{2}", from_month) or not re.fullmatch(r"\d{4}-\d{2}", to_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    if from_month > to_month:
        return jsonify({"error": "'from' must be <= 'to'"}), 400

    months = []
    y, m = map(int, from_month.split("-"))
    end_y, end_m = map(int, to_month.split("-"))
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    if len(months) > 12:
        return jsonify({"error": "Range exceeds 12-month limit"}), 400

    config = load_tracekit_config()
    return jsonify({ym: get_single_month_data(config, ym) for ym in months})


@calendar_bp.route("/api/calendar/<year_month>")
def api_calendar_month(year_month: str):
    """Return sync status and activity counts for a single month."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    config = load_tracekit_config()
    return jsonify(get_single_month_data(config, year_month))


@calendar_bp.route("/api/sync/<year_month>", methods=["POST"])
def sync_month(year_month: str):
    """Enqueue a pull job for the given YYYY-MM month."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    try:
        from tracekit.user_context import get_user_id
        from tracekit.worker import pull_month

        task = pull_month.delay(year_month, user_id=get_user_id())
        return jsonify({"task_id": task.id, "year_month": year_month, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/sync/<year_month>/<provider_name>", methods=["POST"])
def sync_provider_month(year_month: str, provider_name: str):
    """Enqueue a pull job for a single provider and YYYY-MM month."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    valid_providers = {"strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"}
    if provider_name not in valid_providers:
        return jsonify({"error": f"Unknown provider: {provider_name}"}), 400
    try:
        from tracekit.provider_status import PULL_STATUS_QUEUED, is_pull_active, set_pull_status
        from tracekit.worker import pull_provider_month

        if is_pull_active(year_month, provider_name):
            return jsonify({"error": f"A pull is already active for {provider_name}/{year_month}"}), 409

        from tracekit.user_context import get_user_id

        task = pull_provider_month.delay(year_month, provider_name, user_id=get_user_id())
        set_pull_status(year_month, provider_name, PULL_STATUS_QUEUED, job_id=task.id)
        return jsonify({"task_id": task.id, "year_month": year_month, "provider": provider_name, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/sync/file", methods=["POST"])
def sync_file():
    """Enqueue a full scan of the activities data folder."""
    try:
        from tracekit.user_context import get_user_id
        from tracekit.worker import pull_file

        task = pull_file.delay(user_id=get_user_id())
        return jsonify({"task_id": task.id, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/reset/provider/<provider_name>", methods=["POST"])
def reset_provider_data(provider_name: str):
    """Enqueue a reset job for all activities from a single named provider."""
    valid_providers = {"strava", "garmin", "ridewithgps", "spreadsheet", "file", "stravajson"}
    if provider_name not in valid_providers:
        return jsonify({"error": f"Unknown provider: {provider_name}"}), 400
    try:
        from tracekit.user_context import get_user_id
        from tracekit.worker import reset_provider as reset_provider_task

        task = reset_provider_task.delay(provider_name, user_id=get_user_id())
        return jsonify({"task_id": task.id, "provider": provider_name, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/reset/<year_month>", methods=["POST"])
def reset_month(year_month: str):
    """Enqueue a reset job for the given YYYY-MM month."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    try:
        from tracekit.user_context import get_user_id
        from tracekit.worker import reset_month as reset_month_task

        task = reset_month_task.delay(year_month, user_id=get_user_id())
        return jsonify({"task_id": task.id, "year_month": year_month, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/reset", methods=["POST"])
def reset_all():
    """Enqueue a reset-all job that deletes all activities and sync records."""
    try:
        from tracekit.user_context import get_user_id
        from tracekit.worker import reset_all as reset_all_task

        task = reset_all_task.delay(user_id=get_user_id())
        return jsonify({"task_id": task.id, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@calendar_bp.route("/api/sync/status/<task_id>")
def sync_status(task_id: str):
    """Return the current state of a Celery task."""
    try:
        from celery.result import AsyncResult

        from tracekit.worker import celery_app

        result = AsyncResult(task_id, app=celery_app)
        info = None
        if result.failed():
            info = str(result.info)
        return jsonify({"task_id": task_id, "state": result.state, "info": info})
    except Exception as e:
        return jsonify({"error": str(e)}), 503
