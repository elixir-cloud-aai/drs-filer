"""Smoke test against a running app, e.g., of the Compose stack.

Skipped unless `DRS_FILER_URL` is set to the base URL of the API, e.g.,
`http://localhost:8080/ga4gh/drs/v1`; network access is allowed for these
tests (see `tests/smoke/conftest.py`). Each test registers the objects it
needs and deletes them again.
"""

from collections.abc import Iterator
import os
from typing import Any

import pytest
import requests

from tests.mock_data import SERVICE_INFO, drs_object

DRS_FILER_URL = os.environ.get("DRS_FILER_URL", "")
TIMEOUT = 30  # seconds per request

pytestmark = pytest.mark.skipif(not DRS_FILER_URL, reason="DRS_FILER_URL not set")


def _url(path: str) -> str:
    """Get the URL of an API path.

    Args:
        path: Path below the base URL, starting with `/`.

    Returns:
        URL.
    """
    return f"{DRS_FILER_URL.rstrip('/')}{path}"


def _get_object(object_id: str) -> requests.Response:
    """Get an object.

    Args:
        object_id: Identifier of the object.

    Returns:
        Response.
    """
    return requests.get(_url(f"/objects/{object_id}"), timeout=TIMEOUT)


@pytest.fixture
def object_id() -> Iterator[str]:
    """Register an object with two access methods, deleted afterwards.

    Yields:
        Identifier of the object.
    """
    response = requests.post(_url("/objects"), json=drs_object(2), timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    object_id: str = response.json()
    yield object_id
    requests.delete(_url(f"/objects/{object_id}"), timeout=TIMEOUT)


@pytest.fixture
def access_ids(object_id: str) -> list[str]:
    """Identifiers of the access methods of the object.

    Args:
        object_id: Identifier of the object.

    Returns:
        Identifiers of the access methods.
    """
    response = _get_object(object_id)
    assert response.status_code == 200, response.text
    return [method["access_id"] for method in response.json()["access_methods"]]


def test_list_objects(object_id: str) -> None:
    """Registered objects are listed."""
    response = requests.get(_url("/objects"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert object_id in [obj["id"] for obj in response.json()]


def test_get_object(object_id: str) -> None:
    """A registered object has its metadata and a self URI."""
    response = _get_object(object_id)
    assert response.status_code == 200
    obj: dict[str, Any] = response.json()
    assert obj["id"] == object_id
    assert obj["self_uri"].endswith(f"/{object_id}")
    assert obj["name"] == drs_object()["name"]


def test_get_object_not_found() -> None:
    """An unknown object is not found."""
    assert _get_object("unknown-object").status_code == 404


def test_get_access_url(object_id: str, access_ids: list[str]) -> None:
    """The access URL of an access method is returned."""
    response = requests.get(
        _url(f"/objects/{object_id}/access/{access_ids[1]}"), timeout=TIMEOUT
    )
    assert response.status_code == 200
    assert response.json() == drs_object(2)["access_methods"][1]["access_url"]


def test_put_object(object_id: str) -> None:
    """An object is replaced."""
    body = drs_object(2)
    body["name"] = "replaced.bam"
    response = requests.put(_url(f"/objects/{object_id}"), json=body, timeout=TIMEOUT)
    assert response.status_code == 200
    assert _get_object(object_id).json()["name"] == "replaced.bam"


def test_delete_access_method(object_id: str, access_ids: list[str]) -> None:
    """An access method is deleted, but not the last one."""
    url = _url(f"/objects/{object_id}/access/{access_ids[0]}")
    response = requests.delete(url, timeout=TIMEOUT)
    assert response.status_code == 200
    methods = _get_object(object_id).json()["access_methods"]
    assert [method["access_id"] for method in methods] == access_ids[1:]
    url = _url(f"/objects/{object_id}/access/{access_ids[1]}")
    assert requests.delete(url, timeout=TIMEOUT).status_code == 409


def test_delete_object(object_id: str) -> None:
    """A deleted object is gone."""
    response = requests.delete(_url(f"/objects/{object_id}"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert _get_object(object_id).status_code == 404


def test_service_info() -> None:
    """Service info is set and returned."""
    response = requests.post(_url("/service-info"), json=SERVICE_INFO, timeout=TIMEOUT)
    assert response.status_code == 201
    response = requests.get(_url("/service-info"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json() == SERVICE_INFO
