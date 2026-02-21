import json
import os


def run():
    print("Welcome to tracekit configuration!")
    config = {}

    # Home timezone
    print("\n--- Timezone Configuration ---")
    print("Common timezones: US/Eastern, US/Central, US/Mountain, US/Pacific")
    timezone = input("Home timezone (default: US/Eastern): ").strip()
    config["home_timezone"] = timezone or "US/Eastern"

    # Debug mode
    debug_input = input("\nEnable debug mode? (y/N): ").strip().lower()
    config["debug"] = debug_input == "y"

    # Metadata database path
    print("\n--- Database Configuration ---")
    metadata_db_path = input(
        "Path to metadata database (default: /home/vscode/Documents/tracekit-metadata.sqlite3): "
    ).strip()
    config["metadata_db"] = metadata_db_path or "/home/vscode/Documents/tracekit-metadata.sqlite3"

    # Create providers block
    config["providers"] = {}

    print("\n--- Provider Configuration ---")

    # Spreadsheet provider
    print("\nSpreadsheet Provider:")
    enable_spreadsheet = input("Enable spreadsheet provider? (Y/n): ").strip().lower() != "n"
    spreadsheet_path = ""
    spreadsheet_priority = 0
    if enable_spreadsheet:
        spreadsheet_path = input(
            "Path to activity spreadsheet (e.g.: /home/vscode/Documents/exerciselog.xlsx): "
        ).strip()
        spreadsheet_priority = int(input("Priority (1-5, lower is higher priority, default: 1): ").strip() or "1")

    config["providers"]["spreadsheet"] = {
        "enabled": enable_spreadsheet,
        "path": spreadsheet_path,
    }
    if enable_spreadsheet and spreadsheet_priority > 0:
        config["providers"]["spreadsheet"]["priority"] = spreadsheet_priority

    # File provider
    print("\nFile Provider:")
    enable_file = input("Enable file provider? (Y/n): ").strip().lower() != "n"

    config["providers"]["file"] = {"enabled": enable_file}

    # Strava provider
    print("\nStrava Provider:")
    enable_strava = input("Enable Strava provider? (Y/n): ").strip().lower() != "n"
    strava_priority = 0
    if enable_strava:
        print("Note: Strava credentials should be set in .env file.")
        strava_priority = int(input("Priority (1-5, lower is higher priority, default: 3): ").strip() or "3")

    config["providers"]["strava"] = {"enabled": enable_strava}
    if enable_strava and strava_priority > 0:
        config["providers"]["strava"]["priority"] = strava_priority

    # RideWithGPS provider
    print("\nRideWithGPS Provider:")
    enable_ridewithgps = input("Enable RideWithGPS provider? (Y/n): ").strip().lower() != "n"
    ridewithgps_priority = 0
    if enable_ridewithgps:
        print("Note: RideWithGPS credentials should be set in .env file.")
        ridewithgps_priority = int(input("Priority (1-5, lower is higher priority, default: 2): ").strip() or "2")

    config["providers"]["ridewithgps"] = {"enabled": enable_ridewithgps}
    if enable_ridewithgps and ridewithgps_priority > 0:
        config["providers"]["ridewithgps"]["priority"] = ridewithgps_priority

    # Garmin provider
    print("\nGarmin Provider:")
    enable_garmin = input("Enable Garmin provider? (Y/n): ").strip().lower() != "n"
    if enable_garmin:
        print("Note: Garmin credentials should be set in .env file.")

    config["providers"]["garmin"] = {"enabled": enable_garmin}

    # StravaJSON provider (disabled by default)
    config["providers"]["stravajson"] = {"enabled": False}

    # Create provider_priority string based on provider priorities
    providers_with_priority = []
    for provider, settings in config["providers"].items():
        if settings.get("enabled", False) and "priority" in settings:
            providers_with_priority.append((provider, settings["priority"]))

    # Sort by priority (lower number = higher priority)
    providers_with_priority.sort(key=lambda x: x[1])
    priority_list = [p[0] for p in providers_with_priority]

    if priority_list:
        config["provider_priority"] = ",".join(priority_list)
    else:
        # Default priority if none specified
        config["provider_priority"] = "spreadsheet,ridewithgps,strava"

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../tracekit_config.json"))
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
    print(f"\nConfiguration saved to {config_path}")
