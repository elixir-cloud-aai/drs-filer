from flask import json
from foca.models.config import MongoConfig
from werkzeug.exceptions import NotFound
from drs_filer.ga4gh.drs.server import GetObject, GetAccessURL, RegisterObject
import mongomock
import pytest

from foca.models.config import Config
from flask import Flask

INDEX_CONFIG = {
    'keys': [('last_name', -1)],
    'name': 'indexLastName',
    'unique': True,
    'background': False,
    'sparse': False,
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

data_objects_path = "tests/data_objects.json"


def test_RegisterObject():
    """Test for registering new DRSObject"""
    app = Flask(__name__)
    app.config['FOCA'] = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config['FOCA'].db.dbs['drsStore']. \
        collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"id": "1"}):
        res = RegisterObject()
        assert res == {"id": "1"}


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
        res = GetObject("a001")
        assert res == objects[0]


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
        res = GetAccessURL("a001", "1")
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
    with pytest.raises(NotFound):
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
            res = GetAccessURL("a001", "12")
            expected = {
                "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapiens/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",   # noqa: E501
                "headers": [
                    "None"
                ]
            }
            assert res == expected
