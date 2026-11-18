"""Tests for the typed access to the app's config and collections."""

from typing import Any

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.collection import Collection
import pytest

from drs_filer.utils import (
    DB,
    check_id_settings,
    get_collection,
    get_endpoints_config,
    get_foca_config,
    get_id_settings,
)

MONGO_CONFIG: dict[str, Any] = {
    "host": "mongodb",
    "port": 27017,
    "dbs": {DB: {"collections": {"objects": {"indexes": []}}}},
}
ENDPOINTS_CONFIG: dict[str, Any] = {"url_prefix": "https"}


def _app() -> tuple[Flask, Collection[dict[str, Any]]]:
    """Create an app with a FOCA config and a mock `objects` collection.

    The config has `MONGO_CONFIG` and `ENDPOINTS_CONFIG`.

    Returns:
        Flask app, and the collection registered as `objects`.
    """
    app = Flask(__name__)
    config = Config.model_validate(
        {"db": MongoConfig(**MONGO_CONFIG), "endpoints": ENDPOINTS_CONFIG}
    )
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


def test_get_endpoints_config() -> None:
    """The app's own `endpoints` section of the config is returned."""
    app, _ = _app()
    with app.app_context():
        assert get_endpoints_config() == ENDPOINTS_CONFIG


def test_get_endpoints_config_missing() -> None:
    """Without an `endpoints` section, a KeyError is raised."""
    app = Flask(__name__)
    app.config.foca = Config(db=MongoConfig(**MONGO_CONFIG))  # type: ignore[attr-defined]
    with app.app_context(), pytest.raises(KeyError):
        get_endpoints_config()


def _id_app(endpoints: dict[str, Any]) -> Flask:
    """Create an app with the given `endpoints` section of the config.

    Args:
        endpoints: The `endpoints` section.

    Returns:
        Flask app.
    """
    app = Flask(__name__)
    app.config.foca = Config.model_validate(  # type: ignore[attr-defined]
        {"endpoints": endpoints}
    )
    return app


def test_get_id_settings() -> None:
    """The character set and length of a section are returned as set."""
    app = _id_app({"objects": {"id_charset": "aab", "id_length": 3}})
    with app.app_context():
        assert get_id_settings("objects") == ("aab", 3)


@pytest.mark.parametrize(
    "settings",
    [
        {"id_charset": "string.ascii_letters", "id_length": 6},
        {"id_charset": "'ab' + 'cd'", "id_length": 6},
        {"id_charset": "ab/", "id_length": 6},
        {"id_charset": ["a", "b"], "id_length": 6},
        {"id_charset": "", "id_length": 6},
        {"id_charset": None, "id_length": 6},
        {"id_charset": "abc", "id_length": -1},
        {"id_charset": "abc", "id_length": 2.5},
        {"id_charset": "abc", "id_length": False},
    ],
)
def test_get_id_settings_invalid(settings: dict[str, Any]) -> None:
    """Invalid settings raise a ValueError that names the section.

    Args:
        settings: Invalid settings of the section.
    """
    app = _id_app({"access_methods": settings})
    with (
        app.app_context(),
        pytest.raises(ValueError, match=r"^Invalid 'endpoints\.access_methods': "),
    ):
        get_id_settings("access_methods")


@pytest.mark.parametrize(
    "endpoints",
    [{}, {"objects": {"id_length": 6}}, {"objects": {"id_charset": "abc"}}],
    ids=["no-section", "no-charset", "no-length"],
)
def test_get_id_settings_missing(endpoints: dict[str, Any]) -> None:
    """Missing settings raise a KeyError.

    Args:
        endpoints: The `endpoints` section, without some settings.
    """
    app = _id_app(endpoints)
    with app.app_context(), pytest.raises(KeyError):
        get_id_settings("objects")


def test_check_id_settings() -> None:
    """All sections are checked: one invalid section fails the check."""
    valid = {"id_charset": "abc", "id_length": 6}
    app = _id_app({"objects": valid, "access_methods": valid})
    with app.app_context():
        check_id_settings()
    app = _id_app({"objects": valid, "access_methods": {**valid, "id_length": 0}})
    with app.app_context(), pytest.raises(ValueError, match="access_methods"):
        check_id_settings()


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
