"""App tests of authentication and access control (`docs/access-control.md`).

Writes (registering, replacing and deleting objects and access methods,
posting the service info) need an access token of a trusted issuer, and,
until objects have owners (#95), the role `admin`; reads stay public,
except access URLs (`tests/api/test_login_for_reads.py`).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
from flask.testing import FlaskClient
from pydantic import ValidationError
from pymongo import MongoClient
from pymongo.collection import Collection
import pytest
from werkzeug.test import TestResponse
import yaml

from drs_filer.app import create_app
from tests.conftest import ADMIN, EDITOR, USER, make_headers
from tests.mock_data import ADDITIONS_SPEC, API, SERVICE_INFO, body, drs_object

ROOT = Path(__file__).resolve().parents[2]
NOAUTH_OVERLAY = ROOT / "config.noauth.yaml"
DEV_OVERLAY = ROOT / "config.dev.yaml"
# Write operations of the app: (method, path template), with `{object_id}`
# and `{access_id}` of a registered object
WRITES = [
    ("post", "/objects/register"),
    ("put", "/objects/{object_id}"),
    ("delete", "/objects/{object_id}"),
    ("delete", "/objects/{object_id}/access/{access_id}"),
    ("post", "/service-info"),
]
# Operations with a request body, and the body
BODIES = {
    "/objects/register": drs_object,
    "/objects/{object_id}": drs_object,
    "/service-info": lambda: SERVICE_INFO,
}
# Write operations with a request body
WRITES_WITH_BODY = [(method, path) for method, path in WRITES if path in BODIES]
# Marks the default body of an operation (`BODIES`) in `_request()`
DEFAULT_BODY = object()


def _request(
    client: FlaskClient,
    method: str,
    path: str,
    ids: tuple[str, str],
    json: Any = DEFAULT_BODY,
    headers: dict[str, str] | None = None,
) -> TestResponse:
    """Send a write request, with the body of its operation unless given.

    Args:
        client: Test client.
        method: HTTP method.
        path: Path template (`WRITES`).
        ids: Identifiers of an object and of one of its access methods.
        json: Request body; by default, that of `BODIES` (none for
            operations without a body).
        headers: Request headers.

    Returns:
        Response.
    """
    url = API + path.format(object_id=ids[0], access_id=ids[1])
    if json is DEFAULT_BODY:
        factory: Callable[[], Any] | None = BODIES.get(path)
        json = factory() if factory is not None else None
    send = getattr(client, method)
    return send(url, json=json, headers=headers or {})


@pytest.fixture
def ids(client: FlaskClient) -> tuple[str, str]:
    """An object with two access methods, registered by an admin.

    Args:
        client: Test client with an admin's token.

    Returns:
        Identifiers of the object and of its first access method.
    """
    response = client.post(f"{API}/objects/register", json=drs_object(2))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    obj = body(client.get(f"{API}/objects/{object_id}"))
    return object_id, obj["access_methods"][0]["access_id"]


def _assert_unauthorized(response: TestResponse, invalid: bool = False) -> None:
    """Check a `401` with a Bearer challenge, as problem details.

    Args:
        response: Response.
        invalid: Whether the challenge names an invalid token.
    """
    assert response.status_code == 401, body(response)
    assert body(response)["status"] == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer")
    assert ('error="invalid_token"' in challenge) is invalid


def _snapshot(
    objects: Collection[dict[str, Any]], service_info: Collection[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Get the stored objects and service info, to check that nothing changed.

    Args:
        objects: Collection of the objects.
        service_info: Collection of the service info.

    Returns:
        The objects and the service info records.
    """
    return (
        list(objects.find({}, {"_id": False})),
        list(service_info.find({}, {"_id": False})),
    )


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_write_without_token(
    anonymous_client: FlaskClient,
    objects: Collection[dict[str, Any]],
    service_info: Collection[dict[str, Any]],
    ids: tuple[str, str],
    method: str,
    path: str,
) -> None:
    """Writes without a token are refused (`401`), and change nothing."""
    before = _snapshot(objects, service_info)
    _assert_unauthorized(_request(anonymous_client, method, path, ids))
    assert _snapshot(objects, service_info) == before


