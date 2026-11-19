"""Exceptions of the app and their problem details (RFC 9457).

The classes are FOCA's framework-neutral ones (`foca.errors`), which replace
those of Werkzeug and Connexion before FOCA's release on ASGI.
"""

from foca.errors import (
    AccessDeniedProblem,
    AuthenticationProblem,
    BadRequest,
    Conflict,
    ExtraParameterProblem,
    Forbidden,
    HTTPError,
    InternalServerError,
    NotFound,
    PayloadTooLarge,
    RequestValidationProblem,
    Unauthorized,
)
from werkzeug.exceptions import NotImplemented as _NotImplemented

# Documentation of the operations of the DRS specification that DRS-Filer
# doesn't implement
DOCS_API_URL = "https://drs-filer.readthedocs.io/en/latest/api/"


class AccessMethodNotDeleted(Conflict):
    """Raised when deleting the last remaining access method of an object."""

    pass


class AccessMethodNotFound(NotFound):
    """Raised when an access method of an object was not found.

    The object and access method are those of the given identifiers.
    """

    pass


class ObjectNotFound(NotFound):
    """Raised when object with given object identifier was not found."""

    pass


class URLNotFound(NotFound):
    """Raised when Access URL for object was not found."""

    pass


class ValidationError(Exception):
    """Value or object is not compatible with required type or schema."""


class OperationNotImplemented(HTTPError, _NotImplemented):
    """Raised for operations of the DRS specification that aren't implemented."""

    pass


class PassportOperationNotImplemented(OperationNotImplemented):
    """Raised for the passport `POST` operations of the DRS specification.

    DRS-Filer doesn't implement them, by design (see "Passport POST
    endpoints" in `docs/api.md`).
    """

    pass


class BulkObjectIdsMissing(BadRequest):
    """Raised for bulk requests without identifiers (`bulk_object_ids`)."""

    pass


class BulkRequestTooLarge(PayloadTooLarge):
    """Raised for bulk requests with more identifiers than allowed.

    The maximum is `custom.bulk.max_request_length` of the config, served as
    `maxBulkRequestLength` in the service info.
    """

    pass


# Problem details of exceptions raised in app context, served by FOCA
# (`exceptions.mapping` in `config.yaml`); exceptions not listed get those of
# their closest listed base class
exceptions = {
    Exception: {
        "title": "Internal server error",
        "detail": "An unexpected error occurred.",
        "status": 500,
    },
    RequestValidationProblem: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    BadRequest: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    ExtraParameterProblem: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    Unauthorized: {
        "title": "Unauthorized",
        "detail": "The request is unauthorized.",
        "status": 401,
    },
    AuthenticationProblem: {
        "title": "Unauthorized",
        "detail": "The request is unauthorized.",
        "status": 401,
    },
    Forbidden: {
        "title": "Forbidden",
        "detail": "The requester is not authorized to perform this action.",
        "status": 403,
    },
    # Connexion's `Forbidden` (FOCA's access control)
    AccessDeniedProblem: {
        "title": "Forbidden",
        "detail": "The requester is not authorized to perform this action.",
        "status": 403,
    },
    NotFound: {
        "title": "Not found",
        "detail": "The requested resource wasn't found.",
        "status": 404,
    },
    AccessMethodNotFound: {
        "title": "Not found",
        "detail": "The requested access method wasn't found.",
        "status": 404,
    },
    AccessMethodNotDeleted: {
        "title": "Conflict",
        "detail": "Refusing to delete the last remaining access method.",
        "status": 409,
    },
    ObjectNotFound: {
        "title": "Not found",
        "detail": "The requested `DrsObject` wasn't found.",
        "status": 404,
    },
    URLNotFound: {
        "title": "Not found",
        "detail": "The requested access URL wasn't found.",
        "status": 404,
    },
    InternalServerError: {
        "title": "Internal server error",
        "detail": "An unexpected error occurred.",
        "status": 500,
    },
    OperationNotImplemented: {
        "title": "Not implemented",
        "detail": (
            "DRS-Filer doesn't implement this operation; see "
            f"{DOCS_API_URL}#deviations-from-the-specification"
        ),
        "status": 501,
    },
    PassportOperationNotImplemented: {
        "title": "Not implemented",
        "detail": (
            "DRS-Filer doesn't accept GA4GH Passports in request bodies: get "
            "objects and access URLs with GET, with a bearer access token in "
            "the Authorization header if needed; see "
            f"{DOCS_API_URL}#passport-post-endpoints"
        ),
        "status": 501,
    },
    BulkObjectIdsMissing: {
        "title": "Bad request",
        "detail": (
            "The request body needs `bulk_object_ids`, a list of object identifiers."
        ),
        "status": 400,
    },
    PayloadTooLarge: {
        "title": "Payload too large",
        "detail": "The request is too large.",
        "status": 413,
    },
    BulkRequestTooLarge: {
        "title": "Payload too large",
        "detail": (
            "The bulk request has more identifiers than the service info "
            "allows (`maxBulkRequestLength`)."
        ),
        "status": 413,
    },
}
