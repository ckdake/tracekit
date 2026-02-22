"""CLI command: sync-month — display cross-provider diffs and apply them interactively.

This module is intentionally thin.  All business logic lives in
``tracekit.sync``; this file is responsible only for:

  * Rendering the ANSI-coloured comparison table
  * Interactive y/n prompting for each change
  * Wiring accepted changes through to ``tracekit.sync.apply_change``
"""

from collections import defaultdict

from tabulate import tabulate

from tracekit.core import tracekit as tracekit_class
from tracekit.sync import ChangeType, apply_change, build_comparison_rows, compute_month_changes

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

    provider_list, rows = build_comparison_rows(grouped, provider_config, home_tz)

    if not rows:
        return

    # Map structured row data to ANSI-coloured table rows
    _status_to_ansi = {
        "auth": (True, False, False),
        "ok": (False, False, False),
        "missing": (False, True, False),
        "wrong": (False, False, True),
    }

    table_rows = []
    for row in rows:
        table_row = [row["start"]]

        for provider in provider_list:
            sync_name = provider_config.get(provider, {}).get("sync_name", True)
            sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)
            cell = row["providers"][provider]

            if cell["present"]:
                table_row.append(color_id(cell["id"], True))
            else:
                table_row.append(color_text("TBD", False, True, False))

            if sync_name:
                flags = _status_to_ansi.get(cell["name_status"], (False, False, False))
                table_row.append(color_text(cell["display_name"], *flags) if cell["display_name"] else "")

            if sync_equipment:
                flags = _status_to_ansi.get(cell["equip_status"], (False, False, False))
                table_row.append(color_text(cell["display_equipment"], *flags) if cell["display_equipment"] else "")

        table_row.append(f"{row['distance']:.2f}")
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
