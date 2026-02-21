"""Tests for tracekit.sync — the core sync business logic.

These tests exercise the module directly (not through the CLI wrapper) so that:
  * compute_month_changes() and apply_change() are covered
  * The ActivityChange data model (serialisation round-trips) is tested
  * Edge-cases for correlation, name/equipment/metadata sync are explicit
"""

from unittest.mock import MagicMock

import pytest

from tracekit.sync import (
    ActivityChange,
    ChangeType,
    apply_change,
    compute_month_changes,
    convert_activity_to_spreadsheet_format,
    generate_correlation_key,
    process_activity_for_display,
)

# ---------------------------------------------------------------------------
# ActivityChange data model
# ---------------------------------------------------------------------------


class TestActivityChange:
    def test_str_update_name(self):
        ch = ActivityChange(
            change_type=ChangeType.UPDATE_NAME,
            provider="strava",
            activity_id="42",
            old_value="Old Ride",
            new_value="Morning Ride",
        )
        assert "strava" in str(ch)
        assert "Old Ride" in str(ch)
        assert "Morning Ride" in str(ch)

    def test_str_update_equipment(self):
        ch = ActivityChange(
            change_type=ChangeType.UPDATE_EQUIPMENT,
            provider="ridewithgps",
            activity_id="7",
            old_value="",
            new_value="Trek Émonda",
        )
        assert "ridewithgps" in str(ch)
        assert "Trek Émonda" in str(ch)

    def test_str_update_metadata(self):
        ch = ActivityChange(
            change_type=ChangeType.UPDATE_METADATA,
            provider="spreadsheet",
            activity_id="5",
            old_value="",
            new_value="01:30:00",
        )
        assert "duration_hms" in str(ch)
        assert "01:30:00" in str(ch)

    def test_str_add_activity(self):
        ch = ActivityChange(
            change_type=ChangeType.ADD_ACTIVITY,
            provider="spreadsheet",
            activity_id="99",
            new_value="Lunch Ride",
            source_provider="strava",
        )
        assert "spreadsheet" in str(ch)
        assert "Lunch Ride" in str(ch)
        assert "strava" in str(ch)

    def test_str_link_activity(self):
        ch = ActivityChange(
            change_type=ChangeType.LINK_ACTIVITY,
            provider="garmin",
            activity_id="10",
            new_value="20",
            source_provider="strava",
        )
        assert "garmin" in str(ch)

    def test_str_unknown(self):
        # Manually test the fallback branch — create a change with a real type
        # then patch its __str__; simpler: just confirm the default is reached
        # via a subclass trick.  We verify the "Unknown change" path indirectly
        # by testing that all ChangeType values produce non-default strings.
        for ct in ChangeType:
            ch = ActivityChange(change_type=ct, provider="p", activity_id="1")
            assert str(ch) != "Unknown change"

    def test_to_dict_round_trip(self):
        ch = ActivityChange(
            change_type=ChangeType.UPDATE_EQUIPMENT,
            provider="strava",
            activity_id="123",
            old_value="Old Bike",
            new_value="New Bike",
            source_provider=None,
        )
        d = ch.to_dict()
        assert d["change_type"] == "Update Equipment"
        assert d["provider"] == "strava"
        assert d["activity_id"] == "123"

        restored = ActivityChange.from_dict(d)
        assert restored == ch

    def test_from_dict_minimal(self):
        """from_dict handles optional fields that may be absent."""
        d = {"change_type": "Update Name", "provider": "garmin", "activity_id": "7"}
        ch = ActivityChange.from_dict(d)
        assert ch.change_type == ChangeType.UPDATE_NAME
        assert ch.old_value is None
        assert ch.new_value is None
        assert ch.source_provider is None

    def test_to_dict_all_change_types(self):
        for ct in ChangeType:
            ch = ActivityChange(change_type=ct, provider="x", activity_id="1")
            d = ch.to_dict()
            assert ActivityChange.from_dict(d).change_type == ct


# ---------------------------------------------------------------------------
# process_activity_for_display
# ---------------------------------------------------------------------------


