import gzip
import os
import tempfile

from tracekit.providers.file.formats.tcx import parse_tcx


def test_parse_tcx_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "samples", "sample.tcx")
    result = parse_tcx(sample_path)
    assert isinstance(result, dict)
    assert "start_time" in result
    assert "distance" in result
    assert result["start_time"] is not None
    # Distance may be None if not present in the file, but key should exist


def test_parse_tcx_rwgps_course():
    """RideWithGPS exports TCX in Course format, not Activity format."""
    gz_path = os.path.join(os.path.dirname(__file__), "samples", "rwgps.tcx.gz")
    with tempfile.NamedTemporaryFile(suffix=".tcx", delete=False) as tmp:
        tmp_path = tmp.name
        with gzip.open(gz_path, "rb") as f:
            tmp.write(f.read())
    try:
        result = parse_tcx(tmp_path)
        assert isinstance(result, dict)
        assert result.get("start_time") == "2026-02-17T23:27:00Z"
        assert result.get("name") == "Mutinous"
        assert result.get("distance") is not None
        assert abs(result["distance"] - 46699.4 * 0.00062137) < 0.01
    finally:
        os.unlink(tmp_path)
