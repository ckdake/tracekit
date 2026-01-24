import os

from tracekit.providers.file.formats.tcx import parse_tcx


def test_parse_tcx_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "samples", "sample.tcx")
    result = parse_tcx(sample_path)
    assert isinstance(result, dict)
    assert "start_time" in result
    assert "distance" in result
    assert result["start_time"] is not None
    # Distance may be None if not present in the file, but key should exist
