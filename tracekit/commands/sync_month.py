from collections import defaultdict
from datetime import UTC, datetime
from enum import Enum
from typing import NamedTuple
from zoneinfo import ZoneInfo

from tabulate import tabulate

from tracekit.core import tracekit


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


# ANSI color codes for terminal output
green_bg = "\033[42m"
yellow_bg = "\033[43m"
red_bg = "\033[41m"
reset = "\033[0m"


def color_id(id_val, exists):
    if exists:
        return f"{green_bg}{id_val}{reset}"
    else:
        return f"{yellow_bg}TBD{reset}"


def color_text(text, is_auth, is_new, is_wrong):
    """Apply color highlighting to text based on its status."""
    if is_auth:  # Authoritative source
        return f"{green_bg}{text}{reset}"
    elif is_new:  # New activity to be created
        return f"{yellow_bg}{text}{reset}"
    elif is_wrong:  # Different from authoritative source
        return f"{red_bg}{text}{reset}"
    return text  # No highlighting needed


def process_activity_for_display(activity, provider: str) -> dict:
    """Process a provider-specific activity object for display/matching purposes."""
    # Get the provider ID using the provider_id property
    provider_id = getattr(activity, "provider_id", None)

    # Get start_time (now stored as integer timestamp)
    start_time = getattr(activity, "start_time", None)
    timestamp = start_time if start_time else 0

    # Get distance
    distance = getattr(activity, "distance", 0)
    if distance is None:
        distance = 0

    # For spreadsheet provider, the "name" should come from notes field
    # For other providers, use the name field
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
    """Generate a correlation key for matching activities across providers."""
    if not timestamp or not distance:
        return ""

    try:
        dt = datetime.fromtimestamp(timestamp, ZoneInfo("US/Eastern"))
        date_str = dt.strftime("%Y-%m-%d")

        # Create distance buckets to handle GPS precision differences
        # Round to nearest 0.5 for better correlation across providers
        distance_bucket = round(distance * 2) / 2

        return f"{date_str}_{distance_bucket:.1f}"
    except (ValueError, TypeError):
        return ""


def convert_activity_to_spreadsheet_format(source_activity: dict, grouped_activities) -> dict:
    """Convert an activity from any provider to spreadsheet format."""
    # Extract the source activity object
    activity_obj = source_activity["obj"]

    # Get start time and convert to spreadsheet format (date only)
    start_time = ""
    if source_activity["timestamp"]:
        try:
            dt = datetime.fromtimestamp(source_activity["timestamp"], ZoneInfo("US/Eastern"))
            start_time = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    # Collect all provider IDs from the correlated group
    garmin_id = ""
    strava_id = ""
    ridewithgps_id = ""

    # Find the group this activity belongs to
    correlation_key = generate_correlation_key(source_activity["timestamp"], source_activity["distance"])
    if correlation_key in grouped_activities:
        group = grouped_activities[correlation_key]
        for act in group:
            if act["provider"] == "garmin":
                garmin_id = str(act["id"]) if act["id"] else ""
            elif act["provider"] == "strava":
                strava_id = str(act["id"]) if act["id"] else ""
            elif act["provider"] == "ridewithgps":
                ridewithgps_id = str(act["id"]) if act["id"] else ""

    # Round distance to 2 decimal places
    distance = source_activity["distance"] or 0
    if distance:
        distance = round(float(distance), 2)

    # Build spreadsheet activity data
    activity_data = {
        "start_time": start_time,
        "activity_type": getattr(activity_obj, "activity_type", "") or "",
        "location_name": getattr(activity_obj, "location_name", "") or "",
        "city": getattr(activity_obj, "city", "") or "",
        "state": getattr(activity_obj, "state", "") or "",
        "temperature": getattr(activity_obj, "temperature", "") or "",
        "equipment": source_activity["equipment"] or "",
        "duration": getattr(activity_obj, "duration", None),
        "duration_hms": "",  # Will be set below if duration is available
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
        "notes": source_activity["name"] or "",  # Map activity name to notes field
    }

    # Convert duration from seconds to HH:MM:SS format
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


