"""Unit tests for `RegisterService()` controller."""

from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, call

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
import pytest

from drs_filer.custom_config import CustomConfig
from drs_filer.errors.exceptions import NotFound
from drs_filer.ga4gh.drs.endpoints.service_info import (
    CURRENT_ID,
    RegisterServiceInfo,
)

INDEX_CONFIG: dict[str, Any] = {"keys": [("id", 1)]}
COLLECTION_CONFIG: dict[str, Any] = {
    "indexes": [INDEX_CONFIG],
}
DB_CONFIG: dict[str, Any] = {
    "collections": {
        "objects": COLLECTION_CONFIG,
        "service_info": COLLECTION_CONFIG,
    },
}
MONGO_CONFIG: dict[str, Any] = {
    "host": "mongodb",
    "port": 27017,
    "dbs": {
        "drsStore": DB_CONFIG,
    },
}
SERVICE_INFO_CONFIG: dict[str, Any] = {
    "contactUrl": "mailto:support@example.com",
    "createdAt": "2019-06-04T12:58:19Z",
    "description": "This service provides...",
    "documentationUrl": "https://docs.myservice.example.com",
    "environment": "test",
    "id": "org.ga4gh.myservice",
    "name": "My project",
    "organization": {"name": "My organization", "url": "https://example.com"},
    "type": {"artifact": "beacon", "group": "org.ga4gh", "version": "1.0.0"},
    "updatedAt": "2019-06-04T12:58:19Z",
    "version": "1.0.0",
}
DRS_CONFIG: dict[str, Any] = {"hostname": "drs.example.org"}
# The `Location` of posted service info: a relative reference, resolved
# against the URL that the service info was posted to (`POST
# /service-info`), so that it holds whatever the host, port and path prefix
HEADERS_SERVICE_INFO = {
    "Content-type": "application/json",
    "Location": "service-info",
}


def _sections() -> dict[str, Any]:
    """Get the sections of the config of the tests besides the database.

    Returns:
        The custom config (host name `DRS_CONFIG`) and the service info
        (`SERVICE_INFO_CONFIG`).
    """
    return {
        "custom": CustomConfig.model_validate({"drs": DRS_CONFIG}),
        "service_info": {"service": deepcopy(SERVICE_INFO_CONFIG)},
    }


def test_get_service_info() -> None:
    """Test for getting service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    mock_resp = {**deepcopy(SERVICE_INFO_CONFIG), "_id": CURRENT_ID}
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client.insert_one(
        mock_resp
    )

    with app.app_context():
        assert RegisterServiceInfo().get_service_info() == SERVICE_INFO_CONFIG


def test_get_service_info_na() -> None:
    """Test for getting service info if unavailable."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.app_context(), pytest.raises(NotFound):
        RegisterServiceInfo().get_service_info()


def test_set_service_info_from_config() -> None:
    """Test for setting service info from config."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_set_service_info_from_config_missing() -> None:
    """Without service info in the config, it can't be set from the config."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig.model_validate({"drs": DRS_CONFIG}),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.app_context(), pytest.raises(RuntimeError, match="service_info"):
        RegisterServiceInfo().set_service_info_from_config()


def test__upsert_service_info_conflict() -> None:
    """A record with the same `id`, stored meanwhile, is removed on conflict.

    E.g., by an instance of an earlier version during a rolling update,
    between the removal of other records and the replacement.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    collection = MagicMock()
    collection.replace_one.side_effect = [DuplicateKeyError("id"), None]
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client = collection
    data = deepcopy(SERVICE_INFO_CONFIG)

    with app.app_context():
        RegisterServiceInfo()._upsert_service_info(data=data)
    assert collection.replace_one.call_count == 2
    assert collection.delete_many.call_args_list[-1] == call(
        {"id": data["id"], "_id": {"$ne": CURRENT_ID}}
    )


def test_set_service_info_from_config_skip() -> None:
    """Test for skipping setting service info that is already available."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    mock_resp = {**deepcopy(SERVICE_INFO_CONFIG), "_id": CURRENT_ID}
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client.insert_one(
        mock_resp
    )

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_other_records_not_served_and_removed() -> None:
    """Records other than the current one are neither served nor kept.

    Earlier versions stored one record per service info `id` and served the
    newest; the current record is served, also if older, and setting service
    info removes the others.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    collection: Collection[dict[str, Any]] = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client = collection
    collection.insert_one({**deepcopy(SERVICE_INFO_CONFIG), "_id": CURRENT_ID})
    collection.insert_one({**deepcopy(SERVICE_INFO_CONFIG), "id": "org.example.other"})

    with app.app_context():
        service_info = RegisterServiceInfo()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG
        service_info._upsert_service_info(data=deepcopy(SERVICE_INFO_CONFIG))
        assert [record["_id"] for record in collection.find()] == [CURRENT_ID]


def test_set_service_info_from_app_context() -> None:
    """Test for setting service info from app context."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_app_context(
            data=SERVICE_INFO_CONFIG,
        )
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test__upsert_service_info_insert() -> None:
    """Test for creating service info document in database."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data["contactUrl"]
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG


def test__upsert_service_info_update() -> None:
    """Test for replacing service info document in database."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    mock_resp = {**deepcopy(SERVICE_INFO_CONFIG), "_id": CURRENT_ID}
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client.insert_one(
        mock_resp
    )

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data["contactUrl"]
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG


def test__get_headers() -> None:
    """Test for response headers getter."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        **_sections(),
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        headers = service_info._get_headers()
        assert headers == HEADERS_SERVICE_INFO
