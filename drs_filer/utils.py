"""Typed access to the configuration and collections of the app."""

from typing import Any

from foca import get_config
from foca.models.config import Config
from pymongo.collection import Collection

from drs_filer.custom_config import CustomConfig

# Name of the app's database, as configured (`db.dbs` in `config.yaml`)
DB = "drsStore"


def get_foca_config() -> Config:
    """Get the FOCA configuration of the current app.

    Returns:
        FOCA configuration.
    """
    return get_config()


def get_custom_config() -> CustomConfig:
    """Get the app's own configuration (`custom`) of the current app.

    FOCA validates the section against `CustomConfig` on startup and keeps it
    as an untyped extra field of its configuration.

    Returns:
        The custom configuration.

    Raises:
        RuntimeError: The app has no custom configuration of type
            `CustomConfig` (e.g., it was not created by `create_app()`).
    """
    custom = (get_foca_config().model_extra or {}).get("custom")
    if not isinstance(custom, CustomConfig):
        raise RuntimeError(
            f"No custom configuration of type {CustomConfig}; check that "
            "`custom_config_model` is its full module path"
        )
    return custom


def get_collection(name: str) -> Collection[dict[str, Any]]:
    """Get a collection of the app's database.

    Args:
        name: Name of the collection, as configured.

    Returns:
        MongoDB collection.

    Raises:
        KeyError: The collection isn't configured, or FOCA hasn't registered
            it (no database configured, or no client).
    """
    db = get_foca_config().db
    dbs = db.dbs if db is not None else None
    collections = dbs[DB].collections if dbs is not None else None
    collection = collections[name].client if collections is not None else None
    if collection is None:
        raise KeyError(f"Collection '{name}' of database '{DB}' isn't registered")
    return collection
