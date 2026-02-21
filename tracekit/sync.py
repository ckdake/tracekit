"""Core sync logic for comparing and reconciling activities across providers.

This module contains the data models and pure logic for:
  - Correlating activities across providers
  - Computing what changes are needed (the "diff")
  - Applying individual changes to providers

The CLI command and web UI are both thin wrappers around these functions.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, NamedTuple
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from tracekit.core import Tracekit


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ChangeType(Enum):
    UPDATE_NAME = "Update Name"
    UPDATE_EQUIPMENT = "Update Equipment"
    UPDATE_METADATA = "Update Metadata"
    ADD_ACTIVITY = "Add Activity"
    LINK_ACTIVITY = "Link Activity"


class ActivityChange(NamedTuple):
    change_type: ChangeType
    provider: str
    activity_id: str
    old_value: str | None = None
    new_value: str | None = None
    source_provider: str | None = None

    def __str__(self) -> str:
        if self.change_type == ChangeType.UPDATE_NAME:
            return (
                f"Update {self.provider} name for activity {self.activity_id} "
                f"from '{self.old_value}' to '{self.new_value}'"
            )
        elif self.change_type == ChangeType.UPDATE_EQUIPMENT:
            return (
                f"Update {self.provider} equipment for activity {self.activity_id} "
                f"from '{self.old_value}' to '{self.new_value}'"
            )
        elif self.change_type == ChangeType.UPDATE_METADATA:
            return (
                f"Update {self.provider} metadata for activity {self.activity_id} "
                f"(duration_hms: '{self.old_value}' → duration_hms: '{self.new_value}')"
            )
        elif self.change_type == ChangeType.ADD_ACTIVITY:
            return (
                f"Add activity '{self.new_value}' to {self.provider} "
                f"(from {self.source_provider} activity {self.activity_id})"
            )
        elif self.change_type == ChangeType.LINK_ACTIVITY:
            return (
                f"Link {self.provider} activity {self.activity_id} "
                f"with {self.source_provider} activity {self.new_value}"
            )
        return "Unknown change"

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe) for API / task payloads."""
        return {
            "change_type": self.change_type.value,
            "provider": self.provider,
            "activity_id": self.activity_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "source_provider": self.source_provider,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActivityChange:
        """Deserialize from a plain dict."""
        return cls(
            change_type=ChangeType(data["change_type"]),
            provider=data["provider"],
            activity_id=data["activity_id"],
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            source_provider=data.get("source_provider"),
        )


# ---------------------------------------------------------------------------
# Activity helpers
# ---------------------------------------------------------------------------


def process_activity_for_display(activity, provider: str) -> dict:
    """Process a provider-specific activity object for display/matching purposes."""
    provider_id = getattr(activity, "provider_id", None)
    start_time = getattr(activity, "start_time", None)
    timestamp = start_time if start_time else 0

    distance = getattr(activity, "distance", 0)
    if distance is None:
        distance = 0

    if provider == "spreadsheet":
        activity_name = getattr(activity, "notes", "") or ""
    else:
        activity_name = getattr(activity, "name", "") or ""

    return {
        "provider": provider,
        "id": provider_id,
        "timestamp": int(timestamp),
        "distance": float(distance),
        "obj": activity,
        "name": activity_name,
        "equipment": getattr(activity, "equipment", "") or "",
    }


def generate_correlation_key(timestamp: int, distance: float) -> str:
    """Generate a correlation key for matching activities across providers.

    Uses eastern-timezone date + distance bucket (0.5 mi resolution) so that
    activities recorded at slightly different times/distances still match.
    """
    if not timestamp or not distance:
        return ""

    try:
        dt = datetime.fromtimestamp(timestamp, ZoneInfo("US/Eastern"))
        date_str = dt.strftime("%Y-%m-%d")
        distance_bucket = round(distance * 2) / 2
        return f"{date_str}_{distance_bucket:.1f}"
    except (ValueError, TypeError):
        return ""


def convert_activity_to_spreadsheet_format(source_activity: dict, grouped_activities: dict) -> dict:
    """Convert an activity from any provider to spreadsheet row format."""
    activity_obj = source_activity["obj"]

    start_time = ""
    if source_activity["timestamp"]:
        try:
            dt = datetime.fromtimestamp(source_activity["timestamp"], ZoneInfo("US/Eastern"))
            start_time = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    garmin_id = ""
    strava_id = ""
    ridewithgps_id = ""

    correlation_key = generate_correlation_key(source_activity["timestamp"], source_activity["distance"])
    if correlation_key in grouped_activities:
        for act in grouped_activities[correlation_key]:
            if act["provider"] == "garmin":
                garmin_id = str(act["id"]) if act["id"] else ""
            elif act["provider"] == "strava":
                strava_id = str(act["id"]) if act["id"] else ""
            elif act["provider"] == "ridewithgps":
                ridewithgps_id = str(act["id"]) if act["id"] else ""

    distance = source_activity["distance"] or 0
    if distance:
        distance = round(float(distance), 2)

    activity_data = {
        "start_time": start_time,
        "activity_type": getattr(activity_obj, "activity_type", "") or "",
        "location_name": getattr(activity_obj, "location_name", "") or "",
        "city": getattr(activity_obj, "city", "") or "",
        "state": getattr(activity_obj, "state", "") or "",
        "temperature": getattr(activity_obj, "temperature", "") or "",
        "equipment": source_activity["equipment"] or "",
        "duration": getattr(activity_obj, "duration", None),
        "duration_hms": "",
        "distance": distance,
        "max_speed": getattr(activity_obj, "max_speed", "") or "",
        "avg_heart_rate": getattr(activity_obj, "avg_heart_rate", "") or "",
        "max_heart_rate": getattr(activity_obj, "max_heart_rate", "") or "",
        "calories": getattr(activity_obj, "calories", "") or "",
        "max_elevation": getattr(activity_obj, "max_elevation", "") or "",
        "total_elevation_gain": getattr(activity_obj, "total_elevation_gain", "") or "",
        "with_names": getattr(activity_obj, "with_names", "") or "",
        "avg_cadence": getattr(activity_obj, "avg_cadence", "") or "",
        "strava_id": strava_id,
        "garmin_id": garmin_id,
        "ridewithgps_id": ridewithgps_id,
        "notes": source_activity["name"] or "",
    }

    duration_seconds = getattr(activity_obj, "duration", None)
    if duration_seconds:
        try:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            activity_data["duration_hms"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except (ValueError, TypeError):
            pass

    return activity_data


# ---------------------------------------------------------------------------
# Core sync computation
# ---------------------------------------------------------------------------


def _seconds_to_hms(seconds: int) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def compute_month_changes(
    tracekit: Tracekit,
    year_month: str,
) -> tuple[dict, list[ActivityChange]]:
    """Compute all sync changes needed for *year_month*.

    Returns:
        grouped: dict mapping correlation_key → list of processed activity dicts.
            Useful for callers that want to display the activity table.
        changes: flat list of ActivityChange objects describing every update
            / addition needed to bring all providers into sync.
    """
    activities = tracekit.pull_activities(year_month)
    config = tracekit.config

    # Gather all provider activities into a flat list
    all_acts: list[dict] = []
    for provider_name, provider_activities in activities.items():
        for act in provider_activities:
            all_acts.append(process_activity_for_display(act, provider_name))

    # Group by correlation key
    grouped: dict[str, list[dict]] = defaultdict(list)
    for act in all_acts:
        key = generate_correlation_key(act["timestamp"], act["distance"])
        if key:
            grouped[key].append(act)

    # Determine provider priority from config (lower number = higher priority)
    provider_config = config.get("providers", {})
    provider_priorities = {
        name: settings.get("priority", 999)
        for name, settings in provider_config.items()
        if settings.get("enabled", False)
    }
    priority_order = sorted(provider_priorities.items(), key=lambda x: x[1])
    provider_priority = [p for p, _ in priority_order]

    all_changes: list[ActivityChange] = []

    for _key, group in grouped.items():
        if len(group) < 2:
            # Single-provider groups: nothing to sync
            continue

        by_provider = {a["provider"]: a for a in group}

        # Determine authoritative name and equipment
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

        auth_activity = by_provider[auth_provider]

        for provider in by_provider:
            sync_name = provider_config.get(provider, {}).get("sync_name", True)
            sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)
            activity = by_provider[provider]

            # ── Name sync ───────────────────────────────────────────────
            if sync_name and provider != auth_provider and auth_name:
                current_name = activity["name"]
                if current_name != auth_name:
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.UPDATE_NAME,
                            provider=provider,
                            activity_id=str(activity["id"]),
                            old_value=current_name,
                            new_value=auth_name,
                        )
                    )

            # ── Equipment sync ──────────────────────────────────────────
            if sync_equipment and provider != auth_provider and auth_equipment:
                equip_val = (activity["equipment"] or "").strip().lower()
                equip_wrong = activity["equipment"] != auth_equipment or equip_val in ("", "no equipment")
                if equip_wrong:
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.UPDATE_EQUIPMENT,
                            provider=provider,
                            activity_id=str(activity["id"]),
                            old_value=activity["equipment"],
                            new_value=auth_equipment,
                        )
                    )

            # ── Spreadsheet metadata (duration_hms) ─────────────────────
            if provider == "spreadsheet":
                current_duration_hms = getattr(activity.get("obj"), "duration_hms", "") or ""
                expected_duration_hms = ""
                duration_seconds = None

                for p in provider_priority:
                    if p != "spreadsheet" and p in by_provider:
                        obj = by_provider[p]["obj"]
                        for field in ("moving_time", "elapsed_time", "duration"):
                            val = getattr(obj, field, None)
                            if val and isinstance(val, (int, float)):
                                duration_seconds = int(val)
                                break
                        if duration_seconds:
                            break

                if duration_seconds:
                    with contextlib.suppress(ValueError, TypeError):
                        expected_duration_hms = _seconds_to_hms(duration_seconds)

                if expected_duration_hms and current_duration_hms != expected_duration_hms:
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.UPDATE_METADATA,
                            provider=provider,
                            activity_id=str(activity["id"]),
                            old_value=current_duration_hms,
                            new_value=expected_duration_hms,
                        )
                    )

        # ── Missing provider (ADD_ACTIVITY) ─────────────────────────────
        # Check which enabled providers are missing this activity
        for provider_name in provider_priority:
            if provider_name not in by_provider:
                sync_name = provider_config.get(provider_name, {}).get("sync_name", True)
                if sync_name and auth_name:
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.ADD_ACTIVITY,
                            provider=provider_name,
                            activity_id=str(auth_activity["id"]),
                            new_value=auth_name,
                            source_provider=auth_provider,
                        )
                    )

    return dict(grouped), all_changes


