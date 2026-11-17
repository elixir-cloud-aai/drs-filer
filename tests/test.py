"""Integration tests against a running drs-filer instance."""

from collections.abc import Iterator
import os
import time
from typing import Any, NoReturn

import pytest
import requests

DRS_FILER_URL = os.getenv("DRS_FILER_URL", "http://localhost:8080/ga4gh/drs/v1")
TIMEOUT = 30  # seconds per request


@pytest.fixture(scope="function")
def get_object_id() -> Iterator[str | None]:
    """Create an object and return its identifier."""
    yield test_create_object()


@pytest.fixture(scope="function")
def get_access_id(get_object_id: str) -> Iterator[str]:
    """Return the access ID of the object's first access method."""
    obj = test_get_object(get_object_id)
    assert obj is not None
    yield obj["access_methods"][0]["access_id"]


def handle_error(response: requests.Response) -> NoReturn:
    """Helper function to handle common error cases."""
    if response.status_code == 400:
        pytest.fail("Bad Request: The server could not understand the request.")
    elif response.status_code == 401:
        pytest.fail("Unauthorized: Access is denied due to invalid credentials.")
    elif response.status_code == 403:
        pytest.fail(
            "Forbidden: The server understood the request, but refuses to authorize it."
        )
    elif response.status_code == 404:
        pytest.fail("Not Found: The requested resource could not be found.")
    elif response.status_code == 409:
        pytest.fail(
            "Conflict: The request could not be completed due to a conflict with the "
            "current state of the target resource."
        )
    elif response.status_code == 500:
        pytest.fail("Internal Server Error")
    else:
        pytest.fail(
            f"Unexpected Status Code: {response.status_code} - "
            f"{response.json().get('msg')}"
        )


def object_exists(object_id: str) -> bool:
    """Return whether the object with the given ID exists."""
    try:
        obj = test_get_object(object_id)
        return obj is not None
    except Exception:
        return False


def check_access_exists(object_id: str, access_id: str) -> bool:
    """Return whether the given access method of an object exists."""
    response = requests.get(f"{DRS_FILER_URL}/objects/{object_id}", timeout=TIMEOUT)
    # Any other answer (e.g., 202 for a delayed lookup) proves nothing
    assert response.status_code == 200, response.status_code
    access_methods = response.json().get("access_methods", [])
    return any(method.get("access_id") == access_id for method in access_methods)


def test_create_object() -> str | None:
    """Test creating an object."""
    data = {
        "access_methods": [
            {
                "access_url": {"headers": [], "url": "http://example.com/data"},
                "region": "us-east-1",
                "type": "s3",
            }
        ],
        "aliases": ["example_alias"],
        "checksums": [{"checksum": "abc123", "type": "sha-256"}],
        "contents": [],
        "created_time": "2024-06-12T12:58:19Z",
        "description": "An example object",
        "mime_type": "application/json",
        "name": "example_object",
        "size": 1024,
        "updated_time": "2024-06-12T12:58:19Z",
        "version": "1.0",
    }

    response = requests.post(f"{DRS_FILER_URL}/objects", json=data, timeout=TIMEOUT)
    assert response.status_code == 200

    if response.status_code == 200:
        object_id = response.json()
        return object_id
    else:
        handle_error(response)
        return None


def test_get_objects() -> None:
    """Test listing objects."""
    response = requests.get(f"{DRS_FILER_URL}/objects", timeout=TIMEOUT)
    assert response.status_code == 200
    objects = response.json()
    assert isinstance(objects, list)
    assert len(objects) > 0


def test_get_object(
    get_object_id: str, max_retries: int = 5, retry_count: int = 0
) -> dict[str, Any] | None:
    """Test getting an object, retrying while the server answers 202."""
    object_id = get_object_id

    response = requests.get(f"{DRS_FILER_URL}/objects/{object_id}", timeout=TIMEOUT)
    assert response.status_code in (200, 202)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 202:
        if retry_count < max_retries:
            retry_after = int(response.headers.get("Retry-After", 5))
            print(
                f"Accepted: Operation is delayed. Retry after {retry_after} seconds. "
                f"Retry count: {retry_count + 1}"
            )
            time.sleep(retry_after)
            return test_get_object(object_id, max_retries, retry_count + 1)
        else:
            print(f"Maximum retry limit reached ({max_retries}).")
            handle_error(response)
            return None
    else:
        handle_error(response)
        return None


