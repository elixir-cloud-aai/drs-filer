from drs_filer.ga4gh.drs.endpoints.register_new_objects import (
    register_new_objects, prepare_access_data)
import mongomock
import pytest
import string  # noqa: F401

from pymongo.errors import DuplicateKeyError

from flask import Flask
from foca.models.config import Config, MongoConfig
from unittest.mock import MagicMock
from addict import Dict
import json


INDEX_CONFIG = {
    'keys': [('id', 1)]
}

COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}

DB_CONFIG = {
    'collections': {
        'objects': COLLECTION_CONFIG,
    },
}

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
    }
}

INVALID_ENDPOINT_CONFIG = {
    "object": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
    "access_methods": {
        "id_charset": 'string.digits"',
        "id_length": 6
    }
}

data_objects_path = "tests/data_objects.json"


def test_register_new_object_exception():
    """registerNewObject should raise an exception on INVALID_ENDPOINT_CONFIG.
    """

    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(
            db=MongoConfig(**MONGO_CONFIG), endpoints=INVALID_ENDPOINT_CONFIG
        )
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    request_data = Dict()
    request_data.json = {"name": "mock_name"}
    with app.app_context():
        with pytest.raises(KeyError):
            register_new_objects(request_data)


def test_register_new_object_duplicate_key_error():
    """test registerNewObject for DuplicateKeyError.
    """
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG
        )
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client.insert_one = mock
    request_data = Dict()
    request_data.json = {"name": "mock_name"}
    with app.app_context():
        assert isinstance(register_new_objects(request_data), str)


def test_prepare_access_data():
    """Test for prepare_access_data"""
    app = Flask(__name__)
    app.config['FOCA'] = Config(endpoints=ENDPOINT_CONFIG)
    objects = json.loads(open(data_objects_path, "r").read())
    mock_data = objects[0]
    with app.app_context():
        res = prepare_access_data(mock_data)
        assert isinstance(res, dict)
