"""Test cases for object registration."""

from copy import deepcopy
import json
from pathlib import Path
import string  # noqa: F401
from typing import Any
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest
from werkzeug.exceptions import InternalServerError

from drs_filer.ga4gh.drs.endpoints.register_objects import (
    __add_access_ids,
    generate_id,
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
ENDPOINT_CONFIG: dict[str, Any] = {
    "objects": {"id_charset": "string.digits", "id_length": 6},
    "access_methods": {"id_charset": "string.digits", "id_length": 6},
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 8080,
    "api_path": "ga4gh/drs/v1",
}


def test_register_object_literal_id_charset() -> None:
    """Test for registering an object with an ID from a literal charset."""
    app = Flask(__name__)
    endpoint_config = deepcopy(ENDPOINT_CONFIG)
    endpoint_config["objects"]["id_charset"] = "abcdef"
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=endpoint_config,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context():
        assert isinstance(register_object(request_data), str)


def test_register_object_invalid_config() -> None:
    """Test for registering an object with an invalid endpoint configuration."""
    app = Flask(__name__)
    endpoint_config = deepcopy(ENDPOINT_CONFIG)
    del endpoint_config["url_prefix"]
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=endpoint_config,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context(), pytest.raises(KeyError):
        register_object(request_data)


def test_register_object_exceed_retries() -> None:
    """Test for registering an object when unique ID retries run out."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
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
    """Test for __add_access_ids()."""
    app = Flask(__name__)
    app.config.foca = Config(endpoints=ENDPOINT_CONFIG)
    objects = json.loads(Path(data_objects_path).read_text())
    mock_data = objects[0]["access_methods"]
    with app.app_context():
        res = __add_access_ids(mock_data)
        print(res)
        assert isinstance(res, list)


def test_generate_id() -> None:
    """Test for 'generate_id()'."""
    random_id = generate_id()
    assert isinstance(random_id, str)
