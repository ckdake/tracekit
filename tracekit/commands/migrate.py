"""Database migration/bootstrap command.

Ensures all tables exist for the configured backend (SQLite or PostgreSQL).
Designed to be idempotent — safe to run on every container start.
On Postgres, retries the connection for up to ~60 s to handle the case where
the database container is still starting when this process launches.

On the very first Postgres boot (empty database), if `metadata_db` in config
points at an existing SQLite file, every table is copied across verbatim.
"""

import os
import sqlite3
import time

from tracekit.core import tracekit as tracekit_class

_MAX_RETRIES = 12
_RETRY_DELAY = 5  # seconds


def _import_from_sqlite(sqlite_path: str, pg_db) -> None:
    """Copy every table from a SQLite file into the already-connected pg_db."""
    print(f"📦 Importing data from SQLite: {sqlite_path}")
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    cursor = src.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        rows = cursor.execute(f'SELECT * FROM "{table}"').fetchall()
        if not rows:
            continue

        columns = rows[0].keys()
        col_list = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join("%s" for _ in columns)
        sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        with pg_db.atomic():
            for row in rows:
                pg_db.execute_sql(sql, tuple(row))
        print(f"  ✅ {table}: {len(rows)} rows")

    src.close()

    # Advance every serial/identity sequence past the max imported ID so that
    # new inserts don't collide with the rows we just copied in.
    _reset_sequences(pg_db, tables)


def _reset_sequences(pg_db, tables: list[str]) -> None:
    """Set each table's primary-key sequence to MAX(id) so new inserts don't collide."""
    for table in tables:
        try:
            # pg_get_serial_sequence returns NULL if the column has no sequence
            result = pg_db.execute_sql("SELECT pg_get_serial_sequence(%s, 'id')", (table,)).fetchone()
            if not result or not result[0]:
                continue
            pg_db.execute_sql(
                f"SELECT setval(pg_get_serial_sequence(%s, 'id'), MAX(id)) FROM \"{table}\"",
                (table,),
            )
            print(f"  🔢 reset sequence for {table}")
        except Exception as e:
            print(f"  ⚠️  could not reset sequence for {table}: {e}")


def run():
    """Bootstrap / migrate the database schema."""
    database_url = os.environ.get("DATABASE_URL", "")
    backend = "PostgreSQL" if database_url else "SQLite"
    print(f"🗄️  Running database migrations ({backend})...")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with tracekit_class() as tk:
                if not database_url:
                    print("✅ Migrations complete.")
                    return

                # Postgres path — check if the DB is empty
                from tracekit.db import get_db
                from tracekit.provider_sync import ProviderSync

                pg_db = get_db()

                try:
                    is_empty = ProviderSync.select().count() == 0
                except Exception:
                    is_empty = True

                if not is_empty:
                    print("✅ Migrations complete (data already present, skipping import).")
                    return

                # Empty DB — import from SQLite if configured
                sqlite_path = tk.config.get("metadata_db", "")
                if sqlite_path and os.path.isfile(sqlite_path):
                    _import_from_sqlite(sqlite_path, pg_db)
                else:
                    print("No metadata_db SQLite file found — starting fresh.")

                print("✅ Migrations complete.")
                return

        except Exception as e:
            if attempt < _MAX_RETRIES and database_url:
                print(f"⏳ Database not ready (attempt {attempt}/{_MAX_RETRIES}): {e}")
                time.sleep(_RETRY_DELAY)
            else:
                print(f"❌ Migration failed: {e}")
                raise
