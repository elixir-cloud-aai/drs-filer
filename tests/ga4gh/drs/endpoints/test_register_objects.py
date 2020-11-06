"""Test cases for object registration."""

from copy import deepcopy
import json
import string  # noqa: F401
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import (Config, MongoConfig)
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest
from werkzeug.exceptions import InternalServerError

from drs_filer.ga4gh.drs.endpoints.register_objects import (
    __add_access_ids,
    register_object,
    generate_id,
)

data_objects_path = "tests/data_objects.json"
INDEX_CONFIG = {'keys': [('id', 1)]}
COLLECTION_CONFIG = {'indexes': [INDEX_CONFIG]}
DB_CONFIG = {'collections': {'objects': COLLECTION_CONFIG}}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'drsStore': DB_CONFIG,
    },
}
ENDPOINT_CONFIG = {
    "objects": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
    "access_methods": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 8080,
    "api_path": "ga4gh/drs/v1"
}


def test_register_object_literal_id_charset():
    """Test for registering an object with an auto-generated identifier drawn
    from a literal character set.
    """
    app = Flask(__name__)
    endpoint_config = deepcopy(ENDPOINT_CONFIG)
    endpoint_config['objects']['id_charset'] = 'abcdef'
    app.config['FOCA'] = \
        Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=endpoint_config,
        )
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context():
        assert isinstance(register_object(request_data), str)


def test_register_object_invalid_config():
    """Test for registering an object with an invalid endpoint configuration.
    """
    app = Flask(__name__)
    endpoint_config = deepcopy(ENDPOINT_CONFIG)
    del endpoint_config['url_prefix']
    app.config['FOCA'] = \
        Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=endpoint_config,
        )
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = {"name": "mock_name"}
    with app.app_context():
        with pytest.raises(KeyError):
            register_object(request_data)


def test_register_object_exceed_retries():
    """Test for registering an object; exceed retries for generating a unique
    identifier.
    """
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
    mock_resp = MagicMock(side_effect=DuplicateKeyError(''))
    app.config['FOCA'].db.dbs['drsStore'].collections['objects']. \
        client = MagicMock()
    app.config['FOCA'].db.dbs['drsStore'].collections['objects']. \
        client.insert_one = mock_resp

    request_data = {"name": "mock_name", "access_methods": []}
    with app.app_context():
        with pytest.raises(InternalServerError):
            register_object(data=request_data, retries=3)


def test_add_access_ids():
    """Test for __add_access_ids()."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(endpoints=ENDPOINT_CONFIG)
    objects = json.loads(open(data_objects_path, "r").read())
    mock_data = objects[0]['access_methods']
    with app.app_context():
        res = __add_access_ids(mock_data)
        print(res)
        assert isinstance(res, list)


def test_generate_id():
    """Test for 'generate_id()'."""
    random_id = generate_id()
    assert isinstance(random_id, str)
