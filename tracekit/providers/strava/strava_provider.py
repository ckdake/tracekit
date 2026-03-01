"""Strava provider for tracekit."""

import datetime
import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any

import pytz
from dateutil.relativedelta import relativedelta
from stravalib import Client
from stravalib.exc import AccessUnauthorized, RateLimitExceeded, RateLimitTimeout

from tracekit.provider_status import (
    RATE_LIMIT_LONG_TERM,
    RATE_LIMIT_SHORT_TERM,
    ProviderRateLimitError,
    next_midnight_utc,
)
from tracekit.provider_sync import ProviderSync
from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.strava.strava_activity import StravaActivity
from tracekit.user_context import get_user_id


class _RaisingRateLimiter:
    """Stravalib-compatible rate limiter that raises ProviderRateLimitError.

    stravalib's default SleepingRateLimitRule calls ``time.sleep()`` for up to
    the rest of the day when the long-term limit is exceeded, causing Celery
    tasks to hang indefinitely.  This replacement raises immediately so the
    worker can decide whether to retry (short-term) or fail fast (long-term).
    """

    def __init__(self) -> None:
        self.log = logging.getLogger(f"{__name__}._RaisingRateLimiter")

    def __call__(self, response_headers: dict, method) -> None:
        from stravalib.util.limiter import (
            get_rates_from_response_headers,
            get_seconds_until_next_quarter,
        )

        rates = get_rates_from_response_headers(response_headers, method)
        if rates is None:
            self.log.warning("No rates present in response headers")
            return

        if rates.long_usage >= rates.long_limit:
            raise ProviderRateLimitError(
                "Strava daily rate limit exceeded — resets at midnight UTC. "
                "See https://developers.strava.com/docs/rate-limits/",
                provider="strava",
                limit_type=RATE_LIMIT_LONG_TERM,
                reset_at=next_midnight_utc(),
                retry_after=None,
            )

        if rates.short_usage >= rates.short_limit:
            timeout = get_seconds_until_next_quarter()
            raise ProviderRateLimitError(
                f"Strava short-term rate limit hit — retrying in {timeout}s. "
                "See https://developers.strava.com/docs/rate-limits/",
                provider="strava",
                limit_type=RATE_LIMIT_SHORT_TERM,
                reset_at=int(time.time()) + timeout,
                retry_after=timeout,
            )