class TestProcessActivityForDisplay:
    def _make_act(self, **kwargs):
        act = MagicMock()
        for k, v in kwargs.items():
            setattr(act, k, v)
        return act

    def test_basic_fields(self):
        act = self._make_act(
            provider_id="99",
            start_time=1720411200,
            distance=15.5,
            name="Hill Climb",
            equipment="Trek",
        )
        result = process_activity_for_display(act, "strava")
        assert result["provider"] == "strava"
        assert result["id"] == "99"
        assert result["timestamp"] == 1720411200
        assert result["distance"] == 15.5
        assert result["name"] == "Hill Climb"
        assert result["equipment"] == "Trek"

    def test_spreadsheet_uses_notes_as_name(self):
        act = self._make_act(
            provider_id="5",
            start_time=1720411200,
            distance=10.0,
            notes="Spreadsheet name",
            name="ignored",
        )
        result = process_activity_for_display(act, "spreadsheet")
        assert result["name"] == "Spreadsheet name"

    def test_missing_distance_defaults_to_zero(self):
        act = self._make_act(provider_id="1", start_time=1720411200, distance=None, name="")
        result = process_activity_for_display(act, "garmin")
        assert result["distance"] == 0.0

    def test_missing_start_time_defaults_to_zero(self):
        act = self._make_act(provider_id="1", start_time=None, distance=5.0, name="")
        result = process_activity_for_display(act, "garmin")
        assert result["timestamp"] == 0


# ---------------------------------------------------------------------------
# generate_correlation_key
# ---------------------------------------------------------------------------


class TestGenerateCorrelationKey:
    @pytest.mark.parametrize(
        "ts1, d1, ts2, d2",
        [
            (1746504000, 30.55, 1746570520, 30.546996425),
            (1748491200, 15.0, 1748559503, 15.00241904),
            (1743546548, 15.551244, 1743480000, 15.55),
            (1720411200, 2.5, 1720475888, 2.5043798),
            (1741642895, 2.4997, 1741579200, 2.5),
        ],
    )
    def test_same_day_similar_distance_match(self, ts1, d1, ts2, d2):
        assert generate_correlation_key(ts1, d1) == generate_correlation_key(ts2, d2)

    def test_empty_for_zero_timestamp(self):
        assert generate_correlation_key(0, 10.0) == ""

    def test_empty_for_zero_distance(self):
        assert generate_correlation_key(1720411200, 0) == ""

    def test_different_dates_no_match(self):
        # Same distance, two weeks apart → different keys
        assert generate_correlation_key(1720411200, 15.0) != generate_correlation_key(1721620800, 15.0)

    def test_different_distances_no_match(self):
        # Same day, wildly different distances
        assert generate_correlation_key(1720411200, 5.0) != generate_correlation_key(1720411200, 25.0)

    def test_key_format(self):
        key = generate_correlation_key(1720411200, 15.0)
        parts = key.split("_")
        assert len(parts) == 2
        assert parts[0].count("-") == 2  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# convert_activity_to_spreadsheet_format
# ---------------------------------------------------------------------------


