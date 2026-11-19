"""Controllers for DRS endpoints."""

import logging
from typing import Any, NoReturn, cast

from flask import request
from foca.utils.logging import log_traffic

from drs_filer.errors.exceptions import (
    AccessMethodNotDeleted,
    AccessMethodNotFound,
    AuthorizationInfoNotImplemented,
    InternalServerError,
    ObjectNotFound,
    PassportOperationNotImplemented,
    URLNotFound,
)
from drs_filer.ga4gh.drs.access_urls import served_object
from drs_filer.ga4gh.drs.endpoints.register_objects import (
    register_object,
)
from drs_filer.ga4gh.drs.endpoints.service_info import (
    RegisterServiceInfo,
    drs_service_fields,
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

    Without access URLs while these need login (cf.
    `drs_filer.ga4gh.drs.access_urls.served_object()`).

    Returns:
        List of DRS objects as dictionaries, JSONified if returned in app context.
    """
    db_collection = get_collection("objects")
    cursor = db_collection.find({}, {"_id": 0})
    objects = []
    for obj in cursor:
        objects.append(served_object(obj))
    return objects


@log_traffic
def GetObject(object_id: str, expand: bool = False) -> dict[str, Any]:
    """Get DRS object.

    Without access URLs while these need login (cf.
    `drs_filer.ga4gh.drs.access_urls.served_object()`).

    Args:
        object_id: Identifier of DRS object to be retrieved.
        expand: Whether to expand nested bundles; ignored, as bundles are
            served as registered.

    Returns:
        DRS object as dictionary, JSONified if returned in app context.
    """
    return served_object(_get_object(object_id))


def _get_object(object_id: str) -> dict[str, Any]:
    """Get DRS object, without logging the request (for other controllers).

    Args:
        object_id: Identifier of DRS object to be retrieved.

    Returns:
        DRS object as dictionary.

    Raises:
        drs_filer.errors.exceptions.ObjectNotFound: No object has the
            identifier.
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
    obj = _get_object(object_id)
    # Access methods are optional (e.g., for bundles), and so are their
    # `access_url`s; access methods stored before #121 may lack `access_id`
    # (they can't be addressed, but don't break the lookup of the others)
    matches = [
        d for d in obj.get("access_methods", []) if d.get("access_id") == access_id
    ]
    if not matches:
        raise URLNotFound
    # Access IDs should be unique
    if len(matches) > 1:
        raise InternalServerError
    access_url = matches[0].get("access_url")
    if access_url is None:
        raise URLNotFound
    return access_url


@log_traffic
def GetServiceInfo() -> dict[str, Any]:
    """Show information about this service.

    Returns:
        Service info: the stored one, with the DRS fields that the app
        computes (`drs_service_fields()`).
    """
    service_info = RegisterServiceInfo()
    return {**service_info.get_service_info(), **drs_service_fields()}


@log_traffic
def PostServiceInfo() -> tuple[None, int, dict[str, Any]]:
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
        drs_filer.errors.exceptions.ObjectNotFound: If the object doesn't
            exist.
        drs_filer.errors.exceptions.AccessMethodNotFound: If the object has
            no access method with the given identifier (also if it has no
            access methods, e.g., a bundle).
        drs_filer.errors.exceptions.AccessMethodNotDeleted: If attempting to
            delete the last remaining access method, i.e., if the object has
            no access method with another identifier.
        drs_filer.errors.exceptions.InternalServerError: If the access method
            could be deleted, but wasn't.
    """
    db_collection = get_collection("objects")

    # One atomic update: the access method is removed only if the object
    # keeps an access method with another identifier, so that concurrent
    # deletions can't remove the last one
    del_access_methods = db_collection.update_one(
        filter={
            "id": object_id,
            "access_methods.access_id": access_id,
            "access_methods": {"$elemMatch": {"access_id": {"$ne": access_id}}},
        },
        update={
            "$pull": {
                "access_methods": {"access_id": access_id},
            },
        },
    )
    if del_access_methods.modified_count:
        return access_id

    # Nothing deleted: find out why, from the current state of the object
    obj = _get_object(object_id)
    # Access methods are optional (e.g., for bundles), as in `GetAccessURL`
    access_ids = [m.get("access_id") for m in obj.get("access_methods", [])]
    if access_id not in access_ids:
        raise AccessMethodNotFound
    if all(other == access_id for other in access_ids):
        logger.error(
            "Will not delete only remaining access method for object: %s", object_id
        )
        raise AccessMethodNotDeleted
    # Deletable, but not deleted: the object changed between the update and
    # the read (e.g., a concurrent request), or the database failed
    logger.error(
        "Access method %s of object %s not deleted, though it could be",
        access_id,
        object_id,
    )
    raise InternalServerError


@log_traffic
def RegisterObject() -> str:
    """Register new DRS object.

    Returns:
        Identifier of the registered object, generated by the app.
    """
    return register_object(data=_request_body())


# Operations of the DRS specification that DRS-Filer doesn't implement.
# `log_traffic` logs neither request bodies nor parameters (but at `DEBUG`,
# the path), so the passports of the request bodies (credentials) aren't
# logged


@log_traffic
def PostObject(**kwargs: Any) -> NoReturn:
    """Get a DRS object with passports: not implemented.

    Args:
        **kwargs: Parameters and request body of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.PassportOperationNotImplemented: Always.
    """
    raise PassportOperationNotImplemented


@log_traffic
def PostAccessURL(**kwargs: Any) -> NoReturn:
    """Get the access URL of a DRS object with passports: not implemented.

    Args:
        **kwargs: Parameters and request body of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.PassportOperationNotImplemented: Always.
    """
    raise PassportOperationNotImplemented


@log_traffic
def GetBulkObjects(**kwargs: Any) -> NoReturn:
    """Get several DRS objects, with passports: not implemented.

    Args:
        **kwargs: Parameters and request body of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.PassportOperationNotImplemented: Always.
    """
    raise PassportOperationNotImplemented


@log_traffic
def GetBulkAccessURL(**kwargs: Any) -> NoReturn:
    """Get the access URLs of several DRS objects, with passports: not implemented.

    Args:
        **kwargs: Parameters and request body of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.PassportOperationNotImplemented: Always.
    """
    raise PassportOperationNotImplemented


@log_traffic
def OptionsObject(**kwargs: Any) -> NoReturn:
    """Get the authorization info of a DRS object: not implemented yet (#98).

    Args:
        **kwargs: Parameters of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.AuthorizationInfoNotImplemented: Always.
    """
    raise AuthorizationInfoNotImplemented


@log_traffic
def OptionsBulkObject(**kwargs: Any) -> NoReturn:
    """Get the authorization info of DRS objects: not implemented yet (#98).

    Args:
        **kwargs: Parameters and request body of the operation; ignored.

    Raises:
        drs_filer.errors.exceptions.AuthorizationInfoNotImplemented: Always.
    """
    raise AuthorizationInfoNotImplemented


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
