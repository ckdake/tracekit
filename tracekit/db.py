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


def patch_peewee_for_sentry() -> None:
    """Monkey-patch peewee.Database.execute_sql to emit Sentry DB spans.

    Safe to call multiple times — subsequent calls are no-ops.
    Call once after sentry_sdk.init() and before any DB queries.
    """
    try:
        import peewee
        from sentry_sdk.consts import SPANSTATUS
        from sentry_sdk.tracing_utils import record_sql_queries
    except ImportError:
        return

    if getattr(peewee.Database.execute_sql, "_sentry_patched", False):
        return

    _original = peewee.Database.execute_sql

    def _execute_sql(self, sql, params=None):
        with record_sql_queries(
            cursor=None,
            query=sql,
            params_list=None,
            paramstyle=None,
            executemany=False,
            span_origin="auto.db.peewee",
        ) as span:
            with peewee.__exception_wrapper__:
                cursor = self.cursor()
                try:
                    cursor.execute(sql, params or ())
                except Exception:
                    span.set_status(SPANSTATUS.INTERNAL_ERROR)
                    raise
        return cursor

    _execute_sql._sentry_patched = True
    peewee.Database.execute_sql = _execute_sql
