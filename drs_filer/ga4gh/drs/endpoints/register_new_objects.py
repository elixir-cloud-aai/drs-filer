"""Controller for adding new DRS objects."""

from drs_filer.app import logger
import string
from typing import Dict
from flask import (current_app, request)
from random import choice
from pymongo.errors import DuplicateKeyError


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
            id_charset = current_app.config['FOCA'].\
                endpoints['objects']['id_charset']
            id_length = current_app.config['FOCA'].\
                endpoints['objects']['id_length']
            generated_object_id = _create_id(id_charset, id_length)
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

    # Generate the access_ids
    try:
        access_data = data["access_methods"]
        id_charset = current_app.config['FOCA'].\
            endpoints['access_methods']['id_charset']
        id_length = current_app.config['FOCA'].\
            endpoints['access_methods']['id_length']
        access_id_set = set()
        for method in access_data:
            generated_access_id = _create_id(id_charset, id_length)
            if generated_access_id not in access_id_set:
                method['access_id'] = generated_access_id
                access_id_set.add(generated_access_id)
    except KeyError:
        pass

    return data


def _create_id(charset, length) -> str:
    """Creates random ID."""
    return ''.join(choice(charset) for __ in range(length))