# ---------------------------------------------------------------------------
# Applying individual changes
# ---------------------------------------------------------------------------


def apply_change(change: ActivityChange, tracekit: Tracekit, grouped: dict | None = None) -> tuple[bool, str]:
    """Apply a single ActivityChange using the given Tracekit instance.

    Returns:
        (success, message) tuple.  *grouped* is only required for ADD_ACTIVITY.
    """
    provider = change.provider
    change_type = change.change_type

    try:
        if change_type == ChangeType.UPDATE_NAME:
            prov = tracekit.get_provider(provider)
            if not prov:
                return False, f"{provider} provider not available"

            if provider == "ridewithgps":
                ok = prov.update_activity({"ridewithgps_id": change.activity_id, "name": change.new_value})
            elif provider == "strava":
                ok = prov.update_activity({"strava_id": change.activity_id, "name": change.new_value})
            elif provider == "garmin":
                ok = prov.update_activity({"garmin_id": change.activity_id, "name": change.new_value})
            elif provider == "spreadsheet":
                ok = prov.update_activity({"spreadsheet_id": change.activity_id, "notes": change.new_value})
            else:
                return False, f"Name update not supported for provider '{provider}'"
            return (
                (True, f"Name updated for {change.activity_id}")
                if ok
                else (False, f"Name update failed for {change.activity_id}")
            )

        elif change_type == ChangeType.UPDATE_EQUIPMENT:
            prov = tracekit.get_provider(provider)
            if not prov:
                return False, f"{provider} provider not available"

            if provider in ("ridewithgps", "strava"):
                ok = prov.set_gear(change.new_value, change.activity_id)
            elif provider == "spreadsheet":
                ok = prov.update_activity({"spreadsheet_id": change.activity_id, "equipment": change.new_value})
            else:
                return False, f"Equipment update not supported for provider '{provider}'"
            return (
                (True, f"Equipment updated for {change.activity_id}")
                if ok
                else (False, f"Equipment update failed for {change.activity_id}")
            )

        elif change_type == ChangeType.UPDATE_METADATA:
            prov = tracekit.get_provider(provider)
            if not prov:
                return False, f"{provider} provider not available"
            if provider == "spreadsheet":
                ok = prov.update_activity({"spreadsheet_id": change.activity_id, "duration_hms": change.new_value})
                return (
                    (True, f"Metadata updated for {change.activity_id}")
                    if ok
                    else (False, f"Metadata update failed for {change.activity_id}")
                )
            return False, f"Metadata update not supported for provider '{provider}'"

        elif change_type == ChangeType.ADD_ACTIVITY:
            prov = tracekit.get_provider(provider)
            if not prov:
                return False, f"{provider} provider not available"
            if grouped is None:
                return False, "grouped activities dict required for ADD_ACTIVITY"

            # Find the source activity in the grouped dict
            source_activity = None
            for group in grouped.values():
                for act in group:
                    if act["provider"] == change.source_provider and str(act["id"]) == change.activity_id:
                        source_activity = act
                        break
                if source_activity:
                    break

            if not source_activity:
                return False, "Source activity not found in grouped data"

            if provider == "spreadsheet":
                activity_data = convert_activity_to_spreadsheet_format(source_activity, grouped)
                new_id = prov.create_activity(activity_data)
                if new_id:
                    return True, f"Added to spreadsheet with ID {new_id}"
                return False, "Failed to add to spreadsheet"

            return False, f"ADD_ACTIVITY not supported for provider '{provider}'"

        else:
            return False, f"Unsupported change type: {change_type}"

    except Exception as exc:
        return False, str(exc)
