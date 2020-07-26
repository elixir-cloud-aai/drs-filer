from connexion.exceptions import (
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
    BadRequestProblem
)

from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)


class ObjectNotFound(NotFound):
    """Raised when object with given object identifier was not found."""
    pass


class URLNotFound(NotFound):
    """Raised when Access URL for object was not found."""
    pass


exceptions = {
    Exception: {
        "msg": "An unexpected error occurred.",
        "status_code": '500',
    },
    BadRequestProblem: {
        "msg": "The request is malformed.",
        "status_code": '400',
    },
    BadRequest: {
        "msg": "The request is malformed.",
        "status_code": '400',
    },
    ExtraParameterProblem: {
        "msg": "The request is malformed.",
        "status_code": '400',
    },
    Unauthorized: {
        "msg": " The request is unauthorized.",
        "status_code": '401',
    },
    Forbidden: {
        "msg": "The requester is not authorized to perform this action.",
        "status_code": '403',
    },
    NotFound: {
        "msg": "The requested resource wasn't found.",
        "status_code": '404',
    },
    ObjectNotFound: {
        "msg": "The requested `DrsObject` wasn't found.",
        "status_code": '404',
    },
    URLNotFound: {
        "msg": "The requested access URL wasn't found.",
        "status_code": '404',
    },
    InternalServerError: {
        "msg": "An unexpected error occurred",
        "status_code": '500',
    },
}
