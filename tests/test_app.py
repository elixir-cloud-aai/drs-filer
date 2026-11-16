"""Tests of the app factory (`drs_filer.app`)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from drs_filer import app as app_module


def test_create_app():
    """The app is created from the packaged config, with the service info.

    The config path does not depend on the working directory, so that
    Gunicorn can import the app from anywhere.
    """
    with patch.object(app_module, "Foca") as foca, patch.object(
        app_module, "RegisterServiceInfo"
    ) as service_info:
        app = app_module.create_app()
    config_file = Path(foca.call_args.kwargs["config_file"])
    assert config_file.is_absolute()
    assert config_file == (
        Path(app_module.__file__).resolve().parent / "config.yaml"
    )
    assert app is foca.return_value.create_app.return_value
    service_info.return_value.set_service_info_from_config.assert_called_once()


def test_main():
    """The development server runs the app on the configured port."""
    app = MagicMock()
    with patch.object(app_module, "create_app", return_value=app):
        app_module.main()
    app.run.assert_called_once_with(port=app.port)
