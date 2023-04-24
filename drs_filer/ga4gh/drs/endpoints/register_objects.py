"""Controller for registering new DRS objects."""

import logging
from random import choice
import string
from typing import (Dict, List, Optional)

from flask import current_app
from pymongo.errors import DuplicateKeyError

from drs_filer.errors.exceptions import InternalServerError

logger = logging.getLogger(__name__)


def register_object(
    data: Dict,
    object_id: Optional[str] = None,
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
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    conf = current_app.config['FOCA'].endpoints

    url_prefix = conf['service']['url_prefix']
    external_host = conf['service']['external_host']
    external_port = conf['service']['external_port']
    api_path = conf['service']['api_path']

    # Set flags and parameters for POST/PUT routes
    replace = True
    was_replaced = False
    if object_id is None:
        replace = False
        id_length = (
            conf['objects']['id_length']
        )
        id_charset: str = (
            conf['objects']['id_charset']
        )
        # evaluate character set expression or interpret literal string as set
        try:
            id_charset = eval(id_charset)
        except Exception:
            id_charset = ''.join(sorted(set(id_charset)))

    # Add unique access identifiers for each access method
    if 'access_methods' in data:
        data['access_methods'] = __add_access_ids(
            data=data['access_methods']
        )

    # Try to generate unique ID and insert object into database
    for i in range(retries + 1):
        logger.debug(f"Trying to insert/update object: try {i}")

        # Set or generate object identifier
        data['id'] = object_id if object_id is not None else generate_id(
            charset=id_charset,  # type: ignore
            length=id_length,  # type: ignore
        )

        # Generate DRS URL
        data['self_uri'] = (
            f"{url_prefix}://{external_host}:{external_port}/"
            f"{api_path}/{data['id']}"
        )

        # Replace or insert object, then return (PUT)
        if replace:
            result_object = db_collection.replace_one(
                filter={'id': data['id']},
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
            f"Could not generate unique identifier. Tried {retries + 1} times."
        )
        raise InternalServerError

    if was_replaced:
        logger.info(f"Replaced object with id '{data['id']}'.")
    else:
        logger.info(f"Added object with id '{data['id']}'.")
    return data['id']


def __add_access_ids(data: List) -> List:
    """Add access identifiers to posted access methods metadata.

    Args:
        data: List of access method metadata objects.

    Returns:
        Access methods metadata complete with unique access identifiers.
    """
    conf = current_app.config['FOCA'].endpoints
    id_charset = eval(
        conf['access_methods']['id_charset']
    )
    id_length = (
        conf['access_methods']['id_length']
    )
    access_ids = []
    for method in data:
        access_id = generate_id(id_charset, id_length)
        if access_id not in access_ids:
            method['access_id'] = access_id
            access_ids.append(access_id)

    return data


def generate_id(
    charset: str = ''.join([string.ascii_letters, string.digits]),
    length: int = 6
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        charset: String of allowed characters.
        length: Length of returned string.

    Returns:
        Random string of specified length and composed of defined set of
        allowed characters.
    """
    return ''.join(choice(charset) for __ in range(length))
