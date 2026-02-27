import os

import pytest

from tracekit.database import get_all_models, migrate_tables
from tracekit.db import configure_db, get_db


@pytest.fixture(autouse=True)
def reset_user_context():
    """Reset the user_id ContextVar to 0 before every test.

    App tests call set_user_id(1) via the Flask before_request hook; without
    this reset that value leaks into subsequent package tests (same thread).
    """
    from tracekit.user_context import set_user_id

    set_user_id(0)


@pytest.fixture(scope="session", autouse=True)
def test_db():
    test_db_path = "test.sqlite3"
    configure_db(test_db_path)
    db = get_db()
    # Rebind all models to the test DB
    for model in get_all_models():
        model._meta.set_database(db)
    db.connect()
    migrate_tables(get_all_models())
    yield
    db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
