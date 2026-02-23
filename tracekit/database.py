import contextlib
from typing import cast

from peewee import Model, SqliteDatabase

from .activity import Activity
from .appconfig import AppConfig
from .db import get_db
from .notification import Notification
from .provider_status import MonthSyncStatus, ProviderPullStatus, ProviderStatus
from .provider_sync import ProviderSync
from .providers.base_provider_activity import BaseProviderActivity


def migrate_tables(models: list[type[Model]]) -> None:
    db = get_db()
    db.connect(reuse_if_open=True)
    # Schema upgrades must run first so user_id columns exist before create_tables
    # tries to build composite unique indexes that reference them.
    _run_schema_upgrades()
    db.create_tables(models, safe=True)
    db.close()


# ---- low-level helpers -------------------------------------------------------


def _sqlite_table_exists(db, table: str) -> bool:
    row = db.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _sqlite_has_column(db, table: str, col: str) -> bool:
    rows = db.execute_sql(f'PRAGMA table_info("{table}")').fetchall()
    return col in {row[1] for row in rows}


def _pg_has_column(db, table: str, col: str) -> bool:
    row = db.execute_sql(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, col),
    ).fetchone()
    return row is not None


def _add_columns(db, is_sqlite: bool, columns: list[tuple[str, str, str]]) -> None:
    """Add columns idempotently; *columns* is [(table, col, sql_type), ...]."""
    for table, col, col_type in columns:
        if is_sqlite:
            if not _sqlite_has_column(db, table, col):
                with contextlib.suppress(Exception):
                    db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type}')
        else:
            with contextlib.suppress(Exception):
                db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {col_type}')


# ---- unique-constraint migration helpers ------------------------------------


def _sqlite_rebuild_add_user_id(db, table: str, unique_cols: list[str]) -> None:
    """Rebuild a SQLite table to add user_id and replace the unique constraint.

    Uses PRAGMA table_info to derive column definitions dynamically so it works
    even when ALTER TABLE has added columns after initial creation.
    Guards on table not existing (let create_tables handle that) and on user_id
    already existing — idempotent.
    """
    if not _sqlite_table_exists(db, table):
        return  # Table will be created fresh by create_tables() with correct schema
    if _sqlite_has_column(db, table, "user_id"):
        return

    pragma = db.execute_sql(f'PRAGMA table_info("{table}")').fetchall()
    # pragma rows: (cid, name, type, notnull, dflt_value, pk)
    col_defs = []
    copy_cols = []
    for _cid, name, col_type, notnull, dflt_value, pk in pragma:
        copy_cols.append(name)
        if pk:
            col_defs.append(f'"{name}" {col_type} NOT NULL PRIMARY KEY')
        else:
            parts = [f'"{name}"', col_type]
            if notnull:
                parts.append("NOT NULL")
            if dflt_value is not None:
                parts.append(f"DEFAULT {dflt_value}")
            col_defs.append(" ".join(parts))

    col_defs.append('"user_id" INTEGER NOT NULL DEFAULT 0')
    unique_clause = ", ".join(f'"{c}"' for c in unique_cols)
    col_defs.append(f"UNIQUE ({unique_clause})")

    new_table = f"{table}_new"
    with contextlib.suppress(Exception):
        db.execute_sql(f'DROP TABLE IF EXISTS "{new_table}"')
    db.execute_sql(f'CREATE TABLE "{new_table}" ({", ".join(col_defs)})')
    col_list = ", ".join(f'"{c}"' for c in copy_cols)
    db.execute_sql(f'INSERT INTO "{new_table}" ({col_list}) SELECT {col_list} FROM "{table}"')
    db.execute_sql(f'DROP TABLE "{table}"')
    db.execute_sql(f'ALTER TABLE "{new_table}" RENAME TO "{table}"')


