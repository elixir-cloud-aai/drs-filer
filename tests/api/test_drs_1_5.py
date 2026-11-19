"""App tests of the DRS 1.5.0 specification that the app serves.

The served specification, registration at `POST /objects/register`, the
fields that DRS 1.5 adds, and the operations of the specification that
DRS-Filer doesn't implement (`501 Not Implemented`).
"""

import logging
from pathlib import Path
from typing import Any

from flask.testing import FlaskClient
import pytest

from drs_filer.errors.exceptions import DOCS_API_URL, exceptions
from tests.mock_data import API, body, drs_object, validate_error

# The API docs, with the sections that the `501` problem details link to
DOCS_API = Path(__file__).parents[2] / "docs" / "api.md"

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
def test_cors_preflight(client: FlaskClient, path: str) -> None:
    """CORS preflight requests get Flask's answer, not that of `OPTIONS`.

    Not the authorization info of objects: browsers refuse requests whose
    preflight isn't answered with `2xx`, and the preflight of `OPTIONS
    /objects` has no body, which `OptionsBulkObject` requires.
    """
    obj = _register(client, drs_object())
    response = client.options(
        f"{API}{_fill(path, {'id': obj['id']})}",
        headers={
            "Origin": "https://ui.example.org",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response.headers
    assert "OPTIONS" in response.headers["Allow"]


@pytest.mark.parametrize("path", ["/nonexistent", f"{API}/nope"])
def test_cors_preflight_unknown_path(client: FlaskClient, path: str) -> None:
    """CORS preflight requests to unknown paths get `404`, like other ones."""
    response = client.options(
        path,
        headers={
            "Origin": "https://ui.example.org",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize("object_id", ["register", "access"])
def test_object_ids_of_static_paths(client: FlaskClient, object_id: str) -> None:
    """Objects with the identifiers `register` and `access` can be managed.

    `/objects/register` and `/objects/access` have only `POST`, so `GET`,
    `PUT` and `DELETE` reach `/objects/{object_id}` (see "Deviations from
    the specification" in `docs/api.md`).
    """
    response = client.put(f"{API}/objects/{object_id}", json=drs_object())
    assert response.status_code == 200, body(response)
    response = client.get(f"{API}/objects/{object_id}")
    assert response.status_code == 200, body(response)
    assert body(response)["id"] == object_id
    response = client.delete(f"{API}/objects/{object_id}")
    assert response.status_code == 200, body(response)
    response = client.get(f"{API}/objects/{object_id}")
    assert response.status_code == 404


def test_register_drs_1_5_fields(client: FlaskClient) -> None:
    """The fields that DRS 1.5 adds to access methods are registered.

    `cloud`, `region` and `available` (cold storage) are served unchanged,
    also after replacing an object (`PUT`); access methods without them are
    served without them.
    """
    request_body = drs_object(access_methods=2)
    request_body["access_methods"][0].update(
        cloud="aws", region="eu-central-1", available=False
    )
    for field in ("cloud", "region", "available"):
        request_body["access_methods"][1].pop(field, None)
    obj = _register(client, request_body)
    method, other = obj["access_methods"]
    assert method["cloud"] == "aws"
    assert method["region"] == "eu-central-1"
    assert method["available"] is False
    assert not {"cloud", "region", "available"} & other.keys()
    request_body["access_methods"][0].update(
        cloud="gcp", region="europe-west4", available=True
    )
    response = client.put(f"{API}/objects/{obj['id']}", json=request_body)
    assert response.status_code == 200, body(response)
    method = body(client.get(f"{API}/objects/{obj['id']}"))["access_methods"][0]
    assert method["cloud"] == "gcp"
    assert method["region"] == "europe-west4"
    assert method["available"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", "x"), ("self_uri", "drs://drs.example.org/x")],
)
def test_register_server_fields_rejected(
    client: FlaskClient, field: str, value: str
) -> None:
    """Objects can't be registered with the fields that DRS-Filer sets."""
    request_body = {**drs_object(), field: value}
    for response in (
        client.post(f"{API}/objects/register", json=request_body),
        client.put(f"{API}/objects/x", json=request_body),
    ):
        assert response.status_code == 400


@pytest.mark.parametrize(
    ("field", "value"),
    [("access_id", "x"), ("authorizations", {"supported_types": ["None"]})],
)
def test_register_access_method_server_fields_rejected(
    client: FlaskClient, field: str, value: Any
) -> None:
    """Access methods can't be registered with the fields that DRS-Filer sets.

    DRS-Filer sets `authorizations` itself, as it sets `access_id`.
    """
    request_body = drs_object()
    request_body["access_methods"][0][field] = value
    response = client.post(f"{API}/objects/register", json=request_body)
    assert response.status_code == 400


def test_get_object_expand(client: FlaskClient) -> None:
    """`expand` of DRS is accepted; bundles are served as registered."""
    blob = _register(client, drs_object())
    bundle = drs_object(access_methods=0)
    del bundle["access_methods"]
    nested = {"name": "nested", "contents": [{"name": "inner", "id": blob["id"]}]}
    bundle["contents"] = [{"name": "blob", "id": blob["id"]}, nested]
    obj = _register(client, bundle)
    for value in ("true", "false"):
        response = client.get(f"{API}/objects/{obj['id']}?expand={value}")
        assert response.status_code == 200
        assert body(response) == obj
        assert body(response)["contents"] == bundle["contents"]


def test_passports_not_logged(
    client: FlaskClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The passports of requests to passport operations aren't logged.

    Not even at `DEBUG` for valid requests. For malformed request bodies,
    FOCA logs the reason for rejecting them at `DEBUG`, which may quote the
    rejected value, but not at `INFO` and above, the level of the console
    handler of the shipped config.
    """
    passport = "header.passport-marker.signature"
    caplog.set_level(logging.DEBUG)
    response = client.post(f"{API}/objects/x", json={"passports": [passport]})
    assert response.status_code == 501
    assert caplog.records
    assert passport not in caplog.text
    caplog.clear()
    response = client.post(f"{API}/objects", json={"passports": passport})
    assert response.status_code == 400
    logged = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
    assert logged
    assert not [message for message in logged if passport in message]


def test_docs_anchors() -> None:
    """The links of the `501` problem details point to sections of the docs."""
    headings = {
        line.lstrip("#").strip().lower().replace(" ", "-")
        for line in DOCS_API.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    }
    for problem in exceptions.values():
        detail = str(problem["detail"])
        if DOCS_API_URL in detail:
            anchor = detail.split(f"{DOCS_API_URL}#", 1)[1]
            assert anchor in headings, anchor