@pytest.mark.parametrize(("method", "path"), WRITES_WITH_BODY)
def test_write_without_token_before_validation(
    anonymous_client: FlaskClient, ids: tuple[str, str], method: str, path: str
) -> None:
    """Writes without a token are refused before their body is validated."""
    response = _request(anonymous_client, method, path, ids, json={"invalid": 1})
    _assert_unauthorized(response)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param({"key": rsa.generate_private_key(65537, 2048)}, id="key"),
        pytest.param({"expired": True}, id="expired"),
        pytest.param({"audience": "other-client"}, id="audience"),
        pytest.param({"issuer": "https://other.example.org/"}, id="issuer"),
        pytest.param({"typ": "JWT"}, id="id-token"),
        pytest.param({"typ": None}, id="no-type"),
    ],
)
@pytest.mark.parametrize(("method", "path"), WRITES)
def test_write_with_invalid_token(
    anonymous_client: FlaskClient,
    ids: tuple[str, str],
    method: str,
    path: str,
    token: dict[str, Any],
) -> None:
    """Writes with invalid tokens are refused (`401`, `invalid_token`).

    Tokens of other keys, expired ones, those for other audiences or of
    untrusted issuers, and tokens that aren't access tokens (RFC 9068).
    """
    headers = make_headers(ADMIN, **token)
    response = _request(anonymous_client, method, path, ids, headers=headers)
    _assert_unauthorized(response, invalid=True)


def test_write_with_malformed_token(
    anonymous_client: FlaskClient, ids: tuple[str, str]
) -> None:
    """Writes with a token that isn't a JWT are refused (`401`)."""
    response = _request(
        anonymous_client,
        "post",
        "/objects/register",
        ids,
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    _assert_unauthorized(response, invalid=True)


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_write_by_non_admin(
    anonymous_client: FlaskClient,
    objects: Collection[dict[str, Any]],
    service_info: Collection[dict[str, Any]],
    ids: tuple[str, str],
    method: str,
    path: str,
) -> None:
    """Writes with a valid token of a user who isn't an admin get `403`."""
    before = _snapshot(objects, service_info)
    response = _request(anonymous_client, method, path, ids, headers=make_headers(USER))
    assert response.status_code == 403, body(response)
    assert body(response)["status"] == 403
    assert _snapshot(objects, service_info) == before


def _object(
    objects: Collection[dict[str, Any]], object_id: str
) -> dict[str, Any] | None:
    """Get a stored object.

    Args:
        objects: Collection of the objects.
        object_id: Identifier of the object.

    Returns:
        The object; `None` if there is none.
    """
    return objects.find_one({"id": object_id})


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        (method, path, 201 if path == "/service-info" else 200)
        for method, path in WRITES
    ],
)
def test_write_by_admin(
    client: FlaskClient,
    objects: Collection[dict[str, Any]],
    ids: tuple[str, str],
    method: str,
    path: str,
    status: int,
) -> None:
    """Writes with a valid token of an admin succeed, with their effect."""
    object_id, access_id = ids
    response = _request(client, method, path, ids)
    assert response.status_code == status, body(response)
    stored = _object(objects, object_id)
    if path == "/objects/register":
        assert _object(objects, body(response)) is not None
    elif path == "/service-info":
        assert body(client.get(f"{API}/service-info"))["name"] == SERVICE_INFO["name"]
    elif method == "put":
        assert stored is not None
        assert len(stored["access_methods"]) == 1
    elif path == "/objects/{object_id}":
        assert stored is None
    else:
        assert stored is not None
        assert access_id not in [m["access_id"] for m in stored["access_methods"]]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-jwt"}])
@pytest.mark.parametrize(
    "path",
    [
        "/objects",
        "/objects/{object_id}",
        "/service-info",
        "/openapi.json",
    ],
)
def test_reads_public(
    anonymous_client: FlaskClient,
    ids: tuple[str, str],
    headers: dict[str, str],
    path: str,
) -> None:
    """Reads need no token, and ignore invalid ones.

    Except access URLs, which need a token by default
    (`tests/api/test_login_for_reads.py`).
    """
    url = API + path.format(object_id=ids[0], access_id=ids[1])
    response = anonymous_client.get(url, headers=headers)
    assert response.status_code == 200, body(response)


@pytest.mark.parametrize(
    "path", ["/objects", "/objects/abc", "/objects/abc/access/def", "/objects/access"]
)
def test_passport_posts_without_token(anonymous_client: FlaskClient, path: str) -> None:
    """The passport `POST` operations answer `501` without credentials."""
    response = anonymous_client.post(API + path, json={"passports": ["x"]})
    assert response.status_code == 501


