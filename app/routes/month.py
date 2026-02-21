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
from datetime import UTC, datetime

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
from tracekit.sync import compute_month_changes

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

        # -------------------------------------------------------------------
        # Build a JSON-serialisable activity table for the UI
        # -------------------------------------------------------------------
        # Determine provider list sorted consistently
        all_providers: set[str] = set()
        for group in grouped.values():
            for act in group:
                all_providers.add(act["provider"])
        for pname, psettings in provider_config.items():
            if psettings.get("enabled", False):
                all_providers.add(pname)
        provider_list = sorted(all_providers)

        # Provider priority order
        provider_priorities = {
            name: settings.get("priority", 999)
            for name, settings in provider_config.items()
            if settings.get("enabled", False)
        }
        priority_order = sorted(provider_priorities.items(), key=lambda x: x[1])
        provider_priority = [p for p, _ in priority_order]

        rows = []
        for key, group in grouped.items():
            if len(group) < 2:
                continue

            by_provider = {a["provider"]: a for a in group}

            # Determine auth provider / name / equipment
            auth_provider = None
            auth_name = ""
            auth_equipment = ""
            for p in provider_priority:
                if p in by_provider and by_provider[p]["name"]:
                    auth_provider = p
                    auth_name = by_provider[p]["name"]
                    break
            if not auth_provider:
                for p in provider_priority:
                    if p in by_provider:
                        auth_provider = p
                        auth_name = by_provider[p]["name"]
                        break
            for p in provider_priority:
                if p in by_provider and by_provider[p]["equipment"]:
                    auth_equipment = by_provider[p]["equipment"]
                    break
            if not auth_provider:
                continue

            # Start time from the earliest activity in the group
            auth_act = by_provider[auth_provider]
            ts = min((a["timestamp"] for a in group if a["timestamp"]), default=0)
            try:
                start_local = datetime.fromtimestamp(ts, UTC).astimezone(home_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                start_local = "—"

            # Per-provider cells
            provider_cells = {}
            for pname in provider_list:
                cell: dict = {"present": False}
                if pname in by_provider:
                    act = by_provider[pname]
                    current_name = act["name"]
                    name_status = "ok"
                    if pname == auth_provider:
                        name_status = "auth"
                    elif not current_name and auth_name:
                        name_status = "missing"
                    elif current_name and current_name != auth_name and auth_name:
                        name_status = "wrong"

                    equip_val = (act["equipment"] or "").strip().lower()
                    equip_status = "ok"
                    if pname == auth_provider:
                        equip_status = "auth"
                    elif auth_equipment and (act["equipment"] != auth_equipment or equip_val in ("", "no equipment")):
                        equip_status = "missing" if equip_val in ("", "no equipment") else "wrong"

                    cell = {
                        "present": True,
                        "id": str(act["id"]),
                        "name": current_name,
                        "display_name": (current_name if name_status not in ("missing",) else auth_name),
                        "name_status": name_status,
                        "equipment": act["equipment"],
                        "display_equipment": (act["equipment"] if equip_status not in ("missing",) else auth_equipment),
                        "equip_status": equip_status,
                    }
                else:
                    cell = {
                        "present": False,
                        "id": None,
                        "display_name": auth_name,
                        "name_status": "missing",
                        "display_equipment": auth_equipment,
                        "equip_status": "missing",
                    }
                provider_cells[pname] = cell

            rows.append(
                {
                    "start": start_local,
                    "correlation_key": key,
                    "auth_provider": auth_provider,
                    "distance": round(auth_act["distance"], 2),
                    "providers": provider_cells,
                }
            )

        rows.sort(key=lambda r: r["start"])

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
