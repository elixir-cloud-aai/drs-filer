"""Authorization info of objects and access methods (DRS `Authorizations`).

DRS tells clients how to authorize their reads: the authorization info of
objects (`OPTIONS /objects/{object_id}`, `OptionsObject`, and `OPTIONS
/objects`, `OptionsBulkObject`), for `GetObject`, and the `authorizations`
of access methods, for their access URLs (`GetAccessURL`). Both follow the
security requirements of the specification as FOCA registers it, with the
patches of every overlay (cf. `drs_filer.ga4gh.drs.access_urls`): bearer
tokens (`BearerAuth`) of the trusted issuers (`security.auth.issuers`) if
the read requires a token, otherwise none (`None`). Passports
(`PassportAuth`) are never reported, as DRS-Filer doesn't accept them (see
"Passport POST endpoints" in `docs/api.md`), nor basic authentication.

While object reads need login, the authorization info is the same for all
identifiers, whether an object exists or not, so that anonymous clients
can't find out which objects exist; otherwise, unknown objects get `404`
(single) or are unresolved (bulk).
"""

import logging
from typing import Any

from flask import current_app

from drs_filer.errors.exceptions import (
    BulkObjectIdsMissing,
    BulkRequestTooLarge,
    ObjectNotFound,
)
from drs_filer.ga4gh.drs.access_urls import access_urls_need_login, specs_require_login
from drs_filer.utils import get_collection, get_custom_config, get_foca_config

logger = logging.getLogger(__name__)

# Key of the Flask config that caches whether object reads need login
CONFIG_KEY = "DRS_FILER_OBJECT_READS_NEED_LOGIN"
# The operation that serves objects, whose authorization info `OPTIONS`
# reports, and its path
OPERATION_ID = "GetObject"
OBJECT_PATH = "/objects/{object_id}"


def object_reads_need_login() -> bool:
    """Check whether object reads (`GetObject`) need login in the current app.

    Read from the app's specifications once, as for access URLs
    (`drs_filer.ga4gh.drs.access_urls.access_urls_need_login()`), then
    cached in the app's config (`CONFIG_KEY`).

    Returns:
        Whether object reads need login.
    """
    need_login = current_app.config.get(CONFIG_KEY)
    if need_login is None:
        need_login = specs_require_login(
            get_foca_config().api.specs, OBJECT_PATH, OPERATION_ID
        )
        current_app.config[CONFIG_KEY] = need_login
        logger.info(
            "Object reads %s",
            "need login" if need_login else "are public",
        )
    return bool(need_login)


def supported_authorizations(need_login: bool) -> dict[str, Any]:
    """Get the authorization info of a read.

    Args:
        need_login: Whether the read needs login.

    Returns:
        `Authorizations` of DRS, without `drs_object_id`: bearer tokens
        (`BearerAuth`) of the trusted issuers if the read needs login
        (without `bearer_auth_issuers` if none are configured, which only
        apps without authentication can be), otherwise no authorization
        (`None`).
    """
    if not need_login:
        return {"supported_types": ["None"]}
    authorizations: dict[str, Any] = {"supported_types": ["BearerAuth"]}
    issuers = get_foca_config().security.auth.issuer_urls
    if issuers:
        authorizations["bearer_auth_issuers"] = issuers
    return authorizations


def with_access_method_authorizations(obj: dict[str, Any]) -> dict[str, Any]:
    """Add the authorization info of access URLs to an object's access methods.

    Each access method with an `access_id` gets the `authorizations` of
    its access URL (`supported_authorizations()`, as access URLs need
    login or not), replacing stored ones, if any; access methods without
    `access_id` can't be read by it, and are served without.

    Args:
        obj: Object, as served.

    Returns:
        The object, unchanged if it has no access methods, otherwise a copy
        with the authorization info.
    """
    if "access_methods" not in obj:
        return obj
    authorizations = supported_authorizations(access_urls_need_login())
    return {
        **obj,
        "access_methods": [
            {**method, "authorizations": authorizations}
            if "access_id" in method
            else {
                key: value for key, value in method.items() if key != "authorizations"
            }
            for method in obj["access_methods"]
        ],
    }


def object_authorizations(object_id: str) -> dict[str, Any]:
    """Get the authorization info of an object (`OptionsObject`).

    Args:
        object_id: Identifier of the object.

    Returns:
        `Authorizations` of the object.

    Raises:
        drs_filer.errors.exceptions.ObjectNotFound: Object reads are public
            and no object has the identifier.
    """
    need_login = object_reads_need_login()
    if (
        not need_login
        and get_collection("objects").find_one({"id": object_id}, {"_id": 1}) is None
    ):
        raise ObjectNotFound
    return {"drs_object_id": object_id, **supported_authorizations(need_login)}


def bulk_object_authorizations(request_body: dict[str, Any]) -> dict[str, Any]:
    """Get the authorization info of several objects (`OptionsBulkObject`).

    Each identifier is answered once, in the order of the request; the
    summary counts distinct identifiers.

    Args:
        request_body: Request body (`BulkObjectIdNoPassport`), validated by
            Connexion.

    Returns:
        The `summary`, the `unresolved_drs_objects` (the identifiers of
        unknown objects, with `error_code` `404`, while object reads are
        public; none while they need login) and the authorization info of
        the others (`resolved_drs_object`).

    Raises:
        drs_filer.errors.exceptions.BulkObjectIdsMissing: The request has no
            `bulk_object_ids`.
        drs_filer.errors.exceptions.BulkRequestTooLarge: The request has
            more identifiers than `custom.bulk.max_request_length`, counted
            as sent.
    """
    object_ids = request_body.get("bulk_object_ids")
    if object_ids is None:
        raise BulkObjectIdsMissing
    if len(object_ids) > get_custom_config().bulk.max_request_length:
        raise BulkRequestTooLarge
    requested = list(dict.fromkeys(object_ids))
    need_login = object_reads_need_login()
    if need_login:
        found = set(requested)
    else:
        found = {
            obj["id"]
            for obj in get_collection("objects").find(
                {"id": {"$in": requested}}, {"_id": 0, "id": 1}
            )
        }
    authorizations = supported_authorizations(need_login)
    resolved = [object_id for object_id in requested if object_id in found]
    unresolved = [object_id for object_id in requested if object_id not in found]
    return {
        "summary": {
            "requested": len(requested),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
        },
        "unresolved_drs_objects": (
            [{"error_code": 404, "object_ids": unresolved}] if unresolved else []
        ),
        "resolved_drs_object": [
            {"drs_object_id": object_id, **authorizations} for object_id in resolved
        ],
    }
