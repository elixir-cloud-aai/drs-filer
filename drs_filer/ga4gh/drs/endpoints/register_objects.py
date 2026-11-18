"""Controller for registering new DRS objects."""

import logging
from typing import Any

from foca.utils.misc import generate_id
from pymongo.errors import DuplicateKeyError

from drs_filer.errors.exceptions import InternalServerError
from drs_filer.utils import get_collection, get_endpoints_config, get_id_settings

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
    endpoints = get_endpoints_config()
    db_collection = get_collection("objects")
    url_prefix = endpoints["url_prefix"]
    external_host = endpoints["external_host"]
    external_port = endpoints["external_port"]
    api_path = endpoints["api_path"]

    # Set flags and parameters for POST/PUT routes
    replace = True
    was_replaced = False
    if object_id is None:
        replace = False
        id_charset, id_length = get_id_settings("objects")

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


def __add_access_ids(
    data: list[dict[str, Any]],
    retries: int = 9,
) -> list[dict[str, Any]]:
    """Add access identifiers to posted access methods metadata.

    Args:
        data: List of access method metadata objects.
        retries: How many times the generation of a random identifier should
            be retried for each access method if it duplicates the identifier
            of an earlier access method of the same object.

    Returns:
        Access methods metadata complete with unique access identifiers.

    Raises:
        InternalServerError: No unique identifier was found for an access
            method within `retries + 1` attempts.
    """
    id_charset, id_length = get_id_settings("access_methods")
    access_ids: set[str] = set()
    for method in data:
        for _ in range(retries + 1):
            access_id = generate_id(charset=id_charset, length=id_length)
            if access_id not in access_ids:
                break
        else:
            logger.error(
                "Could not generate unique access identifier. Tried %s times.",
                retries + 1,
            )
            raise InternalServerError
        method["access_id"] = access_id
        access_ids.add(access_id)

    return data
