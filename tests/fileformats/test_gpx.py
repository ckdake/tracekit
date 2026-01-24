import os

from tracekit.providers.file.formats.gpx import parse_gpx


def test_parse_gpx_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "samples", "sample.gpx")
    result = parse_gpx(sample_path)
    assert isinstance(result, dict)
    assert "start_time" in result
    assert "distance" in result
    assert result["start_time"] is not None
    assert result["distance"] is not None
