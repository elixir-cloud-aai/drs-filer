"""App tests of the service info endpoints (`/service-info`)."""

from importlib.metadata import version
from pathlib import Path
import threading
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urljoin

from connexion import App
from flask.testing import FlaskClient
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import pytest
import yaml

from drs_filer.app import CONFIG_FILE, create_app
from drs_filer.ga4gh.drs import server as server_module
from drs_filer.ga4gh.drs.endpoints import service_info as service_info_module
from tests.conftest import admin_client
from tests.mock_data import (
    API,
    DRS_SERVICE_FIELDS,
    SERVICE_INFO,
    body,
    drs_object,
    drs_service_fields,
)


def _config_service_info() -> dict[str, Any]:
    """Get the service info served from the base config (no overlay sets it).

    The config doesn't set the version: it is that of the package. The app
    adds the DRS fields (`DRS_SERVICE_FIELDS`).

    Returns:
        Service info.
    """
    service: dict[str, Any] = yaml.safe_load(CONFIG_FILE.read_text())["service_info"][
        "service"
    ]
    assert "version" not in service
    return {**service, "version": version("drs-filer"), **DRS_SERVICE_FIELDS}


def test_get_service_info_from_config(client: FlaskClient) -> None:
    """The app starts with the service info of its config."""
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == _config_service_info()


def test_post_service_info(client: FlaskClient) -> None:
    """Posted service info replaces that of the config.

    Its `Location` is a reference relative to the URL it was posted to (the
    same as that of `GET /service-info`), so it needs no public URL in the
    config and holds behind proxies with other hosts, ports or paths.
    """
    url = f"https://drs.example.org:8443/prefix{API}/service-info"
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert response.headers["Content-Type"] == "application/json"
    assert urljoin(url, response.headers["Location"]) == url
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == {**SERVICE_INFO, **DRS_SERVICE_FIELDS}


