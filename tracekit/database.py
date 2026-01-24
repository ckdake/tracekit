from typing import cast

from peewee import Model

from .activity import Activity
from .db import get_db
from .provider_sync import ProviderSync
from .providers.base_provider_activity import BaseProviderActivity


def migrate_tables(models: list[type[Model]]) -> None:
    db = get_db()
    db.connect(reuse_if_open=True)
    db.create_tables(models)
    db.close()


def get_all_models() -> list[type[Model]]:
    return [Activity, ProviderSync, *list(cast(list[type[Model]], BaseProviderActivity.__subclasses__()))]
