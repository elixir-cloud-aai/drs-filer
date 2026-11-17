"""App tests of the access method endpoints (`/objects/{id}/access/{id}`)."""

from typing import Any
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient
from pymongo.collection import Collection
from pymongo.results import UpdateResult

from drs_filer.ga4gh.drs import server
from tests.mock_data import API, body, drs_object


def _register(client: FlaskClient, access_methods: int) -> tuple[str, list[str]]:
    """Register an object.

    Args:
        client: Test client.
        access_methods: Number of access methods of the object.

    Returns:
        Identifier of the object, and those of its access methods.
    """
    object_id = body(client.post(f"{API}/objects", json=drs_object(access_methods)))
    obj = body(client.get(f"{API}/objects/{object_id}"))
    return object_id, [method["access_id"] for method in obj["access_methods"]]


def test_get_access_url(client: FlaskClient) -> None:
    """The access URL of an access method is returned."""
    object_id, access_ids = _register(client, access_methods=2)
    response = client.get(f"{API}/objects/{object_id}/access/{access_ids[1]}")
    assert response.status_code == 200
    assert body(response) == {
        "headers": [],
        "url": "https://storage.example.org/data/object-1.bam",
    }


def test_get_access_url_object_not_found(client: FlaskClient) -> None:
    """The access URL of an unknown object is not found."""
    response = client.get(f"{API}/objects/unknown/access/unknown")
    assert response.status_code == 404
    assert body(response)["msg"] == "The requested `DrsObject` wasn't found."


def test_get_access_url_not_found(client: FlaskClient) -> None:
    """An unknown access method has no access URL."""
    object_id, _ = _register(client, access_methods=1)
    response = client.get(f"{API}/objects/{object_id}/access/unknown")
    assert response.status_code == 404
    assert body(response)["msg"] == "The requested access URL wasn't found."


def test_get_access_url_invalid_parameter(client: FlaskClient) -> None:
    """Unknown query parameters are rejected (strict validation)."""
    object_id, access_ids = _register(client, access_methods=1)
    response = client.get(f"{API}/objects/{object_id}/access/{access_ids[0]}?unknown=1")
    assert response.status_code == 400


def test_get_access_url_duplicate_ids(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """Access methods with the same identifier are a server error."""
    object_id, access_ids = _register(client, access_methods=2)
    objects.update_one(
        {"id": object_id},
        {"$set": {"access_methods.1.access_id": access_ids[0]}},
    )
    response = client.get(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 500


def test_get_access_url_no_access_methods(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """An object stored without access methods is a server error."""
    object_id, access_ids = _register(client, access_methods=1)
    objects.update_one({"id": object_id}, {"$unset": {"access_methods": ""}})
    response = client.get(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 500


def test_delete_access_method(client: FlaskClient) -> None:
    """A deleted access method is gone; the others stay."""
    object_id, access_ids = _register(client, access_methods=2)
    response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 200
    assert body(response) == access_ids[0]
    obj = body(client.get(f"{API}/objects/{object_id}"))
    assert [method["access_id"] for method in obj["access_methods"]] == [access_ids[1]]


def test_delete_access_method_last(client: FlaskClient) -> None:
    """The last access method of an object is not deleted."""
    object_id, access_ids = _register(client, access_methods=1)
    response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 409
    obj = body(client.get(f"{API}/objects/{object_id}"))
    assert len(obj["access_methods"]) == 1


def test_delete_access_method_not_found(client: FlaskClient) -> None:
    """Deleting an unknown access method fails."""
    object_id, _ = _register(client, access_methods=2)
    response = client.delete(f"{API}/objects/{object_id}/access/unknown")
    assert response.status_code == 404
    assert body(response)["msg"] == "The requested access method wasn't found."


def test_delete_access_method_object_not_found(client: FlaskClient) -> None:
    """Deleting an access method of an unknown object fails."""
    response = client.delete(f"{API}/objects/unknown/access/unknown")
    assert response.status_code == 404


def test_delete_access_method_invalid_parameter(client: FlaskClient) -> None:
    """Unknown query parameters are rejected (strict validation)."""
    response = client.delete(f"{API}/objects/unknown/access/unknown?unknown=1")
    assert response.status_code == 400


def test_delete_access_method_not_modified(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """If the database modifies nothing, the deletion is a server error."""
    object_id, access_ids = _register(client, access_methods=2)
    collection = MagicMock(wraps=objects)
    collection.update_one.return_value = UpdateResult(
        {"n": 1, "nModified": 0}, acknowledged=True
    )
    with patch.object(server, "get_collection", return_value=collection):
        response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 500


def test_delete_access_method_duplicate_ids(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """An ID that all access methods share is not deleted; all of them stay."""
    object_id, access_ids = _register(client, access_methods=2)
    objects.update_one(
        {"id": object_id},
        {"$set": {"access_methods.1.access_id": access_ids[0]}},
    )
    response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 409
    obj = objects.find_one({"id": object_id})
    assert obj is not None
    assert len(obj["access_methods"]) == 2


def test_delete_access_method_no_access_methods(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """Deleting from an object stored without access methods is a server error."""
    object_id, access_ids = _register(client, access_methods=1)
    objects.update_one({"id": object_id}, {"$unset": {"access_methods": ""}})
    response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 500


def test_delete_access_method_other_without_id(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """An access method is deleted if another one, without an ID, stays."""
    object_id, access_ids = _register(client, access_methods=2)
    objects.update_one(
        {"id": object_id}, {"$unset": {"access_methods.1.access_id": ""}}
    )
    response = client.delete(f"{API}/objects/{object_id}/access/{access_ids[0]}")
    assert response.status_code == 200
    obj = objects.find_one({"id": object_id})
    assert obj is not None
    # The requested method is gone; the one without an ID stays
    assert len(obj["access_methods"]) == 1
    assert "access_id" not in obj["access_methods"][0]
