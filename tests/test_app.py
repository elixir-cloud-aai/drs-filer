"""Tests of the app factory (`drs_filer.app`)."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from foca import get_config
from pymongo import MongoClient
import pytest
import yaml

from drs_filer import app as app_module
from drs_filer.custom_config import DEFAULT_ID_CHARSET, CustomConfig
from drs_filer.utils import get_custom_config
from tests.conftest import CONFIG_OVERLAY

PACKAGE_DIR = Path(app_module.__file__).resolve().parent


def _write(path: Path, content: dict[str, Any]) -> str:
    """Write a config overlay.

    Args:
        path: Path of the overlay.
        content: Content of the overlay.

    Returns:
        The path, as a string.
    """
    path.write_text(yaml.safe_dump(content))
    return str(path)


def test_create_app() -> None:
    """The app is created from the packaged config, with the service info.

    FOCA validates the custom config against the app's model; sections of
    earlier versions are checked on startup, and whether access URLs need
    login is read from the specification.
    """
    with (
        patch.object(app_module, "Foca") as foca,
        patch.object(app_module, "RegisterServiceInfo") as service_info,
        patch.object(app_module, "check_removed_sections") as check_removed,
        patch.object(app_module, "access_urls_need_login") as need_login,
        patch.object(app_module, "object_reads_need_login") as reads_need_login,
        # ast-grep-ignore: pydantic-v1-dict
        patch.dict(os.environ),
    ):
        os.environ.pop(app_module.OVERLAY_VARIABLE, None)
        app = app_module.create_app()
    assert foca.call_args.kwargs == {
        "config_file": PACKAGE_DIR / "config.yaml",
        "custom_config_model": "drs_filer.custom_config.CustomConfig",
    }
    assert app is foca.return_value.create_app.return_value
    service_info.return_value.set_service_info_from_config.assert_called_once()
    check_removed.assert_called_once_with()
    need_login.assert_called_once_with()
    reads_need_login.assert_called_once_with()


def test_create_app_custom_config(
    monkeypatch: pytest.MonkeyPatch, mongo_client: MongoClient[dict[str, Any]]
) -> None:
    """The custom config of the app is typed (`CustomConfig`).

    Args:
        monkeypatch: Fixture to set the test overlay with (the settings
            each deployment must make).
        mongo_client: MongoDB client of the app.
    """
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, str(CONFIG_OVERLAY))
    app = app_module.create_app()
    with app.app.app_context():
        assert isinstance(get_custom_config(), CustomConfig)


def test_overlay_variable() -> None:
    """The overlays are those of FOCA's variable `FOCA_CONFIG_OVERLAY`."""
    assert app_module.OVERLAY_VARIABLE == "FOCA_CONFIG_OVERLAY"


def test_create_app_any_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mongo_client: MongoClient[dict[str, Any]],
) -> None:
    """The API specifications are found from any working directory.

    Their paths in the config are relative to the package, which FOCA
    resolves them against, so that the installed package (e.g., in the
    image) works without a particular working directory.

    Args:
        monkeypatch: Fixture to change the working directory with.
        tmp_path: Working directory without the specifications.
        mongo_client: MongoDB client of the app.
    """
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, str(CONFIG_OVERLAY))
    monkeypatch.chdir(tmp_path)
    app = app_module.create_app()
    with app.app.app_context():
        paths = [
            path
            for spec in get_config().api.specs
            for path in (spec.path if isinstance(spec.path, list) else [spec.path])
        ]
    assert paths
    for path in paths:
        assert Path(path).is_file()
        assert Path(path).is_relative_to(PACKAGE_DIR / "api")
    assert Path.cwd() == tmp_path


def test_create_app_overlays(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mongo_client: MongoClient[dict[str, Any]],
) -> None:
    """Overlays from `FOCA_CONFIG_OVERLAY` are merged into the config.

    In order, separated by `:` (empty entries skipped); mappings are merged
    recursively, other values replaced.

    Args:
        monkeypatch: Fixture to set the overlays with.
        tmp_path: Directory of the overlays.
        mongo_client: MongoDB client of the app.
    """
    first = _write(
        tmp_path / "first.yaml",
        {
            "custom": {
                "drs": {"hostname": "first.example.org"},
                "objects": {"id": {"length": 8}},
            },
        },
    )
    second = _write(
        tmp_path / "second.yaml",
        {"custom": {"drs": {"hostname": "localhost"}}, "db": {"host": "db"}},
    )
    monkeypatch.setenv(
        app_module.OVERLAY_VARIABLE, f"{CONFIG_OVERLAY}:{first}::{second}:"
    )
    app = app_module.create_app()
    with app.app.app_context():
        config = get_config()
        custom = get_custom_config()
    assert custom.drs.hostname == "localhost"
    assert custom.objects.id.length == 8
    assert custom.objects.id.charset == DEFAULT_ID_CHARSET
    assert config.db is not None
    assert config.db.host == "db"


def test_main() -> None:
    """The development server runs the app on the configured port."""
    app = MagicMock()
    with patch.object(app_module, "create_app", return_value=app):
        app_module.main()
    app.run.assert_called_once_with(port=app.port)