def _docs_example(title: str) -> dict[str, Any]:
    """Get a YAML example of `docs/access-control.md` by its title.

    Args:
        title: Title of the code block (`title="..."`).

    Returns:
        The example.
    """
    text = (ROOT / "docs" / "access-control.md").read_text()
    block = text.split(f'```yaml title="{title}"\n', 1)[1].split("```", 1)[0]
    example: dict[str, Any] = yaml.safe_load(block)
    return example


def test_editors_example(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    objects: Collection[dict[str, Any]],
    service_info: Collection[dict[str, Any]],
) -> None:
    """The editors of the example in the docs can write, but other users not.

    Editors can't post the service info, as no rule of the example allows it.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        objects: Collection of the objects.
        service_info: Collection of the service info.
    """
    overlay.write_text(yaml.safe_dump(_docs_example("editors.yaml")))
    client = create_app().app.test_client()
    editor = make_headers(EDITOR)
    response = client.post(
        f"{API}/objects/register", json=drs_object(2), headers=editor
    )
    assert response.status_code == 200, body(response)
    object_id = body(response)
    obj = body(client.get(f"{API}/objects/{object_id}"))
    access_id = obj["access_methods"][0]["access_id"]
    url = f"{API}/objects/{object_id}"
    response = client.delete(f"{url}/access/{access_id}", headers=editor)
    assert response.status_code == 200, body(response)
    assert client.put(url, json=drs_object(2), headers=editor).status_code == 200
    assert client.delete(url, headers=make_headers(USER)).status_code == 403
    before = list(service_info.find({}, {"_id": False}))
    response = client.post(f"{API}/service-info", json=SERVICE_INFO, headers=editor)
    assert response.status_code == 403
    assert list(service_info.find({}, {"_id": False})) == before
    assert client.delete(url, headers=editor).status_code == 200
    assert objects.count_documents({}) == 0


def test_spec_security() -> None:
    """Writes require the bearer scheme; the specification's default is none.

    The specification allows anonymous requests and basic authentication on
    all operations; the additions replace that with no requirements, so that
    reads are public, and require `BearerAuth` on writes.
    """
    additions = yaml.safe_load(ADDITIONS_SPEC.read_text())
    assert additions["security"] == []
    for method, path in WRITES:
        operation = additions["paths"][path][method]
        assert operation["security"] == [{"BearerAuth": []}], (method, path)


@pytest.mark.parametrize(
    ("security", "match"),
    [
        ({"auth": {"issuers": []}}, "issuer"),
        ({"auth": {"audience": None}}, "audience"),
        ({"access_control": {"group_mapping": None}}, "admin"),
        ({"access_control": {"enforce": False}}, "enforce"),
    ],
)
def test_missing_deployment_settings_fail_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    security: dict[str, Any],
    match: str,
) -> None:
    """The app refuses to start without an issuer, audience or admin group.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        security: Settings of `security` that undo those of the test
            overlay.
        match: Expected part of the error.
    """
    overlay.write_text(yaml.safe_dump({"security": security}))
    with pytest.raises((ValueError, ValidationError), match=match):
        create_app()


def test_noauth_overlay(
    mongo_client: MongoClient[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mock_idp: None,
) -> None:
    """`config.noauth.yaml` (after `config.dev.yaml`) lets anybody write.

    For local development only (see "Running without authentication" in
    `docs/development.md`).

    Args:
        mongo_client: MongoDB client of the app.
        monkeypatch: Fixture to set the overlays with.
        mock_idp: Mock of the identity provider.
    """
    monkeypatch.setenv("FOCA_CONFIG_OVERLAY", f"{DEV_OVERLAY}:{NOAUTH_OVERLAY}")
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects/register", json=drs_object())
    assert response.status_code == 200, body(response)
    object_id = body(response)
    response = client.delete(f"{API}/objects/{object_id}")
    assert response.status_code == 200, body(response)


def test_dev_overlay_refuses_anonymous_writes(
    mongo_client: MongoClient[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mock_idp: None,
) -> None:
    """The Compose overlay starts without an identity provider of its own.

    Writes then need a token of its fictitious issuer.

    Args:
        mongo_client: MongoDB client of the app.
        monkeypatch: Fixture to set the overlays with.
        mock_idp: Mock of the identity provider.
    """
    monkeypatch.setenv("FOCA_CONFIG_OVERLAY", str(DEV_OVERLAY))
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects/register", json=drs_object())
    _assert_unauthorized(response)
    assert client.get(f"{API}/objects").status_code == 200
