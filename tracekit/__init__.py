"""This is the init module for tracekit"""

# Providers
from .providers.file import FileProvider
from .providers.garmin import GarminProvider
from .providers.ridewithgps import RideWithGPSProvider
from .providers.spreadsheet import SpreadsheetProvider
from .providers.strava import StravaProvider
from .providers.stravajson import StravaJsonProvider

__version__ = "0.0.1"
__all__ = [
    "FileProvider",
    "GarminProvider",
    "RideWithGPSProvider",
    "SpreadsheetProvider",
    "StravaJsonProvider",
    "StravaProvider",
]
