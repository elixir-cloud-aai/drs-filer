"""Tests of the shipped app config and the Compose overlay."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "drs_filer" / "config.yaml"
DEV_OVERLAY_PATH = ROOT / "config.dev.yaml"


def test_debug_mode_off() -> None:
    """The shipped config disables Flask's debug mode.

    Debug mode can enable the Werkzeug debugger, which allows code execution
    for anyone who can reach an error page.
    """
    server = yaml.safe_load(CONFIG_PATH.read_text())["server"]
    assert server["debug"] is False
    assert server["environment"] == "production"


def test_operations_routed_to_package() -> None:
    """All operations are routed to the controllers of the installed package.

    The vendored specifications name `ga4gh.drs.server`, which is importable
    only from the package directory, not from an installed package.
    """
    specs = yaml.safe_load(CONFIG_PATH.read_text())["api"]["specs"]
    assert specs
    for spec in specs:
        assert spec["add_operation_fields"] == {
            "x-swagger-router-controller": "drs_filer.ga4gh.drs.server",
        }


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
