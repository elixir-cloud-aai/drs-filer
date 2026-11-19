"""App tests of the authorization info of objects (DRS `OPTIONS`).

`OPTIONS /objects/{object_id}` (`OptionsObject`) and `OPTIONS /objects`
(`OptionsBulkObject`) tell clients how to authorize the reads of objects
(`GetObject`), and the `authorizations` of access methods how to authorize
the reads of their access URLs (`GetAccessURL`). Both follow the security
requirements of the patched specification that the app serves
(`openapi.json`): bearer tokens (`BearerAuth`) of the trusted issuers, or
none (`None`); never passports (`PassportAuth`), which DRS-Filer doesn't
accept.
"""

from pathlib import Path
from typing import Any

from flask.testing import FlaskClient
from pymongo import MongoClient
import pytest
from werkzeug.test import TestResponse
import yaml

from drs_filer.app import create_app
from tests.conftest import ADMIN, ISSUER, USER, make_headers
from tests.mock_data import API, body, drs_object, validate_error

ACCESS_URLS_PATCH = "api/patches/login-for-access-urls.yaml"
READS_PATCH = "api/patches/login-for-reads.yaml"
OBJECT = "/objects/{object_id}"
ACCESS_URL = "/objects/{object_id}/access/{access_id}"
BEARER = {"supported_types": ["BearerAuth"], "bearer_auth_issuers": [ISSUER]}
NONE = {"supported_types": ["None"]}
# The patches of the overlay, and whether the object reads need login with
# them
READ_MODES = [
    pytest.param([ACCESS_URLS_PATCH], False, id="default"),
    pytest.param([ACCESS_URLS_PATCH, READS_PATCH], True, id="login-for-reads"),
    pytest.param([], False, id="public"),
]


def _overlay(overlay: Path, patches: list[str], **custom: Any) -> None:
    """Set the patches of the specification and custom settings of a test.

    Args:
        overlay: Config overlay.
        patches: Patches, relative to the directory of the base config.
        custom: Settings of the section `custom`, merged into those of the
            test overlay.
    """
    config: dict[str, Any] = {"api": {"specs": {"drs": {"patches": patches}}}}
    if custom:
        config["custom"] = custom
    overlay.write_text(yaml.safe_dump(config))


def _client(overlay: Path, patches: list[str], **custom: Any) -> FlaskClient:
    """Get a test client without token, of an app with the given settings.

    Args:
        overlay: Config overlay.
        patches: Patches of the specification.
        custom: Settings of the section `custom`.

    Returns:
        Test client.
    """
    _overlay(overlay, patches, **custom)
    return create_app().app.test_client()


def _register(client: FlaskClient, access_methods: int = 1) -> str:
    """Register an object, as an admin.

    Args:
        client: Test client.
        access_methods: Number of access methods of the object.

    Returns:
        Identifier of the object.
    """
    response = client.post(
        f"{API}/objects/register",
        json=drs_object(access_methods),
        headers=make_headers(ADMIN),
    )
    assert response.status_code == 200, body(response)
    return str(body(response))


def _required(client: FlaskClient, path: str) -> dict[str, Any]:
    """Get what the served specification requires for a `GET` operation.

    As clients see it in `openapi.json`: the authorization info that
    matches the operation's security requirements (or, if it sets none,
    those of the specification).

    Args:
        client: Test client.
        path: Path of the operation.

    Returns:
        `BEARER` if the operation requires a bearer token, `NONE` if it
        requires nothing.
    """
    spec = body(client.get(f"{API}/openapi.json"))
    operation = spec["paths"][path]["get"]
    security = operation.get("security", spec.get("security"))
    if security == [{"BearerAuth": []}]:
        return BEARER
    assert security == [], security
    return NONE


def _options_bulk(client: FlaskClient, ids: Any) -> TestResponse:
    """Request the authorization info of several objects.

    Args:
        client: Test client.
        ids: Value of `bulk_object_ids`.

    Returns:
        Response.
    """
    return client.options(f"{API}/objects", json={"bulk_object_ids": ids})


