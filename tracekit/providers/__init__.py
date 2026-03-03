"""Fitness service provider integrations for tracekit."""

from .file.file_provider import FileProvider
from .garmin.garmin_provider import GarminProvider
from .intervalsicu.intervalsicu_provider import IntervalsICUProvider
from .ridewithgps.ridewithgps_provider import RideWithGPSProvider
from .spreadsheet.spreadsheet_provider import SpreadsheetProvider
from .strava.strava_provider import StravaProvider
from .stravajson.stravajson_provider import StravaJsonProvider

__all__ = [
    "FileProvider",
    "GarminProvider",
    "IntervalsICUProvider",
    "RideWithGPSProvider",
    "SpreadsheetProvider",
    "StravaJsonProvider",
    "StravaProvider",
]
