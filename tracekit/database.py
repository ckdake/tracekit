import contextlib
from typing import cast

from peewee import Model, SqliteDatabase

from .activity import Activity
from .appconfig import AppConfig
from .db import get_db
from .notification import Notification
from .provider_status import ProviderStatus
from .provider_sync import ProviderSync
from .providers.base_provider_activity import BaseProviderActivity


def migrate_tables(models: list[type[Model]]) -> None:
    db = get_db()
    db.connect(reuse_if_open=True)
    db.create_tables(models)
    _run_schema_upgrades()
    db.close()


def _run_schema_upgrades() -> None:
    """Apply one-time column additions idempotently (SQLite and Postgres).

    Each entry is (table, column, sql_type).  Add new migrations here;
    existing columns are never touched.
    """
    pending = [
        ("garmin_activities", "device_name", "VARCHAR(255)"),
        ("notification", "expires", "INTEGER"),
        ("provider_status", "rate_limit_type", "VARCHAR(64)"),
        ("provider_status", "rate_limit_reset_at", "INTEGER"),
    ]

    db = get_db()
    db.connect(reuse_if_open=True)

    is_sqlite = isinstance(db.obj, SqliteDatabase)

    for table, col, col_type in pending:
        if is_sqlite:
            # SQLite: PRAGMA gives us the column list; ALTER only when missing
            rows = db.execute_sql(f'PRAGMA table_info("{table}")').fetchall()
            existing = {row[1] for row in rows}
            if col not in existing:
                with contextlib.suppress(Exception):
                    db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type}')
        else:
            # Postgres: ADD COLUMN IF NOT EXISTS is idempotent
            with contextlib.suppress(Exception):
                db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {col_type}')


def get_all_models() -> list[type[Model]]:
    return [
        AppConfig,
        Activity,
        ProviderSync,
        ProviderStatus,
        Notification,
        *list(cast(list[type[Model]], BaseProviderActivity.__subclasses__())),
    ]
