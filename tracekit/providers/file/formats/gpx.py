"""GPX file format parser for tracekit.

This module provides functionality to parse GPX (GPS Exchange Format) files and
extract relevant activity data such as start time and distance for use in the tracekit
application.
"""

import gpxpy


def parse_gpx(file_path):
    """Parse a GPX file and return relevant activity data."""
    # probably should convert these to a TCX file
    # examples at https://github.com/tkrajina/gpxpy/blob/dev/gpxinfo
    with open(file_path, encoding="utf-8") as gpx_file:
        gpx = gpxpy.parse(gpx_file)
        start_time = str(gpx.get_time_bounds().start_time)
        distance = gpx.length_2d() * 0.00062137  # meters to miles
        return {
            "start_time": start_time,
            "distance": distance,
        }
