"""Test cases for object registration."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest
from werkzeug.exceptions import InternalServerError

from drs_filer.custom_config import CustomConfig
from drs_filer.ga4gh.drs.endpoints.register_objects import (
    __add_access_ids,
    register_object,
)

data_objects_path = "tests/data_objects.json"
INDEX_CONFIG: dict[str, Any] = {"keys": [("id", 1)]}
COLLECTION_CONFIG: dict[str, Any] = {"indexes": [INDEX_CONFIG]}
DB_CONFIG: dict[str, Any] = {"collections": {"objects": COLLECTION_CONFIG}}
MONGO_CONFIG: dict[str, Any] = {
    "host": "mongodb",
    "port": 27017,
    "dbs": {
        "drsStore": DB_CONFIG,
    },
}
# The app's own config: identifiers of digits, and the public URL
CUSTOM_CONFIG = CustomConfig.model_validate(
    {
        "objects": {"id": {"charset": "0123456789", "length": 6}},
        "access_methods": {"id": {"charset": "0123456789", "length": 6}},
        "service": {
            "url_prefix": "http",
            "external_host": "1.2.3.4",
            "external_port": 8080,
            "api_path": "ga4gh/drs/v1",
        },
    }
)


def test_register_object_literal_id_charset() -> None:
    """Test for registering an object with an ID from a literal charset."""
    app = Flask(__name__)
    custom = CUSTOM_CONFIG.model_copy(deep=True)
    custom.objects.id.charset = "abcdef"
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=custom,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context():
        assert isinstance(register_object(request_data), str)


def test_register_object_invalid_config() -> None:
    """Registering an object fails without the typed custom config."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom={"service": {"url_prefix": "http"}},
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context(), pytest.raises(RuntimeError):
        register_object(request_data)


def test_register_object_exceed_retries() -> None:
    """Test for registering an object when unique ID retries run out."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CUSTOM_CONFIG,
    )
    mock_resp = MagicMock(side_effect=DuplicateKeyError(""))
    app.config.foca.db.dbs["drsStore"].collections["objects"].client = MagicMock()
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client.insert_one = mock_resp

    request_data = {"name": "mock_name", "access_methods": []}
    with app.app_context(), pytest.raises(InternalServerError):
        register_object(data=request_data, retries=3)


def test_add_access_ids() -> None:
    """Access identifiers follow the settings of `custom.access_methods.id`.

    Identifiers are drawn from `0123456789`, with length 6.
    """
    app = Flask(__name__)
    app.config.foca = Config(custom=CUSTOM_CONFIG)
    objects = json.loads(Path(data_objects_path).read_text())
    mock_data = objects[0]["access_methods"]
    with app.app_context():
        res = __add_access_ids(mock_data)
    assert isinstance(res, list)
    access_ids = [method["access_id"] for method in res]
    assert access_ids
    for access_id in access_ids:
        assert len(access_id) == 6
        assert set(access_id) <= set("0123456789")
