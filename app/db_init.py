"""Database initialisation and config loading for the tracekit web app."""

from typing import Any

_db_initialized = False


def _init_db() -> bool:
    """Configure the DB and ensure all tables exist.

    Resolution order (no config file needed):
      1. DATABASE_URL env var  → PostgreSQL
      2. METADATA_DB env var   → SQLite at that path
      3. Default               → metadata.sqlite3 in cwd
    """
    global _db_initialized
    if not _db_initialized:
        try:
            from tracekit.appconfig import get_db_path_from_env
            from tracekit.database import get_all_models, migrate_tables
            from tracekit.db import configure_db

            configure_db(get_db_path_from_env())
            migrate_tables(get_all_models())

            from models.user import User

            migrate_tables([User])

            _db_initialized = True
        except Exception as e:
            print(f"DB init failed: {e}")
            return False
    return True


def load_tracekit_config() -> dict[str, Any]:
    """Load tracekit config — always returns a valid dict.

    Priority: DB rows → JSON file (migrated in on first call) → built-in defaults.
    Never returns an error dict; the app always has a working config.
    """
    _init_db()
    from tracekit.appconfig import load_config

    return load_config()
