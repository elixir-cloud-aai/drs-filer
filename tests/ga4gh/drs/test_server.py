"""Tests for the DRS endpoint controllers."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from flask import Flask, json
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.collection import Collection
import pytest

from drs_filer.errors.exceptions import (
    AccessMethodNotDeleted,
    AccessMethodNotFound,
    InternalServerError,
    ObjectNotFound,
    URLNotFound,
)
from drs_filer.ga4gh.drs.server import (
    DeleteAccessMethod,
    DeleteObject,
    GetAccessURL,
    GetObject,
    PostObject,
    PutObject,
    getServiceInfo,
    postServiceInfo,
)

MOCK_ID_NA = "unavailable"

INDEX_CONFIG: dict[str, Any] = {"keys": [("last_name", -1)]}

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

ENDPOINT_CONFIG: dict[str, Any] = {
    "objects": {"id_charset": "string.digits", "id_length": 6},
    "access_methods": {"id_charset": "string.digits", "id_length": 6},
    "service_info": deepcopy(SERVICE_INFO_CONFIG),
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 8080,
    "api_path": "ga4gh/drs/v1",
}

data_objects_path = "tests/data_objects.json"

MOCK_DATA_OBJECT = {"id": "a011", "description": "mock_object", "name": "mock_object"}


def test_GetObject() -> None:
    """Test for getting DRSObject meta-data using `object_id`."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        obj["_id"] = (
            app.config.foca.db.dbs["drsStore"]
            .collections["objects"]
            .client.insert_one(obj)
            .inserted_id
        )
    del objects[0]["_id"]
    with app.app_context():
        res = GetObject.__wrapped__("a001")
        assert res == objects[0]


def test_GetObject_Not_Found() -> None:
    """GetObject should raise ObjectNotFound for an unknown object."""
    with pytest.raises(ObjectNotFound):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config.foca.db.dbs["drsStore"].collections[
            "objects"
        ].client = mongomock.MongoClient().db.collection
        objects = json.loads(Path(data_objects_path).read_text())
        for obj in objects:
            obj["_id"] = (
                app.config.foca.db.dbs["drsStore"]
                .collections["objects"]
                .client.insert_one(obj)
                .inserted_id
            )
        del objects[0]["_id"]
        with app.app_context():
            GetObject.__wrapped__("a01")


def test_GetAccessURL() -> None:
    """Test for getting DRSObject access url using `object_id` and `access_id`."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        obj["_id"] = (
            app.config.foca.db.dbs["drsStore"]
            .collections["objects"]
            .client.insert_one(obj)
            .inserted_id
        )
    del objects[0]["_id"]
    with app.app_context():
        res = GetAccessURL.__wrapped__("a001", "1")
        expected = {
            "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapiens/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",
            "headers": ["None"],
        }
        assert res == expected


def test_GetAccessURL_Not_Found() -> None:
    """GetAccessURL should raise URLNotFound for an unknown `access_id`."""
    with pytest.raises(URLNotFound):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config.foca.db.dbs["drsStore"].collections[
            "objects"
        ].client = mongomock.MongoClient().db.collection
        objects = json.loads(Path(data_objects_path).read_text())
        for obj in objects:
            obj["_id"] = (
                app.config.foca.db.dbs["drsStore"]
                .collections["objects"]
                .client.insert_one(obj)
                .inserted_id
            )
        del objects[0]["_id"]
        with app.app_context():
            res = GetAccessURL.__wrapped__("a001", "12")
            expected = {
                "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapiens/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",
                "headers": ["None"],
            }
            assert res == expected


def test_GetAccessURL_Object_Not_Found() -> None:
    """GetAccessURL should raise ObjectNotFound for an unknown object."""
    with pytest.raises(ObjectNotFound):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config.foca.db.dbs["drsStore"].collections[
            "objects"
        ].client = mongomock.MongoClient().db.collection
        objects = json.loads(Path(data_objects_path).read_text())
        for obj in objects:
            obj["_id"] = (
                app.config.foca.db.dbs["drsStore"]
                .collections["objects"]
                .client.insert_one(obj)
                .inserted_id
            )
        del objects[0]["_id"]
        with app.app_context():
            GetAccessURL.__wrapped__("001", "12")


def test_GetAccessURL_Key_Error() -> None:
    """GetAccessURL should raise an error when access methods are missing."""
    with pytest.raises(InternalServerError):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
        app.config.foca.db.dbs["drsStore"].collections[
            "objects"
        ].client = mongomock.MongoClient().db.collection
        objects = json.loads(Path(data_objects_path).read_text())
        for obj in objects:
            obj["_id"] = (
                app.config.foca.db.dbs["drsStore"]
                .collections["objects"]
                .client.insert_one(obj)
                .inserted_id
            )
        del objects[0]["_id"]
        with app.app_context():
            GetAccessURL.__wrapped__("a010", "12")


def test_GetAccessURL_Duplicate_Access_Id() -> None:
    """GetAccessURL should return Internal Server Error on duplicate access keys."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        obj["_id"] = (
            app.config.foca.db.dbs["drsStore"]
            .collections["objects"]
            .client.insert_one(obj)
            .inserted_id
        )
    del objects[0]["_id"]
    with app.app_context(), pytest.raises(InternalServerError):
        GetAccessURL.__wrapped__("a003", "3")


