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
    """Register access method.

    Args:
        data: Request object of type `AccessMethodRegister`.
        object_id: DRS object identifier.
        access_id: Access method identifier. Auto-generated if not provided.

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

    if access_id is not None:
        data['access_id'] = access_id
    else:
        data['access_id'] = generate_unique_id(
            data_object=obj,
            charset=id_charset,  # type: ignore
            length=id_length,  # type: ignore
        )

    if replace:
        result = db_collection.update_one(
            filter={'id': object_id},
            update={
                '$set': {
                    'access_methods.$[element]': data
                }
            },
            array_filters=[{'element.access_id': data['access_id']}],
        )

        if(result.modified_count):
            logger.info(
                f"Replaced access method with access_id: {data['access_id']}"
                f" of DRS object with id: {object_id}"
            )
            return data['access_id']
    
    # Try adding the access method incase of POST or incase
    # no element matches with the filter in case of replacement.
    result = db_collection.update_one(
        filter={'id': object_id},
        update={
            '$push': {
                'access_methods': data
            }
        }
    )
    if(result.modified_count):
        logger.info(
            f"Added access method with access_id: {data['access_id']}"
            f" to DRS object with id: {object_id}"
        )
    # Access method neither added nor updated.
    else:
        raise InternalServerError
    return data['access_id']


def generate_unique_id(
    data_object: Dict,
    charset: str = ''.join([string.ascii_letters, string.digits]),
    length: int = 6,
    retries: int = 9
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        data_object: The DRS object
        charset: String of allowed characters.
        length: Length of returned string.
        retries: If `access_id` is not supplied, how many times should the
            generation of a random identifier take place.

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
