"""Controller for adding new DRS objects."""

from drs_filer.app import logger
import string
from typing import Dict
from flask import (current_app, request)
from random import choice
from pymongo.errors import DuplicateKeyError

MAIN_FIELDS_TO_OMIT = ["id", "self_uri"]

ACCESS_FIELDS_TO_OMIT = ["access_id"]

CHARSET = string.ascii_letters + string.digits + ".-_~"

LENGTH = 6


def register_new_objects(request: request) -> str:
    """Add new objects to DRS registry.

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
    data = _prepare_access_data(data)

    while True:
        # Fill in the main fields
        try:
            generated_object_id = _create_id()
            data['id'] = generated_object_id
            data['self_uri'] = \
                f"drs://{current_app.config['FOCA'].server.host}/{data['id']}"
            db_collection.insert_one(data)
        except DuplicateKeyError:
            continue
        except Exception as e:
            raise e
        logger.info(f"object with id: {data['id']} created.")
        break

    return data['id']


def _prepare_access_data(data: Dict) -> Dict:
    """Prepare acess data before registering into database

    Args:
        data: The data to be registered.

    Returns:
        The modified data suitable for registering.
    """

    # Delete the main fields first
    for field in MAIN_FIELDS_TO_OMIT:
        try:
            del data[field]
        except KeyError:
            pass

    try:
        access_data = data["access_methods"]

        # Delete access_fields
        for field in ACCESS_FIELDS_TO_OMIT:
            for method in access_data:
                try:
                    del method[field]
                except KeyError:
                    pass
    except KeyError:
        pass

    # Fill in the access_ids first

    try:
        access_data = data["access_methods"]

        access_id_set = set()
        for field in ACCESS_FIELDS_TO_OMIT:
            for method in access_data:
                generated_access_id = _create_id()
                if generated_access_id not in access_id_set:
                    method[field] = generated_access_id
                    access_id_set.add(generated_access_id)
    except KeyError:
        pass

    return data


def _create_id() -> str:
    """Creates random ID."""
    return ''.join(choice(CHARSET) for __ in range(LENGTH))
