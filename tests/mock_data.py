"""Request bodies and expected values for the app tests."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft4Validator
from werkzeug.test import TestResponse
import yaml

# The package directory, with the base config and the API specifications
PACKAGE_DIR = Path(__file__).parents[1] / "drs_filer"
CONFIG_FILE = PACKAGE_DIR / "config.yaml"
API_DIR = PACKAGE_DIR / "api"
# The vendored DRS specification (DRS 1.5.0)
DRS_SPEC = API_DIR / "20250324.fe25c39.openapi.yaml"
# The app's additions, with the schema of error responses (`Problem`)
ADDITIONS_SPEC = API_DIR / "additions.openapi.yaml"
# Base URL of the API in the test client
API = "/ga4gh/drs/v1"
# Base of the `self_uri` of objects, from the test overlay
# (`tests/config_overlay.yaml`)
SELF_URI_BASE = "https://drs.example.org:443/ga4gh/drs/v1"

_ACCESS_METHOD: dict[str, Any] = {"region": "us-east-1", "type": "https"}
_OBJECT: dict[str, Any] = {
    "aliases": ["object.bam"],
    "checksums": [{"checksum": "e3b0c44298fc1c149afbf4c8996fb924", "type": "md5"}],
    "created_time": "2024-06-12T12:58:19Z",
    "description": "An object of the tests",
    "mime_type": "application/octet-stream",
    "name": "object.bam",
    "size": 1024,
    "updated_time": "2024-06-12T12:58:19Z",
    "version": "1.0",
}


def drs_object(access_methods: int = 1) -> dict[str, Any]:
    """Get a request body to register a DRS object.

    Args:
        access_methods: Number of access methods, each with another URL.

    Returns:
        Request body, a new copy on each call.
    """
    obj = deepcopy(_OBJECT)
    obj["access_methods"] = [
        {
            **deepcopy(_ACCESS_METHOD),
            "access_url": {
                "headers": [],
                "url": f"https://storage.example.org/data/object-{index}.bam",
            },
        }
        for index in range(access_methods)
    ]
    return obj


SERVICE_INFO: dict[str, Any] = {
    "contactUrl": "mailto:support@example.org",
    "createdAt": "2024-06-12T12:58:19Z",
    "description": "DRS-filer of the tests",
    "documentationUrl": "https://docs.example.org",
    "environment": "test",
    "id": "org.example.drs",
    "name": "DRS-filer",
    "organization": {"name": "Example organization", "url": "https://example.org"},
    "type": {"artifact": "drs", "group": "org.ga4gh", "version": "1.5.0"},
    "updatedAt": "2024-06-12T12:58:19Z",
    "version": "1.0.0",
}

# Fields of the service info that the app computes (`DrsService` of DRS
# 1.5.0): bulk requests aren't implemented, so the bulk maximum is the least
# allowed one
DRS_SERVICE_FIELDS: dict[str, Any] = {
    "maxBulkRequestLength": 1,
    "drs": {"maxBulkRequestLength": 1},
}


def body(response: TestResponse) -> Any:
    """Get the JSON body of a response.

    Args:
        response: Response of the test client.

    Returns:
        The decoded JSON body.
    """
    data = response.get_json()
    assert data is not None, response.data
    return data


def error_messages(exc: BaseException) -> str:
    """Get the messages of an exception and of the exceptions that caused it.

    Args:
        exc: Exception.

    Returns:
        The messages, one per line, from the exception to its first cause.
    """
    messages = []
    current: BaseException | None = exc
    while current is not None:
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(messages)


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, e.g., the config or a specification.

    Args:
        path: Path of the file.

    Returns:
        Its content.
    """
    content: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return content


def validate_error(problem: Any) -> None:
    """Check that an error response body conforms to the specification.

    FOCA doesn't validate error responses against the specification, so the
    tests do: against the `Problem` schema of the additions (problem
    details, RFC 9457), with the JSON Schema draft of OpenAPI 3.0 (draft 4,
    as Connexion validates).

    Args:
        problem: Decoded body of an error response.

    Raises:
        AssertionError: The body doesn't conform to `Problem`.
    """
    components = load_yaml(ADDITIONS_SPEC)["components"]
    validator = Draft4Validator(
        {"$ref": "#/components/schemas/Problem", "components": components}
    )
    errors = [error.message for error in validator.iter_errors(problem)]
    assert not errors, errors
