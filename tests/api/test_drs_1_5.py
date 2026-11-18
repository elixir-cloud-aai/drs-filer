"""App tests of the DRS 1.5.0 specification that the app serves.

The served specification, registration at `POST /objects/register`, the
fields that DRS 1.5 adds, and the operations of the specification that
DRS-Filer doesn't implement (`501 Not Implemented`).
"""

from typing import Any

from flask.testing import FlaskClient
import pytest

from tests.mock_data import API, body, drs_object, validate_error

# Link of the problem details of the passport operations
PASSPORT_DOCS = (
    "https://drs-filer.readthedocs.io/en/latest/api/#passport-post-endpoints"
)

# Passport `POST` operations of DRS 1.5.0, which DRS-Filer doesn't implement:
# path (`{id}` is an object's identifier, `{access}` an access identifier)
# and a valid request body
PASSPORT_REQUESTS: dict[str, tuple[str, dict[str, Any]]] = {
    "PostObject": ("/objects/{id}", {"expand": False, "passports": ["x.y.z"]}),
    "PostAccessURL": ("/objects/{id}/access/{access}", {"passports": ["x.y.z"]}),
    "GetBulkObjects": ("/objects", {"bulk_object_ids": ["{id}"], "passports": []}),
    "GetBulkAccessURL": (
        "/objects/access",
        {"bulk_object_access_ids": [{"bulk_object_id": "{id}"}]},
    ),
}


def _register(client: FlaskClient, request_body: dict[str, Any]) -> dict[str, Any]:
    """Register an object and get it.

    Args:
        client: Test client.
        request_body: Metadata of the object.

    Returns:
        The object, as served.
    """
    response = client.post(f"{API}/objects/register", json=request_body)
    assert response.status_code == 200, body(response)
    response = client.get(f"{API}/objects/{body(response)}")
    assert response.status_code == 200, body(response)
    obj: dict[str, Any] = body(response)
    return obj


def _fill(template: Any, values: dict[str, str]) -> Any:
    """Fill the placeholders of strings in a request body or path.

    Args:
        template: Request body or path, with placeholders such as `{id}`.
        values: Values of the placeholders.

    Returns:
        The request body or path with the values.
    """
    if isinstance(template, str):
        return template.format(**values)
    if isinstance(template, list):
        return [_fill(item, values) for item in template]
    if isinstance(template, dict):
        return {key: _fill(value, values) for key, value in template.items()}
    return template


def test_served_spec_is_drs_1_5_0(client: FlaskClient) -> None:
    """The app serves DRS 1.5.0 as OpenAPI 3, with its own endpoints."""
    response = client.get(f"{API}/openapi.json")
    assert response.status_code == 200
    spec = body(response)
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "DRS-Filer"
    assert spec["info"]["version"] == "1.5.0"
    paths = spec["paths"]
    assert paths["/objects/register"]["post"]["operationId"] == "RegisterObject"
    assert paths["/objects"]["post"]["operationId"] == "GetBulkObjects"
    assert paths["/objects"]["get"]["operationId"] == "ListDrsObjects"
    assert paths["/objects/{object_id}"]["post"]["operationId"] == "PostObject"
    # Errors are problem details
    error = spec["components"]["responses"]["404NotFoundDrsObject"]
    assert error["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Problem"
    }
    assert client.get(f"{API}/ui/").status_code == 200
    assert client.get(f"{API}/swagger.json").status_code == 404


def test_register_old_path(client: FlaskClient) -> None:
    """`POST /objects` doesn't register objects any more.

    It is the bulk read of DRS 1.5 (`GetBulkObjects`), which answers `501`;
    the problem details point to the docs.
    """
    response = client.post(f"{API}/objects", json=drs_object())
    assert response.status_code == 501
    problem = body(response)
    assert PASSPORT_DOCS in problem["detail"]
    assert client.get(f"{API}/objects").get_json() == []


@pytest.mark.parametrize("operation", sorted(PASSPORT_REQUESTS))
def test_passport_operations_not_implemented(
    client: FlaskClient, operation: str
) -> None:
    """The passport `POST` operations answer `501`, with a link to the docs.

    Also for registered objects and access methods, and without credentials.
    """
    obj = _register(client, drs_object())
    values = {"id": obj["id"], "access": obj["access_methods"][0]["access_id"]}
    path, request_body = PASSPORT_REQUESTS[operation]
    response = client.post(
        f"{API}{_fill(path, values)}", json=_fill(request_body, values)
    )
    assert response.status_code == 501, body(response)
    assert response.headers["Content-Type"] == "application/problem+json"
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 501
    assert problem["title"] == "Not implemented"
    assert PASSPORT_DOCS in problem["detail"]


@pytest.mark.parametrize("path", ["/objects/{id}", "/objects"])
def test_options_not_implemented(client: FlaskClient, path: str) -> None:
    """The authorization info of objects (`OPTIONS`) answers `501` (#98)."""
    obj = _register(client, drs_object())
    response = client.options(
        f"{API}{_fill(path, {'id': obj['id']})}",
        json={"bulk_object_ids": [obj["id"]]},
    )
    assert response.status_code == 501, body(response)
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 501
    assert "authorization" in problem["detail"]


def test_register_drs_1_5_fields(client: FlaskClient) -> None:
    """The fields that DRS 1.5 adds to access methods are registered."""
    request_body = drs_object()
    request_body["access_methods"][0].update(cloud="aws", available=False)
    obj = _register(client, request_body)
    method = obj["access_methods"][0]
    assert method["cloud"] == "aws"
    assert method["available"] is False


def test_register_authorizations_rejected(client: FlaskClient) -> None:
    """Access methods can't be registered with authorization info.

    DRS-Filer sets `authorizations` itself, as it sets `access_id`.
    """
    request_body = drs_object()
    request_body["access_methods"][0]["authorizations"] = {"supported_types": ["None"]}
    response = client.post(f"{API}/objects/register", json=request_body)
    assert response.status_code == 400


def test_get_object_expand(client: FlaskClient) -> None:
    """`expand` of DRS is accepted; objects are served as registered."""
    obj = _register(client, drs_object())
    for value in ("true", "false"):
        response = client.get(f"{API}/objects/{obj['id']}?expand={value}")
        assert response.status_code == 200
        assert body(response) == obj
