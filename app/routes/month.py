"""Month sync-review routes for the tracekit web app.

Routes
------
GET  /month/<year_month>
    HTML page showing the activity comparison table and pending changes for
    the given YYYY-MM.  The page loads change data asynchronously via the API
    below.

GET  /api/month-changes/<year_month>
    Return the list of changes (as JSON) computed by tracekit.sync for the
    given month.  Each change is the dict representation of an ActivityChange.
    Also returns a ``rows`` list for rendering the comparison table.

POST /api/month-sync/apply
    Enqueue a background Celery task that applies a single change.
    Body (JSON): { "change": <ActivityChange dict>, "year_month": "YYYY-MM" }
    Returns: { "task_id": "...", "status": "queued" }
"""

import re
from datetime import datetime

from db_init import load_tracekit_config
from flask import Blueprint, jsonify, render_template, request

month_bp = Blueprint("month", __name__)

# ---------------------------------------------------------------------------
# Lazy top-level imports — these may not be available if tracekit is not
# fully installed (e.g. in unit-test environments without a Celery broker).
# Importing them here lets tests patch them without needing to mock
# builtins.__import__ or intercept intra-function import calls.
# ---------------------------------------------------------------------------

from tracekit.core import tracekit as tracekit_class
from tracekit.sync import build_comparison_rows, compute_month_changes

try:
    from tracekit.worker import apply_sync_change
except Exception:  # pragma: no cover
    apply_sync_change = None  # type: ignore[assignment]

try:
    from tracekit.notification import create_notification, expiry_timestamp
except Exception:  # pragma: no cover
    create_notification = None  # type: ignore[assignment]
    expiry_timestamp = None  # type: ignore[assignment]


@month_bp.route("/month/<year_month>")
def month_show(year_month: str):
    """Render the month sync-review page."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return "Invalid month format, expected YYYY-MM", 400

    config = load_tracekit_config()
    year, month = int(year_month[:4]), int(year_month[5:7])
    month_name = datetime(year, month, 1).strftime("%B")

    return render_template(
        "month.html",
        year_month=year_month,
        year=year,
        month=month,
        month_name=month_name,
        config=config,
        page_name=f"{month_name} {year} — Sync Review",
    )


@month_bp.route("/api/month-changes/<year_month>")
def api_month_changes(year_month: str):
    """Compute and return pending sync changes for a month as JSON."""
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400

    try:
        config = load_tracekit_config()
        provider_config = config.get("providers", {})

        with tracekit_class() as tk:
            grouped, changes = compute_month_changes(tk, year_month)
            home_tz = tk.home_tz

        provider_list, rows = build_comparison_rows(grouped, provider_config, home_tz)

        return jsonify(
            {
                "year_month": year_month,
                "provider_list": provider_list,
                "rows": rows,
                "changes": [c.to_dict() for c in changes],
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@month_bp.route("/api/month-sync/apply", methods=["POST"])
def api_apply_change():
    """Enqueue a background task to apply a single ActivityChange."""
    data = request.get_json(silent=True)
    if not data or "change" not in data or "year_month" not in data:
        return (
            jsonify({"error": "Expected JSON with 'change' and 'year_month' fields"}),
            400,
        )

    year_month = data["year_month"]
    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400

    try:
        if apply_sync_change is None:
            raise RuntimeError("Celery worker not available — is the worker running?")

        change_dict = data["change"]
        if create_notification and expiry_timestamp:
            create_notification(
                f"Sync change queued for {year_month}: {change_dict.get('change_type')}",
                category="info",
                expires=expiry_timestamp(24),
            )
        task = apply_sync_change.delay(change_dict, year_month)
        return jsonify({"task_id": task.id, "year_month": year_month, "status": "queued"})
    except Exception as exc:
        return jsonify({"error": f"Failed to enqueue task: {exc}"}), 503
