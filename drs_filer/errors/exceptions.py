"""Exceptions of the app and their mapping to HTTP responses."""

from connexion.exceptions import (
    BadRequestProblem,
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
)
from werkzeug.exceptions import (
    BadRequest,
    Conflict,
    InternalServerError,
    NotFound,
)


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


exceptions = {
    Exception: {
        "msg": "An unexpected error occurred.",
        "status_code": 500,
    },
    BadRequestProblem: {
        "msg": "The request is malformed.",
        "status_code": 400,
    },
    BadRequest: {
        "msg": "The request is malformed.",
        "status_code": 400,
    },
    ExtraParameterProblem: {
        "msg": "The request is malformed.",
        "status_code": 400,
    },
    Unauthorized: {
        "msg": " The request is unauthorized.",
        "status_code": 401,
    },
    Forbidden: {
        "msg": "The requester is not authorized to perform this action.",
        "status_code": 403,
    },
    NotFound: {
        "msg": "The requested resource wasn't found.",
        "status_code": 404,
    },
    AccessMethodNotFound: {
        "msg": "The requested access method wasn't found.",
        "status_code": 404,
    },
    AccessMethodNotDeleted: {
        "msg": "Refusing to delete the last remaining access method.",
        "status_code": 409,
    },
    ObjectNotFound: {
        "msg": "The requested `DrsObject` wasn't found.",
        "status_code": 404,
    },
    URLNotFound: {
        "msg": "The requested access URL wasn't found.",
        "status_code": 404,
    },
    InternalServerError: {
        "msg": "An unexpected error occurred",
        "status_code": 500,
    },
}
