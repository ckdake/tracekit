"""CLI command: sync-month — display cross-provider diffs and apply them interactively.

This module is intentionally thin.  All business logic lives in
``tracekit.sync``; this file is responsible only for:

  * Rendering the ANSI-coloured comparison table
  * Interactive y/n prompting for each change
  * Wiring accepted changes through to ``tracekit.sync.apply_change``
"""

from collections import defaultdict
from datetime import UTC, datetime

from tabulate import tabulate

from tracekit.core import tracekit as tracekit_class
from tracekit.sync import ChangeType, apply_change, compute_month_changes

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

green_bg = "\033[42m"
yellow_bg = "\033[43m"
red_bg = "\033[41m"
reset = "\033[0m"


def color_id(id_val, exists):
    if exists:
        return f"{green_bg}{id_val}{reset}"
    return f"{yellow_bg}TBD{reset}"


def color_text(text, is_auth, is_new, is_wrong):
    """Apply ANSI highlight to *text* based on its sync status."""
    if is_auth:
        return f"{green_bg}{text}{reset}"
    elif is_new:
        return f"{yellow_bg}{text}{reset}"
    elif is_wrong:
        return f"{red_bg}{text}{reset}"
    return text


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def _render_table(grouped: dict, all_changes: list, config: dict, home_tz) -> None:
    """Print the ANSI-coloured comparison table for the given grouped activities."""
    provider_config = config.get("providers", {})

    # Determine all providers present
    all_providers: set[str] = set()
    for group in grouped.values():
        for act in group:
            all_providers.add(act["provider"])
    for name, settings in provider_config.items():
        if settings.get("enabled", False):
            all_providers.add(name)
    provider_list = sorted(all_providers)

    # Determine authoritative name/equipment for each group
    provider_priorities = {
        name: settings.get("priority", 999)
        for name, settings in provider_config.items()
        if settings.get("enabled", False)
    }
    priority_order = sorted(provider_priorities.items(), key=lambda x: x[1])
    provider_priority = [p for p, _ in priority_order]

    # Build sorted rows (only multi-provider groups)
    rows = []
    for _key, group in grouped.items():
        if len(group) < 2:
            continue
        start = min(
            (
                datetime.fromtimestamp(a["timestamp"], UTC).astimezone(home_tz)
                if a["timestamp"]
                else datetime.fromtimestamp(0, UTC).astimezone(home_tz)
            )
            for a in group
        )
        by_provider = {a["provider"]: a for a in group}
        rows.append({"start": start, "providers": by_provider})

    rows.sort(key=lambda r: r["start"])

    if not rows:
        return

    table_rows = []
    for row in rows:
        providers = row["providers"]

        auth_provider = None
        auth_name = ""
        auth_equipment = ""

        for p in provider_priority:
            if p in providers and providers[p]["name"]:
                auth_provider = p
                auth_name = providers[p]["name"]
                break
        if not auth_provider:
            for p in provider_priority:
                if p in providers:
                    auth_provider = p
                    auth_name = providers[p]["name"]
                    break
        for p in provider_priority:
            if p in providers and providers[p]["equipment"]:
                auth_equipment = providers[p]["equipment"]
                break

        if not auth_provider:
            continue

        auth_activity = providers[auth_provider]
        table_row = [row["start"].strftime("%Y-%m-%d %H:%M")]

        for provider in provider_list:
            sync_name = provider_config.get(provider, {}).get("sync_name", True)
            sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)

            if provider in providers:
                activity = providers[provider]
                table_row.append(color_id(activity["id"], True))

                if sync_name:
                    current_name = activity["name"]
                    if provider == auth_provider and current_name:
                        name_colored = color_text(current_name, True, False, False)
                    elif current_name == auth_name:
                        name_colored = color_text(current_name, False, False, False)
                    elif not current_name and auth_name:
                        name_colored = color_text(auth_name, False, True, False)
                    elif current_name != auth_name and auth_name:
                        name_colored = color_text(current_name, False, False, True)
                    else:
                        name_colored = color_text(current_name, False, False, False)
                    table_row.append(name_colored)

                if sync_equipment:
                    if provider == auth_provider:
                        equip_colored = color_text(activity["equipment"], True, False, False)
                    else:
                        equip_val = (activity["equipment"] or "").strip().lower()
                        equip_wrong = auth_equipment and (
                            activity["equipment"] != auth_equipment or equip_val in ("", "no equipment")
                        )
                        if equip_wrong and equip_val in ("", "no equipment"):
                            equip_colored = color_text(auth_equipment, False, True, False)
                        else:
                            equip_colored = color_text(activity["equipment"], False, False, bool(equip_wrong))
                    table_row.append(equip_colored)
            else:
                table_row.append(color_text("TBD", False, True, False))
                if sync_name:
                    table_row.append(color_text(auth_name, False, True, False) if auth_name else "")
                if sync_equipment:
                    table_row.append(color_text(auth_equipment, False, True, False) if auth_equipment else "")

        table_row.append(f"{auth_activity['distance']:.2f}")
        table_rows.append(table_row)

    headers = ["Start"]
    for provider in provider_list:
        sync_name = provider_config.get(provider, {}).get("sync_name", True)
        sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)
        headers.append(f"{provider.title()} ID")
        if sync_name:
            headers.append(f"{provider.title()} Name")
        if sync_equipment:
            headers.append(f"{provider.title()} Equip")
    headers.append("Distance (mi)")

    print(
        tabulate(
            table_rows,
            headers=headers,
            tablefmt="plain",
            stralign="left",
            numalign="left",
            colalign=("left",) * len(headers),
        )
    )

    print("\nLegend:")
    print(f"{green_bg}Green{reset} = Source of truth (from highest priority provider)")
    print(f"{yellow_bg}Yellow{reset} = New entry to be created")
    print(f"{red_bg}Red{reset} = Needs to be updated to match source of truth")


