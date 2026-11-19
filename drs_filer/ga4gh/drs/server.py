"""Controllers for DRS endpoints."""

import logging
import re
from typing import Any, NoReturn, cast
from urllib.parse import quote

from bson import ObjectId
from flask import request
from foca.errors import FieldError, InvalidFieldsProblem
from foca.utils.logging import log_traffic

from drs_filer.errors.exceptions import (
    AccessMethodNotDeleted,
    AccessMethodNotFound,
    InternalServerError,
    ObjectNotFound,
    PassportOperationNotImplemented,
    URLNotFound,
)
from drs_filer.ga4gh.drs.access_urls import served_object
from drs_filer.ga4gh.drs.authorizations import (
    bulk_object_authorizations,
    object_authorizations,
    with_access_method_authorizations,
)
from drs_filer.ga4gh.drs.endpoints.register_objects import (
    register_object,
)
from drs_filer.ga4gh.drs.endpoints.service_info import (
    RegisterServiceInfo,
    drs_service_fields,
    invalidates_object_stats,
)
from drs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)

# Page tokens of the object list (`ListDrsObjects()`): the database
# identifier (`_id`) of an object, as 24 hexadecimal digits, as the pattern of
# `pageToken` in the specification
PAGE_TOKEN = re.compile(r"[0-9a-f]{24}")


def _request_body() -> dict[str, Any]:
    """Get the JSON body of the current request.

    Returns:
        Request body, validated by Connexion against the API specification.
    """
    return cast(dict[str, Any], request.json)


def self_uri(object_id: str) -> str:
    """Get the `self_uri` of an object: its DRS URI on the configured host.

    A hostname-based DRS URI, `drs://<hostname>/<id>`, of the host name of
    the config (`custom.drs.hostname`, not of the request, whose `Host`
    clients set), with the identifier percent-encoded, as DRS requires
    (the unreserved characters of URLs stay as they are, except in the
    identifiers `.` and `..`, which would be dot segments that clients
    remove when resolving the URI, RFC 3986, section 5.2.4).

    Args:
        object_id: Identifier of the object.

    Returns:
        The DRS URI of the object.

    Example:
        With `custom.drs.hostname: drs.example.org`, `self_uri("a:b")` is
        `drs://drs.example.org/a%3Ab`.
    """
    hostname = get_custom_config().drs.hostname
    encoded = quote(object_id, safe="")
    if encoded in {".", ".."}:
        encoded = encoded.replace(".", "%2E")
    return f"drs://{hostname}/{encoded}"


def _served(obj: dict[str, Any]) -> dict[str, Any]:
    """Get a stored object as it is served.

    Without the database's `_id`, and with the `self_uri` of the configured
    host (`self_uri()`), which isn't stored, and replaces the one that
    earlier versions stored (an HTTP URL, of the host of their config).

    Args:
        obj: Stored object.

    Returns:
        The object, as served.
    """
    served = {key: value for key, value in obj.items() if key != "_id"}
    served["self_uri"] = self_uri(served["id"])
    return served


def _read(obj: dict[str, Any]) -> dict[str, Any]:
    """Get an object as the object reads serve it.

    Without access URLs while these need login (cf.
    `drs_filer.ga4gh.drs.access_urls.served_object()`), and with the
    authorization info of the access URLs in the access methods (cf.
    `drs_filer.ga4gh.drs.authorizations.with_access_method_authorizations()`).

    Args:
        obj: Object, as served (`_served()`).

    Returns:
        The object, as the object reads serve it.
    """
    return with_access_method_authorizations(served_object(obj))


@log_traffic
def ListDrsObjects(
    pageSize: int | None = None,
    pageToken: str | None = None,
) -> dict[str, Any]:
    """Get a page of the DRS objects.

    Objects are listed by their database identifier (`_id`), descending, and
    served as the object reads serve them (`_read()`). `_id`s are unique, so
    no object is skipped or listed twice; they start with the time of
    registration (in seconds), so the list is newest first, to the second
    (in the same second, and across app instances with clock skew, the order
    is arbitrary, but fixed). Replacing an object (`PUT`) keeps
    its `_id`, so its place in the list. The page token is the `_id` of the
    last object of the previous page, as 24 hexadecimal digits
    (`PAGE_TOKEN`). Connexion checks it against the pattern of the
    specification, which Python's regular expressions also match with a
    newline at the end (`$`), so it is checked again here.

    Args:
        pageSize: Maximum number of objects of the page; by default
            `custom.objects.list.default_page_size`, and at most
            `max_page_size`, to which larger values are reduced.
        pageToken: `nextPageToken` of the previous page.

    Returns:
        The page (`DrsObjectPage`): its objects, and `nextPageToken` unless it
        is the last page.

    Raises:
        foca.errors.InvalidFieldsProblem: The page token is malformed; the
            problem details don't quote it.
    """
    if pageToken is not None and not PAGE_TOKEN.fullmatch(pageToken):
        raise InvalidFieldsProblem(
            [
                FieldError(
                    detail="Must be the 'nextPageToken' of a page.",
                    code="pattern-mismatch",
                    parameter="pageToken",
                )
            ]
        )
    settings = get_custom_config().objects.list
    size = min(
        settings.default_page_size if pageSize is None else pageSize,
        settings.max_page_size,
    )
    query = {} if pageToken is None else {"_id": {"$lt": ObjectId(pageToken)}}
    # One more than the page, to learn whether there is a next page
    found = list(get_collection("objects").find(query).sort("_id", -1).limit(size + 1))
    page: dict[str, Any] = {"objects": [_read(_served(obj)) for obj in found[:size]]}
    if len(found) > size:
        page["nextPageToken"] = str(found[size - 1]["_id"])
    return page


@log_traffic
def GetObject(object_id: str, expand: bool = False) -> dict[str, Any]:
    """Get DRS object.

    As the object reads serve it (`_read()`).

    Args:
        object_id: Identifier of DRS object to be retrieved.
        expand: Whether to expand nested bundles; ignored, as bundles are
            served as registered.

    Returns:
        DRS object as dictionary, JSONified if returned in app context.
    """
    return _read(_get_object(object_id))


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
    return _served(obj)


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
@invalidates_object_stats
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
@invalidates_object_stats
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
def OptionsObject(object_id: str) -> dict[str, Any]:
    """Get the authorization info of a DRS object.

    How to authorize `GetObject` (cf.
    `drs_filer.ga4gh.drs.authorizations.object_authorizations()`).

    Args:
        object_id: Identifier of the DRS object.

    Returns:
        `Authorizations` of the object, JSONified if returned in app context.
    """
    return object_authorizations(object_id)


@log_traffic
def OptionsBulkObject() -> dict[str, Any]:
    """Get the authorization info of several DRS objects.

    How to authorize `GetObject` for each (cf.
    `drs_filer.ga4gh.drs.authorizations.bulk_object_authorizations()`).

    Returns:
        Summary, unresolved identifiers and `Authorizations` of the
        resolved objects, JSONified if returned in app context.
    """
    return bulk_object_authorizations(_request_body())


@log_traffic
@invalidates_object_stats
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