class TestConvertActivityToSpreadsheetFormat:
    def _make_source(
        self,
        provider="strava",
        ts=1720411200,
        distance=15.5,
        name="Test",
        equipment="Trek",
    ):
        obj = MagicMock()
        obj.activity_type = "Ride"
        obj.location_name = "Loc"
        obj.city = "City"
        obj.state = "GA"
        obj.temperature = "72"
        obj.duration = 3600
        obj.max_speed = "25"
        obj.avg_heart_rate = "150"
        obj.max_heart_rate = "175"
        obj.calories = "600"
        obj.max_elevation = "800"
        obj.total_elevation_gain = "300"
        obj.with_names = ""
        obj.avg_cadence = "85"
        return {
            "provider": provider,
            "id": "12345",
            "timestamp": ts,
            "distance": distance,
            "obj": obj,
            "name": name,
            "equipment": equipment,
        }

    def test_basic_conversion(self):
        src = self._make_source()
        key = generate_correlation_key(src["timestamp"], src["distance"])
        grouped = {key: [src]}
        result = convert_activity_to_spreadsheet_format(src, grouped)

        assert result["start_time"] == "2024-07-08"
        assert result["activity_type"] == "Ride"
        assert result["distance"] == 15.5
        assert result["notes"] == "Test"
        assert result["equipment"] == "Trek"
        assert result["duration_hms"] == "01:00:00"

    def test_cross_provider_ids(self):
        strava_act = self._make_source("strava", distance=15.5)
        garmin_act = {**strava_act, "provider": "garmin", "id": "G999"}
        rwgps_act = {**strava_act, "provider": "ridewithgps", "id": "R111"}
        key = generate_correlation_key(strava_act["timestamp"], strava_act["distance"])
        grouped = {key: [strava_act, garmin_act, rwgps_act]}

        result = convert_activity_to_spreadsheet_format(strava_act, grouped)

        assert result["strava_id"] == "12345"
        assert result["garmin_id"] == "G999"
        assert result["ridewithgps_id"] == "R111"

    def test_duration_hms_format(self):
        src = self._make_source()
        src["obj"].duration = 3661  # 1:01:01
        key = generate_correlation_key(src["timestamp"], src["distance"])
        result = convert_activity_to_spreadsheet_format(src, {key: [src]})
        assert result["duration_hms"] == "01:01:01"

    def test_no_duration(self):
        src = self._make_source()
        src["obj"].duration = None
        key = generate_correlation_key(src["timestamp"], src["distance"])
        result = convert_activity_to_spreadsheet_format(src, {key: [src]})
        assert result["duration_hms"] == ""


# ---------------------------------------------------------------------------
# compute_month_changes  (unit-tested with a mocked Tracekit)
# ---------------------------------------------------------------------------


def _make_tracekit_mock(activities_by_provider: dict, provider_config: dict | None = None):
    """Return a MagicMock Tracekit instance that returns *activities_by_provider*."""
    tk = MagicMock()
    tk.pull_activities.return_value = activities_by_provider
    if provider_config is None:
        provider_config = {
            p: {
                "enabled": True,
                "priority": i,
                "sync_name": True,
                "sync_equipment": True,
            }
            for i, p in enumerate(activities_by_provider.keys())
        }
    tk.config = {"providers": provider_config, "home_timezone": "US/Eastern"}
    from zoneinfo import ZoneInfo

    tk.home_tz = ZoneInfo("US/Eastern")
    return tk


def _make_act_obj(name="Ride", equipment="Bike", duration=3600, distance=15.0, ts=1720411200):
    obj = MagicMock()
    obj.provider_id = str(ts)  # unique enough
    obj.start_time = ts
    obj.distance = distance
    obj.name = name
    obj.notes = name  # for spreadsheet
    obj.equipment = equipment
    obj.duration = duration
    obj.duration_hms = ""
    obj.moving_time = None
    obj.elapsed_time = None
    return obj


