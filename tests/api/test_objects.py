"""App tests of the object endpoints (`/objects`, `/objects/{object_id}`)."""

from typing import Any
from unittest.mock import patch

from flask.testing import FlaskClient
from pymongo.collection import Collection

from drs_filer.ga4gh.drs.endpoints import register_objects
from tests.mock_data import API, SELF_URI_BASE, body, drs_object


def _register(client: FlaskClient, access_methods: int = 1) -> str:
    """Register an object.

    Args:
        client: Test client.
        access_methods: Number of access methods of the object.

    Returns:
        Identifier of the object.
    """
    response = client.post(f"{API}/objects", json=drs_object(access_methods))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    assert isinstance(object_id, str)
    return object_id


def test_list_objects_empty(client: FlaskClient) -> None:
    """Without objects, the list is empty."""
    response = client.get(f"{API}/objects")
    assert response.status_code == 200
    assert body(response) == []


def test_list_objects(client: FlaskClient) -> None:
    """Registered objects are listed, without database fields."""
    ids = {_register(client), _register(client)}
    response = client.get(f"{API}/objects")
    assert response.status_code == 200
    assert {obj["id"] for obj in body(response)} == ids
    assert all("_id" not in obj for obj in body(response))


def test_post_object(client: FlaskClient, objects: Collection[dict[str, Any]]) -> None:
    """A posted object gets an identifier, a self URI and access IDs."""
    object_id = _register(client, access_methods=2)
    assert len(object_id) == 6
    response = client.get(f"{API}/objects/{object_id}")
    assert response.status_code == 200
    obj = body(response)
    assert obj["id"] == object_id
    assert obj["self_uri"] == f"{SELF_URI_BASE}/{object_id}"
    access_ids = [method["access_id"] for method in obj["access_methods"]]
    assert len(set(access_ids)) == 2
    assert objects.count_documents({}) == 1


def test_post_object_invalid(client: FlaskClient) -> None:
    """An object without required fields is rejected."""
    request_body = drs_object()
    del request_body["checksums"]
    response = client.post(f"{API}/objects", json=request_body)
    assert response.status_code == 400
    assert body(response)["status_code"] == 400


def test_post_object_ids_exhausted(client: FlaskClient) -> None:
    """If no unique identifier is found, the request fails."""
    with patch.object(register_objects, "generate_id", return_value="taken"):
        assert client.put(f"{API}/objects/taken", json=drs_object()).status_code == 200
        response = client.post(f"{API}/objects", json=drs_object())
    assert response.status_code == 500
    assert body(response)["status_code"] == 500


def test_put_object_new(client: FlaskClient) -> None:
    """An object is registered with the given identifier."""
    response = client.put(f"{API}/objects/my-object", json=drs_object())
    assert response.status_code == 200
    assert body(response) == "my-object"
    obj = body(client.get(f"{API}/objects/my-object"))
    assert obj["self_uri"] == f"{SELF_URI_BASE}/my-object"


def test_put_object_replace(client: FlaskClient) -> None:
    """An existing object is replaced."""
    object_id = _register(client)
    request_body = drs_object()
    request_body["name"] = "replaced.bam"
    response = client.put(f"{API}/objects/{object_id}", json=request_body)
    assert response.status_code == 200
    assert body(response) == object_id
    assert body(client.get(f"{API}/objects/{object_id}"))["name"] == "replaced.bam"
    assert len(body(client.get(f"{API}/objects"))) == 1


def test_put_object_invalid(client: FlaskClient) -> None:
    """An invalid object is rejected."""
    request_body = drs_object()
    request_body["size"] = "large"
    response = client.put(f"{API}/objects/my-object", json=request_body)
    assert response.status_code == 400


def test_get_object_not_found(client: FlaskClient) -> None:
    """An unknown object is not found."""
    response = client.get(f"{API}/objects/unknown")
    assert response.status_code == 404
    assert body(response) == {
        "msg": "The requested `DrsObject` wasn't found.",
        "status_code": 404,
    }


def test_get_object_invalid_parameter(client: FlaskClient) -> None:
    """Unknown query parameters are rejected (strict validation)."""
    object_id = _register(client)
    response = client.get(f"{API}/objects/{object_id}?unknown=1")
    assert response.status_code == 400


def test_delete_object(client: FlaskClient) -> None:
    """A deleted object is gone."""
    object_id = _register(client)
    response = client.delete(f"{API}/objects/{object_id}")
    assert response.status_code == 200
    assert body(response) == object_id
    assert client.get(f"{API}/objects/{object_id}").status_code == 404


def test_delete_object_not_found(client: FlaskClient) -> None:
    """Deleting an unknown object fails."""
    response = client.delete(f"{API}/objects/unknown")
    assert response.status_code == 404


def test_delete_object_invalid_parameter(client: FlaskClient) -> None:
    """Unknown query parameters are rejected (strict validation)."""
    response = client.delete(f"{API}/objects/unknown?unknown=1")
    assert response.status_code == 400
