"""Intervals.icu provider for tracekit."""

import datetime
import json
import os
from decimal import Decimal
from typing import Any

import requests

from tracekit.provider_sync import ProviderSync
from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.intervalsicu.intervalsicu_activity import IntervalsICUActivity
from tracekit.user_context import get_user_id

_BASE_URL = "https://intervals.icu/api/v1"


class IntervalsICUProvider(FitnessProvider):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        cfg = self.config or {}
        if cfg.get("use_personal_credentials"):
            self.client_id = cfg.get("client_id", "").strip()
            self.client_secret = cfg.get("client_secret", "").strip()
        else:
            self.client_id = os.environ.get("INTERVALSICU_CLIENT_ID", "").strip() or cfg.get("client_id", "").strip()
            self.client_secret = (
                os.environ.get("INTERVALSICU_CLIENT_SECRET", "").strip() or cfg.get("client_secret", "").strip()
            )
        self.access_token = cfg.get("access_token", "").strip()
        # athlete_id from config; "0" is the API shortcut for the current user
        self.athlete_id = cfg.get("athlete_id", "0").strip() or "0"

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, path: str, **kwargs) -> Any:
        url = f"{_BASE_URL}{path}"
        resp = requests.get(url, headers=self._auth_headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict) -> Any:
        url = f"{_BASE_URL}{path}"
        resp = requests.put(url, headers=self._auth_headers(), json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @property
    def provider_name(self) -> str:
        return "intervalsicu"

    @staticmethod
    def _parse_date_local(dt_str: str | None) -> int | None:
        """Parse an ISO-8601 local datetime string from Intervals.icu into a UTC Unix timestamp.

        Intervals.icu returns start_date_local without a timezone offset (e.g.
        "2024-11-19T10:30:00").  We treat it as UTC since we have no timezone
        info from the API for this field.
        """
        if not dt_str:
            return None
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return int(dt.timestamp())
        except Exception:
            return None

    @staticmethod
    def _seconds_to_hms(seconds: int | None) -> str | None:
        if not seconds:
            return None
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _activity_to_model(self, raw: dict) -> IntervalsICUActivity:
        """Map a raw Intervals.icu activity dict to an IntervalsICUActivity."""
        act = IntervalsICUActivity()
        act.intervalsicu_id = str(raw.get("id", ""))
        act.name = str(raw.get("name", "") or "")
        act.activity_type = str(raw.get("type", "") or "")

        distance_m = raw.get("distance")
        if distance_m:
            act.distance = Decimal(str(float(distance_m) * 0.000621371))

        act.start_time = self._parse_date_local(raw.get("start_date_local"))

        elapsed = raw.get("elapsed_time") or raw.get("moving_time")
        act.duration_hms = self._seconds_to_hms(elapsed)

        act.total_elevation_gain = (
            Decimal(str(raw["total_elevation_gain"])) if raw.get("total_elevation_gain") else None
        )
        avg_hr = raw.get("average_heartrate")
        if avg_hr:
            act.avg_heart_rate = int(avg_hr)
        max_hr = raw.get("max_heartrate")
        if max_hr:
            act.max_heart_rate = int(max_hr)
        if raw.get("calories"):
            act.calories = int(raw["calories"])

        gear = raw.get("gear")
        if isinstance(gear, dict) and gear.get("name"):
            act.equipment = str(gear["name"])

        act.raw_data = json.dumps(raw, default=str)
        return act

    def pull_activities(self, date_filter: str | None = None) -> list[IntervalsICUActivity]:
        """Pull activities from Intervals.icu for the given month (YYYY-MM)."""
        if date_filter is None:
            print("Intervals.icu provider: pulling all activities not implemented yet")
            return []

        year, month = map(int, date_filter.split("-"))

        if not ProviderSync.get_or_none(date_filter, self.provider_name):
            # Build date range: first day of month → first day of next month (exclusive)
            oldest = f"{year}-{month:02d}-01"
            newest = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

            raw_activities = self._get(
                f"/athlete/{self.athlete_id}/activities",
                params={"oldest": oldest, "newest": newest},
            )
            print(f"Found {len(raw_activities)} Intervals.icu activities for {date_filter}")

            uid = get_user_id()
            for raw in raw_activities:
                try:
                    act = self._activity_to_model(raw)
                    existing = IntervalsICUActivity.get_or_none(
                        (IntervalsICUActivity.intervalsicu_id == act.intervalsicu_id)
                        & (IntervalsICUActivity.user_id == uid)
                    )
                    if existing:
                        continue
                    act.user_id = uid
                    act.save()
                except Exception as e:
                    print(f"Error processing Intervals.icu activity {raw.get('id')}: {e}")
                    continue

            ProviderSync.create(year_month=date_filter, provider=self.provider_name, user_id=uid)
            print(f"Intervals.icu sync complete for {date_filter}")

        # Return all activities for this month from the database
        start = datetime.datetime(year, month, 1, tzinfo=datetime.UTC)
        end = datetime.datetime(
            year + 1 if month == 12 else year, 1 if month == 12 else month + 1, 1, tzinfo=datetime.UTC
        )
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        return list(
            IntervalsICUActivity.select().where(
                (IntervalsICUActivity.start_time >= start_ts)
                & (IntervalsICUActivity.start_time < end_ts)
                & (IntervalsICUActivity.user_id == get_user_id())
            )
        )

    def sync_single_activity(self, activity_id: str) -> IntervalsICUActivity | None:
        """Fetch a single activity from Intervals.icu by ID and upsert it locally.

        Used by the webhook handler for create/update events.
        """
        try:
            raw = self._get(f"/activity/{activity_id}")
        except Exception as e:
            print(f"Intervals.icu webhook: error fetching activity {activity_id}: {e}")
            return None

        if raw is None:
            return None

        uid = get_user_id()
        local = self._activity_to_model(raw)

        existing = IntervalsICUActivity.get_or_none(
            (IntervalsICUActivity.intervalsicu_id == str(activity_id)) & (IntervalsICUActivity.user_id == uid)
        )
        if existing:
            for field in (
                "name",
                "activity_type",
                "distance",
                "start_time",
                "duration_hms",
                "equipment",
                "raw_data",
                "total_elevation_gain",
                "avg_heart_rate",
                "max_heart_rate",
                "calories",
            ):
                val = getattr(local, field, None)
                if val is not None:
                    setattr(existing, field, val)
            existing.save()
            print(f"Intervals.icu webhook: updated local activity {activity_id}")
            return existing
        else:
            local.user_id = uid
            local.save()
            print(f"Intervals.icu webhook: created local activity {activity_id}")
            return local

    # Abstract method implementations

    def create_activity(self, activity_data: dict[str, Any]) -> IntervalsICUActivity:
        activity_data["user_id"] = get_user_id()
        return IntervalsICUActivity.create(**activity_data)

    def get_activity_by_id(self, activity_id: str) -> IntervalsICUActivity | None:
        return IntervalsICUActivity.get_or_none(
            (IntervalsICUActivity.intervalsicu_id == activity_id) & (IntervalsICUActivity.user_id == get_user_id())
        )

    def update_activity(self, activity_data: dict[str, Any]) -> bool:
        """Update an existing Intervals.icu activity via API."""
        provider_id = activity_data["intervalsicu_id"]
        update_data = {k: v for k, v in activity_data.items() if k != "intervalsicu_id"}

        try:
            self._put(f"/activity/{provider_id}", update_data)

            # Refresh local copy
            try:
                fresh = self._get(f"/activity/{provider_id}")
                local = IntervalsICUActivity.get_or_none(
                    (IntervalsICUActivity.intervalsicu_id == str(provider_id))
                    & (IntervalsICUActivity.user_id == get_user_id())
                )
                if local and fresh:
                    local.name = str(fresh.get("name", "") or "")
                    local.save()
            except Exception as e:
                print(f"Could not refresh local Intervals.icu activity {provider_id} after update: {e}")

            return True
        except Exception as e:
            print(f"Error updating Intervals.icu activity {provider_id}: {e}")
            raise

    def get_all_gear(self) -> dict[str, str]:
        """Get all gear from Intervals.icu athlete profile."""
        try:
            gear_list = self._get(f"/athlete/{self.athlete_id}/gear")
            gear_dict = {}
            for item in gear_list:
                gear_id = str(item.get("id", ""))
                gear_name = str(item.get("name", ""))
                if gear_id and gear_name and not item.get("retired"):
                    gear_dict[gear_id] = gear_name
            return gear_dict
        except Exception as e:
            print(f"Error getting Intervals.icu gear: {e}")
            return {}

    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set gear for an Intervals.icu activity by gear name."""
        try:
            all_gear = self.get_all_gear()
            gear_id = None
            for gid, gname in all_gear.items():
                if gname == gear_name:
                    gear_id = gid
                    break

            if gear_id is None:
                print(f"Gear '{gear_name}' not found in Intervals.icu gear list")
                return False

            self._put(f"/activity/{activity_id}", {"gear": {"id": gear_id}})

            # Refresh local copy
            try:
                fresh = self._get(f"/activity/{activity_id}")
                local = IntervalsICUActivity.get_or_none(
                    (IntervalsICUActivity.intervalsicu_id == str(activity_id))
                    & (IntervalsICUActivity.user_id == get_user_id())
                )
                if local and fresh:
                    gear = fresh.get("gear")
                    if isinstance(gear, dict) and gear.get("name"):
                        local.equipment = str(gear["name"])
                    local.save()
            except Exception as e:
                print(f"Could not refresh local Intervals.icu activity {activity_id} after set_gear: {e}")

            return True
        except Exception as e:
            print(f"Error setting gear for Intervals.icu activity {activity_id}: {e}")
            return False

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Delete activities for a specific month or all activities."""
        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )
            uid = get_user_id()
            return (
                IntervalsICUActivity.delete()
                .where(
                    (IntervalsICUActivity.start_time >= start_timestamp)
                    & (IntervalsICUActivity.start_time <= end_timestamp)
                    & (IntervalsICUActivity.user_id == uid)
                )
                .execute()
            )
        else:
            return IntervalsICUActivity.delete().where(IntervalsICUActivity.user_id == get_user_id()).execute()
