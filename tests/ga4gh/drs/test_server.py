"""Tests for the DRS endpoint controllers."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from flask import Flask, json
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.collection import Collection
import pytest

from drs_filer.custom_config import CustomConfig
from drs_filer.errors.exceptions import (
    AccessMethodNotDeleted,
    AccessMethodNotFound,
    InternalServerError,
    ObjectNotFound,
    URLNotFound,
)
from drs_filer.ga4gh.drs.endpoints.service_info import (
    CURRENT_ID,
    drs_service_fields,
)
from drs_filer.ga4gh.drs.server import (
    DeleteAccessMethod,
    DeleteObject,
    GetAccessURL,
    GetObject,
    GetServiceInfo,
    PostServiceInfo,
    PutObject,
    RegisterObject,
    self_uri,
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

# The app's own config: identifiers of digits, and the public host name
CUSTOM_CONFIG = CustomConfig.model_validate(
    {
        "objects": {"id": {"charset": "0123456789", "length": 6}},
        "access_methods": {"id": {"charset": "0123456789", "length": 6}},
        "drs": {"hostname": "drs.example.org"},
    }
)

data_objects_path = "tests/data_objects.json"

MOCK_DATA_OBJECT = {"id": "a011", "description": "mock_object", "name": "mock_object"}


def test_GetObject() -> None:
    """Test for getting DRSObject meta-data using `object_id`."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
        assert res == {**objects[0], "self_uri": "drs://drs.example.org/a001"}


def test_GetObject_Not_Found() -> None:
    """GetObject should raise ObjectNotFound for an unknown object."""
    with pytest.raises(ObjectNotFound):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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


def test_GetAccessURL_No_Access_Methods() -> None:
    """GetAccessURL should raise URLNotFound when access methods are missing."""
    with pytest.raises(URLNotFound):
        app = Flask(__name__)
        app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
        custom=CUSTOM_CONFIG,
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
        custom=CUSTOM_CONFIG,
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
        custom=CUSTOM_CONFIG,
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
        custom=CUSTOM_CONFIG,
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
        custom=CUSTOM_CONFIG,
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
        custom=CUSTOM_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    objects = json.loads(Path(data_objects_path).read_text())
    for obj in objects:
        app.config.foca.db.dbs["drsStore"].collections["objects"].client.insert_one(obj)
    with app.app_context(), pytest.raises(InternalServerError):
        DeleteAccessMethod.__wrapped__("a011", "2")


def test_RegisterObject() -> None:
    """Test for creating a new object with an auto-generated identifier."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = RegisterObject.__wrapped__()
        assert isinstance(res, str)


def test_PutObject() -> None:
    """Test for creating a new object with a user-supplied identigier."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
    app.config.foca.db.dbs["drsStore"].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json={"name": "drsObject"}):
        res = PutObject.__wrapped__("a011")
        assert isinstance(res, str)


def test_PutObject_update() -> None:
    """Test for updating an existing object."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG), custom=CUSTOM_CONFIG)
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
def test_GetServiceInfo() -> None:
    """Test for getting service info, with the computed DRS fields."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CUSTOM_CONFIG,
    )
    mock_resp = {**deepcopy(SERVICE_INFO_CONFIG), "_id": CURRENT_ID}
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs["drsStore"].collections["service_info"].client.insert_one(
        mock_resp
    )

    with app.app_context():
        res = GetServiceInfo.__wrapped__()
        assert res == {**SERVICE_INFO_CONFIG, **drs_service_fields()}


# POST /service-info
def test_PostServiceInfo() -> None:
    """Test for creating service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CUSTOM_CONFIG,
    )
    app.config.foca.db.dbs["drsStore"].collections[
        "service_info"
    ].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(SERVICE_INFO_CONFIG)):
        body, status, _ = PostServiceInfo.__wrapped__()
        res = GetServiceInfo.__wrapped__()
        assert res == {**SERVICE_INFO_CONFIG, **drs_service_fields()}
    assert body is None
    # An integer, not the string "201", so that Flask sets the status code
    assert status == 201


@pytest.mark.parametrize(
    ("object_id", "expected"),
    [
        (".", "drs://drs.example.org/%2E"),
        ("..", "drs://drs.example.org/%2E%2E"),
        ("...", "drs://drs.example.org/..."),
        ("a.b", "drs://drs.example.org/a.b"),
        ("x:y", "drs://drs.example.org/x%3Ay"),
    ],
)
def test_self_uri(object_id: str, expected: str) -> None:
    """The identifier in `self_uri` is percent-encoded, dot segments too.

    `.` and `..` would otherwise be dot segments, which clients remove when
    they resolve the URI to a URL (RFC 3986, section 5.2.4); other
    identifiers keep their unreserved characters.

    Args:
        object_id: Identifier of the object.
        expected: Its `self_uri`.
    """
    app = Flask(__name__)
    app.config.foca = Config(custom=CUSTOM_CONFIG)
    with app.app_context():
        assert self_uri(object_id) == expected
