"""Shared fixtures.

App tests (`tests/api/`) use the app created from `drs_filer/config.yaml`,
the test overlay (`tests/config_overlay.yaml`, with the settings each
deployment must make) and an overlay that is empty unless a test writes to
it, with requests through Flask's test client, so that request and response
validation and error handling are part of every test.

The app tests use an in-memory database (mongomock), or, if the environment
variable `MONGODB_TEST_URI` is set, the MongoDB at that URI (e.g.,
`mongodb://localhost:27017`), as in CI: there, database `drsStore` (`DB`) is
dropped before each test, so use a MongoDB without other data, one per test
run. The tests refuse to start if the database exists already.

Tests can't open network connections (`socket.socket.connect()` and
`connect_ex()`), except to the test database; FOCA's `MONGO_*` variables are
unset, so that apps use database `DB` and no credentials.
"""

from collections.abc import Iterator
import os
from pathlib import Path
import socket
from types import SimpleNamespace
from typing import Any

from connexion import App
from flask.testing import FlaskClient
from foca.database import register_mongodb
import mongomock
from pymongo import MongoClient, uri_parser
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import pytest

from drs_filer.app import OVERLAY_VARIABLE, create_app
from drs_filer.utils import DB

# URI of a MongoDB to test against instead of mongomock (see above)
MONGODB_TEST_URI = os.environ.get("MONGODB_TEST_URI", "")
_CONNECT = socket.socket.connect
# Config overlay with the settings each deployment must make
CONFIG_OVERLAY = Path(__file__).parent / "config_overlay.yaml"
# FOCA's environment variables for the MongoDB connection
MONGO_VARIABLES = (
    "MONGO_HOST",
    "MONGO_PORT",
    "MONGO_DBNAME",
    "MONGO_USERNAME",
    "MONGO_PASSWORD",
)


def _db_addresses(uri: str) -> frozenset[tuple[str, int]]:
    """Get the socket addresses of the hosts of a MongoDB URI.

    Args:
        uri: MongoDB connection string (`mongodb://`), or an empty string.

    Returns:
        IP address and port of each host of the URI; none for an empty string.
    """
    if not uri:
        return frozenset()
    return frozenset(
        (str(info[4][0]), port)
        for host, port in uri_parser.parse_uri(uri)["nodelist"]
        for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    )


# Addresses that the tests may connect to
DB_ADDRESSES = _db_addresses(MONGODB_TEST_URI)


def _no_network(sock: socket.socket, address: Any) -> None:
    """Replace `socket.socket.connect()`, to block network access.

    Connections to the test database (`DB_ADDRESSES`) are allowed.

    Args:
        sock: Socket to connect.
        address: Address to connect to.

    Raises:
        OSError: The address is not one of the test database.
    """
    if isinstance(address, tuple) and tuple(address[:2]) in DB_ADDRESSES:
        _CONNECT(sock, address)
        return
    raise OSError(f"Network access blocked in tests: {address}")


