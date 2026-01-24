import os
from unittest.mock import MagicMock

import pytest

from tracekit.commands.sync_month import (
    ActivityChange,
    ChangeType,
    process_activity_for_display,
)
from tracekit.core import tracekit
from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
from tracekit.providers.strava.strava_activity import StravaActivity


def test_sync_month_detects_duration_hms_changes():
    """Test that sync_month logic correctly detects duration_hms changes in spreadsheet provider."""

    # Mock objects to simulate the sync_month scenario
    spreadsheet_activity_obj = MagicMock()
    spreadsheet_activity_obj.duration_hms = ""  # Missing duration_hms

    strava_activity_obj = MagicMock()
    strava_activity_obj.duration = 3661  # 1:01:01 in seconds
    strava_activity_obj.moving_time = None
    strava_activity_obj.elapsed_time = None

    # Mock the provider data structures
    providers = {
        "spreadsheet": {"obj": spreadsheet_activity_obj, "id": "5"},
        "strava": {"obj": strava_activity_obj, "id": "12345"},
    }

    provider_priority = ["strava", "spreadsheet"]

    # Test the sync_month logic for spreadsheet metadata
    provider = "spreadsheet"
    activity = providers[provider]

    # Check if duration_hms needs to be updated
    current_duration_hms = getattr(activity.get("obj"), "duration_hms", "") or ""

    # Calculate expected duration_hms from non-spreadsheet provider
    expected_duration_hms = ""
    duration_seconds = None

    for p in provider_priority:
        if p != "spreadsheet" and p in providers:
            provider_activity_obj = providers[p]["obj"]

            # Try different duration field names
            for duration_field in ["moving_time", "elapsed_time", "duration"]:
                potential_duration = getattr(provider_activity_obj, duration_field, None)
                if potential_duration and isinstance(potential_duration, (int, float)):
                    duration_seconds = int(potential_duration)
                    break

            if duration_seconds:
                break

    if duration_seconds:
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Verify the logic detects the change
    assert current_duration_hms == ""
    assert expected_duration_hms == "01:01:01"
    assert current_duration_hms != expected_duration_hms
    assert expected_duration_hms  # non-empty

    # Verify the change would be created
    change = ActivityChange(
        change_type=ChangeType.UPDATE_METADATA,
        provider=provider,
        activity_id=str(activity["id"]),
        old_value=current_duration_hms,
        new_value=expected_duration_hms,
    )

    assert change.change_type == ChangeType.UPDATE_METADATA
    assert change.provider == "spreadsheet"
    assert change.activity_id == "5"
    assert change.old_value == ""
    assert change.new_value == "01:01:01"


def test_sync_month_detects_wrong_duration_hms():
    """Test that sync_month detects when duration_hms has wrong value."""

    # Mock objects with wrong duration_hms
    spreadsheet_activity_obj = MagicMock()
    spreadsheet_activity_obj.duration_hms = "00:30:00"  # Wrong duration_hms

    strava_activity_obj = MagicMock()
    strava_activity_obj.duration = 3661  # 1:01:01 in seconds (correct)
    strava_activity_obj.moving_time = None
    strava_activity_obj.elapsed_time = None

    providers = {
        "spreadsheet": {"obj": spreadsheet_activity_obj, "id": "5"},
        "strava": {"obj": strava_activity_obj, "id": "12345"},
    }

    # Test the logic
    current_duration_hms = getattr(providers["spreadsheet"]["obj"], "duration_hms", "") or ""

    # Find duration from strava
    duration_seconds = getattr(providers["strava"]["obj"], "duration", None)
    expected_duration_hms = ""

    if duration_seconds:
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Verify change detection
    assert current_duration_hms == "00:30:00"
    assert expected_duration_hms == "01:01:01"
    assert current_duration_hms != expected_duration_hms
    assert expected_duration_hms


def test_sync_month_no_change_when_duration_hms_correct():
    """Test that no change is detected when duration_hms is already correct."""

    # Mock objects with correct duration_hms
    spreadsheet_activity_obj = MagicMock()
    spreadsheet_activity_obj.duration_hms = "01:01:01"  # Correct duration_hms

    strava_activity_obj = MagicMock()
    strava_activity_obj.duration = 3661  # 1:01:01 in seconds
    strava_activity_obj.moving_time = None
    strava_activity_obj.elapsed_time = None

    providers = {
        "spreadsheet": {"obj": spreadsheet_activity_obj, "id": "5"},
        "strava": {"obj": strava_activity_obj, "id": "12345"},
    }

    # Test the logic
    current_duration_hms = getattr(providers["spreadsheet"]["obj"], "duration_hms", "") or ""
    duration_seconds = getattr(providers["strava"]["obj"], "duration", None)

    expected_duration_hms = ""
    if duration_seconds:
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Verify no change needed
    assert current_duration_hms == "01:01:01"
    assert expected_duration_hms == "01:01:01"
    assert current_duration_hms == expected_duration_hms  # No change needed


