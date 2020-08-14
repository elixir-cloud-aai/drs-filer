"""Controllers for DRS endpoints."""

from typing import Dict

from flask import (current_app, request)
from foca.utils.logging import log_traffic

from drs_filer.errors.exceptions import (
    InternalServerError,
    ObjectNotFound,
    URLNotFound,
)
from drs_filer.ga4gh.drs.endpoints.register_new_objects import (
    register_new_objects,
)


@log_traffic
def RegisterObjects() -> str:
    """Register new DRS object."""
    return register_new_objects(request)


@log_traffic
def GetObject(object_id: str) -> Dict:
    """Get DRS object.

    Args:
        object_id: Identifier of DRS object to be retrieved.

    Returns:
        DRS object as dictionary, JSONified if returned in app context.
    """
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    obj = db_collection.find_one({"id": object_id})
    if not obj:
        raise ObjectNotFound
    del obj["_id"]
    return obj


@log_traffic
def GetAccessURL(object_id: str, access_id: str) -> Dict:
    """Get access URL of DRS object.

    Args:
        object_id: Identifier of DRS object to be retrieved.
        access_id: Identifier of method giving access to DRS object.

    Returns:
        Object with access information for DRS object, containing a URL and
        any relevant header information; response is JSONified if returned in
        app context.
    """
    obj = GetObject.__wrapped__(object_id)
    try:
        access_methods = obj["access_methods"]
        access_urls = [
            d['access_url'] for d in access_methods
            if d['access_id'] == access_id
        ]
    # An access methods dictionary is required for every object and it needs
    # to contain a list of dictionaries wth keys `access_url` and `access_id`
    except KeyError:
        raise InternalServerError
    if not access_urls:
        raise URLNotFound
    elif len(access_urls) == 1:
        return access_urls[0]
    # Access IDs should be unique
    else:
        raise InternalServerError


@log_traffic
def DeleteObject(object_id):
    """Delete DRS object.

    Args:
        object_id: Identifier of DRS object to be deleted.

    Returns:
        `object_id` of deleted object.
    """

    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    obj = db_collection.find_one({"id": object_id})
    if not obj:
        raise ObjectNotFound
    else:
        db_collection.delete_one({"id": object_id})
        return object_id
