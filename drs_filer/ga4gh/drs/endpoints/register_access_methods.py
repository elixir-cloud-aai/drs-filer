import logging
from random import choice
import string
from typing import Dict, Optional

from flask import current_app

from drs_filer.errors.exceptions import (
    ObjectNotFound,
    InternalServerError
)

logger = logging.getLogger(__name__)


def register_access_method(
    data: Dict,
    object_id: str,
    access_id: Optional[str] = None,
) -> str:
    """TODO: Add documentation"""
    # Set parameters
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    obj = db_collection.find_one({"id": object_id})
    if not obj:
        raise ObjectNotFound

    # Set flags and parameters for POST/PUT routes
    replace = True
    if access_id is None:
        replace = False
        id_length = (
            current_app.config['FOCA'].endpoints['objects']['id_length']
        )
        id_charset: str = (
            current_app.config['FOCA'].endpoints['objects']['id_charset']
        )
        # evaluate character set expression or interpret literal string as set
        try:
            id_charset = eval(id_charset)
        except Exception:
            id_charset = ''.join(sorted(set(id_charset)))

    if access_id is not None:
        data['access_id'] = access_id
    else:
        data[access_id] = generate_unique_id(
            data_object=obj,
            charset=id_charset,  # type: ignore
            length=id_length,  # type: ignore
        )

    if replace:
        db_collection.update_one(
            filter={'id': object_id},
            update={
                '$set': {
                    'access_methods.$[element]': data
                }
            },
            array_filters=[{'element.access_id': data['access_id']}],
            upsert=True
        )
        logger.info(
            f"Replaced Access Method with access_id: {data['access_id']}"
            " to object with id: {object_id}"
        )
    else:
        db_collection.update_one(
            filter={'id': object_id},
            update={
                '$push': {
                    'access_methods': data
                }
            }
        )
        logger.info(
            f"Added Access Method with access_id: {data['access_id']}"
            " to object with id: {object_id}"
        )
    return data['access_id']


def generate_unique_id(
    data_object: Dict,
    charset: str = ''.join([string.ascii_letters, string.digits]),
    length: int = 6,
    retries: int = 9
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        charset: String of allowed characters.
        length: Length of returned string.

    Returns:
        Random string of specified length and composed of defined set of
        allowed characters.
    """
    if('access_methods' in data_object):
        access_methods = data_object['access_methods']
        access_ids = []
        for method in access_methods:
            access_ids.append(method['access_id'])
        for i in range(retries + 1):
            logger.debug(f"Trying to generate unique id: try {i}")
            access_id = ''.join(choice(charset) for __ in range(length))
            if(access_id not in access_ids):
                return access_id
        else:
            logger.error(
                f"Could not generate unique identifier."
                " Tried {retries + 1} times."
            )
            raise InternalServerError
    else:
        return ''.join(choice(charset) for __ in range(length))