# ---------------------------------------------------------------------------
# Interactive prompting
# ---------------------------------------------------------------------------


def _prompt_and_apply(all_changes: list, grouped: dict, tracekit) -> None:
    """Walk through each change, prompt y/n, and apply accepted ones."""
    if not all_changes:
        print("\nNo changes needed - all activities are synchronized!")
        return

    # Group changes by type for display
    changes_by_type = defaultdict(list)
    for change in all_changes:
        changes_by_type[change.change_type].append(change)

    print("\nChanges needed:")
    for change_type in ChangeType:
        if changes_by_type[change_type]:
            if change_type == ChangeType.UPDATE_METADATA:
                print(f"\n{change_type.value} Changes:")
            elif change_type == ChangeType.ADD_ACTIVITY:
                print("\nAdd Activities:")
            elif change_type == ChangeType.LINK_ACTIVITY:
                print("\nLink Activities:")
            else:
                print(f"\n{change_type.value}s:")
            for ch in changes_by_type[change_type]:
                print(f"* {ch}")

    print("\n" + "=" * 50)
    print("Interactive Updates")
    print("=" * 50)

    for change in all_changes:
        if change.change_type == ChangeType.LINK_ACTIVITY:
            # LINK_ACTIVITY is not interactively applied yet
            continue

        response = input(f"\n{change}? (y/n): ").strip().lower()
        if response == "y":
            success, msg = apply_change(change, tracekit, grouped=grouped)
            print(f"{'✓' if success else '✗'} {msg}")
        else:
            print("Skipped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(year_month: str) -> None:
    """Run the sync-month command for the given YYYY-MM string."""
    with tracekit_class() as tk:
        grouped, all_changes = compute_month_changes(tk, year_month)

        if not grouped:
            print(f"\nNo activities found for {year_month}")
            return

        multi_provider_count = sum(1 for g in grouped.values() if len(g) >= 2)
        if not multi_provider_count:
            print(f"\nNo correlated activities found for {year_month}")
            print("(Activities that exist in only one provider are not shown)")
            return

        _render_table(grouped, all_changes, tk.config, tk.home_tz)
        _prompt_and_apply(all_changes, grouped, tk)
