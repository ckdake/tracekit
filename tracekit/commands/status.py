"""CLI command: status — show provider activity counts and recent activity."""

from datetime import UTC, datetime

from tabulate import tabulate

from tracekit.core import tracekit as tracekit_class


def run() -> None:
    """Print a provider-by-provider status summary and the most recent activity."""
    with tracekit_class() as tk:
        home_tz = tk.home_tz
        home_timezone = str(home_tz)

        from tracekit.provider_status import get_all_statuses
        from tracekit.stats import get_most_recent_activity, get_provider_activity_counts

        counts = get_provider_activity_counts()
        statuses = get_all_statuses()

        # Build table rows
        all_providers = sorted(set(counts) | set(statuses))
        rows = []
        for provider in all_providers:
            count = counts.get(provider, 0)
            status = statuses.get(provider, {})
            last_op_ts = status.get("last_operation_at")
            if last_op_ts:
                try:
                    last_op = datetime.fromtimestamp(int(last_op_ts), UTC).astimezone(home_tz).strftime("%Y-%m-%d")
                except Exception:
                    last_op = str(last_op_ts)
            else:
                last_op = "—"
            success = status.get("last_success")
            ok_str = "✓" if success is True else ("✗" if success is False else "—")
            rows.append([provider, f"{count:,}", last_op, ok_str])

        print(
            tabulate(
                rows,
                headers=["Provider", "Activities", "Last sync", "OK"],
                tablefmt="simple",
            )
        )

        recent = get_most_recent_activity(home_timezone)
        if recent.get("formatted"):
            print(f"\nMost recent activity: {recent['formatted']}")
        elif not any(r[1] != "0" for r in rows):
            print("\nNo activities in database.")