def _no_network_ex(sock: socket.socket, address: Any) -> int:
    """Replace `socket.socket.connect_ex()`, to block network access.

    As `_no_network()`, but returns `0` for connections to the test database.

    Args:
        sock: Socket to connect.
        address: Address to connect to.

    Returns:
        `0`, the error indicator of `connect_ex()` for success.
    """
    _no_network(sock, address)
    return 0


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate all tests from the network and from deployments' databases.

    Network connections are blocked, except to the test database, and FOCA's
    `MONGO_*` variables (e.g., set as by the Helm chart) are unset.

    Args:
        monkeypatch: Patches of `socket.socket` and of the environment.
    """
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _no_network_ex)
    for variable in MONGO_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def _check_no_db(client: MongoClient[dict[str, Any]]) -> None:
    """Check that a MongoDB has no database `DB`, which the tests would drop.

    Ends the test run (`pytest.exit()`, as a usage error) if the database
    exists, e.g., with data of a deployment, or left by an aborted test run.

    Args:
        client: Client of the MongoDB.
    """
    if DB in client.list_database_names():
        pytest.exit(
            f"MongoDB at MONGODB_TEST_URI has a database '{DB}', which the"
            " tests would drop: use a MongoDB without it (drop it if it is"
            " left from an aborted test run)",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


@pytest.fixture(scope="session")
def _mongodb() -> Iterator[MongoClient[dict[str, Any]] | None]:
    """Client of the MongoDB at `MONGODB_TEST_URI`, if set, for all tests.

    Ends the test run if the MongoDB has a database `DB` before the tests.

    Yields:
        The client; `None` if `MONGODB_TEST_URI` is not set.
    """
    if not MONGODB_TEST_URI:
        yield None
        return
    client: MongoClient[dict[str, Any]] = MongoClient(
        MONGODB_TEST_URI, serverSelectionTimeoutMS=5000
    )
    try:
        try:
            client.admin.command("ping")
        except PyMongoError as err:
            pytest.exit(
                f"MongoDB at MONGODB_TEST_URI is not reachable: {err}",
                returncode=pytest.ExitCode.USAGE_ERROR,
            )
        _check_no_db(client)
        yield client
        client.drop_database(DB)
    finally:
        client.close()


@pytest.fixture
def db_client(
    _mongodb: MongoClient[dict[str, Any]] | None,
) -> MongoClient[dict[str, Any]]:
    """MongoDB client of a test, with an empty database `DB`.

    Args:
        _mongodb: Client of the MongoDB at `MONGODB_TEST_URI`, if set.

    Returns:
        The MongoDB at `MONGODB_TEST_URI` if set, otherwise a new in-memory
        one.
    """
    if _mongodb is None:
        client: MongoClient[dict[str, Any]] = mongomock.MongoClient()
        return client
    _mongodb.drop_database(DB)
    return _mongodb


@pytest.fixture
def mongo_client(
    monkeypatch: pytest.MonkeyPatch,
    db_client: MongoClient[dict[str, Any]],
) -> MongoClient[dict[str, Any]]:
    """MongoDB client used by all apps created in a test (see `db_client`).

    FOCA 0.13 connects with Flask-PyMongo to the configured host; the tests
    replace that client.

    Args:
        monkeypatch: Patches of FOCA's MongoDB client.
        db_client: MongoDB client of the test.

    Returns:
        MongoDB client.
    """

    def create_client(db: str, **kwargs: Any) -> SimpleNamespace:
        """Replace FOCA's `_create_mongo_client()`.

        Args:
            db: Name of the database.
            kwargs: Other arguments (app, host, port); ignored.

        Returns:
            Object with the database as `db`, as Flask-PyMongo's client.
        """
        return SimpleNamespace(db=db_client[db])

    monkeypatch.setattr(register_mongodb, "_create_mongo_client", create_client)
    return db_client


@pytest.fixture
def overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Config overlay merged into `config.yaml` by apps created in a test.

    Merged after the test overlay (`CONFIG_OVERLAY`); empty, unless the test
    writes to it.

    Args:
        tmp_path: Temporary directory.
        monkeypatch: Patches of the variable `FOCA_CONFIG_OVERLAY`.

    Returns:
        Path of the overlay.
    """
    path = tmp_path / "overlay.yaml"
    path.write_text("{}\n")
    monkeypatch.setenv(OVERLAY_VARIABLE, f"{CONFIG_OVERLAY}:{path}")
    return path


@pytest.fixture
def app(mongo_client: MongoClient[dict[str, Any]], overlay: Path) -> App:
    """App created from `config.yaml`, the test overlay and the overlay.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.

    Returns:
        Connexion app.
    """
    return create_app()


@pytest.fixture
def client(app: App) -> FlaskClient:
    """Test client of the app.

    Args:
        app: Connexion app.

    Returns:
        Test client.
    """
    return app.app.test_client()


@pytest.fixture
def objects(mongo_client: MongoClient[dict[str, Any]]) -> Collection[dict[str, Any]]:
    """Collection `objects` of the apps of a test.

    Args:
        mongo_client: MongoDB client.

    Returns:
        The collection.
    """
    return mongo_client[DB]["objects"]


@pytest.fixture
def service_info(
    mongo_client: MongoClient[dict[str, Any]],
) -> Collection[dict[str, Any]]:
    """Collection `service_info` of the apps of a test.

    Args:
        mongo_client: MongoDB client.

    Returns:
        The collection.
    """
    return mongo_client[DB]["service_info"]
