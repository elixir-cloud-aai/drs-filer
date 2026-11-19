"""App tests of login for reads ("Requiring login for reads" of the docs).

Access URLs (`GET /objects/{object_id}/access/{access_id}`) need an access
token by default (the patch `api/patches/login-for-access-urls.yaml`, which
the base config applies), and objects are then served without them;
deployments make them public by leaving the patch out, and require login
for the other reads with `api/patches/login-for-reads.yaml`. Any
authenticated user may read, by named rules that overlays can replace.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from flask.testing import FlaskClient
from pymongo import MongoClient
import pytest
from werkzeug.test import TestResponse
import yaml

from drs_filer.app import create_app
from drs_filer.ga4gh.drs import access_urls
from drs_filer.ga4gh.drs.access_urls import CONFIG_KEY
from tests.conftest import ADMIN, READER, USER, admin_client, make_headers
from tests.mock_data import API, CONFIG_FILE, body, drs_object

ROOT = Path(__file__).resolve().parents[2]
PATCHES_DIR = ROOT / "drs_filer" / "api" / "patches"
ACCESS_URLS_PATCH = "api/patches/login-for-access-urls.yaml"
READS_PATCH = "api/patches/login-for-reads.yaml"
# Reads of the API, other than the service info: path templates, with
# `{object_id}` and `{access_id}` of a registered object
OBJECT_READS = ["/objects", "/objects/{object_id}"]
ACCESS_URL = "/objects/{object_id}/access/{access_id}"
# Always public: the service info, the specification and the Swagger UI
PUBLIC = ["/service-info", "/openapi.json", "/ui/"]


def _patches(overlay: Path, patches: list[str]) -> None:
    """Set the patches of the specification in the overlay of a test.

    Args:
        overlay: Config overlay.
        patches: Patches, relative to the directory of the base config.
    """
    overlay.write_text(
        yaml.safe_dump({"api": {"specs": {"drs": {"patches": patches}}}})
    )


def _register(client: FlaskClient) -> tuple[str, str]:
    """Register an object with two access methods, as an admin.

    Args:
        client: Test client.

    Returns:
        Identifiers of the object and of its first access method.
    """
    response = client.post(
        f"{API}/objects/register", json=drs_object(2), headers=make_headers(ADMIN)
    )
    assert response.status_code == 200, body(response)
    object_id = body(response)
    response = client.get(f"{API}/objects/{object_id}", headers=make_headers(ADMIN))
    assert response.status_code == 200, body(response)
    return object_id, body(response)["access_methods"][0]["access_id"]


def _url(path: str, ids: tuple[str, str]) -> str:
    """Get the URL of a path template.

    Args:
        path: Path template.
        ids: Identifiers of an object and of one of its access methods.

    Returns:
        URL.
    """
    return API + path.format(object_id=ids[0], access_id=ids[1])


def _assert_unauthorized(response: TestResponse) -> None:
    """Check a `401` with a Bearer challenge, as problem details.

    Args:
        response: Response.
    """
    assert response.status_code == 401, body(response)
    assert body(response)["status"] == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def _assert_login_required(client: FlaskClient, url: str) -> None:
    """Check that a read needs a token of any user, for `GET` and `HEAD`.

    Args:
        client: Test client without token.
        url: URL of the read.
    """
    _assert_unauthorized(client.get(url))
    assert client.head(url).status_code == 401, url
    for user in (USER, ADMIN):
        response = client.get(url, headers=make_headers(user))
        assert response.status_code == 200, (url, user, body(response))
        # The rules' "GET|HEAD" is matched as `^(GET|HEAD)$` (model.conf)
        assert client.head(url, headers=make_headers(user)).status_code == 200, url


def _access_methods(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Get the access methods of objects.

    Args:
        objects: Objects, as served.

    Returns:
        Their access methods.
    """
    return [method for obj in objects for method in obj["access_methods"]]


def _served_objects(client: FlaskClient, ids: tuple[str, str]) -> list[Any]:
    """Get the object of `ids` and the list of all objects, as a user.

    Args:
        client: Test client.
        ids: Identifiers of an object and of one of its access methods.

    Returns:
        The object, and the objects of the list.
    """
    headers = make_headers(USER)
    obj = body(client.get(_url("/objects/{object_id}", ids), headers=headers))
    return [obj, *body(client.get(f"{API}/objects", headers=headers))]


