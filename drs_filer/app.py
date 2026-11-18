"""App factory, and entry point for development.

The image serves the app with Gunicorn (`drs_filer.app:create_app()`, see
`drs_filer.gunicorn_config`); `python -m drs_filer.app` runs it with Flask's
development server, for development only.
"""

from pathlib import Path

from connexion import App
from foca import Foca
from foca.config.config_parser import CONFIG_OVERLAY_ENV_VAR

from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo
from drs_filer.utils import check_id_settings

# The package, with the base config and the API specifications
PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PACKAGE_DIR / "config.yaml"
# Config overlays, separated by `:`, merged by FOCA
OVERLAY_VARIABLE = CONFIG_OVERLAY_ENV_VAR


def create_app() -> App:
    """Create the app from the config, and register the service info.

    Settings of generated identifiers are checked first, so that invalid
    ones (e.g., character sets given as expressions) fail the start. The
    config is the package's `config.yaml`, with the overlays of
    `FOCA_CONFIG_OVERLAY` merged into it by FOCA, if any (separated by `:`, in
    order; relative paths of overlays are relative to the working directory).
    FOCA resolves the relative paths of the API specifications against the
    package directory, whatever the working directory (e.g., of Gunicorn in
    the image). Gunicorn calls this in each worker, after forking (MongoDB
    clients must not be shared across forks).

    Returns:
        Connexion app.

    Raises:
        KeyError: Settings of generated identifiers are missing.
        ValueError: Settings of generated identifiers are invalid.
    """
    app = Foca(config_file=CONFIG_FILE).create_app()
    with app.app.app_context():
        check_id_settings()
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    return app


def main() -> None:
    """Run the app with Flask's development server, on the configured port.

    For development only; not for production.
    """
    app = create_app()
    app.run(port=app.port)


if __name__ == "__main__":  # pragma: no cover
    main()
