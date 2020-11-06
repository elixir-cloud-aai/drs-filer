from flask import json
from foca.models.config import MongoConfig
from drs_filer.errors.exceptions import (
    AccessMethodNotFound,
    BadRequest,
    URLNotFound,
    ObjectNotFound,
    InternalServerError)
from drs_filer.ga4gh.drs.server import (
    DeleteAccessMethod,
    DeleteObject,
    GetObject,
    GetAccessURL,
    PostObject,
    PutObject,
)
import mongomock
import pytest

from foca.models.config import Config
from flask import Flask

MOCK_ID_NA = "unavailable"

INDEX_CONFIG = {
    'keys': [('last_name', -1)]
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
        "id_charset": "string.digits",
        "id_length": 6
    },
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 8080,
    "api_path": "ga4gh/drs/v1"
}

data_objects_path = "tests/data_objects.json"

MOCK_DATA_OBJECT = {
    "id": "a011",
    "description": "mock_object",
    "name": "mock_object"
}


def test_GetObject():
    """Test for getting DRSObject meta-data using `object_id`"""
    app = Flask(__name__)
    app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj).inserted_id
    del objects[0]['_id']
    with app.app_context():
        res = GetObject.__wrapped__("a001")
        assert res == objects[0]


def test_GetObject_Not_Found():
    with pytest.raises(ObjectNotFound):
        app = Flask(__name__)
        app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client = mongomock.MongoClient().\
            db.collection
        objects = json.loads(open(data_objects_path, "r").read())
        for obj in objects:
            obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
                collections['objects'].client.insert_one(obj).inserted_id
        del objects[0]['_id']
        with app.app_context():
            GetObject.__wrapped__("a01")


def test_GetAccessURL():
    """Test for getting DRSObject access url using `object_id` and `access_id`
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj).inserted_id
    del objects[0]['_id']
    with app.app_context():
        res = GetAccessURL.__wrapped__("a001", "1")
        expected = {
            "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapiens/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",   # noqa: E501
            "headers": [
                "None"
            ]
        }
        assert res == expected


def test_GetAccessURL_Not_Found():
    """GetAccessURL should raise NotFound exception when access_id is not found
    """
    with pytest.raises(URLNotFound):
        app = Flask(__name__)
        app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client = mongomock.MongoClient().\
            db.collection
        objects = json.loads(open(data_objects_path, "r").read())
        for obj in objects:
            obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
                collections['objects'].client.insert_one(obj).inserted_id
        del objects[0]['_id']
        with app.app_context():
            res = GetAccessURL.__wrapped__("a001", "12")
            expected = {
                "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapiens/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",   # noqa: E501
                "headers": [
                    "None"
                ]
            }
            assert res == expected


def test_GetAccessURL_Object_Not_Found():
    """GetAccessURL should raise NotFound exception when access_id is not found
    """
    with pytest.raises(ObjectNotFound):
        app = Flask(__name__)
        app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client = mongomock.MongoClient().\
            db.collection
        objects = json.loads(open(data_objects_path, "r").read())
        for obj in objects:
            obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
                collections['objects'].client.insert_one(obj).inserted_id
        del objects[0]['_id']
        with app.app_context():
            GetAccessURL.__wrapped__("001", "12")


def test_GetAccessURL_Key_Error():
    """GetAccessURL should raise KeyError exception when access_methods
    are not there"""
    with pytest.raises(InternalServerError):
        app = Flask(__name__)
        app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client = mongomock.MongoClient().\
            db.collection
        objects = json.loads(open(data_objects_path, "r").read())
        for obj in objects:
            obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
                collections['objects'].client.insert_one(obj).inserted_id
        del objects[0]['_id']
        with app.app_context():
            GetAccessURL.__wrapped__("a010", "12")


def test_GetAccessURL_Duplicate_Access_Id():
    """GetAccessURL should return Internal Server Error on duplicate access keys.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().\
        db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj).inserted_id
    del objects[0]['_id']
    with app.app_context():
        with pytest.raises(InternalServerError):
            GetAccessURL.__wrapped__("a003", "3")


def test_DeleteObject():
    """DeleteObject should return the id of the deleted object"""
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj).inserted_id
    del objects[0]['_id']
    with app.app_context():
        res = DeleteObject.__wrapped__("a001")
        assert res == "a001"


def test_DeleteObject_Not_Found():
    """ObjectNotFound should be raised if object id is not found"""
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        obj['_id'] = app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj).inserted_id
    del objects[0]['_id']
    with app.app_context():
        with pytest.raises(ObjectNotFound):
            DeleteObject.__wrapped__("01")


def test_DeleteAccessMethod():
    """Test for deleting an access method `access_id` of an object associated
    with a given `object_id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['objects'].client = \
        mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj)
    with app.app_context():
        res = DeleteAccessMethod.__wrapped__("a011", "2")
        assert res == "2"


def test_DeleteAccessMethod_ObjectNotFound():
    """Test for deleting an access method `access_id` of an object associated
    with a given `object_id` when an object with the specified identifier is
    not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['objects'].client = \
        mongomock.MongoClient().db.collection
    with app.app_context():
        with pytest.raises(ObjectNotFound):
            DeleteAccessMethod.__wrapped__(MOCK_ID_NA, MOCK_ID_NA)


def test_DeleteAccessMethod_AccessMethodNotFound():
    """Test for deleting an access method `access_id` of an object associated
    with a given `object_id` when an access method with the specified
    identifier is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['objects'].client = \
        mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj)
    with app.app_context():
        with pytest.raises(AccessMethodNotFound):
            DeleteAccessMethod.__wrapped__("a011", MOCK_ID_NA)


def test_DeleteAcessMethod_BadRequest(monkeypatch):
    """Test for deleting an access method `access_id` of an object associated
    with a given `object_id` when that access method is the last remaining
    access method associated with object.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['objects'].client = \
        mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj)
    with app.app_context():
        with pytest.raises(BadRequest):
            DeleteAccessMethod.__wrapped__("a001", "1")


def test_DeleteAccessMethod_InternalServerError(monkeypatch):
    """Test for deleting an access method `access_id` of an object associated
    with a given `object_id` when the deletion did not succeed.
    """
    class MongoMockResponse:
        def __init__(self, modified_count):
            self.modified_count = modified_count

    mock_response = MongoMockResponse(modified_count=0)
    monkeypatch.setattr(
        'mongomock.collection.Collection.update_one',
        lambda *args, **kwargs: mock_response
    )
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['drsStore'].collections['objects'].client = \
        mongomock.MongoClient().db.collection
    objects = json.loads(open(data_objects_path, "r").read())
    for obj in objects:
        app.config['FOCA'].db.dbs['drsStore']. \
            collections['objects'].client.insert_one(obj)
    with app.app_context():
        with pytest.raises(InternalServerError):
            DeleteAccessMethod.__wrapped__("a011", "2")


def test_PostObject():
    """Test for creating a new object with an auto-generated identifier."""
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = PostObject.__wrapped__()
        assert isinstance(res, str)


def test_PutObject():
    """Test for creating a new object with a user-supplied identigier."""
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = PutObject.__wrapped__("a011")
        assert isinstance(res, str)


def test_PutObject_update():
    """Test for updating an existing object."""
    app = Flask(__name__)
    app.config['FOCA'] = \
        Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client.insert_one(MOCK_DATA_OBJECT)

    with app.test_request_context(json={"name": "drsObject"}):
        res = PutObject.__wrapped__("a011")
        assert isinstance(res, str)