def test_get_object_access(get_object_id: str, get_access_id: str) -> None:
    """Test getting an access URL of an object."""
    object_id = get_object_id
    access_id = get_access_id
    assert object_id is not None, "Object ID should not be None"
    assert access_id is not None, "Access ID should not be None"

    response = requests.get(
        f"{DRS_FILER_URL}/objects/{object_id}/access/{access_id}", timeout=TIMEOUT
    )

    if response.status_code == 200:
        print(
            f"Following is the object retrieved based on {object_id} and {access_id}:"
        )
        print(response.json())
    elif response.status_code == 202:
        retry_after = int(response.headers.get("Retry-After", 5))
        print(f"202 Accepted: Operation is delayed. Retry after {retry_after} seconds.")
        time.sleep(retry_after)
        return test_get_object_access(object_id, access_id)  # Retry the request
    else:
        handle_error(response)


def test_update_object(get_object_id: str) -> None:
    """Test updating an object."""
    object_id = get_object_id

    data = {
        "access_methods": [
            {
                "access_url": {"headers": ["string"], "url": "string"},
                "region": "us-east-1",
                "type": "s3",
            },
            {
                "access_url": {"headers": ["string"], "url": "string"},
                "region": "us-east-2",
                "type": "s3",
            },
        ],
        "aliases": ["string"],
        "checksums": [{"checksum": "string", "type": "sha-256"}],
        "contents": [
            {
                "contents": [],
                "drs_uri": [
                    "drs://drs.example.org/314159",
                    "drs://drs.example.org/213512",
                ],
                "id": "string",
                "name": "string",
            }
        ],
        "created_time": "2024-07-03T14:16:59.268Z",
        "description": "string",
        "mime_type": "application/json",
        "name": "string",
        "size": 0,
        "updated_time": "2024-07-03T14:16:59.268Z",
        "version": "string",
    }

    response = requests.put(
        f"{DRS_FILER_URL}/objects/{object_id}", json=data, timeout=TIMEOUT
    )
    assert response.status_code == 200
    object_id = get_object_id

    if response.status_code == 200:
        print(f"Updated the object with ID: {object_id}")
    else:
        handle_error(response)


def test_delete_object_access(get_object_id: str, get_access_id: str) -> None:
    """Test deleting an access method of an object."""
    object_id = get_object_id
    access_id = get_access_id

    response = requests.delete(
        f"{DRS_FILER_URL}/objects/{object_id}/access/{access_id}",
        timeout=TIMEOUT,
    )
    assert response.status_code in (200, 409)
    assert (
        response.status_code == 200 and not check_access_exists(object_id, access_id)
    ) or response.status_code == 409

    if response.status_code == 404:
        print(f"Object with ID {object_id} or access ID {access_id} not found.")
    elif response.status_code == 409:
        print(
            f"Refusing to delete the last remaining access method for object "
            f"{object_id}."
        )
    elif response.status_code == 200:
        print(f"Deleted access method with ID {access_id} for object {object_id}.")
    else:
        handle_error(response)


def test_delete_object(get_object_id: str) -> None:
    """Test deleting an object."""
    object_id = get_object_id

    response = requests.delete(f"{DRS_FILER_URL}/objects/{object_id}", timeout=TIMEOUT)
    assert response.status_code == 200
    assert not object_exists(object_id)

    if response.status_code == 200:
        print(f"Deleted the object with ID: {object_id}")
    else:
        handle_error(response)


def test_post_service_info() -> None:
    """Test setting the service info."""
    data = {
        "contactUrl": "mailto:support@example.com",
        "createdAt": "2024-06-12T12:58:19Z",
        "description": "This service provides...",
        "documentationUrl": "https://docs.myservice.example.com",
        "environment": "test",
        "id": "org.ga4gh.myservice",
        "name": "My project",
        "organization": {"name": "My organization", "url": "https://example.com"},
        "type": {"artifact": "beacon", "group": "org.ga4gh", "version": "1.0.0"},
        "updatedAt": "2024-06-12T12:58:19Z",
        "version": "1.0.0",
    }

    response = requests.post(
        f"{DRS_FILER_URL}/service-info", json=data, timeout=TIMEOUT
    )
    assert response.status_code == 201

    if response.status_code == 201:
        print("Service info was successfully created.")
    else:
        handle_error(response)


def test_get_service_info() -> None:
    """Test getting the service info."""
    response = requests.get(f"{DRS_FILER_URL}/service-info", timeout=TIMEOUT)
    assert response.status_code == 200
    service_info = response.json()
    assert "name" in service_info
    assert "version" in service_info
    assert "description" in service_info
    assert "contactUrl" in service_info
