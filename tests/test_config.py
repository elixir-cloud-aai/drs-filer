"""Tests of the shipped app config (`drs_filer/config.yaml`)."""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "drs_filer" / "config.yaml"


def test_debug_mode_off():
    """The shipped config disables Flask's debug mode.

    Debug mode can enable the Werkzeug debugger, which allows code execution
    for anyone who can reach an error page.
    """
    server = yaml.safe_load(CONFIG_PATH.read_text())["server"]
    assert server["debug"] is False
    assert server["environment"] == "production"
