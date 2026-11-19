"""App tests of the pages of the object list (`GET /objects`).

Pages have at most `pageSize` objects (by default
`custom.objects.list.default_page_size`, at most
`custom.objects.list.max_page_size`), newest first, and a `nextPageToken`
for the next page, unless they are the last one.
"""

from pathlib import Path
from typing import Any

from flask.testing import FlaskClient
from jsonschema import Draft4Validator
import pytest
import yaml

from drs_filer.app import create_app
from drs_filer.ga4gh.drs.server import PAGE_TOKEN
from tests.conftest import admin_client
from tests.mock_data import API, body, drs_object, validate_error


def _register(client: FlaskClient, count: int) -> list[str]:
    """Register objects, one after the other.

    Args:
        client: Test client.
        count: Number of objects.

    Returns:
        Identifiers of the objects, in the order of their registration.
    """
    ids = []
    for _ in range(count):
        response = client.post(f"{API}/objects/register", json=drs_object())
        assert response.status_code == 200, body(response)
        ids.append(body(response))
    return ids


def _page(client: FlaskClient, **params: Any) -> dict[str, Any]:
    """Get a page of the object list.

    Args:
        client: Test client.
        **params: Query parameters.

    Returns:
        The page.
    """
    response = client.get(f"{API}/objects", query_string=params)
    assert response.status_code == 200, body(response)
    page: dict[str, Any] = body(response)
    return page


def _all_pages(client: FlaskClient, page_size: int) -> list[list[str]]:
    """Get the identifiers of the objects of all pages of the list.

    Args:
        client: Test client.
        page_size: Page size.

    Returns:
        Identifiers of the objects of each page.
    """
    pages = []
    params: dict[str, Any] = {"pageSize": page_size}
    while True:
        page = _page(client, **params)
        pages.append([obj["id"] for obj in page["objects"]])
        if "nextPageToken" not in page:
            return pages
        params["pageToken"] = page["nextPageToken"]


def _client_with(overlay: Path, **settings: int) -> FlaskClient:
    """Get an admin's test client of an app with settings of the list.

    Args:
        overlay: Config overlay.
        **settings: Settings of `custom.objects.list`.

    Returns:
        Test client.
    """
    overlay.write_text(yaml.safe_dump({"custom": {"objects": {"list": settings}}}))
    return admin_client(create_app())


def test_list_empty(client: FlaskClient) -> None:
    """Without objects, the only page is empty, without a next page."""
    assert _page(client) == {"objects": []}


def test_pages(client: FlaskClient) -> None:
    """The pages have all objects once, newest first; the last has no token."""
    ids = _register(client, 5)
    assert _all_pages(client, 2) == [ids[:2:-1], ids[2:0:-1], ids[:1]]


def test_page_size_exact(client: FlaskClient) -> None:
    """A full last page has no token, so there is no empty page after it."""
    ids = _register(client, 4)
    assert _all_pages(client, 2) == [ids[:1:-1], ids[1::-1]]


def test_page_schema(client: FlaskClient) -> None:
    """Pages conform to `DrsObjectPage` of the served specification.

    Connexion doesn't validate responses, so the test does, with the JSON
    Schema draft of OpenAPI 3.0 (draft 4, as Connexion validates requests).
    """
    _register(client, 3)
    components = body(client.get(f"{API}/openapi.json"))["components"]
    validator = Draft4Validator(
        {"$ref": "#/components/schemas/DrsObjectPage", "components": components}
    )
    for page in (_page(client, pageSize=2), _page(client)):
        errors = [error.message for error in validator.iter_errors(page)]
        assert not errors, errors


def test_page_token_pattern(client: FlaskClient) -> None:
    """The controller checks tokens by the pattern of the specification."""
    spec = body(client.get(f"{API}/openapi.json"))
    (token,) = [
        param
        for param in spec["paths"]["/objects"]["get"]["parameters"]
        if param["name"] == "pageToken"
    ]
    assert token["schema"]["pattern"] == f"^{PAGE_TOKEN.pattern}$"


def test_pages_served_objects(client: FlaskClient) -> None:
    """Objects of pages are served as by `GET /objects/{object_id}`."""
    (object_id,) = _register(client, 1)
    page = _page(client)
    assert page["objects"] == [body(client.get(f"{API}/objects/{object_id}"))]
    assert "_id" not in page["objects"][0]


