"""Typed access to the configuration and collections of the app."""

from typing import Any

from foca import get_config
from foca.models.config import Config
from foca.utils.misc import generate_id
from pymongo.collection import Collection

# Name of the app's database, as configured (`db.dbs` in `config.yaml`)
DB = "drsStore"
# Sections of `endpoints` with the settings of generated identifiers
ID_SECTIONS = ("objects", "access_methods")


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


def get_id_settings(section: str) -> tuple[str, int]:
    """Get the settings of generated identifiers of a section of `endpoints`.

    The character set lists the allowed characters themselves (duplicates
    are ignored). It is never evaluated: expressions using the `string`
    module (e.g., `string.ascii_letters + string.digits`), which earlier
    versions evaluated, are refused, with the checks of FOCA's
    `generate_id()`; other expressions are taken as characters.

    Args:
        section: Section of `endpoints` (`objects` or `access_methods`), with
            `id_charset` and `id_length`.

    Returns:
        Character set and length of identifiers.

    Raises:
        KeyError: The section or one of its settings is missing.
        ValueError: The character set is not a non-empty string or is an
            expression, or the length is not a positive integer.
    """
    settings = get_endpoints_config()[section]
    charset = settings["id_charset"]
    length = settings["id_length"]
    try:
        generate_id(charset=charset, length=1)
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise TypeError(f"'id_length' is not a positive integer: {length}")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid 'endpoints.{section}': {exc}") from exc
    return charset, length


def check_id_settings() -> None:
    """Check the settings of generated identifiers of all sections.

    Called on startup, so that invalid settings fail the start rather than
    requests.

    Raises:
        KeyError: A section or one of its settings is missing.
        ValueError: Settings of a section are invalid (see
            `get_id_settings()`).
    """
    for section in ID_SECTIONS:
        get_id_settings(section)


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