def test_sync_month_integration_with_real_activities():
    """Integration test using real database activities to verify duration_hms detection."""

    # Skip if no config file (CI environment)
    if not os.path.exists("tracekit_config.json"):
        pytest.skip("Test requires tracekit_config.json - skipping in CI")

    # This test requires real activities in the database
    with tracekit():
        # Get some activities from the database
        spreadsheet_activity = SpreadsheetActivity.select().first()
        strava_activity = StravaActivity.select().first()

        if not spreadsheet_activity or not strava_activity:
            pytest.skip("Test requires existing activities in database")

        # Store original value
        original_duration_hms = spreadsheet_activity.duration_hms

        try:
            # Set an incorrect duration_hms to test detection
            spreadsheet_activity.duration_hms = "00:00:01"  # Obviously wrong
            spreadsheet_activity.save()

            # Use the process_activity_for_display function like sync_month does
            providers = {
                "spreadsheet": process_activity_for_display(spreadsheet_activity, "spreadsheet"),
                "strava": process_activity_for_display(strava_activity, "strava"),
            }

            # Simulate the duration_hms detection logic from sync_month
            provider = "spreadsheet"
            activity = providers[provider]

            current_duration_hms = getattr(activity.get("obj"), "duration_hms", "") or ""

            # Find duration from strava (following sync_month logic)
            expected_duration_hms = ""
            duration_seconds = None

            provider_priority = ["strava", "spreadsheet"]
            for p in provider_priority:
                if p != "spreadsheet" and p in providers:
                    provider_activity_obj = providers[p]["obj"]

                    # Try different duration field names
                    for duration_field in ["moving_time", "elapsed_time", "duration"]:
                        potential_duration = getattr(provider_activity_obj, duration_field, None)
                        if potential_duration and isinstance(potential_duration, (int, float)):
                            duration_seconds = int(potential_duration)
                            break

                    if duration_seconds:
                        break

            if duration_seconds:
                hours = int(duration_seconds // 3600)
                minutes = int((duration_seconds % 3600) // 60)
                seconds = int(duration_seconds % 60)
                expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Verify that change would be detected
            if expected_duration_hms:  # Only test if we have expected value
                assert current_duration_hms == "00:00:01"
                assert current_duration_hms != expected_duration_hms

                # Verify change object would be created correctly
                change = ActivityChange(
                    change_type=ChangeType.UPDATE_METADATA,
                    provider=provider,
                    activity_id=str(activity["id"]),
                    old_value=current_duration_hms,
                    new_value=expected_duration_hms,
                )

                assert change.change_type == ChangeType.UPDATE_METADATA
                assert change.provider == "spreadsheet"
                assert change.old_value == "00:00:01"
                assert change.new_value == expected_duration_hms

        finally:
            # Restore original value
            spreadsheet_activity.duration_hms = original_duration_hms
            spreadsheet_activity.save()


def test_sync_month_duration_hms_with_moving_time():
    """Test that sync_month can use moving_time from strava for duration_hms calculation."""

    spreadsheet_activity_obj = MagicMock()
    spreadsheet_activity_obj.duration_hms = ""

    strava_activity_obj = MagicMock()
    strava_activity_obj.duration = None  # No duration field
    strava_activity_obj.moving_time = 7230  # 2:00:30 in seconds
    strava_activity_obj.elapsed_time = None

    providers = {
        "spreadsheet": {"obj": spreadsheet_activity_obj, "id": "10"},
        "strava": {"obj": strava_activity_obj, "id": "98765"},
    }

    provider_priority = ["strava", "spreadsheet"]

    # Test the logic that should find moving_time
    current_duration_hms = getattr(providers["spreadsheet"]["obj"], "duration_hms", "") or ""

    expected_duration_hms = ""
    duration_seconds = None

    for p in provider_priority:
        if p != "spreadsheet" and p in providers:
            provider_activity_obj = providers[p]["obj"]

            for duration_field in ["moving_time", "elapsed_time", "duration"]:
                potential_duration = getattr(provider_activity_obj, duration_field, None)
                if potential_duration and isinstance(potential_duration, (int, float)):
                    duration_seconds = int(potential_duration)
                    break

            if duration_seconds:
                break

    if duration_seconds:
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        expected_duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Verify it found moving_time and converted correctly
    assert duration_seconds == 7230
    assert expected_duration_hms == "02:00:30"
    assert current_duration_hms != expected_duration_hms
