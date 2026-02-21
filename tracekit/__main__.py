# pylint: disable=import-outside-toplevel
"""Main entry point for the tracekit CLI.

This module provides the command-line interface for tracekit, allowing users to
authenticate with Strava, configure their environment, sync activities, and
access help/documentation.
"""

import argparse

from dotenv import load_dotenv

load_dotenv()


def main():
    """Main function for the tracekit CLI."""
    parser = argparse.ArgumentParser(description="tracekit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth-strava", help="Authenticate with Strava and get an access token")
    subparsers.add_parser("auth-garmin", help="Authenticate with Garmin Connect and store tokens")
    subparsers.add_parser("configure", help="Configure tracekit for your environment")
    subparsers.add_parser(
        "migrate",
        help="Bootstrap / migrate the database schema (safe to run on every start)",
    )

    sync_month_parser = subparsers.add_parser(
        "sync-month",
        help=("Correlate and show all activities for a given month (YYYY-MM) across all sources, dry run"),
    )
    sync_month_parser.add_argument("year_month", type=str, help="Year and month in YYYY-MM format")
    subparsers.add_parser("help", help="Show usage and documentation")
    pull_parser = subparsers.add_parser("pull", help="Pull activities from all providers")
    pull_parser.add_argument(
        "--date",
        help="Date filter in YYYY-MM format (if not specified, pulls all activities)",
    )

    reset_parser = subparsers.add_parser("reset", help="Reset (delete) activities and sync records")
    reset_parser.add_argument(
        "--date",
        help="Date filter in YYYY-MM format (if not specified, resets all data)",
    )

    args = parser.parse_args()

    if args.command == "auth-strava":
        from tracekit.commands.auth_strava import run

        run()
    elif args.command == "auth-garmin":
        from tracekit.commands.auth_garmin import run

        run()
    elif args.command == "configure":
        from tracekit.commands.configure import run

        run()
    elif args.command == "migrate":
        from tracekit.commands.migrate import run

        run()
    elif args.command == "sync-month":
        from tracekit.commands.sync_month import run

        run(args.year_month)
    elif args.command == "pull":
        from tracekit.commands.pull import run

        # Only pass --date if set, otherwise pass None
        pull_args = ["--date", args.date] if hasattr(args, "date") and args.date else None
        run(pull_args)
    elif args.command == "reset":
        from tracekit.commands.reset import run

        # Only pass --date if set, otherwise pass None
        reset_args = ["--date", args.date] if hasattr(args, "date") and args.date else None
        run(reset_args)
    elif args.command == "help" or args.command is None:
        print(
            """
tracekit - Aggregate, sync, and analyze your fitness activity data.

Usage:
    python -m tracekit <command>

Commands:
    auth-strava   Authenticate with Strava and get an access token
    auth-garmin   Authenticate with Garmin Connect and store tokens
    configure     Configure tracekit for your environment (paths, API keys, etc)
    show-month    Show all activities for a given month (YYYY-MM) from all sources
    sync-month    Correlate and show all activities for a given month (YYYY-MM)
                  across all sources, dry run
    pull          Pull activities from all providers
    reset         Reset (delete) activities and sync records
    help          Show this help and usage documentation

Setup:
    1. Run 'python -m tracekit configure' to set up some basics
    2. Authenticate with each provider you need, e.g. 'python -m tracekit auth-strava'.
    3. Use 'python -m tracekit sync-month YYYY-MM' to view activity correlations.

See README.md for more details.
"""
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
