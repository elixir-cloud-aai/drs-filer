"""Tests of the shipped app config and the Compose overlay."""

from pathlib import Path
import string

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "drs_filer" / "config.yaml"
DEV_OVERLAY_PATH = ROOT / "config.dev.yaml"
# HTTP methods of the Path Item Objects of OpenAPI 2
METHODS = {"get", "put", "post", "delete", "options", "head", "patch"}


def test_debug_mode_off() -> None:
    """The shipped config disables Flask's debug mode.

    Debug mode can enable the Werkzeug debugger, which allows code execution
    for anyone who can reach an error page.
    """
    server = yaml.safe_load(CONFIG_PATH.read_text())["server"]
    assert server["debug"] is False


def test_operations_routed_to_package() -> None:
    """All operations are routed to the controllers of the installed package.

    Each operation names `drs_filer.ga4gh.drs.server` itself: FOCA's
    `add_operation_fields` doesn't change fields that operations set, and
    `ga4gh.drs.server` is importable only from the package directory, not
    from an installed package.
    """
    specs = yaml.safe_load(CONFIG_PATH.read_text())["api"]["specs"]
    paths = [path for spec in specs for path in spec["path"]]
    assert paths
    for path in paths:
        spec = yaml.safe_load((CONFIG_PATH.parent / path).read_text())
        operations = [
            operation
            for path_item in spec["paths"].values()
            for method, operation in path_item.items()
            if method in METHODS
        ]
        assert operations, path
        for operation in operations:
            controller = operation.get("x-swagger-router-controller")
            assert controller == "drs_filer.ga4gh.drs.server", (
                path,
                operation["operationId"],
            )


def test_dev_overlay() -> None:
    """The Compose overlay builds URLs of the host it publishes the app on.

    It changes nothing else, so that it keeps Flask's debug mode off.
    """
    overlay = yaml.safe_load(DEV_OVERLAY_PATH.read_text())
    assert overlay == {
        "endpoints": {
            "url_prefix": "http",
            "external_host": "localhost",
            "external_port": 8080,
        },
    }


def test_id_charsets_literal() -> None:
    """Identifiers are drawn from the characters of the shipped config.

    The characters are listed themselves (no expression), and are those that
    earlier versions evaluated `string.ascii_letters + string.digits +
    ".-_~"` to: letters, digits and the unreserved characters of URLs.
    """
    endpoints = yaml.safe_load(CONFIG_PATH.read_text())["endpoints"]
    expected = string.ascii_letters + string.digits + ".-_~"
    for section in ("objects", "access_methods"):
        assert endpoints[section]["id_charset"] == expected
        assert endpoints[section]["id_length"] == 6