def _assert_no_passports(data: Any) -> None:
    """Check that a response advertises no passports.

    Args:
        data: JSON body of the response.
    """
    text = str(data)
    assert "PassportAuth" not in text
    assert "passport_auth_issuers" not in text


@pytest.mark.parametrize(("patches", "need_login"), READ_MODES)
def test_options_object(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    patches: list[str],
    need_login: bool,
) -> None:
    """The authorization info of an object is what `GetObject` requires.

    Bearer tokens of the trusted issuers if the object reads need login,
    otherwise none, as the served specification says; for anonymous
    clients, too (the operation is public), and with a token.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        patches: Patches of the specification.
        need_login: Whether the object reads need login with these patches.
    """
    client = _client(overlay, patches)
    object_id = _register(client)
    expected = BEARER if need_login else NONE
    assert _required(client, OBJECT) == expected
    for headers in ({}, make_headers(USER)):
        response = client.options(f"{API}/objects/{object_id}", headers=headers)
        assert response.status_code == 200, body(response)
        assert body(response) == {"drs_object_id": object_id, **expected}
        _assert_no_passports(body(response))


def test_options_object_not_found(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """While object reads are public, unknown objects get `404`.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, [ACCESS_URLS_PATCH])
    response = client.options(f"{API}/objects/nothing")
    assert response.status_code == 404, body(response)
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 404


def test_options_object_login_hides_existence(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """While object reads need login, unknown objects get the same answer.

    So that anonymous clients can't find out which objects exist, which
    they can't read.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, [ACCESS_URLS_PATCH, READS_PATCH])
    response = client.options(f"{API}/objects/nothing")
    assert response.status_code == 200, body(response)
    assert body(response) == {"drs_object_id": "nothing", **BEARER}


@pytest.mark.parametrize(("patches", "need_login"), READ_MODES)
def test_options_bulk(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    patches: list[str],
    need_login: bool,
) -> None:
    """The bulk authorization info lists each requested object once.

    While object reads are public, unknown objects are unresolved (`404`);
    while they need login, all are resolved, so that their existence
    doesn't show.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        patches: Patches of the specification.
        need_login: Whether the object reads need login with these patches.
    """
    client = _client(overlay, patches)
    first, second = _register(client), _register(client)
    expected = BEARER if need_login else NONE
    response = _options_bulk(client, [first, "nothing", second, first])
    assert response.status_code == 200, body(response)
    data = body(response)
    _assert_no_passports(data)
    if need_login:
        assert data == {
            "summary": {"requested": 3, "resolved": 3, "unresolved": 0},
            "unresolved_drs_objects": [],
            "resolved_drs_object": [
                {"drs_object_id": object_id, **expected}
                for object_id in (first, "nothing", second)
            ],
        }
    else:
        assert data == {
            "summary": {"requested": 3, "resolved": 2, "unresolved": 1},
            "unresolved_drs_objects": [{"error_code": 404, "object_ids": ["nothing"]}],
            "resolved_drs_object": [
                {"drs_object_id": object_id, **expected}
                for object_id in (first, second)
            ],
        }


def test_options_bulk_empty(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """An empty bulk request gets an empty answer.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    response = _options_bulk(_client(overlay, [ACCESS_URLS_PATCH]), [])
    assert response.status_code == 200, body(response)
    assert body(response) == {
        "summary": {"requested": 0, "resolved": 0, "unresolved": 0},
        "unresolved_drs_objects": [],
        "resolved_drs_object": [],
    }


def test_options_bulk_without_ids(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Bulk requests without `bulk_object_ids` get `400`, naming the field.

    The specification doesn't require the field, so the app checks it.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, [ACCESS_URLS_PATCH])
    response = client.options(f"{API}/objects", json={})
    assert response.status_code == 400, body(response)
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 400
    assert "`bulk_object_ids`" in problem["detail"]


@pytest.mark.parametrize(
    "request_body",
    [{"bulk_object_ids": None}, {"bulk_object_ids": "a"}, {"bulk_object_ids": [1]}],
)
def test_options_bulk_invalid(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    request_body: dict[str, Any],
) -> None:
    """Bulk requests whose identifiers aren't a list of strings get `400`.

    Rejected by the validation of the request body against the
    specification (`BulkObjectIdNoPassport`), with the invalid fields.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        request_body: Request body.
    """
    client = _client(overlay, [ACCESS_URLS_PATCH])
    response = client.options(f"{API}/objects", json=request_body)
    assert response.status_code == 400, body(response)
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 400
    assert "errors" in problem


@pytest.mark.parametrize(("patches", "need_login"), READ_MODES)
def test_options_bulk_too_large(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    patches: list[str],
    need_login: bool,
) -> None:
    """Bulk requests with more identifiers than the maximum get `413`.

    Counted as sent, duplicates too; the maximum is configurable and served
    in the service info (`maxBulkRequestLength`).

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        patches: Patches of the specification.
        need_login: Whether the object reads need login with these patches.
    """
    client = _client(overlay, patches, bulk={"max_request_length": 2})
    service_info = body(client.get(f"{API}/service-info"))
    assert service_info["maxBulkRequestLength"] == 2
    assert service_info["drs"]["maxBulkRequestLength"] == 2
    assert _options_bulk(client, ["a", "b"]).status_code == 200
    response = _options_bulk(client, ["a", "a", "b"])
    assert response.status_code == 413, body(response)
    problem = body(response)
    validate_error(problem)
    assert problem["status"] == 413
    assert "maxBulkRequestLength" in problem["detail"]


def test_bulk_maximum_default(app: Any) -> None:
    """The bulk maximum is 100 by default.

    Args:
        app: App of the base config and the test overlay.
    """
    client = app.app.test_client()
    assert body(client.get(f"{API}/service-info"))["maxBulkRequestLength"] == 100
    assert _options_bulk(client, [str(index) for index in range(100)]).status_code == (
        200
    )
    response = _options_bulk(client, [str(index) for index in range(101)])
    assert response.status_code == 413


@pytest.mark.parametrize(
    "patches",
    [
        pytest.param([ACCESS_URLS_PATCH], id="default"),
        pytest.param([ACCESS_URLS_PATCH, READS_PATCH], id="login-for-reads"),
        pytest.param([], id="public"),
    ],
)
def test_access_method_authorizations(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path, patches: list[str]
) -> None:
    """Access methods say what their access URLs require.

    As the served specification says for `GetAccessURL`: bearer tokens of
    the trusted issuers while access URLs need login (the default), none if
    they are public; in single and listed objects.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        patches: Patches of the specification.
    """
    client = _client(overlay, patches)
    object_id = _register(client, access_methods=2)
    expected = _required(client, ACCESS_URL)
    assert expected == (BEARER if patches else NONE)
    headers = make_headers(USER)
    obj = body(client.get(f"{API}/objects/{object_id}", headers=headers))
    objects = body(client.get(f"{API}/objects", headers=headers))
    methods = [method for o in (obj, *objects) for method in o["access_methods"]]
    assert len(methods) == 4
    for method in methods:
        assert method["authorizations"] == expected
        _assert_no_passports(method)


def test_options_cors_preflight(app: Any) -> None:
    """CORS preflight requests still get Flask's answer, without a body.

    Args:
        app: App of the base config and the test overlay.
    """
    client = app.app.test_client()
    response = client.options(
        f"{API}/objects",
        headers={
            "Origin": "https://ui.example.org",
            "Access-Control-Request-Method": "OPTIONS",
        },
    )
    assert response.status_code == 200
    assert "OPTIONS" in response.headers["Allow"]
