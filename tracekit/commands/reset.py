import argparse

from tracekit.core import tracekit as tracekit_class
from tracekit.provider_sync import ProviderSync


def run(args=None):
    if args is None:
        args = []

    parser = argparse.ArgumentParser(description="Reset activities and sync records")
    parser.add_argument(
        "--date",
        help="Date filter in YYYY-MM format (if not specified, resets all activities)",
    )
    parsed_args = parser.parse_args(args)
    year_month = parsed_args.date

    with tracekit_class() as tracekit:
        enabled_providers = tracekit.enabled_providers
        if not enabled_providers:
            print("No providers are enabled. Check your configuration.")
            return

        if year_month:
            print(f"Resetting data for {year_month}...")
        else:
            print("Resetting ALL data...")
            confirm = input("This will delete ALL activities and sync records. Are you sure? (yes/no): ")
            if confirm.lower() != "yes":
                print("Reset cancelled.")
                return

        total_deleted = 0
        for provider_name in enabled_providers:
            print(f"\nResetting {provider_name}...")
            try:
                provider = tracekit.get_provider(provider_name)
                deleted_count = provider.reset_activities(year_month)
                print(f"  Deleted {deleted_count} {provider_name} activities")
                total_deleted += deleted_count
            except Exception as e:
                print(f"  Error resetting {provider_name}: {e}")

        # Reset ProviderSync records
        sync_deleted = 0
        if year_month:
            for provider_name in enabled_providers:
                sync_record = ProviderSync.get_or_none(year_month, provider_name)
                if sync_record:
                    sync_record.delete_instance()
                    sync_deleted += 1
            print(f"\nDeleted {sync_deleted} sync records for {year_month}")
        else:
            sync_deleted = ProviderSync.delete().execute()
            print(f"\nDeleted {sync_deleted} sync records")

        print(f"\nReset complete! Total activities deleted: {total_deleted}")
