"""Unit tests of whether access URLs need login, and of served objects."""

from pathlib import Path
from typing import Any

from flask import Flask
from foca.models.config import APIConfig, Config, SpecConfig
import pytest
import yaml

from drs_filer.ga4gh.drs.access_urls import (
    CONFIG_KEY,
    access_urls_need_login,
    requires_login,
    served_object,
    specs_require_login,
)
from tests.mock_data import ADDITIONS_SPEC, API_DIR, DRS_SPEC

ACCESS_URLS_PATCH = API_DIR / "patches" / "login-for-access-urls.yaml"
BEARER: list[dict[str, list[str]]] = [{"BearerAuth": []}]


def _spec(**kwargs: Any) -> SpecConfig:
    """Get the config of the app's specification, with other settings.

    Args:
        kwargs: Settings of `SpecConfig`.

    Returns:
        Config of the specification.
    """
    return SpecConfig(path=[DRS_SPEC, ADDITIONS_SPEC], **kwargs)


def _access_url_security(security: Any) -> dict[str, Any]:
    """Get a patch that sets the security of access URLs.

    Args:
        security: Security requirements.

    Returns:
        Patch.
    """
    path = "/objects/{object_id}/access/{access_id}"
    return {"paths": {path: {"get": {"security": security}}}}


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        # Public reads (root `security: []` of the additions)
        ({}, False),
        ({"patches": [ACCESS_URLS_PATCH]}, True),
        ({"patches": [_access_url_security(BEARER)]}, True),
        # An anonymous alternative
        ({"patches": [_access_url_security([*BEARER, {}])]}, False),
        ({"patches": [_access_url_security([])]}, False),
        # `disable_auth` removes all security requirements
        ({"patches": [ACCESS_URLS_PATCH], "disable_auth": True}, False),
        # The root's requirements, appended or patched, if the operation
        # sets none
        ({"append": [{"security": BEARER}]}, True),
        ({"patches": [{"security": BEARER}]}, True),
        ({"patches": [{"security": [{}, *BEARER]}]}, False),
    ],
)
def test_requires_login(settings: dict[str, Any], expected: bool) -> None:
    """Whether access URLs need a token follows the patched specification.

    Args:
        settings: Settings of the specification's config.
        expected: Whether access URLs need a token.
    """
    assert requires_login(_spec(**settings)) is expected


def test_requires_login_empty_patch_file(tmp_path: Path) -> None:
    """Patch files without content change nothing.

    Args:
        tmp_path: Temporary directory.
    """
    patch = tmp_path / "patch.yaml"
    patch.write_text("# nothing\n")
    assert requires_login(_spec(patches=[patch, ACCESS_URLS_PATCH])) is True
    assert requires_login(_spec(patches=[ACCESS_URLS_PATCH, patch])) is True


def test_requires_login_without_operation(tmp_path: Path) -> None:
    """Specifications without `GetAccessURL` don't say (`None`).

    Args:
        tmp_path: Temporary directory.
    """
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "openapi": "3.0.3",
                "security": BEARER,
                "paths": {
                    "/other": {"get": {"operationId": "Other"}, "post": {}},
                    "/empty": None,
                },
            }
        )
    )
    assert requires_login(SpecConfig(path=spec)) is None
    assert specs_require_login([SpecConfig(path=spec)]) is False
    assert specs_require_login([]) is False
    assert specs_require_login(
        [SpecConfig(path=spec), _spec(patches=[ACCESS_URLS_PATCH])]
    )


def _app(specs: list[SpecConfig]) -> Flask:
    """Get a Flask app with the FOCA config of specifications.

    Args:
        specs: Configs of the specifications.

    Returns:
        App.
    """
    app = Flask(__name__)
    app.config.foca = Config(api=APIConfig(specs=specs))
    return app


def test_access_urls_need_login_cached() -> None:
    """The result is read from the specification once per app."""
    app = _app([_spec(patches=[ACCESS_URLS_PATCH])])
    with app.app_context():
        assert access_urls_need_login() is True
        assert app.config[CONFIG_KEY] is True
        app.config[CONFIG_KEY] = False
        assert access_urls_need_login() is False


OBJECT: dict[str, Any] = {
    "id": "a",
    "access_methods": [
        {"type": "https", "access_id": "1", "access_url": {"url": "https://x"}},
        {"type": "s3", "access_url": {"url": "s3://x"}},
        {"type": "s3", "access_id": "3"},
    ],
}


def test_served_object_without_access_urls() -> None:
    """While access URLs need login, objects are served without them.

    The object itself is unchanged.
    """
    with _app([_spec(patches=[ACCESS_URLS_PATCH])]).app_context():
        served = served_object(OBJECT)
    assert served == {
        "id": "a",
        "access_methods": [
            {"type": "https", "access_id": "1"},
            {"type": "s3"},
            {"type": "s3", "access_id": "3"},
        ],
    }
    assert OBJECT["access_methods"][0]["access_url"] == {"url": "https://x"}


def test_served_object_unchanged() -> None:
    """Objects are served as stored if access URLs are public, or have none."""
    with _app([_spec()]).app_context():
        assert served_object(OBJECT) is OBJECT
    bundle = {"id": "b", "contents": []}
    with _app([_spec(patches=[ACCESS_URLS_PATCH])]).app_context():
        assert served_object(bundle) is bundle
