"""Smoke test against a running app, e.g., of the Compose stack.

Skipped unless `DRS_FILER_URL` is set to the base URL of the API, e.g.,
`http://localhost:8080/ga4gh/drs/v1`; network access is allowed for these
tests (see `tests/smoke/conftest.py`). Each test registers the objects it
needs and deletes them again. Writes and access URLs need an access token
of an admin, set in `DRS_FILER_TOKEN`, unless authentication is disabled
(as in CI, with `config.noauth.yaml` or `config.api.specs.drs.disable_auth`
of the chart; see "Running without authentication" in
`docs/development.md`); other reads and the passport operations are sent
without a token.
"""

from collections.abc import Iterator
import os
from typing import Any

import pytest
import requests

from tests.mock_data import SERVICE_INFO, drs_object, drs_service_fields

DRS_FILER_URL = os.environ.get("DRS_FILER_URL", "")
TIMEOUT = 30  # seconds per request
# Session of the writes and of access URLs, with the token of
# `DRS_FILER_TOKEN`, if set
WRITER = requests.Session()
if token := os.environ.get("DRS_FILER_TOKEN", ""):
    WRITER.headers["Authorization"] = f"Bearer {token}"

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
    response = WRITER.post(
        _url("/objects/register"), json=drs_object(2), timeout=TIMEOUT
    )
    assert response.status_code == 200, response.text
    object_id: str = response.json()
    yield object_id
    WRITER.delete(_url(f"/objects/{object_id}"), timeout=TIMEOUT)


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


def _list_objects(
    session: requests.Session | None = None, page_size: int = 50
) -> list[dict[str, Any]]:
    """List all objects, page by page.

    Args:
        session: Session of the requests (e.g., `WRITER`, with a token); by
            default, requests without a token.
        page_size: Number of objects per page.

    Returns:
        Objects of all pages.
    """
    client = session or requests.Session()
    objects: list[dict[str, Any]] = []
    params: dict[str, Any] = {"pageSize": page_size}
    while True:
        response = client.get(_url("/objects"), params=params, timeout=TIMEOUT)
        assert response.status_code == 200, response.text
        page = response.json()
        objects.extend(page["objects"])
        if "nextPageToken" not in page:
            return objects
        params["pageToken"] = page["nextPageToken"]


def test_list_objects(object_id: str) -> None:
    """Registered objects are listed, on pages of one object, too.

    A second object makes sure that the pages of one object are several.
    """
    response = WRITER.post(
        _url("/objects/register"), json=drs_object(), timeout=TIMEOUT
    )
    assert response.status_code == 200, response.text
    other: str = response.json()
    try:
        assert {object_id, other} <= {obj["id"] for obj in _list_objects()}
        objects = _list_objects(page_size=1)
        assert {object_id, other} <= {obj["id"] for obj in objects}
        assert len({obj["id"] for obj in objects}) == len(objects)
    finally:
        WRITER.delete(_url(f"/objects/{other}"), timeout=TIMEOUT)


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
    """The access URL of an access method is returned (with the token)."""
    response = WRITER.get(
        _url(f"/objects/{object_id}/access/{access_ids[1]}"), timeout=TIMEOUT
    )
    assert response.status_code == 200
    assert response.json() == drs_object(2)["access_methods"][1]["access_url"]


def test_put_object(object_id: str) -> None:
    """An object is replaced."""
    body = drs_object(2)
    body["name"] = "replaced.bam"
    response = WRITER.put(_url(f"/objects/{object_id}"), json=body, timeout=TIMEOUT)
    assert response.status_code == 200
    assert _get_object(object_id).json()["name"] == "replaced.bam"


def test_delete_access_method(object_id: str, access_ids: list[str]) -> None:
    """An access method is deleted, but not the last one."""
    url = _url(f"/objects/{object_id}/access/{access_ids[0]}")
    response = WRITER.delete(url, timeout=TIMEOUT)
    assert response.status_code == 200
    methods = _get_object(object_id).json()["access_methods"]
    assert [method["access_id"] for method in methods] == access_ids[1:]
    url = _url(f"/objects/{object_id}/access/{access_ids[1]}")
    assert WRITER.delete(url, timeout=TIMEOUT).status_code == 409


def test_delete_object(object_id: str) -> None:
    """A deleted object is gone."""
    response = WRITER.delete(_url(f"/objects/{object_id}"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert _get_object(object_id).status_code == 404


def test_service_info(object_id: str) -> None:
    """Service info is set and returned, with the stats of the objects.

    The stats are those of the listed objects: their number, and the total
    size of the blobs (objects without `contents`). The object of the
    fixture `object_id` makes sure that there is one, so that the stats
    aren't trivially zero; other tests' objects may be there too. Exact for
    a single Gunicorn worker (as in CI): other workers keep their stats for
    `custom.stats.cache_seconds` after writes. Objects are listed with the
    writer's token, in case reads require login.
    """
    response = WRITER.post(_url("/service-info"), json=SERVICE_INFO, timeout=TIMEOUT)
    assert response.status_code == 201
    objects = _list_objects(WRITER)
    assert object_id in [obj["id"] for obj in objects]
    blobs = [obj["size"] for obj in objects if "contents" not in obj]
    response = requests.get(_url("/service-info"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json() == {
        **SERVICE_INFO,
        **drs_service_fields(len(objects), sum(blobs)),
    }


def test_authorization_info(object_id: str) -> None:
    """The authorization info of objects follows the served specification.

    `BearerAuth` if `GetObject` requires a bearer token in `openapi.json`,
    otherwise `None` (e.g., without authentication, as in CI); never
    passports. Sent without a token, as clients do before they log in.

    Args:
        object_id: Identifier of a registered object.
    """
    spec = requests.get(_url("/openapi.json"), timeout=TIMEOUT).json()
    operation = spec["paths"]["/objects/{object_id}"]["get"]
    security = operation.get("security", spec.get("security")) or []
    need_login = bool(security) and {} not in security
    response = requests.options(_url(f"/objects/{object_id}"), timeout=TIMEOUT)
    assert response.status_code == 200
    info = response.json()
    assert info["drs_object_id"] == object_id
    assert info["supported_types"] == (["BearerAuth"] if need_login else ["None"])
    assert "passport_auth_issuers" not in info
    response = requests.options(
        _url("/objects"), json={"bulk_object_ids": [object_id]}, timeout=TIMEOUT
    )
    assert response.status_code == 200
    assert response.json()["resolved_drs_object"] == [info]


def test_drs_1_5_0() -> None:
    """The app serves DRS 1.5.0; the passport operations answer `501`."""
    response = requests.get(_url("/openapi.json"), timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json()["info"]["version"] == "1.5.0"
    response = requests.post(
        _url("/objects"), json={"bulk_object_ids": ["x"]}, timeout=TIMEOUT
    )
    assert response.status_code == 501
