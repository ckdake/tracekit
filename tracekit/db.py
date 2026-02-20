import os

from peewee import Proxy, SqliteDatabase

# Use a Proxy object that can be configured later
db = Proxy()

_configured = False


def configure_db(db_path: str = "metadata.sqlite3"):
    """Configure the database backend.

    Resolution order:
    1. DATABASE_URL environment variable → PostgreSQL (production)
    2. db_path argument → SQLite (dev / default)
    """
    global _configured
    if not _configured:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            # playhouse.db_url ships with peewee — no extra package needed
            # for the connect() call itself, but psycopg2-binary must be
            # installed for postgres:// URLs (see [production] extra).
            from playhouse.db_url import connect

            database = connect(database_url)
        else:
            database = SqliteDatabase(
                db_path,
                pragmas={
                    "journal_mode": "wal",  # safe concurrent readers
                    "foreign_keys": 1,
                },
            )
        db.initialize(database)
        _configured = True
    return db


def get_db():
    """Get the configured database instance."""
    if not _configured:
        raise RuntimeError("Database not configured. Call configure_db() first.")
    return db
