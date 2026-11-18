"""App tests of the object endpoints (`/objects`, `/objects/{object_id}`)."""

from typing import Any
from unittest.mock import patch

from flask.testing import FlaskClient
from pymongo.collection import Collection
import pytest

from drs_filer.ga4gh.drs.endpoints import register_objects
from tests.mock_data import API, SELF_URI_BASE, body, drs_object, validate_error


def _register(client: FlaskClient, access_methods: int = 1) -> str:
    """Register an object.

    Args:
        client: Test client.
        access_methods: Number of access methods of the object.

    Returns:
        Identifier of the object.
    """
    response = client.post(f"{API}/objects/register", json=drs_object(access_methods))
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
    response = client.post(f"{API}/objects/register", json=request_body)
    assert response.status_code == 400
    problem = body(response)
    assert problem["status"] == 400
    # With the invalid fields (`errors`)
    assert problem["errors"]
    validate_error(problem)


def test_post_object_invalid_timestamp(client: FlaskClient) -> None:
    """An object with a timestamp that isn't RFC 3339 is rejected.

    The formats of the specification (`date-time`) are validated.
    """
    response = client.post(
        f"{API}/objects/register", json={**drs_object(), "created_time": "2024-06-12"}
    )
    assert response.status_code == 400
    problem = body(response)
    assert [error["pointer"] for error in problem["errors"]] == ["#/created_time"]
    validate_error(problem)


def test_post_object_ids_exhausted(client: FlaskClient) -> None:
    """If no unique identifier is found, the request fails."""
    with patch.object(register_objects, "generate_id", return_value="taken"):
        assert client.put(f"{API}/objects/taken", json=drs_object()).status_code == 200
        response = client.post(f"{API}/objects/register", json=drs_object())
    assert response.status_code == 500
    assert body(response)["status"] == 500


def test_post_object_duplicate_access_id(client: FlaskClient) -> None:
    """A duplicate access identifier is drawn again (#121).

    Every access method gets an identifier that is unique within the object.
    Access identifiers are drawn before the object identifier.
    """
    ids = iter(["acc001", "acc001", "acc002", "obj001"])
    with patch.object(
        register_objects, "generate_id", side_effect=lambda **_: next(ids)
    ):
        response = client.post(
            f"{API}/objects/register", json=drs_object(access_methods=2)
        )
    assert response.status_code == 200, body(response)
    assert body(response) == "obj001"
    obj = body(client.get(f"{API}/objects/obj001"))
    assert [method["access_id"] for method in obj["access_methods"]] == [
        "acc001",
        "acc002",
    ]


def test_post_object_access_ids_exhausted(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """If no unique access identifier is found, the request fails (#121).

    The first access method gets "taken"; the second tries 10 times.
    """
    with patch.object(
        register_objects, "generate_id", return_value="taken"
    ) as generate_id:
        response = client.post(
            f"{API}/objects/register", json=drs_object(access_methods=2)
        )
    assert generate_id.call_count == 1 + 10
    assert response.status_code == 500
    assert body(response)["status"] == 500
    assert objects.count_documents({}) == 0


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


def test_get_object_stored_invalid_timestamp(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """A stored object with a timestamp that isn't RFC 3339 is a server error.

    Responses are validated, including formats (`docs/upgrading.md`), e.g.,
    for objects registered before the formats were checked.
    """
    object_id = _register(client)
    objects.update_one({"id": object_id}, {"$set": {"created_time": "2024-06-12"}})
    response = client.get(f"{API}/objects/{object_id}")
    assert response.status_code == 500
    validate_error(body(response))


def test_get_object_not_found(client: FlaskClient) -> None:
    """An unknown object is not found, with problem details (RFC 9457)."""
    response = client.get(f"{API}/objects/unknown")
    assert response.status_code == 404
    assert response.headers["Content-Type"] == "application/problem+json"
    problem = body(response)
    assert problem == {
        "title": "Not found",
        "detail": "The requested `DrsObject` wasn't found.",
        "status": 404,
    }
    validate_error(problem)


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


def test_self_uri_not_stored(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """The `self_uri` is computed when serving, not stored (#97).

    So it follows the configured host name, also for objects registered
    before it changed.
    """
    posted = _register(client)
    client.put(f"{API}/objects/my-object", json=drs_object())
    for object_id in (posted, "my-object"):
        stored = objects.find_one({"id": object_id})
        assert stored is not None
        assert "self_uri" not in stored


@pytest.mark.parametrize(
    "stored",
    [
        {},
        {"self_uri": "http://193.166.24.114:8080/ga4gh/drs/v1/legacy"},
    ],
    ids=["without-self-uri", "http-self-uri"],
)
def test_self_uri_of_stored_objects(
    client: FlaskClient,
    objects: Collection[dict[str, Any]],
    stored: dict[str, Any],
) -> None:
    """Stored objects get the DRS URI of the host, whatever they stored.

    Earlier versions stored an HTTP URL of the configured host as
    `self_uri`; objects stored without one are served with one too (#97).

    Args:
        client: Test client.
        objects: Collection of the objects.
        stored: Stored `self_uri`, if any.
    """
    request_body = drs_object()
    objects.insert_one({**request_body, "id": "legacy", **stored})
    expected = f"{SELF_URI_BASE}/legacy"
    obj = body(client.get(f"{API}/objects/legacy"))
    assert obj["self_uri"] == expected
    assert [obj["self_uri"] for obj in body(client.get(f"{API}/objects"))] == [
        expected
    ]


@pytest.mark.parametrize(
    ("object_id", "path", "encoded"),
    [
        ("a b", "a%20b", "a%20b"),
        ("x:y", "x:y", "x%3Ay"),
        ("ä~.-_", "%C3%A4~.-_", "%C3%A4~.-_"),
    ],
    ids=["space", "colon", "non-ascii"],
)
def test_self_uri_percent_encoded(
    client: FlaskClient, object_id: str, path: str, encoded: str
) -> None:
    """The identifier in `self_uri` is percent-encoded, as DRS requires.

    In hostname-based DRS URIs, the identifier is always percent-encoded
    (so `:` can't occur in them); the unreserved characters of URLs stay.

    Args:
        client: Test client.
        object_id: Identifier of the object.
        path: Identifier in the request path.
        encoded: Identifier in the `self_uri`.
    """
    response = client.put(f"{API}/objects/{path}", json=drs_object())
    assert response.status_code == 200, body(response)
    assert body(response) == object_id
    obj = body(client.get(f"{API}/objects/{path}"))
    assert obj["self_uri"] == f"{SELF_URI_BASE}/{encoded}"
