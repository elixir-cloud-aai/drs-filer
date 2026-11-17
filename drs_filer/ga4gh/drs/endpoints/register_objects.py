"""Controller for registering new DRS objects."""

import logging
from random import choice
import string
from typing import Any

from pymongo.errors import DuplicateKeyError

from drs_filer.errors.exceptions import InternalServerError
from drs_filer.utils import get_collection, get_foca_config

logger = logging.getLogger(__name__)


def register_object(
    data: dict[str, Any],
    object_id: str | None = None,
    retries: int = 9,
) -> str:
    """Register data object.

    Args:
        data: Request object of type `DrsObjectRegister`.
        object_id: DRS object identifier. Auto-generated if not provided.
        retries: If `object_id` is not supplied, how many times should the
            generation of a random identifier and insertion into the database
            be retried in case of `DuplicateKeyError`s.

    Returns:
        A unique identifier for the object.
    """
    # Set parameters
    foca_config = get_foca_config()
    db_collection = get_collection("objects")
    url_prefix = foca_config.endpoints["url_prefix"]
    external_host = foca_config.endpoints["external_host"]
    external_port = foca_config.endpoints["external_port"]
    api_path = foca_config.endpoints["api_path"]

    # Set flags and parameters for POST/PUT routes
    replace = True
    was_replaced = False
    if object_id is None:
        replace = False
        id_length = foca_config.endpoints["objects"]["id_length"]
        id_charset: str = foca_config.endpoints["objects"]["id_charset"]
        # evaluate character set expression or interpret literal string as set
        # `eval()` of the operator's config (not of requests); replaced by a
        # literal character set in #54
        try:
            id_charset = eval(id_charset)  # noqa: S307
        except Exception:
            id_charset = "".join(sorted(set(id_charset)))

    # Add unique access identifiers for each access method
    if "access_methods" in data:
        data["access_methods"] = __add_access_ids(data=data["access_methods"])

    # Try to generate unique ID and insert object into database
    for i in range(retries + 1):
        logger.debug("Trying to insert/update object: try %s", i)

        # Set or generate object identifier
        data["id"] = (
            object_id
            if object_id is not None
            else generate_id(
                charset=id_charset,
                length=id_length,
            )
        )

        # Generate DRS URL
        data["self_uri"] = (
            f"{url_prefix}://{external_host}:{external_port}/{api_path}/{data['id']}"
        )

        # Replace or insert object, then return (PUT)
        if replace:
            result_object = db_collection.replace_one(
                filter={"id": data["id"]},
                replacement=data,
                upsert=True,
            )
            if result_object.modified_count:
                was_replaced = True
            break

        # Try to insert new object (POST); continue with next iteration if
        # key exists
        try:
            db_collection.insert_one(data)
            break
        except DuplicateKeyError:
            continue

    else:
        logger.error(
            "Could not generate unique identifier. Tried %s times.", retries + 1
        )
        raise InternalServerError

    if was_replaced:
        logger.info("Replaced object with id '%s'.", data["id"])
    else:
        logger.info("Added object with id '%s'.", data["id"])
    return data["id"]


def __add_access_ids(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add access identifiers to posted access methods metadata.

    Args:
        data: List of access method metadata objects.

    Returns:
        Access methods metadata complete with unique access identifiers.
    """
    foca_config = get_foca_config()
    # `eval()` of the operator's config (not of requests); replaced by a
    # literal character set in #54
    id_charset = eval(foca_config.endpoints["access_methods"]["id_charset"])  # noqa: S307
    id_length = foca_config.endpoints["access_methods"]["id_length"]
    access_ids = []
    for method in data:
        access_id = generate_id(id_charset, id_length)
        if access_id not in access_ids:
            method["access_id"] = access_id
            access_ids.append(access_id)

    return data


def generate_id(
    charset: str = "".join([string.ascii_letters, string.digits]), length: int = 6
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        charset: String of allowed characters.
        length: Length of returned string.

    Returns:
        Random string of specified length and composed of defined set of
        allowed characters.
    """
    # Identifiers, not secrets: a cryptographic generator is not needed
    return "".join(choice(charset) for __ in range(length))  # noqa: S311
