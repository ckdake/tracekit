"""File provider for tracekit.
This module defines the FileProvider class, which provides an interface
for processing activity files from the filesystem (GPX, FIT, TCX, etc).
"""

import datetime
import glob
import gzip
import hashlib
import json
import logging
import multiprocessing
import os
import tempfile
from typing import Any, Optional

import dateparser
from peewee import DoesNotExist

from tracekit.provider_sync import ProviderSync
from tracekit.providers.base_provider import FitnessProvider
from tracekit.providers.file.file_activity import FileActivity

from .formats.fit import parse_fit
from .formats.gpx import parse_gpx
from .formats.tcx import parse_tcx


class FileProvider(FitnessProvider):
    """File provider for processing activity files from filesystem."""

    def __init__(self, file_glob: str, config: dict[str, Any] | None = None):
        """Initialize with file glob pattern for finding activity files."""
        super().__init__(config)
        self.file_glob = file_glob

        if self.config:
            self.debug = self.config.get("debug", False)
            if self.debug:
                logging.basicConfig(level=logging.DEBUG)

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return "file"

    @staticmethod
    def _determine_file_format(file_path: str) -> tuple[str, bool]:
        file_lower = file_path.lower()

        if ".fit.gz" in file_lower:
            return "fit", True
        if ".tcx.gz" in file_lower:
            return "tcx", True
        if ".gpx.gz" in file_lower:
            return "gpx", True
        if file_lower.endswith(".gpx"):
            return "gpx", False
        if file_lower.endswith(".tcx"):
            return "tcx", False
        if file_lower.endswith(".fit"):
            return "fit", False
        raise ValueError(f"Unknown file format: {file_path}")

    @staticmethod
    def _calculate_checksum(file_path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @staticmethod
    def _convert_start_time_to_int(start_time_val) -> int | None:
        """Convert various start_time formats to Unix timestamp integer."""
        if not start_time_val:
            return None
        try:
            # If it's already an integer, return it
            if isinstance(start_time_val, int):
                return start_time_val
            # If it's a string that looks like a timestamp
            if isinstance(start_time_val, str) and start_time_val.isdigit():
                return int(start_time_val)
            # Parse as datetime string and convert to timestamp
            dt = dateparser.parse(str(start_time_val))
            if dt:
                return int(dt.timestamp())
        except (ValueError, TypeError, AttributeError):
            pass
        return None

    @staticmethod
    def _parse_file(file_path: str) -> dict | None:
        """Parse an activity file and return activity data."""

        file_format, is_gzipped = FileProvider._determine_file_format(file_path)

        fp = None
        read_file = file_path
        try:
            if is_gzipped:
                fp = tempfile.NamedTemporaryFile()
                with gzip.open(file_path, "rb") as f:
                    data = f.read()
                    if file_format in ["gpx", "tcx"]:
                        data = data.lstrip()
                    fp.write(data)
                read_file = fp.name
            if file_format == "gpx":
                result = parse_gpx(read_file)
            elif file_format == "fit":
                result = parse_fit(read_file)
            elif file_format == "tcx":
                result = parse_tcx(read_file)
            else:
                print(f"Unsupported file format: {file_format}")
                return None

            result["file_path"] = os.path.basename(file_path)
            result["file_checksum"] = FileProvider._calculate_checksum(file_path)
            result["file_size"] = os.path.getsize(file_path)
            result["file_format"] = file_format
            return result

        except Exception as e:
            print(f"Error parsing {file_format} file {file_path}: {e}")
            return None
        finally:
            if fp:
                fp.close()

    @staticmethod
    def _file_processing_worker(args):
        (file_path,) = args
        try:
            parsed_data = FileProvider._parse_file(file_path)
            return (file_path, parsed_data)
        except Exception as e:
            print(f"Error parsing file {file_path}: {e}")
            return (file_path, None)

    def _pull_all_activities(self) -> list["FileActivity"]:
        """Process all files matching the glob pattern without date filtering."""
        file_paths = glob.glob(self.file_glob)
        print(f"Found {len(file_paths)} files matching pattern: {self.file_glob}")

        unprocessed_file_paths = []
        for file_path in file_paths:
            try:
                checksum = FileProvider._calculate_checksum(file_path)

                FileActivity.get(
                    FileActivity.file_path == os.path.basename(file_path),
                    FileActivity.file_checksum == checksum,
                )
                continue
            except DoesNotExist:
                unprocessed_file_paths.append(file_path)

        print(f"Processing {len(unprocessed_file_paths)} new files...")

        processed_count = 0

        if unprocessed_file_paths:
            with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
                results = pool.map(
                    self._file_processing_worker,
                    [(fp,) for fp in unprocessed_file_paths],
                )

            for file_path, parsed_data in results:
                if not parsed_data:
                    continue
                try:
                    existing_file_activity = FileActivity.get_or_none(
                        FileActivity.file_path == parsed_data.get("file_path"),
                        FileActivity.file_checksum == parsed_data.get("file_checksum"),
                    )
                    if existing_file_activity is None:
                        file_activity = self._process_parsed_data(parsed_data)
                        if file_activity:
                            processed_count += 1
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
                    continue

            print(f"Processed {processed_count} new file activities")

        return self._get_activities()

    def _get_activities(self, date_filter: str | None = None) -> list["FileActivity"]:
        """Get FileActivity objects for a specific month."""
        file_activities = []

        if date_filter:
            year, month = map(int, date_filter.split("-"))
            for activity in FileActivity.select():
                if hasattr(activity, "start_time") and activity.start_time:
                    try:
                        # Convert timestamp to datetime for comparison
                        dt = datetime.datetime.fromtimestamp(int(activity.start_time))
                        if dt.year == year and dt.month == month:
                            file_activities.append(activity)
                    except (ValueError, TypeError):
                        continue
        else:
            file_activities = list(FileActivity.select())

        return file_activities

    def _process_parsed_data(self, parsed_data: dict) -> Optional["FileActivity"]:
        """Process a single activity files parsed data and store in file_activities table."""
        file_activity = FileActivity.create(
            file_path=parsed_data.get("file_path"),
            file_checksum=parsed_data.get("file_checksum"),
            file_size=parsed_data.get("file_size"),
            file_format=parsed_data.get("file_format"),
            name=parsed_data.get("name", ""),
            distance=parsed_data.get("distance", 0),
            start_time=self._convert_start_time_to_int(parsed_data.get("start_time")),
            activity_type=parsed_data.get("activity_type", ""),
            duration_hms=parsed_data.get("duration_hms", ""),
            raw_data=json.dumps(parsed_data),
        )
        return file_activity

    def _mark_all_months_as_synced(self) -> None:
        """Mark all months containing activities as synced for this provider."""
        # Get all unique months that have activities
        activities = FileActivity.select()
        unique_months = set()

        for activity in activities:
            if activity.start_time:
                try:
                    # Convert Unix timestamp to datetime and extract year-month
                    dt = datetime.datetime.fromtimestamp(activity.start_time)
                    year_month = f"{dt.year:04d}-{dt.month:02d}"
                    unique_months.add(year_month)
                except (ValueError, TypeError):
                    continue

        # Create ProviderSync records for all months (if they don't already exist)
        for year_month in unique_months:
            existing_sync = ProviderSync.get_or_none(year_month, self.provider_name)
            if not existing_sync:
                ProviderSync.create(year_month=year_month, provider=self.provider_name)
                print(f"Marked {year_month} as synced for {self.provider_name}")

    def pull_activities(self, date_filter: str | None = None) -> list["FileActivity"]:
        """
        Process activity files and return FileActivity objects.
        If date_filter is provided (YYYY-MM format), only returns activities from that month.
        If date_filter is None, processes all files and returns all FileActivity objects.
        """
        if date_filter is None:
            return self._pull_all_activities()

        existing_sync = ProviderSync.get_or_none(date_filter, self.provider_name)
        if not existing_sync:
            self._pull_all_activities()
            # For file provider, mark ALL months containing activities as synced
            # since we process all files regardless of date_filter
            self._mark_all_months_as_synced()
        else:
            print(f"Month {date_filter} already synced for {self.provider_name}")

        return self._get_activities(date_filter)

    def get_activity_by_id(self, activity_id: str) -> Optional["FileActivity"]:
        """Get a specific activity by its file activity ID."""
        try:
            return FileActivity.get_by_id(int(activity_id))
        except (ValueError, DoesNotExist):
            return None

    def update_activity(self, activity_data: dict[str, Any]) -> Any:
        """File provider does not support updating activities."""
        raise NotImplementedError("File provider does not support updating activities")

    def create_activity(self, activity_data: dict[str, Any]) -> str:
        """File provider does not support creating activities."""
        raise NotImplementedError("File provider does not support creating activities")

    def get_all_gear(self) -> dict[str, str]:
        """Get all unique equipment from file activities."""
        gear_set = set()
        for activity in FileActivity.select():
            if hasattr(activity, "equipment") and activity.equipment:
                gear_set.add(str(activity.equipment))
        return {name: name for name in gear_set}

    def set_gear(self, gear_name: str, activity_id: str) -> bool:
        """File provider does not support setting gear."""
        raise NotImplementedError("File provider does not support setting gear")

    def reset_activities(self, date_filter: str | None = None) -> int:
        """Reset (delete) File activities from local database."""
        from tracekit.providers.file.file_activity import FileActivity

        if date_filter:
            start_timestamp, end_timestamp = self._YYYY_MM_to_unixtime_range(
                date_filter, self.config.get("home_timezone", "US/Eastern")
            )

            return (
                FileActivity.delete()
                .where((FileActivity.start_time >= start_timestamp) & (FileActivity.start_time <= end_timestamp))
                .execute()
            )
        else:
            return FileActivity.delete().execute()
