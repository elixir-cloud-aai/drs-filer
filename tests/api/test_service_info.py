"""App tests of the service info endpoints (`/service-info`)."""

from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import yaml

from drs_filer.app import CONFIG_FILE, create_app
from drs_filer.ga4gh.drs.endpoints import service_info as service_info_module
from tests.mock_data import API, DRS_SERVICE_FIELDS, SERVICE_INFO, body


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
    """Posted service info replaces that of the config."""
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert response.headers["Content-Type"] == "application/json"
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == {**SERVICE_INFO, **DRS_SERVICE_FIELDS}


def test_get_service_info_after_restart(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """After a restart, the service info of the config is served again.

    Posted service info (here with another `id`) is served until then.
    """
    client = create_app().app.test_client()
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert body(client.get(f"{API}/service-info")) == {
        **SERVICE_INFO,
        **DRS_SERVICE_FIELDS,
    }
    client = create_app().app.test_client()
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
    client = create_app().app.test_client()
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
    client = create_app().app.test_client()
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
