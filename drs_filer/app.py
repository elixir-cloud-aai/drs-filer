"""App factory, and entry point for development.

The image serves the app with Gunicorn (`drs_filer.app:create_app()`, see
`drs_filer.gunicorn_config`); `python app.py` (in `drs_filer/`) runs it with
Flask's development server, for development only.
"""

import logging
from pathlib import Path

from connexion import App
from foca import Foca

from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo

logger = logging.getLogger(__name__)


def create_app() -> App:
    """Create the app from the config, and register the service info.

    The config (`config.yaml` next to this module) is found independently of
    the working directory; the paths of the API specifications in the config
    are relative to the working directory, though, so the app must be started
    in `drs_filer/` (as the image does). Gunicorn calls this in each worker,
    after forking (MongoDB clients must not be shared across forks).

    Returns:
        Connexion app.
    """
    foca = Foca(config_file=Path(__file__).resolve().parent / "config.yaml")
    app = foca.create_app()
    with app.app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    return app


def main() -> None:
    """Run the app with Flask's development server, on the configured port.

    For development only; not for production.
    """
    app = create_app()
    app.run(port=app.port)


if __name__ == '__main__':  # pragma: no cover
    main()
