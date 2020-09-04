"""Controller for registering new DRS objects."""

import logging
from random import choice
import string
from typing import (List)

from flask import (current_app, request)
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


def register_new_objects(request: request) -> str:
    """Register data object.

    Args:
        request: API request object.

    Returns:
        A unique identifier for the object.
    """
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    data = request.json

    # Add unique access identifiers for each access method
    if 'access_methods' in data:
        data['access_methods'] = __add_access_ids(
            data=data['access_methods']
        )

    while True:
        # Add object identifier and DRS URL
        id_charset = eval(
            current_app.config['FOCA'].endpoints['objects']['id_charset']
        )
        id_length = (
            current_app.config['FOCA'].endpoints['objects']['id_length']
        )
        data['id'] = generate_id(charset=id_charset, length=id_length)
        url_prefix = current_app.config['FOCA'].endpoints['url_prefix']
        external_host = current_app.config['FOCA'].endpoints['external_host']
        external_port = current_app.config['FOCA'].endpoints['external_port']
        api_path = current_app.config['FOCA'].endpoints['api_path']
        data['self_uri'] = (
            f"{url_prefix}://{external_host}:{external_port}/"
            f"{api_path}/{data['id']}"
        )
        try:
            db_collection.insert_one(data)
        except DuplicateKeyError:
            continue
        logger.info(f"Object with id '{data['id']}' created.")
        break

    return data['id']


def __add_access_ids(data: List) -> List:
    """Add access identifiers to posted access methods metadata.

    Args:
        data: List of access method metadata objects.

    Returns:
        Access methods metadata complete with unique access identifiers.
    """
    id_charset = eval(
        current_app.config['FOCA'].endpoints['access_methods']['id_charset']
    )
    id_length = (
        current_app.config['FOCA'].endpoints['access_methods']['id_length']
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
