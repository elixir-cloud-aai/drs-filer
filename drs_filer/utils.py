"""Typed access to the configuration and collections of the app."""

from typing import Any

from foca import get_config
from foca.models.config import Config
from pymongo.collection import Collection

# Name of the app's database, as configured (`db.dbs` in `config.yaml`)
DB = "drsStore"


def get_foca_config() -> Config:
    """Get the FOCA configuration of the current app.

    Returns:
        FOCA configuration.
    """
    return get_config()


def get_endpoints_config() -> dict[str, Any]:
    """Get the app's own section of the configuration (`endpoints`).

    FOCA keeps sections that it doesn't know as untyped extra fields of its
    configuration.

    Returns:
        The `endpoints` section of the configuration.

    Raises:
        KeyError: The configuration has no `endpoints` section.
    """
    extra = get_foca_config().model_extra or {}
    if "endpoints" not in extra:
        raise KeyError("The configuration has no 'endpoints' section")
    endpoints: dict[str, Any] = extra["endpoints"]
    return endpoints


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
