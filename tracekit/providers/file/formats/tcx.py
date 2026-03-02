"""TCX file format parser for tracekit.

This module provides functionality to parse TCX (Training Center XML) files and extract
relevant activity data such as start time and distance for use in the tracekit application.
"""

import xml.etree.ElementTree as ET


def parse_tcx(file_path):
    """Parse a TCX file and return relevant activity data.

    Handles both Activity format (e.g. Garmin exports) and Course format
    (e.g. RideWithGPS exports).  Returns a dict with at least ``start_time``
    and ``distance`` keys on success, or ``{}`` if neither format is found.
    """
    tree = ET.parse(file_path)
    root = tree.getroot()
    ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}

    # Activity format (Garmin): StartTime is an attribute on <Lap>
    activities = root.findall(".//tcx:Activity", ns)
    if activities:
        first_activity = activities[0]
        lap = first_activity.find(".//tcx:Lap", ns)
        start_time = lap.get("StartTime") if lap is not None else None
        distance_elem = first_activity.find(".//tcx:DistanceMeters", ns)
        distance = float(distance_elem.text) * 0.00062137 if distance_elem is not None else None
        return {"start_time": start_time, "distance": distance}

    # Course format (RideWithGPS): start time lives in the first Trackpoint
    courses = root.findall(".//tcx:Course", ns)
    if courses:
        first_course = courses[0]
        name_elem = first_course.find("tcx:Name", ns)
        name = name_elem.text if name_elem is not None else None
        lap_distance = first_course.find("tcx:Lap/tcx:DistanceMeters", ns)
        distance = float(lap_distance.text) * 0.00062137 if lap_distance is not None else None
        first_time = first_course.find(".//tcx:Trackpoint/tcx:Time", ns)
        start_time = first_time.text if first_time is not None else None
        return {"start_time": start_time, "distance": distance, "name": name}

    return {}
