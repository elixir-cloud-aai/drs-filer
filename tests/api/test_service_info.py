"""App tests of the service info endpoints (`/service-info`)."""

from typing import Any
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import yaml

from drs_filer.app import CONFIG_FILE
from drs_filer.ga4gh.drs.endpoints import service_info as service_info_module
from tests.mock_data import API, SERVICE_INFO, body


def test_get_service_info_from_config(client: FlaskClient) -> None:
    """The app starts with the service info of its config."""
    expected = yaml.safe_load(CONFIG_FILE.read_text())["endpoints"]["service_info"]
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == expected


def test_post_service_info(client: FlaskClient) -> None:
    """Posted service info replaces that of the config."""
    response = client.post(f"{API}/service-info", json=SERVICE_INFO)
    assert response.status_code == 201
    assert response.headers["Content-Type"] == "application/json"
    response = client.get(f"{API}/service-info")
    assert response.status_code == 200
    assert body(response) == SERVICE_INFO


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
