"""Typed access to the configuration and collections of the app."""

from typing import Any

from flask import current_app
from foca.models.config import Config
from pymongo.collection import Collection

# Name of the app's database, as configured (`db.dbs` in `config.yaml`)
DB = "drsStore"


def get_foca_config() -> Config:
    """Get the FOCA configuration of the current app.

    Returns:
        FOCA configuration.
    """
    # FOCA 0.13 sets the attribute on Flask's untyped `Config`; replaced by
    # `foca.get_config()` with the FOCA upgrade (#87)
    config: Config = current_app.config.foca  # type: ignore[attr-defined]
    return config


def get_collection(name: str) -> Collection[dict[str, Any]]:
    """Get a collection of the app's database.

    Args:
        name: Name of the collection, as configured.

    Returns:
        MongoDB collection.
    """
    collection: Collection[dict[str, Any]] = (
        get_foca_config().db.dbs[DB].collections[name].client
    )
    return collection
