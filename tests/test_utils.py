"""Tests for the typed access to the app's config and collections."""

from typing import Any

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.collection import Collection
import pytest

from drs_filer.custom_config import CustomConfig, DrsConfig
from drs_filer.utils import (
    DB,
    get_collection,
    get_custom_config,
    get_foca_config,
)

MONGO_CONFIG: dict[str, Any] = {
    "host": "mongodb",
    "port": 27017,
    "dbs": {DB: {"collections": {"objects": {"indexes": []}}}},
}


def _app() -> tuple[Flask, Collection[dict[str, Any]]]:
    """Create an app with a FOCA config and a mock `objects` collection.

    The config has `MONGO_CONFIG`.

    Returns:
        Flask app, and the collection registered as `objects`.
    """
    app = Flask(__name__)
    config = Config.model_validate({"db": MongoConfig(**MONGO_CONFIG)})
    collection: Collection[dict[str, Any]] = mongomock.MongoClient().db.collection
    assert config.db is not None and config.db.dbs is not None
    collections = config.db.dbs[DB].collections
    assert collections is not None
    collections["objects"].client = collection
    app.config.foca = config  # type: ignore[attr-defined]
    return app, collection


def test_get_foca_config() -> None:
    """The FOCA config of the current app is returned."""
    app, _ = _app()
    with app.app_context():
        assert get_foca_config() is app.config.foca  # type: ignore[attr-defined]


def test_get_custom_config() -> None:
    """The custom config of the current app is returned."""
    app = Flask(__name__)
    custom = CustomConfig(drs=DrsConfig(hostname="drs.example.org"))
    app.config.foca = Config.model_validate({"custom": custom})  # type: ignore[attr-defined]
    with app.app_context():
        assert get_custom_config() is custom


@pytest.mark.parametrize(
    "extra",
    [{}, {"custom": {"drs": {"hostname": "drs.example.org"}}}],
    ids=["missing", "untyped"],
)
def test_get_custom_config_missing(extra: dict[str, Any]) -> None:
    """Without a custom config of type `CustomConfig`, a RuntimeError is raised.

    Args:
        extra: Extra sections of the config: none, or an untyped `custom`.
    """
    app = Flask(__name__)
    app.config.foca = Config.model_validate(extra)  # type: ignore[attr-defined]
    with app.app_context(), pytest.raises(RuntimeError, match="CustomConfig"):
        get_custom_config()


def test_get_collection() -> None:
    """A configured collection is returned by name."""
    app, collection = _app()
    with app.app_context():
        assert get_collection("objects") is collection


def test_get_collection_unknown() -> None:
    """An unknown collection name raises a KeyError."""
    app, _ = _app()
    with app.app_context(), pytest.raises(KeyError):
        get_collection("unknown")


@pytest.mark.parametrize(
    "mongo_config",
    [
        None,
        {"host": "mongodb", "port": 27017, "dbs": None},
        {"host": "mongodb", "port": 27017, "dbs": {DB: {"collections": None}}},
        MONGO_CONFIG,
    ],
    ids=["no-db", "no-dbs", "no-collections", "no-client"],
)
def test_get_collection_not_registered(mongo_config: dict[str, Any] | None) -> None:
    """A collection that isn't registered (no client) raises a KeyError."""
    db = None if mongo_config is None else MongoConfig(**mongo_config)
    app = Flask(__name__)
    app.config.foca = Config(db=db)  # type: ignore[attr-defined]
    with app.app_context(), pytest.raises(KeyError):
        get_collection("objects")