def test_get_service_info_after_restart(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """After a restart, the service info of the config is served again.

    Posted service info (here with another `id`) is served until then.
    """
    client = admin_client(create_app())
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert body(client.get(f"{API}/service-info")) == {
        **SERVICE_INFO,
        **DRS_SERVICE_FIELDS,
    }
    client = admin_client(create_app())
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == _config_service_info()


def test_get_service_info_from_config_with_stored_records(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    service_info: Collection[dict[str, Any]],
) -> None:
    """On startup, the config's service info replaces all stored records.

    Records stored by earlier versions: an older one with the `id` of the
    config, and a newer one with another `id` and a URL that doesn't conform
    to the specification (served, it would fail the response validation).
    """
    config_info = _config_service_info()
    service_info.insert_one({**config_info, "name": "Old name"})
    service_info.insert_one(
        {**SERVICE_INFO, "id": "org.example.other", "documentationUrl": "docs/abc"}
    )
    client = admin_client(create_app())
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == config_info
    assert [
        record["id"] for record in service_info.find({}, {"_id": False, "id": True})
    ] == [config_info["id"]]


def test_post_service_info_with_stored_records(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    service_info: Collection[dict[str, Any]],
) -> None:
    """Posted service info replaces all stored records, also of another `id`.

    The unique index on `id` doesn't get in the way of a record stored by an
    earlier version with the posted `id`.
    """
    client = admin_client(create_app())
    service_info.insert_one({**SERVICE_INFO, "name": "Old name"})
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert body(client.get(f"{API}/service-info")) == {
        **SERVICE_INFO,
        **DRS_SERVICE_FIELDS,
    }
    assert service_info.count_documents({}) == 1


def test_post_service_info_invalid(client: FlaskClient) -> None:
    """Service info without required fields is rejected."""
    request_body = {key: value for key, value in SERVICE_INFO.items() if key != "id"}
    response = client.post(f"{API}/service-info", json=request_body)
    assert response.status_code == 400


def test_post_service_info_unknown_organization_field(client: FlaskClient) -> None:
    """Service info with an undefined field in `organization` is rejected."""
    organization = {**SERVICE_INFO["organization"], "email": "a@example.org"}
    response = client.post(
        f"{API}/service-info", json={**SERVICE_INFO, "organization": organization}
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "service_type",
    [
        {"group": "org.ga4gh", "artifact": "trs", "version": "1.5.0"},
        {"group": "org.ga4gh", "artifact": "drs", "version": "1.2.0"},
        {"group": "org.example", "artifact": "drs", "version": "1.5.0"},
    ],
)
def test_post_service_info_other_type(
    client: FlaskClient, service_type: dict[str, str]
) -> None:
    """Service info of another type than DRS 1.5.0 is rejected.

    It would describe another API than the one served.
    """
    response = client.post(
        f"{API}/service-info", json={**SERVICE_INFO, "type": service_type}
    )
    assert response.status_code == 400
    assert response.headers["Content-Type"] == "application/problem+json"


def test_post_service_info_invalid_format(client: FlaskClient) -> None:
    """Service info with an invalid URL or timestamp is rejected.

    The formats (`uri`, `date-time`) of the specification are validated; the
    service info of the config must conform to them, too, as responses are
    validated (`test_get_service_info_from_config`).
    """
    for key, value in (("documentationUrl", "docs/abc"), ("createdAt", "2020-01-01")):
        response = client.post(f"{API}/service-info", json={**SERVICE_INFO, key: value})
        assert response.status_code == 400, key


def test_get_service_info_not_found(
    client: FlaskClient, service_info: Collection[dict[str, Any]]
) -> None:
    """Without service info, it is not found."""
    service_info.delete_many({})
    response = client.get(f"{API}/service-info")
    assert response.status_code == 404


def test_post_service_info_database_error(client: FlaskClient) -> None:
    """A failing database is a server error."""
    collection = MagicMock()
    collection.replace_one.side_effect = PyMongoError("down")
    with patch.object(service_info_module, "get_collection", return_value=collection):
        response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 500
    assert body(response)["status"] == 500


def test_post_service_info_drs_fields_rejected(client: FlaskClient) -> None:
    """The DRS fields of the service info can't be posted: the app sets them."""
    for key, value in DRS_SERVICE_FIELDS.items():
        response = client.post(f"{API}/service-info", json={**SERVICE_INFO, key: value})
        assert response.status_code == 400, key


def test_post_service_info_not_drs(client: FlaskClient) -> None:
    """Service info of another type than DRS is rejected.

    `GET /service-info` serves `DrsService`, of type `drs`.
    """
    service_type = {**SERVICE_INFO["type"], "artifact": "trs"}
    response = client.post(
        f"{API}/service-info", json={**SERVICE_INFO, "type": service_type}
    )
    assert response.status_code == 400


def test_get_service_info_drs_fields_computed(
    client: FlaskClient, service_info: Collection[dict[str, Any]]
) -> None:
    """The DRS fields are computed when serving, not stored."""
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    stored = service_info.find_one({}, {"_id": False})
    assert stored is not None
    assert not DRS_SERVICE_FIELDS.keys() & stored.keys()


def _register(client: FlaskClient, request_body: dict[str, Any]) -> str:
    """Register an object.

    Args:
        client: Test client.
        request_body: Metadata of the object.

    Returns:
        The identifier of the object.
    """
    response = client.post(f"{API}/objects/register", json=request_body)
    assert response.status_code == 200, body(response)
    object_id: str = body(response)
    return object_id


def _stats(client: FlaskClient) -> dict[str, Any]:
    """Get the stats of the service info.

    Args:
        client: Test client.

    Returns:
        The `drs` section of the service info.
    """
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200, body(response)
    drs: dict[str, Any] = body(response)["drs"]
    return drs


def test_get_service_info_stats(client: FlaskClient) -> None:
    """The stats of the service info follow the registered objects.

    `drs.objectCount` counts all objects, blobs and bundles;
    `drs.totalObjectSize` adds up the sizes of blobs only: a bundle's size is
    that of its contents, and an object's access methods (mirrors) are
    copies of the same bytes, so neither is counted twice. Replacing and
    deleting objects updates them.
    """
    assert _stats(client) == drs_service_fields(0, 0)["drs"]
    first = _register(client, {**drs_object(), "size": 1024})
    second = _register(client, {**drs_object(access_methods=2), "size": 2048})
    bundle = {**drs_object(), "size": 3072}
    del bundle["access_methods"]
    bundle["contents"] = [
        {"name": "first", "id": first},
        {"name": "second", "id": second},
    ]
    _register(client, bundle)
    assert _stats(client) == drs_service_fields(3, 3072)["drs"]
    response = client.put(f"{API}/objects/{first}", json={**drs_object(), "size": 1})
    assert response.status_code == 200, body(response)
    assert _stats(client) == drs_service_fields(3, 2049)["drs"]
    response = client.delete(f"{API}/objects/{second}")
    assert response.status_code == 200, body(response)
    assert _stats(client) == drs_service_fields(2, 1)["drs"]


def test_get_service_info_stats_large(client: FlaskClient) -> None:
    """Sizes beyond 32 bits are added up exactly (`int64`)."""
    size = 2**40 + 1
    for _ in range(3):
        _register(client, {**drs_object(), "size": size})
    assert _stats(client) == drs_service_fields(3, 3 * size)["drs"]


def test_get_service_info_stats_anonymous(
    client: FlaskClient, anonymous_client: FlaskClient
) -> None:
    """The stats are served with the service info, which is public."""
    _register(client, drs_object())
    assert _stats(anonymous_client) == drs_service_fields(1, 1024)["drs"]


@pytest.mark.parametrize("failing", ["count_documents", "aggregate"])
def test_get_service_info_stats_database_error(
    client: FlaskClient, failing: str
) -> None:
    """A failing database is a server error, also for each query of the stats.

    The other queries succeed: the service info is found, and the other
    query of the stats has a result.
    """
    collection = MagicMock()
    collection.find_one.return_value = dict(SERVICE_INFO)
    collection.count_documents.return_value = 0
    collection.aggregate.return_value = iter([])
    getattr(collection, failing).side_effect = PyMongoError("down")
    with patch.object(service_info_module, "get_collection", return_value=collection):
        response = client.get(f"{API}/service-info")
    assert response.status_code == 500
    assert body(response)["status"] == 500


class _Clock:
    """Clock of the kept stats (`time.monotonic()`), set by the tests.

    Attributes:
        now: The time, in seconds.
    """

    def __init__(self) -> None:
        """Start at 1000 s."""
        self.now = 1000.0

    def monotonic(self) -> float:
        """Get the time.

        Returns:
            The time, in seconds.
        """
        return self.now


def _stats_client(overlay: Path, stats: dict[str, Any]) -> FlaskClient:
    """Create an app with stats settings, and get its test client.

    Args:
        overlay: Config overlay of the test.
        stats: Settings of the stats (`custom.stats`).

    Returns:
        Test client, with an admin's access token.
    """
    overlay.write_text(yaml.safe_dump({"custom": {"stats": stats}}))
    return admin_client(create_app())


def test_get_service_info_stats_kept(
    client: FlaskClient,
    objects: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stats are kept for `cache_seconds` (by default 60 s), per process.

    Objects written by another process (here, straight into the database)
    show once they expire; writes through the app show at once
    (`test_get_service_info_stats`).
    """
    clock = _Clock()
    monkeypatch.setattr(service_info_module, "time", clock)
    assert _stats(client) == drs_service_fields(0, 0)["drs"]
    objects.insert_one({"id": "other", "size": 7})
    clock.now += 59
    assert _stats(client) == drs_service_fields(0, 0)["drs"]
    clock.now += 1
    assert _stats(client) == drs_service_fields(1, 7)["drs"]


def test_get_service_info_stats_not_kept(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    objects: Collection[dict[str, Any]],
) -> None:
    """With `cache_seconds: 0`, the stats are computed for each request."""
    client = _stats_client(overlay, {"cache_seconds": 0})
    assert _stats(client) == drs_service_fields(0, 0)["drs"]
    objects.insert_one({"id": "other", "size": 7})
    assert _stats(client) == drs_service_fields(1, 7)["drs"]


def test_get_service_info_stats_disabled(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With `enabled: false`, the service info has no stats (they're optional).

    The database isn't read for them.
    """
    client = _stats_client(overlay, {"enabled": False})
    _register(client, drs_object())
    with patch.object(service_info_module, "_compute_object_stats") as compute:
        assert _stats(client) == {"maxBulkRequestLength": 1}
    compute.assert_not_called()


def test_get_service_info_stats_failed_write(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """A write that fails after changing objects makes the kept stats stale."""
    assert _stats(client) == drs_service_fields(0, 0)["drs"]

    def fail(**kwargs: Any) -> str:
        """Change objects, then fail.

        Args:
            **kwargs: Arguments of `register_object()`.

        Raises:
            PyMongoError: Always.
        """
        objects.insert_one({"id": "partial", "size": 7})
        raise PyMongoError("down")

    with patch.object(server_module, "register_object", side_effect=fail):
        response = client.post(f"{API}/objects/register", json=drs_object())
    assert response.status_code == 500
    assert _stats(client) == drs_service_fields(1, 7)["drs"]


def test_get_service_info_stats_write_while_computing(
    client: FlaskClient, objects: Collection[dict[str, Any]]
) -> None:
    """Stats computed while a write made them stale aren't kept.

    As with a write of another thread of the process between the queries of
    the stats: the stats served then may miss it, the next ones don't.
    """
    compute = service_info_module._compute_object_stats

    def concurrent_write() -> dict[str, int]:
        """Compute the stats, while another thread writes an object.

        Returns:
            The stats, from before the write.
        """
        stats = compute()
        objects.insert_one({"id": "concurrent", "size": 7})
        service_info_module.invalidate_object_stats()
        return stats

    with patch.object(
        service_info_module, "_compute_object_stats", side_effect=concurrent_write
    ):
        assert _stats(client) == drs_service_fields(0, 0)["drs"]
    assert _stats(client) == drs_service_fields(1, 7)["drs"]


def test_get_service_info_stats_slow(
    client: FlaskClient,
    objects: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stats that take longer than `cache_seconds` to compute are kept too.

    They are kept from the time they were computed.
    """
    clock = _Clock()
    monkeypatch.setattr(service_info_module, "time", clock)
    compute = service_info_module._compute_object_stats

    def slow() -> dict[str, int]:
        """Compute the stats, taking 100 s.

        Returns:
            The stats.
        """
        clock.now += 100
        return compute()

    with patch.object(
        service_info_module, "_compute_object_stats", side_effect=slow
    ) as computed:
        assert _stats(client) == drs_service_fields(0, 0)["drs"]
        objects.insert_one({"id": "other", "size": 7})
        clock.now += 59
        assert _stats(client) == drs_service_fields(0, 0)["drs"]
    assert computed.call_count == 1


def test_get_service_info_stats_computed_once(app: App) -> None:
    """Threads that need the stats while one computes them wait for its stats.

    Only one thread of a process reads all objects at a time.
    """
    started = threading.Event()
    release = threading.Event()
    compute = service_info_module._compute_object_stats
    results: list[dict[str, int]] = []

    def blocking() -> dict[str, int]:
        """Compute the stats once released.

        Returns:
            The stats.
        """
        started.set()
        assert release.wait(10)
        return compute()

    def get_stats() -> None:
        """Get the stats in an app context, as a request would."""
        with app.app.app_context():
            results.append(service_info_module.object_stats())

    with patch.object(
        service_info_module, "_compute_object_stats", side_effect=blocking
    ) as computed:
        threads = [threading.Thread(target=get_stats) for _ in range(3)]
        threads[0].start()
        assert started.wait(10)
        for thread in threads[1:]:
            thread.start()
        release.set()
        for thread in threads:
            thread.join(10)
    assert computed.call_count == 1
    assert results == [{"objectCount": 0, "totalObjectSize": 0}] * 3
