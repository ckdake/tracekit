import contextlib
from typing import cast

from peewee import Model

from .activity import Activity
from .appconfig import AppConfig
from .db import get_db
from .notification import Notification
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
    ]

    db = get_db()
    db.connect(reuse_if_open=True)

    for table, col, col_type in pending:
        # SQLite: use PRAGMA to detect existing columns before ALTER
        with contextlib.suppress(Exception):
            rows = db.execute_sql(f'PRAGMA table_info("{table}")').fetchall()
            if rows is not None:  # non-empty result means it's SQLite
                existing = {row[1] for row in rows}
                if col not in existing:
                    db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type}')
                continue

        # Postgres: ADD COLUMN IF NOT EXISTS (no-op when already present)
        with contextlib.suppress(Exception):
            db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {col_type}')


def get_all_models() -> list[type[Model]]:
    return [
        AppConfig,
        Activity,
        ProviderSync,
        Notification,
        *list(cast(list[type[Model]], BaseProviderActivity.__subclasses__())),
    ]
