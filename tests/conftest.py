"""Shared fixtures.

App tests (`tests/api/`) use the app created from `drs_filer/config.yaml`,
the test overlay (`tests/config_overlay.yaml`, with the settings each
deployment must make) and an overlay that is empty unless a test writes to
it, with requests through Flask's test client, so that request and response
validation and error handling are part of every test. The identity provider
of the test overlay is replaced by a mock (`mock_get()`); requests of the test
client `client` carry an access token of an admin, those of
`anonymous_client` none (see `make_headers()` for tokens of other users).

The app tests use an in-memory database (mongomock), or, if the environment
variable `MONGODB_TEST_URI` is set, the MongoDB at that URI (e.g.,
`mongodb://localhost:27017`), as in CI: there, database `drsStore` (`DB`) is
dropped before each test, so use a MongoDB without other data, one per test
run. The tests refuse to start if the database exists already.

Tests can't open connections (`socket.socket.connect()` and
`connect_ex()`), except to the test database; FOCA's `MONGO_*` variables are
unset, so that apps use database `DB` and no credentials.
"""

from collections.abc import Iterator
import os
from pathlib import Path
import socket
import time
from typing import Any

from connexion import App
from cryptography.hazmat.primitives.asymmetric import rsa
from flask.testing import FlaskClient
from foca.database import register_mongodb
from foca.security import auth
import jwt
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
# The trusted issuer of the test overlay, a fictitious identity provider; all
# its endpoints are mocked (`mock_get()`)
ISSUER = "https://login.example.org/oidc/"
AUDIENCE = "client-id"
# Claim with the group memberships of users (`claim_groups` of the test
# overlay), released in access tokens
GROUP_CLAIM = "groups"
# Group mapped to the role `admin` in the test overlay
ADMIN_GROUP = "drs-admins"
ADMIN = "admin@example.org"
# A user who isn't an admin
USER = "alice@example.org"
# A user of the group that the example of `docs/access-control.md` maps to
# the role `editor`
EDITOR = "editor@example.org"
# Group memberships of the users, as released in their tokens
GROUPS = {ADMIN: [ADMIN_GROUP], USER: ["drs-users"], EDITOR: ["drs-editors"]}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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
        IP address and port of each host of the URI; none for an empty string,
        or if a host can't be resolved (the ping of `_mongodb()` then ends
        the test run with a clear message).
    """
    if not uri:
        return frozenset()
    try:
        return frozenset(
            (str(info[4][0]), port)
            for host, port in uri_parser.parse_uri(uri)["nodelist"]
            for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    except socket.gaierror:
        return frozenset()


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

    FOCA connects with PyMongo to the configured host; the tests replace that
    client.

    Args:
        monkeypatch: Patches of FOCA's MongoDB client.
        db_client: MongoDB client of the test.

    Returns:
        MongoDB client.
    """
    monkeypatch.setattr(
        register_mongodb, "MongoClient", lambda *args, **kwargs: db_client
    )
    return db_client


class MockResponse:
    """Mock response of `requests.get()`."""

    def __init__(self, data: dict[str, Any], status_code: int = 200) -> None:
        """Create a response.

        Args:
            data: JSON body.
            status_code: HTTP status code.
        """
        self.data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise an error for error status codes, as `requests` does.

        Raises:
            requests.HTTPError: The status code is 400 or higher.
        """
        if self.status_code >= 400:
            raise auth.requests.HTTPError(str(self.status_code))

    def json(self) -> dict[str, Any]:
        """Get the JSON body.

        Returns:
            The JSON body.
        """
        return self.data


def mock_get(url: str, **kwargs: Any) -> MockResponse:
    """Mock `requests.get()` for the identity provider (`ISSUER`).

    Serves its discovery and JWK set endpoints; other requests fail.

    Args:
        url: Requested URL.
        kwargs: Other arguments of `requests.get()`; ignored.

    Returns:
        Response of the endpoint.

    Raises:
        requests.ConnectionError: The URL is not an endpoint of the identity
            provider.
    """
    if url.rstrip("/") == f"{ISSUER}.well-known/openid-configuration":
        return MockResponse({"issuer": ISSUER, "jwks_uri": f"{ISSUER}jwk"})
    if url == f"{ISSUER}jwk":
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
        return MockResponse({"keys": [{**jwk, "kid": "rsa1", "use": "sig"}]})
    raise auth.requests.ConnectionError(f"Unexpected request in tests: {url}")


def make_token(
    user: str = ADMIN,
    key: rsa.RSAPrivateKey = KEY,
    typ: str | None = "at+jwt",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expired: bool = False,
) -> str:
    """Get an access token for a user, signed by the identity provider.

    The token lists the user's groups (`GROUPS`) in the group claim.

    Args:
        user: User identifier (`sub` claim).
        key: Key that signs the token.
        typ: Type of the token (`typ` header), `at+jwt` for access tokens
            (RFC 9068); `None` for no type.
        issuer: Issuer of the token (`iss` claim).
        audience: Audience of the token (`aud` claim).
        expired: Whether the token expired (10 minutes ago); otherwise, it
            expires in 5 minutes.

    Returns:
        The token.
    """
    now = int(time.time())
    claims: dict[str, Any] = {
        "aud": audience,
        "sub": user,
        "iss": issuer,
        "iat": now - 1200 if expired else now,
        "exp": now - 600 if expired else now + 300,
        GROUP_CLAIM: GROUPS.get(user, []),
    }
    return jwt.encode(
        claims,
        key,
        algorithm="RS256",
        # PyJWT omits `typ` if it is `None` (and sets `JWT` if it is missing)
        headers={"kid": "rsa1", "typ": typ},
    )


def make_headers(user: str = ADMIN, **kwargs: Any) -> dict[str, str]:
    """Get request headers with an access token for a user.

    Args:
        user: User identifier (`sub` claim); by default, an admin.
        kwargs: Other arguments of `make_token()`.

    Returns:
        Request headers.
    """
    return {"Authorization": f"Bearer {make_token(user, **kwargs)}"}


def admin_client(app: App) -> FlaskClient:
    """Get a test client whose requests carry an access token of an admin.

    Requests can still send headers of their own, e.g., `make_headers()` of
    other users, which replace the token.

    Args:
        app: Connexion app.

    Returns:
        Test client.
    """
    test_client = app.app.test_client()
    test_client.environ_base["HTTP_AUTHORIZATION"] = make_headers()["Authorization"]
    return test_client


@pytest.fixture
def mock_idp(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace the identity provider by a mock (`mock_get()`).

    FOCA's caches of the identity provider's responses are cleared before
    and after the test.

    Args:
        monkeypatch: Patches of the requests of FOCA's token validation.

    Yields:
        Nothing; the mock applies until the end of the test.
    """
    monkeypatch.setattr(auth.requests, "get", mock_get)
    auth.clear_caches()
    yield
    auth.clear_caches()


@pytest.fixture
def overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_idp: None) -> Path:
    """Config overlay merged into `config.yaml` by apps created in a test.

    Merged after the test overlay (`CONFIG_OVERLAY`), whose identity provider
    is mocked; empty, unless the test writes to it.

    Args:
        tmp_path: Temporary directory.
        monkeypatch: Patches of the variable `FOCA_CONFIG_OVERLAY`.
        mock_idp: Mock of the identity provider.

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
    """Test client of the app, whose requests carry an admin's access token.

    Args:
        app: Connexion app.

    Returns:
        Test client (cf. `admin_client()`).
    """
    return admin_client(app)


@pytest.fixture
def anonymous_client(app: App) -> FlaskClient:
    """Test client of the app, whose requests carry no access token.

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
