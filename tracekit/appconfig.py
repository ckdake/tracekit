"""Application configuration model and helpers.

The DB (``appconfig`` table) is always the source of truth.

On every ``load_config()`` call the file is checked:
  - If a JSON config file exists *and* its contents differ from the DB,
    the DB is updated to match the file.
  - If the DB is empty and no file exists, built-in defaults are seeded.

This means:
  * No config file required — the app always boots.
  * Editing the JSON file and restarting picks up the changes.
  * All runtime edits (e.g. via the settings UI) are stored in the DB.

The AppConfig peewee model is included in ``get_all_models()`` so it is
created automatically by ``migrate_tables()`` on every boot.
"""

import copy
import json
import os
from pathlib import Path
from typing import Any

from peewee import CharField, Model, TextField

from .db import db

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "home_timezone": "UTC",
    "debug": False,
    "providers": {
        "strava": {
            "enabled": False,
            "priority": 3,
            "sync_equipment": True,
            "sync_name": True,
            "client_id": "",
            "client_secret": "",
            "access_token": "",
            "refresh_token": "",
            "token_expires": "0",
        },
        "ridewithgps": {
            "enabled": False,
            "priority": 2,
            "sync_equipment": True,
            "sync_name": True,
            "email": "",
            "password": "",
            "apikey": "",
        },
        "garmin": {
            "enabled": False,
            "sync_equipment": False,
            "sync_name": True,
            "email": "",
            "garth_tokens": "",
        },
        "spreadsheet": {
            "enabled": False,
            "path": "",
            "priority": 1,
            "sync_equipment": True,
            "sync_name": True,
        },
        "file": {
            "enabled": False,
            "sync_equipment": False,
            "sync_name": False,
        },
        "stravajson": {"enabled": False},
    },
}

# Candidate JSON config file locations (searched in order)
_FILE_PATHS: list[Path] = [
    Path("tracekit_config.json"),
    Path("../tracekit_config.json"),
]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class AppConfig(Model):
    """Key-value store for application configuration.

    Each top-level key from the config dict (e.g. ``home_timezone``,
    ``providers``) is stored as one row with the value JSON-encoded.
    """

    key = CharField(unique=True, max_length=128)
    value = TextField()  # JSON-encoded value

    class Meta:
        database = db
        table_name = "appconfig"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_from_db() -> dict[str, Any] | None:
    """Return config dict from DB rows, or ``None`` if the table is empty."""
    try:
        rows = list(AppConfig.select())
        if not rows:
            return None
        return {r.key: json.loads(r.value) for r in rows}
    except Exception:
        return None


def _load_from_file() -> dict[str, Any] | None:
    """Try each candidate path; return parsed JSON or ``None``."""
    for path in _FILE_PATHS:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Return the current configuration, always using the DB as source of truth.

    On every call:
      1. If a JSON config file exists and its top-level keys differ from what
         is stored in the DB, the DB is updated to match the file.
      2. If the DB is empty (first boot, no file), built-in defaults are seeded.
      3. The DB contents are returned.

    If the DB is not yet configured (early startup edge-case) the function
    falls back to the JSON file or built-in defaults without persisting.
    """
    try:
        from .db import get_db

        get_db()  # raises RuntimeError if not yet configured
    except RuntimeError:
        # DB not available — best-effort fallback, nothing persisted
        return _load_from_file() or copy.deepcopy(DEFAULT_CONFIG)

    file_cfg = _load_from_file()
    db_cfg = _load_from_db()

    if db_cfg is None:
        # First boot — seed from file or defaults
        source = file_cfg if file_cfg is not None else copy.deepcopy(DEFAULT_CONFIG)
        save_config(source)
        return source

    if file_cfg is not None and file_cfg != db_cfg:
        # File has been updated since last boot — sync changes into the DB.
        # We do a key-level merge so that keys only present in the DB
        # (added via settings UI) are not deleted.
        merged = {**db_cfg, **file_cfg}
        save_config(merged)
        return merged

    return db_cfg


def save_config(config: dict[str, Any]) -> None:
    """Persist every top-level key of *config* to the DB as JSON values.

    Uses upsert semantics so it is safe to call repeatedly.
    """
    try:
        for key, value in config.items():
            (
                AppConfig.insert(key=key, value=json.dumps(value))
                .on_conflict(
                    conflict_target=[AppConfig.key],
                    update={AppConfig.value: json.dumps(value)},
                )
                .execute()
            )
    except Exception as e:
        print(f"Warning: could not save config to DB: {e}")


def get_db_path_from_env() -> str:
    """Return the SQLite path to use when no DATABASE_URL is set.

    Checks the ``METADATA_DB`` environment variable first, then falls back
    to ``metadata.sqlite3`` in the current working directory.
    """
    return os.environ.get("METADATA_DB", "metadata.sqlite3")