def run(year_month):
    with tracekit() as tracekit:
        # Use the new pull_activities method to get provider-specific activities
        activities = tracekit.pull_activities(year_month)

        config = tracekit.config
        home_tz = tracekit.home_tz

        # Process all activities from all providers
        all_acts = []

        # Dynamically process activities from all enabled providers
        for provider_name, provider_activities in activities.items():
            for act in provider_activities:
                all_acts.append(process_activity_for_display(act, provider_name))

        if not all_acts:
            print(f"\nNo activities found for {year_month}")
            return

        # Group activities by correlation key (date + distance)
        grouped = defaultdict(list)
        for act in all_acts:
            correlation_key = generate_correlation_key(act["timestamp"], act["distance"])
            if correlation_key:  # Only group activities with valid correlation keys
                grouped[correlation_key].append(act)

        # Build rows for the table
        rows = []
        for group in grouped.values():
            # Skip single-activity groups if they're just one provider
            # (no correlation to show)
            if len(group) == 1:
                continue

            # Find the earliest start time in the group for ordering
            start = min(
                (
                    datetime.fromtimestamp(a["timestamp"], UTC).astimezone(home_tz)
                    if a["timestamp"]
                    else datetime.fromtimestamp(0, UTC).astimezone(home_tz)
                )
                for a in group
            )

            # Organize by provider
            by_provider = {}
            for a in group:
                by_provider[a["provider"]] = a

            rows.append(
                {
                    "start": start,
                    "providers": by_provider,
                    "correlation_key": generate_correlation_key(group[0]["timestamp"], group[0]["distance"]),
                }
            )

        # Sort by start time
        rows.sort(key=lambda r: r["start"])

        # Determine which providers we actually have data for
        all_providers = set()
        for row in rows:
            all_providers.update(row["providers"].keys())

        # Get all enabled providers from config to ensure we show them all
        enabled_providers = []
        provider_config = config.get("providers", {})
        for provider_name, provider_settings in provider_config.items():
            if provider_settings.get("enabled", False):
                enabled_providers.append(provider_name)

        # Combine providers that have data with all enabled providers
        all_providers.update(enabled_providers)
        provider_list = sorted(all_providers)

        if not rows:
            print(f"\nNo correlated activities found for {year_month}")
            print("(Activities that exist in only one provider are not shown)")
            return

        # Build table
        table = []
        all_changes = []

        # Determine authoritative provider based on config priority
        # New config structure has priorities as numbers (lower = higher priority)
        provider_priorities = {}
        provider_config = config.get("providers", {})

        for provider_name, provider_settings in provider_config.items():
            if provider_settings.get("enabled", False):
                # Default priority is 999 for providers without explicit priority
                priority = provider_settings.get("priority", 999)
                provider_priorities[provider_name] = priority

        # Sort providers by priority (lower number = higher priority)
        priority_order = sorted(provider_priorities.items(), key=lambda x: x[1])
        provider_priority = [provider for provider, _ in priority_order]

        for row in rows:
            providers = row["providers"]

            # Find authoritative provider for this group based on data availability
            auth_provider = None
            auth_name = ""
            auth_equipment = ""

            # Find the best provider for name field
            for p in provider_priority:
                if p in providers and providers[p]["name"]:
                    auth_provider = p
                    auth_name = providers[p]["name"]
                    break

            # If no provider found yet, fall back to first available provider
            if not auth_provider:
                for p in provider_priority:
                    if p in providers:
                        auth_provider = p
                        auth_name = providers[p]["name"]
                        break

            # Find the best provider for equipment field
            for p in provider_priority:
                if p in providers and providers[p]["equipment"]:
                    auth_equipment = providers[p]["equipment"]
                    break

            if not auth_provider:
                continue

            auth_activity = providers[auth_provider]

            # Build table row
            table_row = [row["start"].strftime("%Y-%m-%d %H:%M")]

            for provider in provider_list:
                sync_name = provider_config.get(provider, {}).get("sync_name", True)
                sync_equipment = provider_config.get(provider, {}).get("sync_equipment", True)
                if provider in providers:
                    activity = providers[provider]
                    # Color code based on authority
                    id_colored = color_id(activity["id"], True)
                    table_row.append(id_colored)
                    # Name column
                    if sync_name:
                        current_name = activity["name"]
                        if provider == auth_provider and current_name:
                            # This is the authoritative provider and has a name
                            name_colored = color_text(current_name, True, False, False)
                        elif current_name and current_name == auth_name:
                            # This provider has the correct name
                            name_colored = color_text(current_name, False, False, False)
                        elif not current_name and auth_name:
                            # This provider is missing the name, show auth name in green
                            name_colored = color_text(auth_name, False, True, False)
                            # Create UPDATE_NAME change
                            all_changes.append(
                                ActivityChange(
                                    change_type=ChangeType.UPDATE_NAME,
                                    provider=provider,
                                    activity_id=str(activity["id"]),
                                    old_value=current_name,
                                    new_value=auth_name,
                                )
                            )
                        elif current_name != auth_name and auth_name:
                            # This provider has wrong name
                            name_colored = color_text(current_name, False, False, True)
                            # Create UPDATE_NAME change
                            all_changes.append(
                                ActivityChange(
                                    change_type=ChangeType.UPDATE_NAME,
                                    provider=provider,
                                    activity_id=str(activity["id"]),
                                    old_value=current_name,
                                    new_value=auth_name,
                                )
                            )
                        else:
                            # Default case (no auth name available or same name)
                            name_colored = color_text(current_name, False, False, False)
                        table_row.append(name_colored)

                    # Special handling for spreadsheet metadata (duration_hms field)
                    if provider == "spreadsheet":
                        # Check if duration_hms needs to be updated with properly formatted duration
                        current_duration_hms = getattr(activity.get("obj"), "duration_hms", "") or ""

                        # Calculate the expected duration_hms from a non-spreadsheet provider
                        # Find the first non-spreadsheet provider with duration data
                        expected_duration_hms = ""
                        duration_seconds = None

                        for p in provider_priority:
                            if p != "spreadsheet" and p in providers:
                                provider_activity_obj = providers[p]["obj"]
                                # For non-spreadsheet providers, duration should be stored as int s
                                potential_duration = None

                                # Try different duration field names that providers might use
                                for duration_field in [
                                    "moving_time",
                                    "elapsed_time",
                                    "duration",
                                ]:
                                    potential_duration = getattr(provider_activity_obj, duration_field, None)
                                    if potential_duration and isinstance(potential_duration, (int, float)):
                                        duration_seconds = int(potential_duration)
                                        break

                                if duration_seconds:
                                    break

                        if duration_seconds:
                            try:
                                hours = int(duration_seconds // 3600)
                                minutes = int((duration_seconds % 3600) // 60)
                                seconds = int(duration_seconds % 60)
                                expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                            except (ValueError, TypeError):
                                pass

                        if current_duration_hms != expected_duration_hms and expected_duration_hms:
                            all_changes.append(
                                ActivityChange(
                                    change_type=ChangeType.UPDATE_METADATA,
                                    provider=provider,
                                    activity_id=str(activity["id"]),
                                    old_value=current_duration_hms,
                                    new_value=expected_duration_hms,
                                )
                            )
                    # Equipment column
                    if sync_equipment:
                        if provider == auth_provider:
                            equip_colored = color_text(activity["equipment"], True, False, False)
                        else:
                            equip_val = (activity["equipment"] or "").strip().lower()
                            equip_wrong = False
                            show_auth_equip = False
                            if auth_equipment and (
                                activity["equipment"] != auth_equipment
                                or equip_val == ""
                                or equip_val == "no equipment"
                            ):
                                equip_wrong = True
                                if equip_val == "" or equip_val == "no equipment":
                                    show_auth_equip = True
                            if show_auth_equip:
                                equip_colored = color_text(auth_equipment, False, True, False)
                            else:
                                equip_colored = color_text(activity["equipment"], False, False, equip_wrong)
                            if equip_wrong and auth_equipment:
                                all_changes.append(
                                    ActivityChange(
                                        change_type=ChangeType.UPDATE_EQUIPMENT,
                                        provider=provider,
                                        activity_id=str(activity["id"]),
                                        old_value=activity["equipment"],
                                        new_value=auth_equipment,
                                    )
                                )
                        table_row.append(equip_colored)
                else:
                    # Missing from this provider
                    missing_id = color_text("TBD", False, True, False)
                    table_row.append(missing_id)
                    if sync_name:
                        missing_name = color_text(auth_name, False, True, False) if auth_name else ""
                        table_row.append(missing_name)
                    if sync_equipment:
                        missing_equip = color_text(auth_equipment, False, True, False) if auth_equipment else ""
                        table_row.append(missing_equip)
                    # Record that this activity should be added to this provider
                    if sync_name and auth_name:
                        all_changes.append(
                            ActivityChange(
                                change_type=ChangeType.ADD_ACTIVITY,
                                provider=provider,
                                activity_id=str(auth_activity["id"]),
                                new_value=auth_name,
                                source_provider=auth_provider,
                            )
                        )

            # Add distance
            table_row.append(f"{auth_activity['distance']:.2f}")
            table.append(table_row)

        # Build headers
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
                table,
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

        if all_changes:
            # Group changes by type for better readability
            changes_by_type = defaultdict(list)
            for change in all_changes:
                changes_by_type[change.change_type].append(change)

            print("\nChanges needed:")
            for change_type in ChangeType:
                if changes_by_type[change_type]:
                    # Handle pluralization correctly
                    if change_type == ChangeType.UPDATE_METADATA:
                        print(f"\n{change_type.value} Changes:")
                    elif change_type == ChangeType.ADD_ACTIVITY:
                        print("\nAdd Activities:")
                    elif change_type == ChangeType.LINK_ACTIVITY:
                        print("\nLink Activities:")
                    else:
                        print(f"\n{change_type.value}s:")
                    for change in changes_by_type[change_type]:
                        print(f"* {change}")

            # Interactive prompting for supported changes
            print("\n" + "=" * 50)
            print("Interactive Updates")
            print("=" * 50)

            # Prompt for ridewithgps equipment updates
            ridewithgps_equipment_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_EQUIPMENT] if change.provider == "ridewithgps"
            ]

            # Prompt for strava equipment updates
            strava_equipment_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_EQUIPMENT] if change.provider == "strava"
            ]

            # Prompt for ridewithgps name updates
            ridewithgps_name_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_NAME] if change.provider == "ridewithgps"
            ]

            # Prompt for strava name updates
            strava_name_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_NAME] if change.provider == "strava"
            ]

            # Prompt for garmin name updates
            garmin_name_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_NAME] if change.provider == "garmin"
            ]

            # Prompt for spreadsheet additions
            spreadsheet_additions = [
                change for change in changes_by_type[ChangeType.ADD_ACTIVITY] if change.provider == "spreadsheet"
            ]

            # Prompt for spreadsheet notes updates (UPDATE_NAME for notes field)
            spreadsheet_name_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_NAME] if change.provider == "spreadsheet"
            ]

            # Prompt for spreadsheet metadata updates (UPDATE_METADATA for duration_hms, etc.)
            spreadsheet_metadata_changes = [
                change for change in changes_by_type[ChangeType.UPDATE_METADATA] if change.provider == "spreadsheet"
            ]

            if (
                ridewithgps_equipment_changes
                or strava_equipment_changes
                or ridewithgps_name_changes
                or strava_name_changes
                or garmin_name_changes
                or spreadsheet_additions
                or spreadsheet_name_changes
                or spreadsheet_metadata_changes
            ):
                # Get the ridewithgps provider from the existing tracekit instance
                ridewithgps_provider = tracekit.ridewithgps
                strava_provider = tracekit.strava
                garmin_provider = tracekit.garmin
                spreadsheet_provider = tracekit.spreadsheet

                if not ridewithgps_provider and (ridewithgps_equipment_changes or ridewithgps_name_changes):
                    print("RideWithGPS provider not available")
                elif not strava_provider and (strava_equipment_changes or strava_name_changes):
                    print("Strava provider not available")
                elif not garmin_provider and garmin_name_changes:
                    print("Garmin provider not available")
                elif not spreadsheet_provider and (
                    spreadsheet_additions or spreadsheet_name_changes or spreadsheet_metadata_changes
                ):
                    print("Spreadsheet provider not available")
                else:
                    # Process equipment updates
                    if ridewithgps_equipment_changes and ridewithgps_provider:
                        print("\nProcessing RideWithGPS equipment updates...")
                        for change in ridewithgps_equipment_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = ridewithgps_provider.set_gear(change.new_value, change.activity_id)
                                    if success:
                                        print(f"✓ Gear for {change.activity_id}")
                                    else:
                                        print(f"✗ Gear for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Gear for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process strava equipment updates
                    if strava_equipment_changes and strava_provider:
                        print("\nProcessing Strava equipment updates...")
                        for change in strava_equipment_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = strava_provider.set_gear(change.new_value, change.activity_id)
                                    if success:
                                        print(f"✓ Gear for {change.activity_id}")
                                    else:
                                        print(f"✗ Gear for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Gear for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process ridewithgps name updates
                    if ridewithgps_name_changes and ridewithgps_provider:
                        print("\nProcessing RideWithGPS name updates...")
                        for change in ridewithgps_name_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = ridewithgps_provider.update_activity(
                                        {
                                            "ridewithgps_id": change.activity_id,
                                            "name": change.new_value,
                                        }
                                    )
                                    if success:
                                        print(f"✓ Name for {change.activity_id}")
                                    else:
                                        print(f"✗ Name for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Name for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process strava name updates
                    if strava_name_changes and strava_provider:
                        print("\nProcessing Strava name updates...")
                        for change in strava_name_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = strava_provider.update_activity(
                                        {
                                            "strava_id": change.activity_id,
                                            "name": change.new_value,
                                        }
                                    )
                                    if success:
                                        print(f"✓ Name for {change.activity_id}")
                                    else:
                                        print(f"✗ Name for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Name for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process garmin name updates
                    if garmin_name_changes and garmin_provider:
                        print("\nProcessing Garmin name updates...")
                        for change in garmin_name_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = garmin_provider.update_activity(
                                        {
                                            "garmin_id": change.activity_id,
                                            "name": change.new_value,
                                        }
                                    )
                                    if success:
                                        print(f"✓ Name for {change.activity_id}")
                                    else:
                                        print(f"✗ Name for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Name for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process spreadsheet additions
                    if spreadsheet_additions and spreadsheet_provider:
                        print("\nProcessing Spreadsheet additions...")
                        for change in spreadsheet_additions:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    # Find the source activity in the grouped activities
                                    source_activity = None
                                    for group in grouped.values():
                                        for act in group:
                                            if (
                                                act["provider"] == change.source_provider
                                                and str(act["id"]) == change.activity_id
                                            ):
                                                source_activity = act
                                                break
                                        if source_activity:
                                            break

                                    if source_activity:
                                        # Convert source activity to spreadsheet format
                                        activity_data = convert_activity_to_spreadsheet_format(source_activity, grouped)

                                        # Create the activity in spreadsheet
                                        new_id = spreadsheet_provider.create_activity(activity_data)
                                        if new_id:
                                            print(f"✓ Added activity to spreadsheet with ID {new_id}")
                                        else:
                                            print("✗ Failed to add activity to spreadsheet")
                                    else:
                                        print("✗ Could not find source activity")
                                except Exception as e:
                                    print(f"✗ Error adding to spreadsheet: {e}")
                            else:
                                print("Skipped")

                    # Process spreadsheet notes updates (UPDATE_NAME for notes field)
                    if spreadsheet_name_changes and spreadsheet_provider:
                        print("\nProcessing Spreadsheet notes updates...")
                        for change in spreadsheet_name_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = spreadsheet_provider.update_activity(
                                        {
                                            "spreadsheet_id": change.activity_id,
                                            "notes": change.new_value,
                                        }
                                    )
                                    if success:
                                        print(f"✓ Notes for {change.activity_id}")
                                    else:
                                        print(f"✗ Notes for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Notes for {change.activity_id}: {e}")
                            else:
                                print("Skipped")

                    # Process spreadsheet metadata updates (UPDATE_METADATA for duration_hms, etc.)
                    if spreadsheet_metadata_changes and spreadsheet_provider:
                        print("\nProcessing Spreadsheet metadata updates...")
                        for change in spreadsheet_metadata_changes:
                            prompt = f"\n{change}? (y/n): "
                            response = input(prompt).strip().lower()

                            if response == "y":
                                try:
                                    success = spreadsheet_provider.update_activity(
                                        {
                                            "spreadsheet_id": change.activity_id,
                                            "duration_hms": change.new_value,
                                        }
                                    )
                                    if success:
                                        print(f"✓ Metadata for {change.activity_id}")
                                    else:
                                        print(f"✗ Metadata for {change.activity_id}")
                                except Exception as e:
                                    print(f"✗ Metadata for {change.activity_id}: {e}")
                            else:
                                print("Skipped")
        else:
            print("\nNo changes needed - all activities are synchronized!")
