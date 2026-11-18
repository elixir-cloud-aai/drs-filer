"""Tests of the shipped app config and the Compose overlay."""

from pathlib import Path
import string

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "drs_filer" / "config.yaml"
DEV_OVERLAY_PATH = ROOT / "config.dev.yaml"
# HTTP methods of the Path Item Objects of OpenAPI 3
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def test_debug_mode_off() -> None:
    """The shipped config disables Flask's debug mode.

    Debug mode can enable the Werkzeug debugger, which allows code execution
    for anyone who can reach an error page.
    """
    server = yaml.safe_load(CONFIG_PATH.read_text())["server"]
    assert server["debug"] is False


def test_operations_routed_to_package() -> None:
    """All operations are routed to the controllers of the installed package.

    FOCA adds `drs_filer.ga4gh.drs.server` to all operations
    (`add_operation_fields`), unless they name another controller, which none
    does. Connexion reads `x-openapi-router-controller` for OpenAPI 3; the
    vendored specification names `ga4gh.drs.server` in
    `x-swagger-router-controller` (of OpenAPI 2), which Connexion ignores
    here, and which wouldn't be importable from an installed package.
    """
    spec = yaml.safe_load(CONFIG_PATH.read_text())["api"]["specs"]["drs"]
    assert spec["add_operation_fields"] == {
        "x-openapi-router-controller": "drs_filer.ga4gh.drs.server"
    }
    assert spec["path"]
    for path in spec["path"]:
        content = yaml.safe_load((CONFIG_PATH.parent / path).read_text())
        operations = [
            operation
            for path_item in content["paths"].values()
            for method, operation in path_item.items()
            if method in METHODS
        ]
        assert operations, path
        for operation in operations:
            assert "x-openapi-router-controller" not in operation, path


def test_dev_overlay() -> None:
    """The Compose overlay builds URLs of the host it publishes the app on.

    It changes nothing else, so that it keeps Flask's debug mode off.
    """
    overlay = yaml.safe_load(DEV_OVERLAY_PATH.read_text())
    assert overlay == {
        "custom": {
            "service": {
                "url_prefix": "http",
                "external_host": "localhost",
                "external_port": 8080,
            },
        },
    }


def test_id_charsets_literal() -> None:
    """Identifiers are drawn from the characters of the shipped config.

    The characters are listed themselves (no expression), and are those that
    earlier versions evaluated `string.ascii_letters + string.digits +
    ".-_~"` to: letters, digits and the unreserved characters of URLs.
    """
    custom = yaml.safe_load(CONFIG_PATH.read_text())["custom"]
    expected = string.ascii_letters + string.digits + ".-_~"
    for section in ("objects", "access_methods"):
        assert custom[section]["id"] == {"charset": expected, "length": 6}


def test_service_info_defaults() -> None:
    """The service info is that of a DRS 1.5.0, with the package's version.

    `version` isn't set, so that it is that of the installed package.
    """
    service_info = yaml.safe_load(CONFIG_PATH.read_text())["service_info"]
    assert service_info["package"] == "drs-filer"
    assert "version" not in service_info["service"]
    assert service_info["service"]["type"] == {
        "group": "org.ga4gh",
        "artifact": "drs",
        "version": "1.5.0",
    }
