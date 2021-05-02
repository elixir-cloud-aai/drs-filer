"""Unit tests for `RegisterService()` controller."""

import mongomock
import pytest
import string  # noqa: F401

from copy import deepcopy
from flask import Flask
from foca.models.config import Config, MongoConfig
from pymongo.errors import DuplicateKeyError

from unittest.mock import MagicMock

from drs_filer.ga4gh.drs.endpoints.service_info import (
    RegisterServiceInfo
)
from drs_filer.errors.exceptions import (
    NotFound,
    ValidationError,
)

INDEX_CONFIG = {
    'keys': [('id', 1)]
}
COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}
DB_CONFIG = {
    'collections': {
        'objects': COLLECTION_CONFIG,
        'service_info': COLLECTION_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'drsStore': DB_CONFIG,
    },
}
SERVICE_INFO_CONFIG = {
    "contactUrl": "mailto:support@example.com",
    "createdAt": "2019-06-04T12:58:19Z",
    "description": "This service provides...",
    "documentationUrl": "https://docs.myservice.example.com",
    "environment": "test",
    "id": "org.ga4gh.myservice",
    "name": "My project",
    "organization": {
        "name": "My organization",
        "url": "https://example.com"
    },
    "type": {
        "artifact": "beacon",
        "group": "org.ga4gh",
        "version": "1.0.0"
    },
    "updatedAt": "2019-06-04T12:58:19Z",
    "version": "1.0.0"
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
    "service_info": deepcopy(SERVICE_INFO_CONFIG),
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 8080,
    "api_path": "ga4gh/drs/v1"
}
SERVICE_CONFIG = {
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/drs/v1",
}
HEADERS_SERVICE_INFO = {
    'Content-type': 'application/json',
    'Location': (
        f"{SERVICE_CONFIG['url_prefix']}://{SERVICE_CONFIG['external_host']}:"
        f"{SERVICE_CONFIG['external_port']}/{SERVICE_CONFIG['api_path']}/"
        "service-info"
    )
}


def test_get_service_info():
    """Test for getting service info."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        assert RegisterServiceInfo().get_service_info() == SERVICE_INFO_CONFIG


def test_get_service_info_na():
    """Test for getting service info if unavailable."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        with pytest.raises(NotFound):
            RegisterServiceInfo().get_service_info()


def test_set_service_info_from_config():
    """Test for setting service info from config."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_set_service_info_from_config_corrupt():
    """Test for setting service info from corrupt config."""
    app = Flask(__name__)
    mock_resp = deepcopy(ENDPOINT_CONFIG)
    del mock_resp['service_info']['id']
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=mock_resp,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        with pytest.raises(ValidationError):
            service_info = RegisterServiceInfo()
            service_info.set_service_info_from_config()


def test_set_service_info_from_config_skip():
    """Test for skipping setting service info because it is already
    available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_get_service_info_duplicatekey():
    """Test for duplicated service info config."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    app.config['FOCA'].db.dbs['drsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['drsStore'] \
        .collections['service_info'].client.insert_one = mock
    mock_db_call = MagicMock(name="Find_Obj")
    mock_db_call.return_value.sort.return_value \
        .limit.return_value.next.return_value = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['drsStore'] \
        .collections['service_info'].client.find = mock_db_call
    with app.app_context():
        get_service_info = RegisterServiceInfo().get_service_info()
        assert get_service_info == SERVICE_INFO_CONFIG


def test_set_service_info_from_app_context(self):
    """Test for setting service info from app context."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_app_context(
            data=SERVICE_INFO_CONFIG,
        )
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG

def test__upsert_service_info_insert(self):
    """Test for creating service info document in database."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data['contactUrl']
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG

def test__upsert_service_info_update(self):
    """Test for replacing service info document in database."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client.insert_one(mock_resp)

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data['contactUrl']
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG

def test__get_headers(self):
    """Test for response headers getter."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    with app.app_context():
        service_info = RegisterServiceInfo()
        headers = service_info._get_headers()
        assert headers == HEADERS_SERVICE_INFO
