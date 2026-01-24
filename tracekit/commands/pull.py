import argparse
import datetime

from tracekit.core import tracekit


def print_activities(provider_name, activities, id_field, home_tz):
    print(f"\n{provider_name} (for selected month):")
    print(f"{'ID':<12} {'Name':<30} {'Raw Timestamp':<12} {'Local Time':<19} {'Distance (mi)':>12}")
    print("-" * 85)
    for act in activities:
        act_id = getattr(act, id_field, None)
        name = getattr(act, "name", None) or getattr(act, "notes", "")
        start_time = getattr(act, "start_time", None)
        date_str = ""
        raw_timestamp = "None"
        if start_time:
            try:
                timestamp = int(start_time)
                utc_dt = datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
                local_dt = utc_dt.astimezone(home_tz)
                raw_timestamp = str(timestamp)
                date_str = f"{local_dt.strftime('%Y-%m-%d %H:%M')} {local_dt.tzname()}"
            except (ValueError, TypeError):
                date_str = "invalid"
                raw_timestamp = str(start_time) if start_time else "None"
        dist = getattr(act, "distance", 0)
        line = f"{act_id!s:<12} {str(name)[:28]:<30} {raw_timestamp!s:<12} {date_str!s:<19} {dist:12.2f}"
        print(line)


def get_months():
    now = datetime.datetime.now()
    earliest = datetime.datetime(2000, 1, 1)
    months = []
    current = now.replace(day=1)
    while current >= earliest:
        months.append(current.strftime("%Y-%m"))
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)
    return months


def run(args=None):
    if args is None:
        args = []

    parser = argparse.ArgumentParser(description="Pull activities from providers")
    parser.add_argument(
        "--date",
        help="Date filter in YYYY-MM format (if not specified, pulls all activities)",
    )
    parsed_args = parser.parse_args(args)
    year_month = parsed_args.date

    with tracekit() as tracekit:
        enabled_providers = tracekit.enabled_providers
        if not enabled_providers:
            print("No providers are enabled. Check your configuration.")
            return

        home_tz = tracekit.home_tz
        months = [year_month] if year_month else get_months()
        for month in months:
            print(f"\n=== {month} ===")
            activities = tracekit.pull_activities(month)
            for provider_name, provider_activities in activities.items():
                if provider_activities:
                    display_name = provider_name.title()
                    print_activities(display_name, provider_activities, "provider_id", home_tz)
