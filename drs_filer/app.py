"""App factory, and entry point for development.

The image serves the app with Gunicorn (`drs_filer.app:create_app()`, see
`drs_filer.gunicorn_config`); `python -m drs_filer.app` runs it with Flask's
development server, for development only.
"""

from pathlib import Path

from connexion import App
from foca import Foca, get_config
from foca.config.config_parser import CONFIG_OVERLAY_ENV_VAR

from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo

# The package, with the base config and the API specifications
PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PACKAGE_DIR / "config.yaml"
# Config overlays, separated by `:`, merged by FOCA
OVERLAY_VARIABLE = CONFIG_OVERLAY_ENV_VAR
# Model of the app's own config section (`custom`), validated by FOCA
CUSTOM_CONFIG_MODEL = "drs_filer.custom_config.CustomConfig"
# Sections of earlier versions, which would be ignored, and what replaced them
REMOVED_SECTIONS = {
    "endpoints": (
        "the config section 'endpoints' was replaced: set the public URL in "
        "'custom.service', identifiers in 'custom.objects.id' and "
        "'custom.access_methods.id' ('charset' and 'length'), and the service "
        "info in 'service_info.service' (see 'Upgrading' in the documentation)"
    ),
}


def check_removed_sections() -> None:
    """Fail on config sections of earlier versions, which would be ignored.

    FOCA keeps sections that it doesn't know as untyped extra fields, so a
    config overlay of an earlier version would silently leave the defaults
    in place (e.g., the public URL and the placeholder service info).

    Raises:
        ValueError: The config has a section of an earlier version (cf.
            `REMOVED_SECTIONS`).
    """
    extra = get_config().model_extra or {}
    removed = sorted(REMOVED_SECTIONS.keys() & extra.keys())
    if removed:
        reasons = "; ".join(REMOVED_SECTIONS[section] for section in removed)
        raise ValueError(f"Invalid config: {reasons}")


def create_app() -> App:
    """Create the app from the config, and register the service info.

    FOCA validates the config, including the app's own section (`custom`,
    against `drs_filer.custom_config.CustomConfig`) and the service info
    (`service_info`), so that invalid settings (e.g., character sets of
    identifiers given as expressions, or unknown keys) fail the start; so do
    sections of earlier versions (`check_removed_sections()`). The service
    info of the config (with the version of the package, unless set) then
    replaces the stored one. The config is the package's `config.yaml`, with
    the overlays of `FOCA_CONFIG_OVERLAY` merged into it by FOCA, if any
    (separated by `:`, in order; relative paths of overlays are relative to
    the working directory). FOCA resolves the relative paths of the API
    specifications against the package directory, whatever the working
    directory (e.g., of Gunicorn in the image). Gunicorn calls this in each
    worker, after forking (MongoDB clients must not be shared across forks).

    Returns:
        Connexion app.

    Raises:
        ValueError: The custom config is invalid (FOCA raises it from a
            `ValueError` that names the invalid setting and the reason), or
            the config has a section of an earlier version.
        pydantic.ValidationError: FOCA's config is invalid, e.g., the
            service info.
    """
    app = Foca(
        config_file=CONFIG_FILE, custom_config_model=CUSTOM_CONFIG_MODEL
    ).create_app()
    with app.app.app_context():
        check_removed_sections()
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