def test_access_urls_need_login_by_default(app: Any) -> None:
    """Access URLs need a token of any user by default; other reads don't.

    Also for objects and access methods that don't exist, so that their
    existence doesn't show.

    Args:
        app: App of the base config and the test overlay.
    """
    client = app.app.test_client()
    ids = _register(client)
    _assert_login_required(client, _url(ACCESS_URL, ids))
    response = client.get(_url(ACCESS_URL, ids), headers=make_headers(USER))
    assert body(response) == drs_object(2)["access_methods"][0]["access_url"]
    _assert_unauthorized(client.get(_url(ACCESS_URL, ("nothing", "nothing"))))
    response = client.get(
        _url(ACCESS_URL, ids), headers={"Authorization": "Bearer not-a-jwt"}
    )
    _assert_unauthorized(response)
    assert 'error="invalid_token"' in response.headers["WWW-Authenticate"]
    for path in [*OBJECT_READS, *PUBLIC]:
        assert client.get(_url(path, ids)).status_code == 200, path


def test_objects_without_access_urls_by_default(app: Any) -> None:
    """While access URLs need login, objects are served without them.

    Their access methods keep their `access_id`, with which clients get the
    access URL (DRS requires one of `access_url` and `access_id`); objects
    are served without them also to admins, and nothing is changed in the
    database.

    Args:
        app: App of the base config and the test overlay.
    """
    client = app.app.test_client()
    ids = _register(client)
    for headers in ({}, make_headers(USER), make_headers(ADMIN)):
        obj = body(client.get(_url("/objects/{object_id}", ids), headers=headers))
        objects = body(client.get(f"{API}/objects", headers=headers))
        methods = _access_methods([obj, *objects])
        assert len(methods) == 4
        for method in methods:
            assert "access_url" not in method
            assert method["access_id"]
            assert method["type"] == "https"
    response = client.get(_url(ACCESS_URL, ids), headers=make_headers(USER))
    assert response.status_code == 200, body(response)


