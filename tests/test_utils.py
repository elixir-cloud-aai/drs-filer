"""Tests for the typed access to the app's config and collections."""

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
import pytest

from drs_filer.utils import DB, get_collection, get_foca_config

MONGO_CONFIG = {
    "host": "mongodb",
    "port": 27017,
    "dbs": {DB: {"collections": {"objects": {"indexes": []}}}},
}


def _app() -> Flask:
    """Create an app with a FOCA config and a mock `objects` collection.

    Returns:
        Flask app.
    """
    app = Flask(__name__)
    config = Config(db=MongoConfig(**MONGO_CONFIG))
    config.db.dbs[DB].collections[
        "objects"
    ].client = mongomock.MongoClient().db.collection
    app.config.foca = config  # type: ignore[attr-defined]
    return app


def test_get_foca_config() -> None:
    """The FOCA config of the current app is returned."""
    app = _app()
    with app.app_context():
        assert get_foca_config() is app.config.foca  # type: ignore[attr-defined]


def test_get_collection() -> None:
    """A configured collection is returned by name."""
    app = _app()
    with app.app_context():
        expected = get_foca_config().db.dbs[DB].collections["objects"].client
        assert get_collection("objects") is expected


def test_get_collection_unknown() -> None:
    """An unknown collection name raises a KeyError."""
    with _app().app_context(), pytest.raises(KeyError):
        get_collection("unknown")