def _pg_migrate_user_id_composite_unique(db, table: str, unique_cols: list[str]) -> None:
    """For PostgreSQL: add user_id, drop old unique constraints, create new index.

    Idempotent — skips if user_id column already exists.
    """
    if _pg_has_column(db, table, "user_id"):
        return

    # Add user_id column
    with contextlib.suppress(Exception):
        db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "user_id" INTEGER NOT NULL DEFAULT 0')

    # Drop all unique indexes/constraints on this table that don't include user_id.
    # We query pg_indexes for unique entries then try both DROP CONSTRAINT and DROP INDEX.
    rows = db.execute_sql(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename = %s AND indexdef LIKE '%%UNIQUE%%' AND indexdef NOT LIKE '%%user_id%%'",
        (table,),
    ).fetchall()
    for (indexname,) in rows:
        # Try constraint first (inline UNIQUE in CREATE TABLE), then plain index
        with contextlib.suppress(Exception):
            db.execute_sql(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{indexname}"')
        with contextlib.suppress(Exception):
            db.execute_sql(f'DROP INDEX IF EXISTS "{indexname}"')

    # Create the new composite unique index
    index_name = f"{table}_{'_'.join(unique_cols)}"
    unique_clause = ", ".join(f'"{c}"' for c in unique_cols)
    with contextlib.suppress(Exception):
        db.execute_sql(f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" ON "{table}" ({unique_clause})')


def _migrate_unique_with_user_id(db, is_sqlite: bool, table: str, unique_cols: list[str]) -> None:
    """Dispatch to the right migration path based on database type."""
    if is_sqlite:
        _sqlite_rebuild_add_user_id(db, table, unique_cols)
    else:
        _pg_migrate_user_id_composite_unique(db, table, unique_cols)


# ---- special case: activity.user_id type change ------------------------------


def _migrate_activity_user_id(db, is_sqlite: bool) -> None:
    """Ensure activity.user_id is an integer column with 0 as the default/fill.

    Previously this column was CharField(null=True); for PostgreSQL we also
    convert the column type to INTEGER.
    """
    if is_sqlite:
        if not _sqlite_table_exists(db, "activity"):
            return  # Will be created fresh
        if not _sqlite_has_column(db, "activity", "user_id"):
            with contextlib.suppress(Exception):
                db.execute_sql('ALTER TABLE "activity" ADD COLUMN "user_id" INTEGER NOT NULL DEFAULT 0')
        with contextlib.suppress(Exception):
            db.execute_sql('UPDATE "activity" SET "user_id" = 0 WHERE "user_id" IS NULL')
    else:
        # Add column if missing (new install or column truly absent)
        with contextlib.suppress(Exception):
            db.execute_sql('ALTER TABLE "activity" ADD COLUMN IF NOT EXISTS "user_id" INTEGER NOT NULL DEFAULT 0')
        # If user_id was previously VARCHAR, convert it to INTEGER
        type_row = db.execute_sql(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'activity' AND column_name = 'user_id'",
        ).fetchone()
        if type_row and type_row[0] in ("character varying", "text", "character"):
            with contextlib.suppress(Exception):
                db.execute_sql(
                    'ALTER TABLE "activity" '
                    'ALTER COLUMN "user_id" TYPE INTEGER '
                    "USING COALESCE(NULLIF(\"user_id\", '')::INTEGER, 0)"
                )
            with contextlib.suppress(Exception):
                db.execute_sql('ALTER TABLE "activity" ALTER COLUMN "user_id" SET NOT NULL')
            with contextlib.suppress(Exception):
                db.execute_sql('ALTER TABLE "activity" ALTER COLUMN "user_id" SET DEFAULT 0')
        # Fill any remaining NULLs
        with contextlib.suppress(Exception):
            db.execute_sql('UPDATE "activity" SET "user_id" = 0 WHERE "user_id" IS NULL')


# ---- main migration entry point ----------------------------------------------


def _run_schema_upgrades() -> None:
    """Apply one-time migrations idempotently (SQLite and Postgres).

    Called at startup before create_tables so new composite indexes are ready.
    """
    db = get_db()
    db.connect(reuse_if_open=True)
    is_sqlite = isinstance(db.obj, SqliteDatabase)

    # ---- simple ADD COLUMN migrations ----------------------------------------
    _add_columns(
        db,
        is_sqlite,
        [
            ("garmin_activities", "device_name", "VARCHAR(255)"),
            ("notification", "expires", "INTEGER"),
            ("provider_status", "rate_limit_type", "VARCHAR(64)"),
            ("provider_status", "rate_limit_reset_at", "INTEGER"),
            # user_id for tables that only need ADD COLUMN (no constraint change)
            ("notification", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("strava_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("garmin_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("ridewithgps_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("spreadsheet_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("file_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            ("stravajson_activities", "user_id", "INTEGER NOT NULL DEFAULT 0"),
            # user account status (blocked by default; admin sets active)
            ("user", "status", "VARCHAR(16) NOT NULL DEFAULT 'blocked'"),
            # Stripe subscription fields
            ("user", "stripe_customer_id", "VARCHAR(255)"),
            ("user", "stripe_subscription_status", "VARCHAR(64)"),
            ("user", "stripe_subscription_end", "INTEGER"),
        ],
    )

    # Ensure the admin user (id=1) is always active.
    with contextlib.suppress(Exception):
        db.execute_sql('UPDATE "user" SET "status" = \'active\' WHERE "id" = 1')

    # ---- activity.user_id: VARCHAR(null=True) → INTEGER NOT NULL DEFAULT 0 --
    _migrate_activity_user_id(db, is_sqlite)

    # ---- tables needing unique constraint change + user_id -------------------
    # appconfig: (key) → (key, user_id)
    _migrate_unique_with_user_id(db, is_sqlite, "appconfig", ["key", "user_id"])
    # providersync: (year_month, provider) → (year_month, provider, user_id)
    _migrate_unique_with_user_id(db, is_sqlite, "providersync", ["year_month", "provider", "user_id"])
    # provider_status: (provider) → (provider, user_id)
    _migrate_unique_with_user_id(db, is_sqlite, "provider_status", ["provider", "user_id"])
    # provider_pull_status: (year_month, provider) → (year_month, provider, user_id)
    _migrate_unique_with_user_id(db, is_sqlite, "provider_pull_status", ["year_month", "provider", "user_id"])
    # month_sync_status: (year_month) → (year_month, user_id)
    _migrate_unique_with_user_id(db, is_sqlite, "month_sync_status", ["year_month", "user_id"])


def get_all_models() -> list[type[Model]]:
    return [
        AppConfig,
        Activity,
        ProviderSync,
        ProviderStatus,
        ProviderPullStatus,
        MonthSyncStatus,
        Notification,
        *list(cast(list[type[Model]], BaseProviderActivity.__subclasses__())),
    ]
