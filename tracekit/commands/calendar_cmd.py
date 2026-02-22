"""CLI command: calendar — show the month-by-month sync grid."""

import argparse

from tabulate import tabulate

from tracekit.core import tracekit as tracekit_class


def run(args=None) -> None:
    """Print the sync calendar as a text table."""
    if args is None:
        args = []

    parser = argparse.ArgumentParser(description="Show sync calendar")
    parser.add_argument(
        "--months",
        type=int,
        default=0,
        help="Limit to the most recent N months (default: show all)",
    )
    parsed = parser.parse_args(args)

    with tracekit_class() as tk:
        home_tz = tk.home_tz
        home_timezone = str(home_tz)

    from tracekit.calendar import get_calendar_shell

    shell = get_calendar_shell(home_timezone)

    if shell.get("error"):
        print(f"Error: {shell['error']}")
        return

    months = shell["months"]
    providers = shell["providers"]

    if not months:
        print("No sync data found. Run 'pull' to fetch activities first.")
        return

    # Most-recent first
    months = list(reversed(months))
    if parsed.months > 0:
        months = months[: parsed.months]

    from tracekit.calendar import get_single_month_data

    # Build the table
    headers = ["Month"] + [p.title() for p in providers]
    rows = []
    for stub in months:
        ym = stub["year_month"]
        month_data = get_single_month_data(ym, home_timezone)
        if month_data.get("error"):
            row = [f"{stub['month_name']} {stub['year']}"] + ["?"] * len(providers)
        else:
            provider_status = month_data.get("provider_status", {})
            activity_counts = month_data.get("activity_counts", {})
            row = [f"{stub['month_name']} {stub['year']}"]
            for p in providers:
                synced = provider_status.get(p, False)
                count = activity_counts.get(p, 0)
                if synced and count:
                    row.append(f"✓ {count}")
                elif synced:
                    row.append("✓")
                else:
                    row.append("—")
        rows.append(row)

    print(tabulate(rows, headers=headers, tablefmt="simple"))
