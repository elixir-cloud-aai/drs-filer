"""Request bodies and expected values for the app tests."""

from copy import deepcopy
from typing import Any

from werkzeug.test import TestResponse

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
    "type": {"artifact": "drs", "group": "org.ga4gh", "version": "1.1.0"},
    "updatedAt": "2024-06-12T12:58:19Z",
    "version": "1.0.0",
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