def test_access_urls_public_without_patch(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Without the patch, access URLs are public, and served with objects.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _patches(overlay, [])
    client = create_app().app.test_client()
    ids = _register(client)
    response = client.get(_url(ACCESS_URL, ids))
    assert response.status_code == 200, body(response)
    assert body(response) == drs_object(2)["access_methods"][0]["access_url"]
    methods = _access_methods(_served_objects(client, ids))
    urls = [method["access_url"] for method in drs_object(2)["access_methods"]]
    assert [method["access_url"] for method in methods] == urls * 2


def test_login_for_reads(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With both patches, all reads need a token of any user.

    The service info, the specification and the Swagger UI stay public.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _patches(overlay, [ACCESS_URLS_PATCH, READS_PATCH])
    client = create_app().app.test_client()
    ids = _register(client)
    for path in [*OBJECT_READS, ACCESS_URL]:
        _assert_login_required(client, _url(path, ids))
    _assert_unauthorized(client.get(_url("/objects/{object_id}", ("nothing", ""))))
    for path in PUBLIC:
        assert client.get(API + path).status_code == 200, path
    for method in _access_methods(_served_objects(client, ids)):
        assert "access_url" not in method


def test_login_for_object_reads_only(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With only the patch for the other reads, access URLs are public.

    Objects are then served with their access URLs, to logged-in users.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _patches(overlay, [READS_PATCH])
    client = create_app().app.test_client()
    ids = _register(client)
    for path in OBJECT_READS:
        _assert_login_required(client, _url(path, ids))
    assert client.get(_url(ACCESS_URL, ids)).status_code == 200
    for method in _access_methods(_served_objects(client, ids)):
        assert "access_url" in method


def test_named_rules(mongo_client: MongoClient[dict[str, Any]], overlay: Path) -> None:
    """Overlays restrict reads by removing or replacing the named rules.

    Admins may still read.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    overlay.write_text(
        yaml.safe_dump(
            {"security": {"access_control": {"policies": {"get-access-urls": None}}}}
        )
    )
    client = create_app().app.test_client()
    ids = _register(client)
    url = _url(ACCESS_URL, ids)
    assert client.get(url, headers=make_headers(USER)).status_code == 403
    assert client.get(url, headers=make_headers(ADMIN)).status_code == 200


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


def test_docs_overlay_examples(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The overlays of the docs have the effects that the docs describe.

    `public-access-urls.yaml` makes access URLs public;
    `login-for-reads.yaml` requires login for all reads; `readers.yaml`, on
    top of it, lets only readers (and admins) read.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    overlay.write_text(yaml.safe_dump(_docs_example("public-access-urls.yaml")))
    client = create_app().app.test_client()
    ids = _register(client)
    assert client.get(_url(ACCESS_URL, ids)).status_code == 200
    overlay.write_text(yaml.safe_dump(_docs_example("login-for-reads.yaml")))
    client = create_app().app.test_client()
    for path in [*OBJECT_READS, ACCESS_URL]:
        _assert_login_required(client, _url(path, ids))
    merged = _docs_example("login-for-reads.yaml")
    merged["security"] = _docs_example("readers.yaml")["security"]
    overlay.write_text(yaml.safe_dump(merged))
    client = create_app().app.test_client()
    for path in [*OBJECT_READS, ACCESS_URL]:
        url = _url(path, ids)
        _assert_unauthorized(client.get(url))
        assert client.get(url, headers=make_headers(USER)).status_code == 403, path
        assert client.get(url, headers=make_headers(READER)).status_code == 200, path
        assert client.head(url, headers=make_headers(READER)).status_code == 200, path
        assert client.get(url, headers=make_headers(ADMIN)).status_code == 200, path
    # Readers can't write
    response = client.delete(
        _url("/objects/{object_id}", ids), headers=make_headers(READER)
    )
    assert response.status_code == 403
    assert admin_client(create_app()).get(_url(ACCESS_URL, ids)).status_code == 200


def _read_operations(spec: dict[str, Any]) -> set[str]:
    """Get the paths of the read (`GET`) operations of a specification.

    Args:
        spec: Specification.

    Returns:
        Paths.
    """
    return {path for path, item in spec["paths"].items() if "get" in item}


def test_patches_cover_reads() -> None:
    """The shipped patches cover each read except the service info, once.

    Each sets the security requirements of its reads to a bearer token
    (`BearerAuth`); the patch for access URLs covers access URLs only.
    Checked against the served paths in the tests above; here against the
    patches and the specification, so that new reads aren't missed.
    """
    config = yaml.safe_load(CONFIG_FILE.read_text())
    reads: set[str] = set()
    for path in config["api"]["specs"]["drs"]["path"]:
        reads |= _read_operations(
            yaml.safe_load((CONFIG_FILE.parent / path).read_text())
        )
    access = yaml.safe_load((PATCHES_DIR / "login-for-access-urls.yaml").read_text())
    other = yaml.safe_load((PATCHES_DIR / "login-for-reads.yaml").read_text())
    assert set(access["paths"]) == {ACCESS_URL}
    assert not set(access["paths"]) & set(other["paths"])
    assert set(access["paths"]) | set(other["paths"]) == reads - {"/service-info"}
    for patch in (access, other):
        assert set(patch) == {"paths"}
        for item in patch["paths"].values():
            assert item == {"get": {"security": [{"BearerAuth": []}]}}


@pytest.mark.parametrize(
    ("patches", "need_login"),
    [([], False), ([ACCESS_URLS_PATCH], True), ([READS_PATCH], False)],
)
def test_access_urls_need_login_flag(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    patches: list[str],
    need_login: bool,
) -> None:
    """The app knows whether access URLs need login, from the patched spec.

    As the specification that it serves says (`openapi.json`, as FOCA
    merged and patched it); logged once on startup, with the messages that
    the docs quote (FOCA's logging config replaces the handlers of `caplog`,
    so the logger is mocked).

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        patches: Patches of the overlay.
        need_login: Whether access URLs need login with these patches.
    """
    _patches(overlay, patches)
    with patch.object(access_urls, "logger") as logger:
        app = create_app()
        client = app.app.test_client()
        assert app.app.config[CONFIG_KEY] is need_login
        spec = body(client.get(f"{API}/openapi.json"))
        operation = spec["paths"][ACCESS_URL]["get"]
        security = operation.get("security", spec.get("security"))
        assert (security == [{"BearerAuth": []}]) is need_login
        client.get(f"{API}/objects")
    expected = "Access URLs need login" if need_login else "Access URLs are public"
    logger.info.assert_called_once()
    message, *args = logger.info.call_args.args
    assert (message % tuple(args)).startswith(expected)


def test_readers_with_default_patches(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With the default patches, the readers' rules restrict access URLs only.

    Objects stay public, as the docs say.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    overlay.write_text(yaml.safe_dump(_docs_example("readers.yaml")))
    client = create_app().app.test_client()
    ids = _register(client)
    url = _url(ACCESS_URL, ids)
    assert client.get(url, headers=make_headers(USER)).status_code == 403
    assert client.get(url, headers=make_headers(READER)).status_code == 200
    for path in OBJECT_READS:
        assert client.get(_url(path, ids)).status_code == 200, path
