"""FIT file format parser for tracekit.

This module provides functionality to parse FIT (Flexible and Interoperable Data Transfer) files
and extract relevant activity data such as start time and distance for use in the tracekit
application.
"""

import fitparse  # type: ignore


def parse_fit(file_path):
    """Parse a FIT file and return relevant activity data."""
    # should these get converted to tcx, or vice versa?
    # examples at fitdump -n session 998158033.fit
    fitfile = fitparse.FitFile(file_path)
    start_time = None
    distance = None
    for record in fitfile.get_messages("session"):
        data = {d.name: d.value for d in record}
        if "start_time" in data:
            start_time = str(data["start_time"])
        if "total_distance" in data:
            distance = float(data["total_distance"]) * 0.00062137  # meters to miles
    return {
        "start_time": start_time,
        "distance": distance,
    }