class TestComputeMonthChanges:
    def test_no_activities_returns_empty(self):
        tk = _make_tracekit_mock({})
        grouped, changes = compute_month_changes(tk, "2024-07")
        assert grouped == {}
        assert changes == []

    def test_single_provider_no_changes(self):
        act = _make_act_obj()
        tk = _make_tracekit_mock({"strava": [act]})
        _grouped, changes = compute_month_changes(tk, "2024-07")
        # Single-provider groups are skipped
        assert changes == []

    def test_matching_activities_no_name_change_needed(self):
        act1 = _make_act_obj(name="Morning Ride", ts=1720411200, distance=15.0)
        act2 = _make_act_obj(name="Morning Ride", ts=1720411200, distance=15.0)
        act2.provider_id = "other-id"
        tk = _make_tracekit_mock(
            {"strava": [act1], "ridewithgps": [act2]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "ridewithgps": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        name_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_NAME]
        assert name_changes == []

    def test_name_mismatch_generates_change(self):
        act1 = _make_act_obj(name="Authoritative Name", ts=1720411200, distance=15.0)
        act2 = _make_act_obj(name="Wrong Name", ts=1720411200, distance=15.0)
        act2.provider_id = "rwgps-id"
        tk = _make_tracekit_mock(
            {"strava": [act1], "ridewithgps": [act2]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "ridewithgps": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        name_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_NAME]
        assert len(name_changes) == 1
        assert name_changes[0].provider == "ridewithgps"
        assert name_changes[0].new_value == "Authoritative Name"

    def test_equipment_mismatch_generates_change(self):
        act1 = _make_act_obj(name="Ride", equipment="Trek", ts=1720411200, distance=15.0)
        act2 = _make_act_obj(name="Ride", equipment="", ts=1720411200, distance=15.0)
        act2.provider_id = "rwgps-id"
        tk = _make_tracekit_mock(
            {"strava": [act1], "ridewithgps": [act2]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "ridewithgps": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        equip_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_EQUIPMENT]
        assert any(c.provider == "ridewithgps" and c.new_value == "Trek" for c in equip_changes)

    def test_missing_provider_generates_add_activity(self):
        """An activity present in strava but absent from spreadsheet → ADD_ACTIVITY."""
        act = _make_act_obj(name="Ride", ts=1720411200, distance=15.0)
        act2 = _make_act_obj(name="Ride", ts=1720411200, distance=15.0)
        act2.provider_id = "rwgps-id"
        tk = _make_tracekit_mock(
            {"strava": [act], "ridewithgps": [act2]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "ridewithgps": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "spreadsheet": {
                    "enabled": True,
                    "priority": 3,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        add_changes = [c for c in changes if c.change_type == ChangeType.ADD_ACTIVITY]
        assert any(c.provider == "spreadsheet" for c in add_changes)

    def test_spreadsheet_duration_hms_missing_generates_metadata_change(self):
        strava_act = _make_act_obj(name="Ride", ts=1720411200, distance=15.0, duration=3661)
        spreadsheet_act = _make_act_obj(name="Ride", ts=1720411200, distance=15.0)
        spreadsheet_act.duration_hms = ""
        spreadsheet_act.notes = "Ride"
        spreadsheet_act.provider_id = "ss-5"
        tk = _make_tracekit_mock(
            {"strava": [strava_act], "spreadsheet": [spreadsheet_act]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "spreadsheet": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        meta_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_METADATA]
        assert len(meta_changes) == 1
        assert meta_changes[0].new_value == "01:01:01"

    def test_spreadsheet_correct_duration_hms_no_change(self):
        strava_act = _make_act_obj(name="Ride", ts=1720411200, distance=15.0, duration=3661)
        spreadsheet_act = _make_act_obj(name="Ride", ts=1720411200, distance=15.0)
        spreadsheet_act.duration_hms = "01:01:01"
        spreadsheet_act.notes = "Ride"
        spreadsheet_act.provider_id = "ss-5"
        tk = _make_tracekit_mock(
            {"strava": [strava_act], "spreadsheet": [spreadsheet_act]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                "spreadsheet": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": True,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        meta_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_METADATA]
        assert meta_changes == []

    def test_sync_name_false_skips_name_changes(self):
        act1 = _make_act_obj(name="Auth Name", ts=1720411200, distance=15.0)
        act2 = _make_act_obj(name="Other Name", ts=1720411200, distance=15.0)
        act2.provider_id = "rwgps-id"
        tk = _make_tracekit_mock(
            {"strava": [act1], "ridewithgps": [act2]},
            provider_config={
                "strava": {
                    "enabled": True,
                    "priority": 1,
                    "sync_name": True,
                    "sync_equipment": True,
                },
                # sync_name=False → no UPDATE_NAME changes for rwgps
                "ridewithgps": {
                    "enabled": True,
                    "priority": 2,
                    "sync_name": False,
                    "sync_equipment": True,
                },
            },
        )
        _, changes = compute_month_changes(tk, "2024-07")
        name_changes = [c for c in changes if c.change_type == ChangeType.UPDATE_NAME]
        assert name_changes == []


# ---------------------------------------------------------------------------
# apply_change
# ---------------------------------------------------------------------------


class TestApplyChange:
    def _make_tk(self):
        tk = MagicMock()
        tk.get_provider.return_value = MagicMock()
        return tk

    def test_update_name_strava(self):
        tk = self._make_tk()
        tk.get_provider.return_value.update_activity.return_value = True
        ch = ActivityChange(ChangeType.UPDATE_NAME, "strava", "42", "Old", "New")
        ok, msg = apply_change(ch, tk)
        assert ok
        assert "42" in msg

    def test_update_name_unknown_provider(self):
        tk = self._make_tk()
        ch = ActivityChange(ChangeType.UPDATE_NAME, "unknown_provider", "1", "A", "B")
        ok, msg = apply_change(ch, tk)
        assert not ok
        assert "not supported" in msg

    def test_update_equipment_ridewithgps(self):
        tk = self._make_tk()
        tk.get_provider.return_value.set_gear.return_value = True
        ch = ActivityChange(ChangeType.UPDATE_EQUIPMENT, "ridewithgps", "7", "", "Trek")
        ok, _msg = apply_change(ch, tk)
        assert ok

    def test_update_metadata_spreadsheet(self):
        tk = self._make_tk()
        tk.get_provider.return_value.update_activity.return_value = True
        ch = ActivityChange(ChangeType.UPDATE_METADATA, "spreadsheet", "5", "", "01:30:00")
        ok, _msg = apply_change(ch, tk)
        assert ok

    def test_update_metadata_non_spreadsheet_unsupported(self):
        tk = self._make_tk()
        ch = ActivityChange(ChangeType.UPDATE_METADATA, "strava", "5", "", "01:30:00")
        ok, msg = apply_change(ch, tk)
        assert not ok
        assert "not supported" in msg

    def test_add_activity_requires_grouped(self):
        tk = self._make_tk()
        ch = ActivityChange(
            ChangeType.ADD_ACTIVITY,
            "spreadsheet",
            "99",
            new_value="Ride",
            source_provider="strava",
        )
        ok, msg = apply_change(ch, tk, grouped=None)
        assert not ok
        assert "grouped" in msg

    def test_add_activity_source_not_found(self):
        tk = self._make_tk()
        ch = ActivityChange(
            ChangeType.ADD_ACTIVITY,
            "spreadsheet",
            "99",
            new_value="Ride",
            source_provider="strava",
        )
        ok, msg = apply_change(ch, tk, grouped={})
        assert not ok
        assert "not found" in msg

    def test_add_activity_spreadsheet_success(self):
        tk = self._make_tk()
        tk.get_provider.return_value.create_activity.return_value = 123

        act_obj = MagicMock()
        act_obj.activity_type = "Ride"
        act_obj.location_name = ""
        act_obj.city = ""
        act_obj.state = ""
        act_obj.temperature = ""
        act_obj.duration = 3600
        act_obj.max_speed = ""
        act_obj.avg_heart_rate = ""
        act_obj.max_heart_rate = ""
        act_obj.calories = ""
        act_obj.max_elevation = ""
        act_obj.total_elevation_gain = ""
        act_obj.with_names = ""
        act_obj.avg_cadence = ""
        source_act = {
            "provider": "strava",
            "id": "99",
            "timestamp": 1720411200,
            "distance": 15.0,
            "obj": act_obj,
            "name": "Ride",
            "equipment": "Trek",
        }
        key = generate_correlation_key(1720411200, 15.0)
        grouped = {key: [source_act]}
        ch = ActivityChange(
            ChangeType.ADD_ACTIVITY,
            "spreadsheet",
            "99",
            new_value="Ride",
            source_provider="strava",
        )
        ok, msg = apply_change(ch, tk, grouped=grouped)
        assert ok
        assert "123" in msg

    def test_provider_not_available(self):
        tk = MagicMock()
        tk.get_provider.return_value = None
        ch = ActivityChange(ChangeType.UPDATE_NAME, "strava", "1", "A", "B")
        ok, msg = apply_change(ch, tk)
        assert not ok
        assert "not available" in msg

    def test_apply_change_exception_returns_false(self):
        tk = MagicMock()
        tk.get_provider.side_effect = RuntimeError("boom")
        ch = ActivityChange(ChangeType.UPDATE_NAME, "strava", "1", "A", "B")
        ok, msg = apply_change(ch, tk)
        assert not ok
        assert "boom" in msg
