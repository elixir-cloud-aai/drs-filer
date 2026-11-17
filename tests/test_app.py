"""Tests of the app factory (`drs_filer.app`)."""

import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import yaml
from foca.config.config_parser import ConfigParser

from drs_filer import app as app_module

PACKAGE_DIR = Path(app_module.__file__).resolve().parent


def _create_app(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Create the app with FOCA's config parsing, but without a database.

    Args:
        monkeypatch: Fixture to patch the app module with.

    Returns:
        What FOCA got: the config file (`file`, and its content, `content`,
        read when FOCA parsed it), the working directory (`cwd`), and the
        parsed config (`config`).
    """
    calls: Dict[str, Any] = {}

    def foca(config_file: Path) -> MagicMock:
        calls["file"] = Path(config_file)
        calls["content"] = yaml.safe_load(Path(config_file).read_text())
        calls["cwd"] = Path.cwd()
        calls["config"] = ConfigParser(
            config_file=config_file, format_logs=False
        ).config
        return MagicMock()

    monkeypatch.setattr(app_module, "Foca", foca)
    monkeypatch.setattr(app_module, "RegisterServiceInfo", MagicMock())
    app_module.create_app()
    return calls


def _write(path: Path, content: Dict[str, Any]) -> str:
    """Write a config overlay.

    Args:
        path: Path of the overlay.
        content: Content of the overlay.

    Returns:
        The path, as a string.
    """
    path.write_text(yaml.safe_dump(content))
    return str(path)


def test_create_app():
    """The app is created from the packaged config, with the service info."""
    with patch.object(app_module, "Foca") as foca, patch.object(
        app_module, "RegisterServiceInfo"
    ) as service_info, patch.dict(os.environ):
        os.environ.pop(app_module.OVERLAY_VARIABLE, None)
        app = app_module.create_app()
    assert foca.call_args.kwargs["config_file"] == PACKAGE_DIR / "config.yaml"
    assert app is foca.return_value.create_app.return_value
    service_info.return_value.set_service_info_from_config.assert_called_once()


def test_create_app_any_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The API specifications are found from any working directory.

    Their paths in the config are relative to the package, so that the
    installed package (e.g., in the image) works without a particular
    working directory; the working directory is restored afterwards.

    Args:
        monkeypatch: Fixture to change the working directory with.
        tmp_path: Working directory without the specifications.
    """
    monkeypatch.delenv(app_module.OVERLAY_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    calls = _create_app(monkeypatch)
    assert calls["cwd"] == PACKAGE_DIR
    paths: List[Path] = [
        path for spec in calls["config"].api.specs for path in spec.path
    ]
    assert paths
    for path in paths:
        assert path.is_file()
        assert path.is_relative_to(PACKAGE_DIR / "api")
    assert Path.cwd() == tmp_path


def test_create_app_overlays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Overlays from `FOCA_CONFIG_OVERLAY` are merged into the config.

    As in later FOCA versions: in order, separated by `:`; mappings are
    merged recursively, other values (including lists) replaced. The merged
    config is removed once FOCA has parsed it.

    Args:
        monkeypatch: Fixture to set the overlays with.
        tmp_path: Directory of the overlays.
    """
    first = _write(
        tmp_path / "first.yaml",
        {
            "endpoints": {
                "external_host": "first.example.org",
                "external_port": 8443,
            },
            "exceptions": {"required_members": [["status_code"], ["msg"]]},
        },
    )
    second = _write(
        tmp_path / "second.yaml",
        {"endpoints": {"external_host": "localhost"}, "db": {"host": "db"}},
    )
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, f"{first}::{second}:")
    calls = _create_app(monkeypatch)
    content = calls["content"]
    assert content["endpoints"]["external_host"] == "localhost"
    assert content["endpoints"]["external_port"] == 8443
    assert content["endpoints"]["api_path"] == "ga4gh/drs/v1"
    assert content["exceptions"]["required_members"] == [["status_code"], ["msg"]]
    assert content["exceptions"]["status_member"] == ["status_code"]
    assert calls["config"].db.host == "db"
    assert calls["cwd"] == PACKAGE_DIR
    assert not calls["file"].exists()


def test_create_app_overlay_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """An empty overlay changes nothing.

    Args:
        monkeypatch: Fixture to set the overlay with.
        tmp_path: Directory of the overlay.
    """
    overlay = tmp_path / "empty.yaml"
    overlay.write_text("")
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, str(overlay))
    calls = _create_app(monkeypatch)
    assert calls["content"] == yaml.safe_load(
        (PACKAGE_DIR / "config.yaml").read_text()
    )


def test_create_app_overlay_not_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """An overlay that isn't a mapping is refused.

    Args:
        monkeypatch: Fixture to set the overlay with.
        tmp_path: Directory of the overlay.
    """
    overlay = tmp_path / "list.yaml"
    overlay.write_text("- a\n- b\n")
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, str(overlay))
    with pytest.raises(ValueError, match="list.yaml"):
        _create_app(monkeypatch)


def test_create_app_overlay_relative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Relative overlay paths are relative to the working directory.

    Not to the package directory, in which FOCA parses the config: a local
    `config.yaml` overlay is read, not the package's base config.

    Args:
        monkeypatch: Fixture to set the overlay and working directory with.
        tmp_path: Working directory with the overlay.
    """
    _write(tmp_path / "config.yaml", {"endpoints": {"external_host": "local"}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, "config.yaml")
    calls = _create_app(monkeypatch)
    assert calls["content"]["endpoints"]["external_host"] == "local"
    assert Path.cwd() == tmp_path


@pytest.mark.parametrize("overlays", ["", ":", "::"])
def test_create_app_no_overlays(monkeypatch: pytest.MonkeyPatch, overlays: str):
    """Without overlay paths, FOCA parses the packaged config itself.

    Args:
        monkeypatch: Fixture to set the overlays with.
        overlays: Value of `FOCA_CONFIG_OVERLAY` without paths.
    """
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, overlays)
    calls = _create_app(monkeypatch)
    assert calls["file"] == PACKAGE_DIR / "config.yaml"


def test_create_app_overlay_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A missing overlay fails the start, naming the file.

    A typo in a deployment's overlay path must not start the app with the
    base config (e.g., the wrong public URL).

    Args:
        monkeypatch: Fixture to set the overlay with.
        tmp_path: Directory without the overlay.
    """
    monkeypatch.setenv(app_module.OVERLAY_VARIABLE, str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        _create_app(monkeypatch)


def test_merge():
    """Mappings are merged recursively; other values replace the base's."""
    base = {"a": {"b": 1, "c": [1, 2]}, "d": {"e": 1}, "f": 1}
    overlay = {"a": {"c": [3], "g": 2}, "d": None, "h": {"i": 1}}
    assert app_module._merge(base, overlay) == {
        "a": {"b": 1, "c": [3], "g": 2},
        "d": None,
        "f": 1,
        "h": {"i": 1},
    }
    # The base is left as is
    assert base == {"a": {"b": 1, "c": [1, 2]}, "d": {"e": 1}, "f": 1}


def test_main():
    """The development server runs the app on the configured port."""
    app = MagicMock()
    with patch.object(app_module, "create_app", return_value=app):
        app_module.main()
    app.run.assert_called_once_with(port=app.port)
