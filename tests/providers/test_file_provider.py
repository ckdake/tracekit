import gzip
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from tracekit.providers.file.file_provider import FileProvider


def create_sample_gpx_file(tmpdir):
    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest">
  <trk>
    <name>Test GPX</name>
    <trkseg>
      <trkpt lat="38.5" lon="-120.2"><ele>1000</ele><time>2024-05-27T12:00:00Z</time></trkpt>
      <trkpt lat="40.7" lon="-120.95"><ele>2000</ele><time>2024-05-27T12:10:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""
    gpx_path = os.path.join(tmpdir, "test.gpx")
    with open(gpx_path, "w") as f:
        f.write(gpx_content)
    return gpx_path


@patch("tracekit.provider_sync.ProviderSync.create")
@patch("tracekit.provider_sync.ProviderSync.get_or_none")
@patch("tracekit.providers.file.file_activity.FileActivity.select")
@patch("tracekit.providers.file.file_activity.FileActivity.get")
@patch("tracekit.providers.file.file_activity.FileActivity.create")
def test_file_provider_parses_gpx(mock_create, mock_get, mock_select, mock_sync_get, mock_sync_create, tmp_path):
    """Test that FileProvider can parse GPX files."""
    from peewee import DoesNotExist

    # Mock that month hasn't been synced yet
    mock_sync_get.return_value = None

    # Mock that file hasn't been processed before
    mock_get.side_effect = DoesNotExist()

    # Mock the create method
    mock_activity = MagicMock()
    mock_activity.start_time = "1716811800"  # May 27, 2024 timestamp
    mock_create.return_value = mock_activity

    # Mock the select method to return our mock activity (as a chainable queryset)
    # Use side_effect so a fresh iterator is produced on each iteration attempt.
    items = [mock_activity]
    mock_qs = MagicMock()
    mock_qs.__iter__ = MagicMock(side_effect=lambda: iter(items))
    mock_qs.where.return_value = mock_qs
    mock_select.return_value = mock_qs

    gpx_file = create_sample_gpx_file(tmp_path)
    provider = FileProvider(str(tmp_path), config={"home_timezone": "US/Eastern", "test_mode": True})

    # Call pull_activities - it should process the file into database
    activities = provider.pull_activities("2024-05")  # Match the date in our test data

    # Verify FileActivity.create was called
    mock_create.assert_called_once()
    call_args = mock_create.call_args[1]  # Get keyword arguments

    # Verify the data passed to create
    assert call_args["file_path"] == os.path.basename(gpx_file)
    assert call_args["file_format"] == "gpx"
    assert call_args["start_time"]  # Should have a start time

    # Verify that FileActivity objects are returned
    assert isinstance(activities, list)
    assert len(activities) == 1
    assert activities[0] == mock_activity  # Should return the created FileActivity


@patch("tracekit.provider_sync.ProviderSync.create")
@patch("tracekit.provider_sync.ProviderSync.get_or_none")
@patch("tracekit.providers.file.file_activity.FileActivity.select")
@patch("tracekit.providers.file.file_activity.FileActivity.get")
@patch("tracekit.providers.file.file_activity.FileActivity.create")
def test_file_provider_processes_multiple_files(
    mock_create, mock_get, mock_select, mock_sync_get, mock_sync_create, tmp_path
):
    """Test processing multiple files."""
    from peewee import DoesNotExist

    # Mock that month hasn't been synced yet
    mock_sync_get.return_value = None

    # Mock that files haven't been processed before
    mock_get.side_effect = DoesNotExist()

    # Create mock activities for the files
    mock_activity1 = MagicMock()
    mock_activity1.start_time = "1716811800"  # May 27, 2024 timestamp
    mock_activity2 = MagicMock()
    mock_activity2.start_time = "1716811800"  # May 27, 2024 timestamp

    # Mock create to return different activities for each call
    mock_create.side_effect = [mock_activity1, mock_activity2]

    # Mock select to return both activities (as a chainable queryset)
    # Use side_effect so a fresh iterator is produced on each iteration attempt.
    items = [mock_activity1, mock_activity2]
    mock_qs = MagicMock()
    mock_qs.__iter__ = MagicMock(side_effect=lambda: iter(items))
    mock_qs.where.return_value = mock_qs
    mock_select.return_value = mock_qs

    # Create multiple sample files
    gpx1 = create_sample_gpx_file(tmp_path)
    gpx2_path = os.path.join(tmp_path, "test2.gpx")
    shutil.copy(gpx1, gpx2_path)

    # Use FileProvider to process multiple files
    provider = FileProvider(
        str(tmp_path),
        config={"home_timezone": "US/Eastern", "test_mode": True},
    )
    activities = provider.pull_activities("2024-05")  # Match the date in our test data

    # Should have called create twice (once for each file)
    assert mock_create.call_count == 2

    # Should return FileActivity objects
    assert isinstance(activities, list)
    assert len(activities) == 2
    assert activities[0] == mock_activity1
    assert activities[1] == mock_activity2


def test_activity_file_determines_format():
    """Test file format detection."""
    provider = FileProvider("/tmp", config={"home_timezone": "US/Eastern", "test_mode": True})

    format_type, is_gzipped = provider._determine_file_format("test.gpx")
    assert format_type == "gpx"
    assert is_gzipped is False

    format_type, is_gzipped = provider._determine_file_format("test.gpx.gz")
    assert format_type == "gpx"
    assert is_gzipped is True

    format_type, is_gzipped = provider._determine_file_format("test.fit")
    assert format_type == "fit"
    assert is_gzipped is False

    format_type, is_gzipped = provider._determine_file_format("test.fit.gz")
    assert format_type == "fit"
    assert is_gzipped is True


