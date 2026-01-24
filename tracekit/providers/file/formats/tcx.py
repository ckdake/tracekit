"""TCX file format parser for tracekit.

This module provides functionality to parse TCX (Training Center XML) files and extract
relevant activity data such as start time and distance for use in the tracekit application.
"""

import xml.etree.ElementTree as ET

# Alternatively:
# examples at https://github.com/vkurup/python-tcxparser
# tcx = tcxparser.TCXParser(file)
# self.activity_metadata.set_start_time(str(tcx.started_at))
# self.activity_metadata.distance = tcx.distance * 0.00062137


def parse_tcx(file_path):
    """Parse a TCX file and return relevant activity data."""
    tree = ET.parse(file_path)
    root = tree.getroot()
    # Example: extract start time and distance (expand as needed)
    ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    activities = root.findall(".//tcx:Activity", ns)
    if not activities:
        return {}
    first_activity = activities[0]
    start_time = first_activity.find(".//tcx:Lap", ns).get("StartTime")
    # DistanceMeters is optional and may need to be summed from Trackpoints
    distance_elem = first_activity.find(".//tcx:DistanceMeters", ns)
    distance = float(distance_elem.text) * 0.00062137 if distance_elem is not None else None
    return {
        "start_time": start_time,
        "distance": distance,
    }
