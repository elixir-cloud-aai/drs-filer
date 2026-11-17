"""Controllers for DRS endpoints."""

import logging
from typing import Any, cast

from flask import request
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
from drs_filer.utils import get_collection

logger = logging.getLogger(__name__)


def _request_body() -> dict[str, Any]:
    """Get the JSON body of the current request.

    Returns:
        Request body, validated by Connexion against the API specification.
    """
    return cast(dict[str, Any], request.json)


@log_traffic
def ListDrsObjects() -> list[dict[str, Any]]:
    """Get all DRS objects.

    Returns:
        List of DRS objects as dictionaries, JSONified if returned in app context.
    """
    db_collection = get_collection("objects")
    cursor = db_collection.find({}, {"_id": 0})
    objects = []
    for obj in cursor:
        objects.append(obj)
    return objects


@log_traffic
def GetObject(object_id: str) -> dict[str, Any]:
    """Get DRS object.

    Args:
        object_id: Identifier of DRS object to be retrieved.

    Returns:
        DRS object as dictionary, JSONified if returned in app context.
    """
    db_collection = get_collection("objects")
    obj = db_collection.find_one({"id": object_id})
    if not obj:
        raise ObjectNotFound
    del obj["_id"]
    return obj


@log_traffic
def GetAccessURL(object_id: str, access_id: str) -> dict[str, Any]:
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
            d["access_url"] for d in access_methods if d["access_id"] == access_id
        ]
    # An access methods dictionary is required for every object and it needs
    # to contain a list of dictionaries wth keys `access_url` and `access_id`
    except KeyError as err:
        raise InternalServerError from err
    if not access_urls:
        raise URLNotFound
    elif len(access_urls) == 1:
        return access_urls[0]
    # Access IDs should be unique
    else:
        raise InternalServerError


@log_traffic
def getServiceInfo() -> dict[str, Any]:
    """Show information about this service.

    Returns:
        Service info.
    """
    service_info = RegisterServiceInfo()
    return service_info.get_service_info()


@log_traffic
def postServiceInfo() -> tuple[None, int, dict[str, Any]]:
    """Set information about this service.

    Returns:
        An empty 201 response with headers.
    """
    service_info = RegisterServiceInfo()
    headers = service_info.set_service_info_from_app_context(data=_request_body())
    return None, 201, headers


@log_traffic
def DeleteObject(object_id: str) -> str:
    """Delete DRS object.

    Args:
        object_id: Identifier of DRS object to be deleted.

    Returns:
        `object_id` of deleted object.
    """
    db_collection = get_collection("objects")
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
    db_collection = get_collection("objects")

    obj = GetObject.__wrapped__(object_id=object_id)
    access_methods = obj["access_methods"]

    if access_id not in [m.get("access_id", None) for m in access_methods]:
        raise AccessMethodNotFound

    if len(access_methods) == 1:
        logger.error(
            "Will not delete only remaining access method for object: %s", object_id
        )
        raise AccessMethodNotDeleted

    del_access_methods = db_collection.update_one(
        filter={"id": object_id},
        update={
            "$pull": {
                "access_methods": {"access_id": access_id},
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
    return register_object(data=_request_body())


@log_traffic
def PutObject(object_id: str) -> str:
    """Add/replace DRS object with a user-supplied ID.

    Args:
        object_id: Identifier of DRS object to be created/updated.

    Returns:
        Identifier of created/updated DRS object.

    """
    return register_object(
        data=_request_body(),
        object_id=object_id,
    )
