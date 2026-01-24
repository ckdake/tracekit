from peewee import Proxy, SqliteDatabase

# Use a Proxy object that can be configured later
db = Proxy()

_configured = False


def configure_db(db_path: str):
    """Configure database with the given path"""
    global _configured
    if not _configured:
        database = SqliteDatabase(db_path)
        db.initialize(database)
        _configured = True
    return db


def get_db():
    """Get the configured database instance"""
    if not _configured:
        raise RuntimeError("Database not configured. Call configure_db() first.")
    return db