class StravaProvider(FitnessProvider):
    def __init__(
        self,
        token: str,
        refresh_token: str | None = None,
        token_expires: str | None = "0",
        config: dict[str, Any] | None = None,
    ):
        super().__init__(config)

        self.debug = os.environ.get("STRAVALIB_DEBUG") == "1"
        if not self.debug and self.config:
            self.debug = self.config.get("debug", False)

        if self.debug:
            logging.basicConfig(level=logging.DEBUG)

        self.client = Client(
            access_token=token,
            refresh_token=refresh_token,
            token_expires=int(token_expires),
            rate_limiter=_RaisingRateLimiter(),
        )

    def _raise_rate_limit(self, exc: RateLimitExceeded, operation: str) -> None:
        """Convert a stravalib rate-limit exception into a ProviderRateLimitError.

        RateLimitTimeout (short-term, has a wait timeout) → RATE_LIMIT_SHORT_TERM.
        RateLimitExceeded without a short timeout      → RATE_LIMIT_LONG_TERM.
        """
        timeout = getattr(exc, "timeout", None)
        if isinstance(exc, RateLimitTimeout) and timeout and timeout <= 920:
            raise ProviderRateLimitError(
                f"Strava short-term rate limit hit during {operation} — retrying in {timeout}s. "
                f"See https://developers.strava.com/docs/rate-limits/",
                provider="strava",
                limit_type=RATE_LIMIT_SHORT_TERM,
                reset_at=int(__import__("time").time()) + int(timeout),
                retry_after=int(timeout),
            ) from exc
        raise ProviderRateLimitError(
            f"Strava daily rate limit exceeded during {operation} — resets at midnight UTC. "
            f"See https://developers.strava.com/docs/rate-limits/",
            provider="strava",
            limit_type=RATE_LIMIT_LONG_TERM,
            reset_at=next_midnight_utc(),
            retry_after=None,
        ) from exc

    def _handle_unauthorized(self, exc: AccessUnauthorized, operation: str) -> None:
        """Clear stored tokens and raise so callers know auth is gone."""
        print(f"Strava 401 Unauthorized during {operation} — clearing tokens.")
        try:
            from tracekit.appconfig import clear_strava_tokens

            clear_strava_tokens()
        except Exception as clear_err:
            print(f"Could not clear Strava tokens: {clear_err}")
        raise AccessUnauthorized(f"Strava token revoked or expired ({operation}). Please re-authorize.") from exc

    def _ensure_fresh_token(self) -> None:
        """Silently refresh the access token if it is expired or about to expire.

        Requires client_id and client_secret to be present in self.config.
        On success the new tokens are written back to the DB so subsequent
        provider instances (and the web app) see the updated values.
        Does nothing if the token is still valid or if credentials are missing.
        """
        try:
            expires_at = int(getattr(self.client, "token_expires", 0) or 0)
        except (TypeError, ValueError):
            expires_at = 0

        # Still valid with a 60-second buffer — nothing to do.
        if expires_at > 0 and time.time() < expires_at - 60:
            return

        cfg = self.config or {}
        client_id = cfg.get("client_id", "").strip()
        client_secret = cfg.get("client_secret", "").strip()
        refresh_token = cfg.get("refresh_token", "").strip()

        if not (client_id and client_secret and refresh_token):
            return  # Can't refresh; let the API call fail naturally.

        try:
            print("Strava access token expired — refreshing automatically…")
            token_info = self.client.refresh_access_token(
                client_id=int(client_id),
                client_secret=client_secret,
                refresh_token=refresh_token,
            )

            new_access = str(token_info["access_token"])
            new_refresh = str(token_info.get("refresh_token", refresh_token))
            new_expires = str(token_info.get("expires_at", "0"))

            # Update the in-memory client.
            self.client.access_token = new_access
            self.client.refresh_token = new_refresh
            self.client.token_expires = int(new_expires)

            # Update our config dict so future calls within the same instance are correct.
            cfg["access_token"] = new_access
            cfg["refresh_token"] = new_refresh
            cfg["token_expires"] = new_expires

            # Persist to DB so the web app and future instances see the new tokens.
            from tracekit.appconfig import load_config, save_config

            saved_config = load_config()
            providers = saved_config.get("providers", {})
            strava_updated = providers.get("strava", {}).copy()
            strava_updated["access_token"] = new_access
            strava_updated["refresh_token"] = new_refresh
            strava_updated["token_expires"] = new_expires
            providers["strava"] = strava_updated
            save_config({**saved_config, "providers": providers})

            print("Strava token refreshed and saved.")
        except AccessUnauthorized as e:
            self._handle_unauthorized(e, "token_refresh")
        except Exception as e:
            print(f"Strava token refresh failed: {e}. Proceeding with existing token.")

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return "strava"

    @staticmethod
    def _normalize_strava_gear_name(gear_name: str) -> str:
        """
        Extracts the year (YYYY) and the word(s) before it from a Strava gear name,
        and returns a string in the format 'YYYY EquipmentName'.
        If the gear name already starts with the year, return it unchanged.
        """
        match = re.search(r"(\b\d{4}\b)", gear_name)
        if match:
            year = match.group(1)
            before_year = gear_name[: match.start()].strip()
            # If the gear name already starts with the year, return as is
            if gear_name.strip().startswith(year):
                return gear_name
            return f"{year} {before_year}"
        return gear_name

    def pull_activities(self, date_filter: str | None = None) -> list[StravaActivity]:
        """Pull activities from Strava API for the given date filter."""
        if date_filter is None:
            print("Strava provider: pulling all activities not implemented yet")
            return []

        # Check if already synced
        existing_sync = ProviderSync.get_or_none(date_filter, self.provider_name)
        if not existing_sync:
            # First time processing this month - fetch from Strava API
            raw_activities = self._fetch_strava_activities_for_month(date_filter)
            print(f"Found {len(raw_activities)} Strava activities for {date_filter}")

            processed_count = 0
            for strava_lib_activity in raw_activities:
                try:
                    # Convert stravalib activity to our StravaActivity
                    strava_activity = self._convert_to_strava_activity(strava_lib_activity)

                    # Check for duplicates (scoped to current user)
                    uid = get_user_id()
                    existing = StravaActivity.get_or_none(
                        (StravaActivity.strava_id == strava_activity.strava_id) & (StravaActivity.user_id == uid)
                    )
                    if existing:
                        continue

                    # Save to database
                    strava_activity.user_id = uid
                    strava_activity.save()
                    processed_count += 1

                except ProviderRateLimitError:
                    # Let rate-limit errors propagate so the worker can handle them correctly.
                    raise
                except Exception as e:
                    print(f"Error processing Strava activity: {e}")
                    continue

            # Mark this month as synced
            ProviderSync.create(year_month=date_filter, provider=self.provider_name, user_id=get_user_id())
            print(f"Synced {processed_count} Strava activities")
        else:
            print(f"Month {date_filter} already synced for {self.provider_name}")

        # Always return activities for the requested month from database
        return self._get_strava_activities_for_month(date_filter)

    def _get_strava_activities_for_month(self, date_filter: str) -> list["StravaActivity"]:
        """Get StravaActivity objects for a specific month."""

        year, month = map(int, date_filter.split("-"))
        strava_activities = []

        for activity in StravaActivity.select().where(StravaActivity.user_id == get_user_id()):
            if hasattr(activity, "start_time") and activity.start_time:
                try:
                    # Convert timestamp to datetime for comparison
                    dt = datetime.datetime.fromtimestamp(int(activity.start_time))
                    if dt.year == year and dt.month == month:
                        strava_activities.append(activity)
                except (ValueError, TypeError):
                    continue

        return strava_activities

    def _fetch_strava_activities_for_month(self, year_month: str):
        """Fetch raw stravalib activities for the given year_month."""
        self._ensure_fresh_token()
        year, month = map(int, year_month.split("-"))
        tz = pytz.UTC
        start_date = tz.localize(datetime.datetime(year, month, 1))
        end_date = start_date + relativedelta(months=1)

        try:
            activities = []
            for activity in self.client.get_activities(after=start_date, before=end_date, limit=None):
                activities.append(activity)
            return activities
        except AccessUnauthorized as exc:
            self._handle_unauthorized(exc, "fetch_activities")
        except (RateLimitExceeded, RateLimitTimeout) as exc:
            self._raise_rate_limit(exc, "fetch_activities")

    def _activity_to_model(self, full_activity) -> StravaActivity:
        """Map a stravalib DetailedActivity to a StravaActivity model (no API calls)."""
        strava_activity = StravaActivity()

        strava_activity.strava_id = str(getattr(full_activity, "id", ""))
        strava_activity.name = str(getattr(full_activity, "name", "") or "")
        strava_activity.activity_type = str(getattr(full_activity, "type", "") or "")

        distance_m = getattr(full_activity, "distance", None)
        if distance_m:
            strava_activity.distance = Decimal(str(float(distance_m) * 0.000621371))

        start_date = getattr(full_activity, "start_date", None)
        if start_date:
            strava_activity.start_time = int(start_date.timestamp())

        elapsed_time = getattr(full_activity, "elapsed_time", None)
        if elapsed_time:
            if hasattr(elapsed_time, "total_seconds"):
                total_seconds = int(elapsed_time.total_seconds())
            elif hasattr(elapsed_time, "seconds"):
                total_seconds = int(elapsed_time.seconds)
            else:
                total_seconds = int(elapsed_time)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            strava_activity.duration_hms = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        gear = getattr(full_activity, "gear", None)
        if gear and hasattr(gear, "name"):
            gear_name = getattr(gear, "name", None)
            if gear_name:
                strava_activity.equipment = self._normalize_strava_gear_name(str(gear_name))

        if hasattr(full_activity, "model_dump"):
            raw_data = full_activity.model_dump()
        elif hasattr(full_activity, "dict"):
            raw_data = full_activity.dict()
        else:
            raw_data = dict(full_activity)
        strava_activity.raw_data = json.dumps(raw_data, default=str)

        return strava_activity

    def _convert_to_strava_activity(self, strava_lib_activity) -> StravaActivity:
        """Convert a stravalib activity (summary) to our StravaActivity object."""
        activity_id = getattr(strava_lib_activity, "id", None)
        full_activity = strava_lib_activity

        if activity_id is not None:
            time.sleep(1)  # Throttle API calls to avoid rate limit
            try:
                full_activity = self.client.get_activity(int(activity_id))
            except AccessUnauthorized as exc:
                self._handle_unauthorized(exc, "get_activity")
            except (RateLimitExceeded, RateLimitTimeout) as exc:
                self._raise_rate_limit(exc, "get_activity")

        return self._activity_to_model(full_activity)

    def sync_single_activity(self, strava_id: str) -> StravaActivity | None:
        """Fetch a single activity from Strava by ID and upsert it locally.

        Used by the webhook handler for create/update events.
        """
        self._ensure_fresh_token()
        try:
            full_activity = self.client.get_activity(int(strava_id))
        except AccessUnauthorized as exc:
            self._handle_unauthorized(exc, "sync_single_activity")
            return None
        except (RateLimitExceeded, RateLimitTimeout) as exc:
            self._raise_rate_limit(exc, "sync_single_activity")
            return None
        except Exception as e:
            print(f"Error fetching Strava activity {strava_id}: {e}")
            return None

        if full_activity is None:
            return None

        local = self._activity_to_model(full_activity)
        uid = get_user_id()

        existing = StravaActivity.get_or_none(
            (StravaActivity.strava_id == str(strava_id)) & (StravaActivity.user_id == uid)
        )
        if existing:
            for field in ("name", "activity_type", "distance", "start_time", "duration_hms", "equipment", "raw_data"):
                setattr(existing, field, getattr(local, field))
            existing.save()
            print(f"Strava webhook: updated local activity {strava_id}")
            return existing
        else:
            local.user_id = uid
            local.save()
            print(f"Strava webhook: created local activity {strava_id}")
            return local

    # Abstract method implementations
    def create_activity(self, activity_data: dict[str, Any]) -> StravaActivity:
        """Create a new StravaActivity from activity data."""
        activity_data["user_id"] = get_user_id()
        return StravaActivity.create(**activity_data)

    def get_activity_by_id(self, activity_id: str) -> StravaActivity | None:
        """Get a StravaActivity by its provider ID."""
        return StravaActivity.get_or_none(
            (StravaActivity.strava_id == activity_id) & (StravaActivity.user_id == get_user_id())
        )

    def update_activity(self, activity_data: dict[str, Any]) -> bool:
        """Update an existing Strava activity via API."""
        self._ensure_fresh_token()
        provider_id = activity_data["strava_id"]

        try:
            # Remove the provider_id from the data before sending to API
            update_data = {k: v for k, v in activity_data.items() if k != "strava_id"}

            # Use stravalib to update the activity
            self.client.update_activity(activity_id=int(provider_id), **update_data)

            # Pull fresh data from upstream to sync our local copy (best-effort)
            try:
                fresh_activity = self.client.get_activity(int(provider_id))
                local = StravaActivity.get_or_none(
                    (StravaActivity.strava_id == str(provider_id)) & (StravaActivity.user_id == get_user_id())
                )
                if local and fresh_activity:
                    local.name = str(getattr(fresh_activity, "name", "") or "")
                    local.save()
            except Exception as e:
                print(f"Could not refresh local Strava activity {provider_id} after update: {e}")

            return True

        except AccessUnauthorized as exc:
            self._handle_unauthorized(exc, "update_activity")
        except (RateLimitExceeded, RateLimitTimeout) as exc:
            self._raise_rate_limit(exc, "update_activity")
        except Exception as e:
            print(f"Error updating Strava activity {provider_id}: {e}")
            raise

    def get_all_gear(self) -> dict[str, str]:
        """Get all gear from Strava athlete profile."""
        self._ensure_fresh_token()
        try:
            athlete = self.client.get_athlete()
            gear_dict = {}

            # Add bikes
            if hasattr(athlete, "bikes") and athlete.bikes:
                for bike in athlete.bikes:
                    if hasattr(bike, "id") and hasattr(bike, "name"):
                        gear_id = str(bike.id)
                        gear_name = str(bike.name)
                        gear_dict[gear_id] = gear_name

            # Add shoes
            if hasattr(athlete, "shoes") and athlete.shoes:
                for shoe in athlete.shoes:
                    if hasattr(shoe, "id") and hasattr(shoe, "name"):
                        gear_id = str(shoe.id)
                        gear_name = str(shoe.name)
                        gear_dict[gear_id] = gear_name

            return gear_dict

        except AccessUnauthorized as exc:
            self._handle_unauthorized(exc, "get_athlete")
        except Exception as e:
            print(f"Error getting Strava gear: {e}")
            return {}

    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """Set gear for a Strava activity by gear name."""
        try:
            all_gear = self.get_all_gear()
            gear_id = None
            for gid, gname in all_gear.items():
                if gname == gear_name:
                    gear_id = gid
                    break

            if gear_id is None:
                print(f"Gear '{gear_name}' not found in Strava gear list")
                print("Available gear:")
                for gid, gname in all_gear.items():
                    print(f"  {gid}: {gname}")
                return False

            # Use stravalib to update the activity with gear_id
            self.client.update_activity(activity_id=int(activity_id), gear_id=gear_id)

            # Pull fresh data from upstream to sync our local copy (best-effort)
            try:
                fresh_activity = self.client.get_activity(int(activity_id))
                local = StravaActivity.get_or_none(
                    (StravaActivity.strava_id == str(activity_id)) & (StravaActivity.user_id == get_user_id())
                )
                if local and fresh_activity:
                    gear = getattr(fresh_activity, "gear", None)
                    if gear and hasattr(gear, "name") and gear.name:
                        local.equipment = self._normalize_strava_gear_name(str(gear.name))
                    local.save()
            except Exception as e:
                print(f"Could not refresh local Strava activity {activity_id} after set_gear: {e}")

            return True

        except Exception as e:
            print(f"Error setting gear for Strava activity {activity_id}: {e}")
            return False

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Delete activities for a specific month or all activities."""
        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )

            uid = get_user_id()
            deleted_count = (
                StravaActivity.delete()
                .where(
                    (StravaActivity.start_time >= start_timestamp)
                    & (StravaActivity.start_time <= end_timestamp)
                    & (StravaActivity.user_id == uid)
                )
                .execute()
            )
            return deleted_count
        else:
            return StravaActivity.delete().where(StravaActivity.user_id == get_user_id()).execute()
