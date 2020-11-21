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
    retries: int = 9
) -> str:
    """Register access method.

    Args:
        data: Request object of type `AccessMethodRegister`.
        object_id: DRS object identifier.
        access_id: Access method identifier. Auto-generated if not provided.
        retries: If `access_id` is not supplied, how many times should the
            generation of a random identifier and insertion into the database
            be retried in case of duplicate access_ids.

    Returns:
        A unique identifier for the access method.
    """
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

    # Try to generate unique ID and insert object into database
    for i in range(retries + 1):
        logger.debug(f"Trying to insert/update access method: try {i}")
        # Set or generate object identifier
        if access_id is not None:
            data['access_id'] = access_id
        else:
            data['access_id'] = generate_id(
                charset=id_charset,  # type: ignore
                length=id_length,  # type: ignore
            )
        # Replace access method, then return (PUT)
        if replace:
            result_replace = db_collection.update_one(
                filter={'id': object_id},
                update={
                    '$set': {
                        'access_methods.$[element]': data
                    }
                },
                array_filters=[{'element.access_id': data['access_id']}],
            )

            if(result_replace.modified_count):
                logger.info(
                    f"Replaced access method with access_id: "
                    f"{data['access_id']} of DRS object with id: {object_id}"
                )
                break

        # Try inserting the access method incase of POST or incase
        # no element matches with the filter incase of PUT.
        result_insert = db_collection.update_one(
            filter={
                'id': object_id,
                'access_methods.access_id': {'$ne': data['access_id']}
            },
            update={
                '$push': {
                    'access_methods': data
                }
            }
        )
        if(result_insert.modified_count):
            logger.info(
                f"Added access method with access_id: {data['access_id']}"
                f" to DRS object with id: {object_id}"
            )
            break
    # Access method neither added nor updated.
    else:
        logger.error(
            f"Could not generate unique identifier. Tried {retries + 1} times."
        )
        raise InternalServerError
    return data['access_id']


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
