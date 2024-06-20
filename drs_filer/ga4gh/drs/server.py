"""Controllers for DRS endpoints."""

import logging
from typing import (Dict, Tuple)

from flask import (current_app, request)
from foca.utils.logging import log_traffic

from drs_filer.errors.exceptions import (
    AccessMethodNotDeleted,
    AccessMethodNotFound,
    InternalServerError,
    ObjectNotFound,
    URLNotFound,
)
from drs_filer.ga4gh.drs.endpoints.register_objects import (
    register_object,
)
from drs_filer.ga4gh.drs.endpoints.service_info import (
    RegisterServiceInfo,
)

logger = logging.getLogger(__name__)


@log_traffic
def GetObject(object_id: str) -> Dict:
    """Get DRS object.

    Args:
        object_id: Identifier of DRS object to be retrieved.

    Returns:
        DRS object as dictionary, JSONified if returned in app context.
    """
    db_collection = (
        current_app.config.foca.db.dbs['drsStore'].
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
def getServiceInfo() -> Dict:
    """Show information about this service.

    Returns:
        An empty 201 response with headers.
    """
    service_info = RegisterServiceInfo()
    return service_info.get_service_info()


@log_traffic
def postServiceInfo() -> Tuple[None, str, Dict]:
    """Show information about this service.

    Returns:
        An empty 201 response with headers.
    """
    service_info = RegisterServiceInfo()
    headers = service_info.set_service_info_from_app_context(data=request.json)
    return None, '201', headers


@log_traffic
def DeleteObject(object_id):
    """Delete DRS object.

    Args:
        object_id: Identifier of DRS object to be deleted.

    Returns:
        `object_id` of deleted object.
    """

    db_collection = (
        current_app.config.foca.db.dbs['drsStore'].
        collections['objects'].client
    )
    obj = db_collection.find_one({"id": object_id})
    if not obj:
        raise ObjectNotFound
    else:
        db_collection.delete_one({"id": object_id})
        return object_id


@log_traffic
def DeleteAccessMethod(object_id: str, access_id: str) -> str:
    """Delete DRS object's Access Method.

    Args:
        object_id: Identifier of DRS object to be deleted.
        access_id: Identifier of the access method to be deleted

    Returns:
        `access_id` of deleted object.

    Raises:
        drs_filer.errors.exceptions.AccessMethodNotDeleted: If attempting to
            delete the last remaining access method.
    """

    db_collection = (
        current_app.config.foca.db.dbs['drsStore'].
        collections['objects'].client
    )

    obj = GetObject.__wrapped__(object_id=object_id)
    access_methods = obj['access_methods']

    if access_id not in [m.get('access_id', None) for m in access_methods]:
        raise AccessMethodNotFound

    if len(access_methods) == 1:
        logger.error(
            "Will not delete only remaining access method for object: "
            f"{object_id}"
        )
        raise AccessMethodNotDeleted

    del_access_methods = db_collection.update_one(
        filter={'id': object_id},
        update={
            '$pull': {
                'access_methods': {'access_id': access_id},
            },
        },
    )

    if del_access_methods.modified_count:
        return access_id
    else:
        raise InternalServerError


@log_traffic
def PostObject() -> str:
    """Register new DRS object."""
    return register_object(data=request.json)


@log_traffic
def PutObject(object_id: str):
    """Add/replace DRS object with a user-supplied ID.

    Args:
        object_id: Identifier of DRS object to be created/updated.

    Returns:
        Identifier of created/updated DRS object.

    """
    return register_object(
        data=request.json,
        object_id=object_id,
    )
