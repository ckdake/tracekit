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
from datetime import UTC, datetime
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
    DOWNLOAD_FROM_GARMIN = "Download Source File"
    DOWNLOAD_FROM_RIDEWITHGPS = "Download Source File from RideWithGPS"
    DOWNLOAD_FROM_INTERVALSICU = "Download Source File from Intervals.icu"


class ActivityChange(NamedTuple):
    change_type: ChangeType
    provider: str
    activity_id: str
    old_value: str | None = None
    new_value: str | None = None
    source_provider: str | None = None
    stale: bool = False  # True when write-only provider data is >7 days old (current state unknown)

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
        elif self.change_type == ChangeType.DOWNLOAD_FROM_GARMIN:
            return (
                f"Download source file from Garmin for activity {self.activity_id} "
                f"('{self.new_value}') to file provider"
            )
        elif self.change_type == ChangeType.DOWNLOAD_FROM_RIDEWITHGPS:
            return (
                f"Download source file from RideWithGPS for activity {self.activity_id} "
                f"('{self.new_value}') to file provider"
            )
        elif self.change_type == ChangeType.DOWNLOAD_FROM_INTERVALSICU:
            return (
                f"Download source file from Intervals.icu for activity {self.activity_id} "
                f"('{self.new_value}') to file provider"
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
            "stale": self.stale,
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
            stale=data.get("stale", False),
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


def generate_correlation_keys(timestamp: int, distance: float) -> tuple[str, str]:
    """Generate a pair of correlation keys for matching activities across providers.

    Returns (fine_key, coarse_key):
      - fine_key:   200 m buckets (boundaries at 100 m intervals)
      - coarse_key: 2000 m buckets (boundaries at 1000 m intervals)

    Two activities are considered the same if they share at least one key.
    Using two resolutions eliminates the boundary-straddling problem: GPS
    variance across providers is ~30 m, so two readings of the same activity
    can only straddle a fine-key (100 m) boundary — and the coarse key
    catches that case, since the coarse boundaries are 1000 m apart.
    """
    if not timestamp or not distance:
        return "", ""

    try:
        dt = datetime.fromtimestamp(timestamp, ZoneInfo("US/Eastern"))
        date_str = dt.strftime("%Y-%m-%d")
        dist_m = float(distance) * 1609.344
        fine = round(dist_m / 200) * 200
        coarse = round(dist_m / 2000) * 2000
        return f"{date_str}_f_{int(fine)}", f"{date_str}_c_{int(coarse)}"
    except (ValueError, TypeError):
        return "", ""


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

    fine_key, coarse_key = generate_correlation_keys(source_activity["timestamp"], source_activity["distance"])
    # Fast path: canonical fine key (covers 99% of cases).
    group = grouped_activities.get(fine_key) or []
    # Slow path: scan for coarse key match (boundary-straddling activities where
    # the canonical group is stored under a different fine key).
    if not group and coarse_key:
        for acts_in_group in grouped_activities.values():
            for act in acts_in_group:
                _, act_coarse = generate_correlation_keys(act.get("timestamp"), act.get("distance"))
                if act_coarse == coarse_key:
                    group = acts_in_group
                    break
            if group:
                break
    for act in group:
        provider = act["provider"]
        if provider == "garmin":
            garmin_id = str(act["id"]) if act["id"] else ""
        elif provider == "strava":
            strava_id = str(act["id"]) if act["id"] else ""
        elif provider == "ridewithgps":
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

    provider_config = config.get("providers", {})

    # Providers flagged write_only (e.g. Strava per their API TOS) may never be
    # authoritative sources for other providers.  Their data is also subject to a
    # 7-day freshness window: stale records are excluded from correlation so that
    # activities won't be wrongly matched against data that may have drifted.
    _write_only_freshness_days = 7
    write_only_providers = {name for name, cfg in provider_config.items() if cfg.get("write_only", False)}

    _now = datetime.now(UTC)

    # Gather all provider activities into a flat list, excluding stale write-only data.
    all_acts: list[dict] = []
    for provider_name, provider_activities in activities.items():
        is_write_only = provider_name in write_only_providers
        for act in provider_activities:
            if is_write_only:
                updated_at = getattr(act, "updated_at", None)
                if updated_at is not None:
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=UTC)
                    if (_now - updated_at).days >= _write_only_freshness_days:
                        continue  # too stale for matching
            all_acts.append(process_activity_for_display(act, provider_name))

    # Group by fine key first (one entry per fine-key cluster).
    fine_grouped: dict[str, list[dict]] = defaultdict(list)
    for act in all_acts:
        fine_key, _ = generate_correlation_keys(act["timestamp"], act["distance"])
        if fine_key:
            fine_grouped[fine_key].append(act)

    # Detect boundary-straddling activities: two fine-key groups that share a
    # coarse key mean the same physical activity was split across a fine boundary.
    coarse_to_fines: dict[str, set[str]] = defaultdict(set)
    for act in all_acts:
        fine_key, coarse_key = generate_correlation_keys(act["timestamp"], act["distance"])
        if fine_key and coarse_key:
            coarse_to_fines[coarse_key].add(fine_key)

    # Union-find: merge fine-key groups that share a coarse key.
    _parent: dict[str, str] = {}

    def _resolve(fk: str) -> str:
        root = fk
        while _parent.get(root, root) != root:
            root = _parent[root]
        node = fk
        while _parent.get(node, node) != root:
            nxt = _parent.get(node, node)
            _parent[node] = root
            node = nxt
        return root

    for fine_keys in coarse_to_fines.values():
        if len(fine_keys) > 1:
            fk_list = sorted(fine_keys)
            canon = _resolve(fk_list[0])
            for fk in fk_list[1:]:
                r = _resolve(fk)
                if r != canon:
                    _parent[r] = canon

    # Build final grouped dict: one entry per physical group (canonical fine key).
    grouped_dd: dict[str, list[dict]] = defaultdict(list)
    seen_ak: set[tuple] = set()
    for fine_key, acts in fine_grouped.items():
        canon = _resolve(fine_key)
        for act in acts:
            ak = (act["provider"], str(act["id"]))
            if ak not in seen_ak:
                seen_ak.add(ak)
                grouped_dd[canon].append(act)
    grouped: dict[str, list[dict]] = dict(grouped_dd)

    # Determine provider priority from config (lower number = higher priority)
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

        # Determine authoritative name and equipment.
        # Write-only providers (e.g. Strava) are never the authority — they can
        # only receive updates from authoritative providers, never drive them.
        auth_provider = None
        auth_name = ""
        auth_equipment = ""

        for p in provider_priority:
            if p in by_provider and by_provider[p]["name"] and p not in write_only_providers:
                auth_provider = p
                auth_name = by_provider[p]["name"]
                break

        if not auth_provider:
            for p in provider_priority:
                if p in by_provider and p not in write_only_providers:
                    auth_provider = p
                    auth_name = by_provider[p]["name"]
                    break

        for p in provider_priority:
            if p in by_provider and by_provider[p]["equipment"] and p not in write_only_providers:
                auth_equipment = by_provider[p]["equipment"]
                break

        if not auth_provider:
            continue

        auth_activity = by_provider[auth_provider]

        # Strip leading/trailing whitespace from the authoritative name so all
        # providers (including the authority itself) converge on the clean value.
        auth_name_stripped = (auth_name or "").strip()

        for provider in by_provider:
            sync_name = provider_config.get(provider, {}).get("sync_name", True)
            sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)
            activity = by_provider[provider]

            # ── Name sync ───────────────────────────────────────────────
            if sync_name and auth_name_stripped:
                current_name = activity["name"]
                # For the authoritative provider, only suggest an update if its
                # own name has leading/trailing spaces (no cross-provider diff).
                # For every other provider, compare against the stripped name.
                if provider == auth_provider:
                    if auth_name != auth_name_stripped:
                        all_changes.append(
                            ActivityChange(
                                change_type=ChangeType.UPDATE_NAME,
                                provider=provider,
                                activity_id=str(activity["id"]),
                                old_value=auth_name,
                                new_value=auth_name_stripped,
                            )
                        )
                    continue
                if current_name != auth_name_stripped:
                    # For write-only providers, flag if the stored data is stale so
                    # the UI can warn that the current remote state is unknown.
                    is_stale = provider in write_only_providers and (
                        (obj_updated := getattr(activity.get("obj"), "updated_at", None)) is not None
                        and (_now - (obj_updated if obj_updated.tzinfo else obj_updated.replace(tzinfo=UTC))).days
                        >= _write_only_freshness_days
                    )
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.UPDATE_NAME,
                            provider=provider,
                            activity_id=str(activity["id"]),
                            old_value=current_name,
                            new_value=auth_name_stripped,
                            stale=is_stale,
                        )
                    )

            # ── Equipment sync ──────────────────────────────────────────
            if sync_equipment and provider != auth_provider and auth_equipment:
                equip_val = (activity["equipment"] or "").strip().lower()
                equip_wrong = activity["equipment"] != auth_equipment or equip_val in (
                    "",
                    "no equipment",
                )
                if equip_wrong:
                    is_stale = provider in write_only_providers and (
                        (obj_updated := getattr(activity.get("obj"), "updated_at", None)) is not None
                        and (_now - (obj_updated if obj_updated.tzinfo else obj_updated.replace(tzinfo=UTC))).days
                        >= _write_only_freshness_days
                    )
                    all_changes.append(
                        ActivityChange(
                            change_type=ChangeType.UPDATE_EQUIPMENT,
                            provider=provider,
                            activity_id=str(activity["id"]),
                            old_value=activity["equipment"],
                            new_value=auth_equipment,
                            stale=is_stale,
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
        # Check which enabled providers are missing this activity.
        # Write-only providers cannot be the source of an ADD_ACTIVITY —
        # activities originating in Strava must never propagate outward.
        if auth_provider in write_only_providers:
            continue
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

    # Suggest downloading source files from Garmin when garmin has an activity
    # but the file provider has no corresponding file.  Only when both providers
    # are enabled and connected.
    if "garmin" in provider_priorities and "file" in provider_priorities:
        for _key, group in grouped.items():
            by_provider = {a["provider"]: a for a in group}
            if "garmin" in by_provider and "file" not in by_provider:
                garmin_act = by_provider["garmin"]
                all_changes.append(
                    ActivityChange(
                        change_type=ChangeType.DOWNLOAD_FROM_GARMIN,
                        provider="file",
                        activity_id=str(garmin_act["id"]),
                        new_value=garmin_act["name"],
                        source_provider="garmin",
                    )
                )

    # Same for RideWithGPS.
    if "ridewithgps" in provider_priorities and "file" in provider_priorities:
        for _key, group in grouped.items():
            by_provider = {a["provider"]: a for a in group}
            if "ridewithgps" in by_provider and "file" not in by_provider:
                rwgps_act = by_provider["ridewithgps"]
                all_changes.append(
                    ActivityChange(
                        change_type=ChangeType.DOWNLOAD_FROM_RIDEWITHGPS,
                        provider="file",
                        activity_id=str(rwgps_act["id"]),
                        new_value=rwgps_act["name"],
                        source_provider="ridewithgps",
                    )
                )

    # Same for Intervals.icu — but skip activities that were imported from Strava
    # because the /activity/{id}/file endpoint does not support them.
    if "intervalsicu" in provider_priorities and "file" in provider_priorities:
        for _key, group in grouped.items():
            by_provider = {a["provider"]: a for a in group}
            if "intervalsicu" in by_provider and "file" not in by_provider:
                icu_act = by_provider["intervalsicu"]
                act_obj = icu_act.get("obj")
                act_source = (getattr(act_obj, "source", None) or "").upper()
                if act_source == "STRAVA":
                    continue
                all_changes.append(
                    ActivityChange(
                        change_type=ChangeType.DOWNLOAD_FROM_INTERVALSICU,
                        provider="file",
                        activity_id=str(icu_act["id"]),
                        new_value=icu_act["name"],
                        source_provider="intervalsicu",
                    )
                )

    return dict(grouped), all_changes


# ---------------------------------------------------------------------------
# Comparison table builder (shared between CLI and web)
# ---------------------------------------------------------------------------


def build_comparison_rows(
    grouped: dict,
    provider_config: dict,
    home_tz,
) -> tuple[list[str], list[dict]]:
    """Build a structured activity comparison table from grouped activities.

    Both the CLI renderer and the web API use this to avoid duplicating the
    authority-provider selection and per-cell status computation.

    Args:
        grouped:         dict mapping correlation_key → list of processed activity dicts
                         (as returned by ``compute_month_changes``).
        provider_config: ``config["providers"]`` dict with priority / enabled flags.
        home_tz:         A tzinfo-compatible object for local timestamp formatting.

    Returns:
        (provider_list, rows) where:
          - provider_list is a sorted list of all provider names present.
          - rows is a list of JSON-serialisable dicts:
              {
                  "start": "YYYY-MM-DD HH:MM",
                  "correlation_key": str,
                  "auth_provider": str,
                  "distance": float,
                  "providers": {
                      provider_name: {
                          "present":          bool,
                          "id":               str | None,
                          "name":             str,
                          "display_name":     str,
                          "name_status":      "auth"|"ok"|"missing"|"wrong",
                          "equipment":        str,
                          "display_equipment":str,
                          "equip_status":     "auth"|"ok"|"missing"|"wrong",
                      }
                  },
              }
    """
    from datetime import UTC, datetime

    all_providers: set[str] = set()
    for group in grouped.values():
        for act in group:
            all_providers.add(act["provider"])
    for pname, psettings in provider_config.items():
        if psettings.get("enabled", False):
            all_providers.add(pname)
    provider_list = sorted(all_providers)

    provider_priorities = {
        name: settings.get("priority", 999)
        for name, settings in provider_config.items()
        if settings.get("enabled", False)
    }
    priority_order = sorted(provider_priorities.items(), key=lambda x: x[1])
    provider_priority = [p for p, _ in priority_order]

    rows: list[dict] = []
    for key, group in grouped.items():
        if len(group) < 2:
            continue

        by_provider = {a["provider"]: a for a in group}

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

        auth_act = by_provider[auth_provider]
        ts = min((a["timestamp"] for a in group if a["timestamp"]), default=0)
        try:
            start_local = datetime.fromtimestamp(ts, UTC).astimezone(home_tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            start_local = "—"

        provider_cells: dict[str, dict] = {}
        for pname in provider_list:
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

                provider_cells[pname] = {
                    "present": True,
                    "id": str(act["id"]),
                    "name": current_name,
                    "display_name": (current_name if name_status != "missing" else auth_name),
                    "name_status": name_status,
                    "equipment": act["equipment"],
                    "display_equipment": (act["equipment"] if equip_status != "missing" else auth_equipment),
                    "equip_status": equip_status,
                }
            else:
                provider_cells[pname] = {
                    "present": False,
                    "id": None,
                    "name": "",
                    "display_name": auth_name,
                    "name_status": "missing",
                    "equipment": "",
                    "display_equipment": auth_equipment,
                    "equip_status": "missing",
                }

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
    return provider_list, rows


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
            elif provider == "intervalsicu":
                ok = prov.update_activity({"intervalsicu_id": change.activity_id, "name": change.new_value})
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

            try:
                if provider in ("ridewithgps", "strava", "intervalsicu", "garmin"):
                    ok = prov.set_gear(change.new_value, change.activity_id)
                elif provider == "spreadsheet":
                    ok = prov.update_activity(
                        {
                            "spreadsheet_id": change.activity_id,
                            "equipment": change.new_value,
                        }
                    )
                else:
                    return (
                        False,
                        f"Equipment update not supported for provider '{provider}'",
                    )
                return (
                    (True, f"Equipment updated for {change.activity_id}")
                    if ok
                    else (False, f"Equipment update failed for {change.activity_id}")
                )
            except Exception as exc:
                from tracekit.providers.garmin.garmin_provider import (
                    GarminGearNotFoundError,
                )

                if isinstance(exc, GarminGearNotFoundError):
                    return (
                        False,
                        f"Gear '{exc.gear_name}' not found in Garmin Connect. "
                        f"Add it at connect.garmin.com/modern/gear before syncing.",
                    )
                return (
                    False,
                    f"Equipment update failed for {change.activity_id}: {exc}",
                )

        elif change_type == ChangeType.UPDATE_METADATA:
            prov = tracekit.get_provider(provider)
            if not prov:
                return False, f"{provider} provider not available"
            if provider == "spreadsheet":
                ok = prov.update_activity(
                    {
                        "spreadsheet_id": change.activity_id,
                        "duration_hms": change.new_value,
                    }
                )
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

        elif change_type == ChangeType.DOWNLOAD_FROM_GARMIN:
            garmin_prov = tracekit.get_provider("garmin")
            file_prov = tracekit.get_provider("file")
            if not garmin_prov:
                return False, "Garmin provider not available"
            if not file_prov:
                return False, "File provider not available"

            garmin_id = change.activity_id
            dest_dir = file_prov.data_folder

            try:
                file_path = garmin_prov.download_activity_file(garmin_id, dest_dir)
            except FileExistsError as exc:
                return False, f"File already exists — will not overwrite: {exc}"

            result = file_prov.process_single_file(file_path)
            if result.get("status") in ("ok", "skipped"):
                return True, f"Downloaded and ingested {result.get('file')}"
            return (
                False,
                f"Download succeeded but ingestion failed: {result.get('reason', 'unknown')}",
            )

        elif change_type == ChangeType.DOWNLOAD_FROM_RIDEWITHGPS:
            rwgps_prov = tracekit.get_provider("ridewithgps")
            file_prov = tracekit.get_provider("file")
            if not rwgps_prov:
                return False, "RideWithGPS provider not available"
            if not file_prov:
                return False, "File provider not available"

            rwgps_id = change.activity_id
            dest_dir = file_prov.data_folder

            try:
                file_path = rwgps_prov.download_activity_file(rwgps_id, dest_dir)
            except FileExistsError as exc:
                return False, f"File already exists — will not overwrite: {exc}"

            result = file_prov.process_single_file(file_path)
            if result.get("status") in ("ok", "skipped"):
                return True, f"Downloaded and ingested {result.get('file')}"
            return (
                False,
                f"Download succeeded but ingestion failed: {result.get('reason', 'unknown')}",
            )

        elif change_type == ChangeType.DOWNLOAD_FROM_INTERVALSICU:
            icu_prov = tracekit.get_provider("intervalsicu")
            file_prov = tracekit.get_provider("file")
            if not icu_prov:
                return False, "Intervals.icu provider not available"
            if not file_prov:
                return False, "File provider not available"

            icu_id = change.activity_id
            dest_dir = file_prov.data_folder

            try:
                file_path = icu_prov.download_activity_file(icu_id, dest_dir)
            except FileExistsError as exc:
                return False, f"File already exists — will not overwrite: {exc}"

            result = file_prov.process_single_file(file_path)
            if result.get("status") in ("ok", "skipped"):
                return True, f"Downloaded and ingested {result.get('file')}"
            return (
                False,
                f"Download succeeded but ingestion failed: {result.get('reason', 'unknown')}",
            )

        else:
            return False, f"Unsupported change type: {change_type}"

    except Exception as exc:
        return False, str(exc)
