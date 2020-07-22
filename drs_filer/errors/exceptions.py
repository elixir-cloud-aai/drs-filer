from connexion.exceptions import (
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
    BadRequestProblem
)

from werkzeug.exceptions import (
    BadRequest,
    BadGateway,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    ServiceUnavailable,
)

exceptions = {
    Exception: {
        "msg": "An unexpected error occurred",
        "status_code": '500',
    },
    BadRequestProblem: {
        "msg": "The request is malformed",
        "status_code": '400',
    },
    BadRequest: {
        "msg": "Bad Request",
        "status_code": '400',
    },
    ExtraParameterProblem: {
        "msg": "Bad Request",
        "status_code": '400',
    },
    Unauthorized: {
        "msg": " The request is unauthorized.",
        "status_code": '401',
    },
    Forbidden: {
        "msg": "The requester is not authorized to perform this action",
        "status_code": '403',
    },
    NotFound: {
        "msg": "The requested `DrsObject` wasn't found",
        "status_code": '404',
    },
    InternalServerError: {
        "msg": "An unexpected error occurred",
        "status_code": '500',
    },
    BadGateway: {
        "msg": "Bad Gateway",
        "status_code": '502',
    },
    ServiceUnavailable: {
        "msg": "Service Unavailable",
        "status_code": '502',
    },
    GatewayTimeout: {
        "msg": "Gateway Timeout",
        "status_code": '504',
    }
}
