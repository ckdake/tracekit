"""File-specific activity model."""

from peewee import CharField

from tracekit.db import db
from tracekit.providers.base_provider_activity import BaseProviderActivity


class FileActivity(BaseProviderActivity):
    """File-specific activity data.

    Stores activity data parsed from files (GPX, FIT, TCX, etc).
    Uses file path + checksum as unique identifier to prevent reprocessing.
    """

    # File-specific ID field (file path)
    file_path = CharField(max_length=500, index=True)

    # File metadata for deduplication
    file_checksum = CharField(max_length=64, index=True)  # SHA256 hash
    file_size = CharField(max_length=20, null=True)  # File size in bytes
    file_format = CharField(max_length=10, null=True)  # gpx, fit, tcx, etc.

    # Combined unique constraint on path + checksum
    class Meta:
        database = db
        table_name = "file_activities"
        indexes = ((("file_path", "file_checksum"), True),)  # Unique together

    @property
    def provider_id(self) -> str:
        """Return the file path as the provider ID."""
        return str(self.file_path) if self.file_path else ""

    @provider_id.setter
    def provider_id(self, value: str) -> None:
        """Set the file path when provider_id is set."""
        self.file_path = value