def test_DeleteObject() -> None:
    """DeleteObject should return the id of the deleted object."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        obj["_id"] = (
            app.config.foca.db.dbs["drsStore"]
            .collections["objects"]
            .client.insert_one(obj)
            .inserted_id
        )
    del objects[0]["_id"]
    with app.app_context():
        res = DeleteObject.__wrapped__("a001")
        assert res == "a001"


def test_DeleteObject_Not_Found() -> None:
    """ObjectNotFound should be raised if object id is not found."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        obj["_id"] = (
            app.config.foca.db.dbs["drsStore"]
            .collections["objects"]
            .client.insert_one(obj)
            .inserted_id
        )
    del objects[0]["_id"]
    with app.app_context(), pytest.raises(ObjectNotFound):
        DeleteObject.__wrapped__("01")


def test_DeleteAccessMethod() -> None:
    """Test for deleting an access method of an object."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(obj)
    with app.app_context():
        res = DeleteAccessMethod.__wrapped__("a011", "2")
        assert res == "2"


def test_DeleteAccessMethod_ObjectNotFound() -> None:
    """Test for deleting an access method of an unknown object."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    with app.app_context(), pytest.raises(ObjectNotFound):
        DeleteAccessMethod.__wrapped__(MOCK_ID_NA, MOCK_ID_NA)


def test_DeleteAccessMethod_AccessMethodNotFound() -> None:
    """Test for deleting an unknown access method of an object."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(obj)
    with app.app_context(), pytest.raises(AccessMethodNotFound):
        DeleteAccessMethod.__wrapped__("a011", MOCK_ID_NA)


def test_DeleteAccessMethod_AccessMethodNotDeleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test for deleting the last remaining access method of an object."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(obj)
    with app.app_context(), pytest.raises(AccessMethodNotDeleted):
        DeleteAccessMethod.__wrapped__("a001", "1")


def _seeded_app() -> tuple[Flask, Collection[dict[str, Any]]]:
    """Create an app whose object collection holds the test objects.

    Returns:
        The app, and its (mongomock) object collection.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    collection: Collection[dict[str, Any]] = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["objects"].client = collection
    for obj in json.loads(Path(data_objects_path).read_text()):
        collection.insert_one(obj)
    return app, collection


def test_DeleteAccessMethod_concurrent_keeps_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent deletions never remove the last access method of an object.

    Object `a011` has two access methods. The deletion of the first one runs
    the deletion of the second one just before it writes, as a concurrent
    request could; afterwards, exactly one access method is left, and one of
    the deletions is refused. This simulates the interleaving that the old
    check-then-update code lost; in production, the guarantee comes from
    MongoDB updating a single document atomically (the API tests run the same
    filter against a real MongoDB when `MONGODB_TEST_URI` is set).
    """
    app, collection = _seeded_app()
    update_one = collection.update_one
    interleaved = False
    outcomes: list[str] = []

    def delete(access_id: str) -> None:
        """Delete an access method of `a011` and record the outcome."""
        try:
            outcomes.append(DeleteAccessMethod.__wrapped__("a011", access_id))
        except AccessMethodNotDeleted:
            outcomes.append("refused")

    def interleaved_update_one(*args: Any, **kwargs: Any) -> Any:
        """Run the second deletion before the first one writes."""
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            delete("2")
        return update_one(*args, **kwargs)

    monkeypatch.setattr(collection, "update_one", interleaved_update_one)
    with app.app_context():
        delete("1")
    assert interleaved
    assert outcomes == ["2", "refused"]
    obj = collection.find_one({"id": "a011"})
    assert obj is not None
    assert [method["access_id"] for method in obj["access_methods"]] == ["1"]


def test_DeleteAccessMethod_duplicate_ids_keeps_last() -> None:
    """Deleting a duplicated access ID never removes all access methods.

    Both access methods of object `a003` have the same access ID, so deleting
    it would leave the object without access methods.
    """
    app, collection = _seeded_app()
    with app.app_context(), pytest.raises(AccessMethodNotDeleted):
        DeleteAccessMethod.__wrapped__("a003", "3")
    obj = collection.find_one({"id": "a003"})
    assert obj is not None
    assert len(obj["access_methods"]) == 2


def test_DeleteAccessMethod_InternalServerError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test for deleting an access method when the deletion fails."""

    class MongoMockResponse:
        def __init__(self, modified_count: int) -> None:
            self.modified_count = modified_count

    mock_response = MongoMockResponse(modified_count=0)
    monkeypatch.setattr(
        "mongomock.collection.Collection.update_one",
        lambda *args, **kwargs: mock_response,
    )
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(obj)
    with app.app_context(), pytest.raises(InternalServerError):
        DeleteAccessMethod.__wrapped__("a011", "2")


def test_PostObject() -> None:
    """Test for creating a new object with an auto-generated identifier."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = PostObject.__wrapped__()
        assert isinstance(res, str)


def test_PutObject() -> None:
    """Test for creating a new object with a user-supplied identigier."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = PutObject.__wrapped__("a011")
        assert isinstance(res, str)


def test_PutObject_update() -> None:
    """Test for updating an existing object."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), endpoints=ENDPOINT_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(
        MOCK_DATA_OBJECT
    )

    with app.test_request_context(json={"name": "drsObject"}):
        res = PutObject.__wrapped__("a011")
        assert isinstance(res, str)


# GET /service-info
def test_getServiceInfo() -> None:
    """Test for getting service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client.insert_one(
        mock_resp
    )

    with app.app_context():
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG


# POST /service-info
def test_postServiceInfo() -> None:
    """Test for creating service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(SERVICE_INFO_CONFIG)):
        body, status, _ = postServiceInfo.__wrapped__()
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG
    assert body is None
    # An integer, not the string "201", so that Flask sets the status code
    assert status == 201
