"""Unit tests of the authorization info of objects and access methods."""

from typing import Any
from unittest.mock import patch

from flask import Flask
from foca.models.config import APIConfig, AuthConfig, Config, SecurityConfig, SpecConfig
import pytest

from drs_filer.ga4gh.drs import authorizations
from drs_filer.ga4gh.drs.access_urls import CONFIG_KEY as ACCESS_URLS_KEY
from drs_filer.ga4gh.drs.access_urls import requires_login
from drs_filer.ga4gh.drs.authorizations import (
    CONFIG_KEY,
    OBJECT_PATH,
    OPERATION_ID,
    object_reads_need_login,
    supported_authorizations,
    with_access_method_authorizations,
)
from tests.mock_data import ADDITIONS_SPEC, API_DIR, DRS_SPEC

PATCHES = API_DIR / "patches"
ACCESS_URLS_PATCH = PATCHES / "login-for-access-urls.yaml"
READS_PATCH = PATCHES / "login-for-reads.yaml"
ISSUERS = ["https://login.example.org/oidc/", "https://other.example.org/"]


def _spec(**kwargs: Any) -> SpecConfig:
    """Get the config of the app's specification, with other settings.

    Args:
        kwargs: Settings of `SpecConfig`.

    Returns:
        Config of the specification.
    """
    return SpecConfig(path=[DRS_SPEC, ADDITIONS_SPEC], **kwargs)


def _app(specs: list[SpecConfig], issuers: list[Any] | None = None) -> Flask:
    """Get a Flask app with the FOCA config of specifications and issuers.

    Args:
        specs: Configs of the specifications.
        issuers: Trusted issuers (`security.auth.issuers`); none by default.

    Returns:
        App.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        api=APIConfig(specs=specs),
        security=SecurityConfig(
            auth=AuthConfig(issuers=issuers or [], audience=["client-id"])
        ),
    )
    return app


@pytest.mark.parametrize(
    ("patches", "expected"),
    [
        ([], False),
        ([ACCESS_URLS_PATCH], False),
        ([READS_PATCH], True),
        ([ACCESS_URLS_PATCH, READS_PATCH], True),
    ],
)
def test_object_reads_require_login(patches: list[Any], expected: bool) -> None:
    """Whether `GetObject` needs a token follows the patches for reads only.

    Args:
        patches: Patches of the specification.
        expected: Whether object reads need a token.
    """
    assert requires_login(_spec(patches=patches), OBJECT_PATH, OPERATION_ID) is (
        expected
    )


def test_object_reads_need_login_cached() -> None:
    """The result is read from the specification once per app, and logged."""
    app = _app([_spec(patches=[READS_PATCH])])
    with app.app_context(), patch.object(authorizations, "logger") as logger:
        assert object_reads_need_login() is True
        assert app.config[CONFIG_KEY] is True
        app.config[CONFIG_KEY] = False
        assert object_reads_need_login() is False
    logger.info.assert_called_once_with("Object reads %s", "need login")


def test_supported_authorizations() -> None:
    """Bearer tokens of the trusted issuers, or none; never passports."""
    issuers = [ISSUERS[0], {"issuer": ISSUERS[1]}, ISSUERS[0]]
    with _app([], issuers=issuers).app_context():
        assert supported_authorizations(True) == {
            "supported_types": ["BearerAuth"],
            "bearer_auth_issuers": ISSUERS,
        }
        assert supported_authorizations(False) == {"supported_types": ["None"]}
    with _app([]).app_context():
        assert supported_authorizations(True) == {"supported_types": ["BearerAuth"]}


def test_access_method_authorizations() -> None:
    """Access methods with an `access_id` get the authorization info.

    Stored authorization info is replaced, or dropped from access methods
    without `access_id`; the object itself is unchanged, and bundles are
    served as they are.
    """
    stored = {"supported_types": ["PassportAuth"], "passport_auth_issuers": ["x"]}
    obj: dict[str, Any] = {
        "id": "a",
        "access_methods": [
            {"type": "https", "access_id": "1", "authorizations": stored},
            {"type": "s3", "access_url": {"url": "s3://x"}, "authorizations": stored},
        ],
    }
    app = _app([_spec(patches=[ACCESS_URLS_PATCH])], issuers=ISSUERS[:1])
    with app.app_context():
        served = with_access_method_authorizations(obj)
        bundle = {"id": "b", "contents": []}
        assert with_access_method_authorizations(bundle) is bundle
    assert app.config[ACCESS_URLS_KEY] is True
    assert served == {
        "id": "a",
        "access_methods": [
            {
                "type": "https",
                "access_id": "1",
                "authorizations": {
                    "supported_types": ["BearerAuth"],
                    "bearer_auth_issuers": ISSUERS[:1],
                },
            },
            {"type": "s3", "access_url": {"url": "s3://x"}},
        ],
    }
    assert obj["access_methods"][0]["authorizations"] is stored