def test_new_objects_not_on_later_pages(client: FlaskClient) -> None:
    """Objects registered while paging are not on the next pages.

    They come before the first page (newest first), so that no object of the
    next pages is skipped or listed twice.
    """
    ids = _register(client, 3)
    first = _page(client, pageSize=2)
    new = _register(client, 2)
    second = _page(client, pageSize=2, pageToken=first["nextPageToken"])
    assert [obj["id"] for obj in second["objects"]] == ids[:1]
    assert "nextPageToken" not in second
    assert [obj["id"] for obj in _page(client)["objects"]] == [*new[::-1], *ids[::-1]]


def test_token_of_deleted_object(client: FlaskClient) -> None:
    """The token stays valid when the last object of its page is deleted."""
    ids = _register(client, 3)
    first = _page(client, pageSize=2)
    assert client.delete(f"{API}/objects/{ids[1]}").status_code == 200
    second = _page(client, pageSize=2, pageToken=first["nextPageToken"])
    assert [obj["id"] for obj in second["objects"]] == ids[:1]


def test_token_of_replaced_object(client: FlaskClient) -> None:
    """Replacing an object (`PUT`) keeps its place in the list."""
    ids = _register(client, 3)
    first = _page(client, pageSize=2)
    response = client.put(f"{API}/objects/{ids[1]}", json=drs_object())
    assert response.status_code == 200
    second = _page(client, pageSize=2, pageToken=first["nextPageToken"])
    assert [obj["id"] for obj in second["objects"]] == ids[:1]
    assert _all_pages(client, 2) == [ids[:0:-1], ids[:1]]


@pytest.mark.usefixtures("mongo_client")
def test_default_page_size(overlay: Path) -> None:
    """Without `pageSize`, pages have the configured default size.

    Args:
        overlay: Config overlay.
    """
    client = _client_with(overlay, default_page_size=2)
    ids = _register(client, 3)
    page = _page(client)
    assert [obj["id"] for obj in page["objects"]] == ids[:0:-1]
    assert "nextPageToken" in page


@pytest.mark.usefixtures("mongo_client")
@pytest.mark.parametrize("page_size", [4, 1000, 2**63, 2**70])
def test_page_size_capped(overlay: Path, page_size: int) -> None:
    """Page sizes above the configured maximum are reduced to it.

    Also sizes beyond the integers of MongoDB (8 bytes), which would
    otherwise fail the query.

    Args:
        overlay: Config overlay.
        page_size: Requested page size.
    """
    client = _client_with(overlay, default_page_size=1, max_page_size=3)
    ids = _register(client, 5)
    page = _page(client, pageSize=page_size)
    assert [obj["id"] for obj in page["objects"]] == ids[:1:-1]
    assert "nextPageToken" in page


@pytest.mark.parametrize("page_size", ["0", "-1", "abc", "1.5", ""])
def test_invalid_page_size(client: FlaskClient, page_size: str) -> None:
    """Page sizes that aren't positive integers are refused.

    Args:
        client: Test client.
        page_size: Invalid page size.
    """
    response = client.get(f"{API}/objects", query_string={"pageSize": page_size})
    assert response.status_code == 400
    problem = body(response)
    validate_error(problem)
    assert [error.get("parameter") for error in problem.get("errors", [])] == [
        "pageSize"
    ]


@pytest.mark.parametrize(
    "token",
    [
        "x",
        "",
        "0123456789abcdef0123456",
        "0123456789abcdef012345678",
        "0123456789ABCDEF01234567",
        "<script>alert(1)</script>",
        "0123456789abcdef01234567\n",
    ],
    ids=["short", "empty", "23-hex", "25-hex", "uppercase", "markup", "newline"],
)
def test_invalid_page_token(client: FlaskClient, token: str) -> None:
    """Malformed page tokens are refused, without echoing them.

    Args:
        client: Test client.
        token: Malformed page token.
    """
    _register(client, 1)
    response = client.get(f"{API}/objects", query_string={"pageToken": token})
    assert response.status_code == 400
    problem = body(response)
    validate_error(problem)
    assert [error.get("parameter") for error in problem.get("errors", [])] == [
        "pageToken"
    ]
    if token:
        assert token not in response.get_data(as_text=True)


def test_unknown_page_token(client: FlaskClient) -> None:
    """A well-formed token that no page gave lists the objects before it.

    Tokens are positions in the list, so one of the past (e.g., of an object
    deleted since) lists the objects registered before it.
    """
    _register(client, 2)
    assert _page(client, pageToken="0" * 24) == {"objects": []}
    assert len(_page(client, pageToken="f" * 24)["objects"]) == 2