@patch("tracekit.provider_sync.ProviderSync.create")
@patch("tracekit.provider_sync.ProviderSync.get_or_none")
@patch("tracekit.providers.file.file_activity.FileActivity.select")
@patch("tracekit.providers.file.file_activity.FileActivity.get")
@patch("tracekit.providers.file.file_activity.FileActivity.create")
def test_file_provider_handles_gzipped(mock_create, mock_get, mock_select, mock_sync_get, mock_sync_create, tmp_path):
    """Test that gzipped files are decompressed, flushed to disk, and parsed correctly."""
    from peewee import DoesNotExist

    # Mock that month hasn't been synced yet
    mock_sync_get.return_value = None

    # Mock that file hasn't been processed before
    mock_get.side_effect = DoesNotExist()

    mock_activity = MagicMock()
    mock_activity.start_time = "1716811800"
    mock_create.return_value = mock_activity
    gzip_items = [mock_activity]
    mock_qs = MagicMock()
    mock_qs.__iter__ = MagicMock(side_effect=lambda: iter(gzip_items))
    mock_qs.where.return_value = mock_qs
    mock_select.return_value = mock_qs

    # Create a gzipped GPX file
    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest">
  <trk>
    <name>Test Gzipped GPX</name>
    <trkseg>
      <trkpt lat="38.5" lon="-120.2"><ele>1000</ele><time>2024-05-27T12:00:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""

    gpx_gz_path = os.path.join(tmp_path, "test.gpx.gz")
    with gzip.open(gpx_gz_path, "wt") as f:
        f.write(gpx_content)

    provider = FileProvider(str(tmp_path), config={"home_timezone": "US/Eastern", "test_mode": True})

    # Test format detection
    format_type, is_gzipped = provider._determine_file_format(gpx_gz_path)
    assert format_type == "gpx"
    assert is_gzipped

    # Gzipped files should parse successfully now that the temp file is flushed
    activities = provider.pull_activities("2024-05")
    assert mock_create.call_count == 1
    call_args = mock_create.call_args[1]
    assert call_args["file_format"] == "gpx"
    assert isinstance(activities, list)


def test_file_provider_initialization():
    """Test FileProvider initialization."""
    provider = FileProvider("/tmp", config={"home_timezone": "US/Eastern", "test_mode": True})
    assert provider.data_folder == "/tmp"
    assert provider.provider_name == "file"


def test_file_provider_with_config():
    """Test FileProvider initialization with config."""
    config = {"home_timezone": "US/Pacific", "test_mode": True}
    provider = FileProvider("/tmp", config=config)
    assert provider.config == config
    assert provider.data_folder == "/tmp"


def test_file_provider_without_config():
    """Test FileProvider initialization without config."""
    provider = FileProvider("/tmp")
    assert provider.config == {}
    assert provider.data_folder == "/tmp"


def test_file_provider_with_none_config():
    """Test FileProvider initialization with None config."""
    provider = FileProvider("/tmp", config=None)
    assert provider.config == {}
    assert provider.data_folder == "/tmp"


def test_file_provider_readonly_methods():
    """Test that file provider properly raises NotImplementedError for write operations."""
    provider = FileProvider("/tmp", config={"home_timezone": "US/Eastern", "test_mode": True})

    # These should raise NotImplementedError
    with pytest.raises(NotImplementedError, match="does not support updating"):
        provider.update_activity({"id": 1, "name": "test"})

    with pytest.raises(NotImplementedError, match="does not support creating"):
        provider.create_activity({"name": "test"})

    with pytest.raises(NotImplementedError, match="does not support setting gear"):
        provider.set_gear("bike", "1")


@patch("tracekit.providers.file.file_activity.FileActivity.get")
def test_file_provider_get_activity_by_id(mock_get):
    """Test getting activity by ID works."""
    mock_activity = MagicMock()
    mock_get.return_value = mock_activity

    provider = FileProvider("/tmp", config={"home_timezone": "US/Eastern", "test_mode": True})
    result = provider.get_activity_by_id("123")

    assert result == mock_activity
    # The actual implementation should convert the ID to an integer
    mock_get.assert_called_once()


@patch("tracekit.providers.file.file_activity.FileActivity.select")
def test_file_provider_get_all_gear(mock_select):
    """Test getting gear from file activities."""
    # Mock activities with equipment
    mock_activity1 = MagicMock()
    mock_activity1.equipment = "Bike"
    mock_activity2 = MagicMock()
    mock_activity2.equipment = "Shoes"
    mock_activity3 = MagicMock()
    mock_activity3.equipment = "Bike"  # Duplicate

    mock_qs = MagicMock()
    mock_qs.__iter__ = MagicMock(return_value=iter([mock_activity1, mock_activity2, mock_activity3]))
    mock_qs.where.return_value = mock_qs
    mock_select.return_value = mock_qs

    provider = FileProvider("/tmp", config={"home_timezone": "US/Eastern", "test_mode": True})
    gear = provider.get_all_gear()

    # Should return unique gear as key-value pairs
    expected = {"Bike": "Bike", "Shoes": "Shoes"}
    assert gear == expected
