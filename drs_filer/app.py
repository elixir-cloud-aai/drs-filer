"""App factory, and entry point for development.

The image serves the app with Gunicorn (`drs_filer.app:create_app()`, see
`drs_filer.gunicorn_config`); `python -m drs_filer.app` runs it with Flask's
development server, for development only.
"""

from pathlib import Path

from connexion import App
from flask import Response, current_app, request
from foca import Foca, get_config
from foca.api.service_info import get_service_info as get_config_service_info
from foca.config.config_parser import CONFIG_OVERLAY_ENV_VAR

from drs_filer.ga4gh.drs.endpoints.service_info import (
    SERVICE_TYPE,
    RegisterServiceInfo,
)

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
        "the config section 'endpoints' was replaced: set the public host "
        "name in 'custom.drs.hostname', identifiers in 'custom.objects.id' and "
        "'custom.access_methods.id' ('charset' and 'length'), and the service "
        "info in 'service_info.service' (see 'Upgrading' in the documentation)"
    ),
}


def check_removed_sections() -> None:
    """Fail on config sections of earlier versions, which would be ignored.

    FOCA keeps sections that it doesn't know as untyped extra fields, so a
    config overlay of an earlier version would silently leave the defaults
    in place (e.g., the placeholder service info).

    Raises:
        ValueError: The config has a section of an earlier version (cf.
            `REMOVED_SECTIONS`).
    """
    extra = get_config().model_extra or {}
    removed = sorted(REMOVED_SECTIONS.keys() & extra.keys())
    if removed:
        reasons = "; ".join(REMOVED_SECTIONS[section] for section in removed)
        raise ValueError(f"Invalid config: {reasons}")


def check_service_type() -> None:
    """Fail on service info of another type than the API that the app serves.

    `GET /service-info` serves `DrsService` (DRS 1.5.0), whose
    `type.artifact` is `drs`; FOCA validates the service info against the
    GA4GH `Service` schema only, so that other artifacts would fail every
    response instead of the start, and other groups or versions would
    describe another API to clients and registries.

    Raises:
        ValueError: `service_info.service.type` isn't `SERVICE_TYPE`.
    """
    service_type = get_config_service_info()["type"]
    if service_type != SERVICE_TYPE:
        raise ValueError(
            "Invalid config: 'service_info.service.type' must be "
            f"{SERVICE_TYPE}, the type of the API that DRS-Filer serves, "
            f"not {service_type}"
        )


def answer_cors_preflight() -> Response | None:
    """Answer CORS preflight requests before the API operations do.

    DRS defines `OPTIONS` operations (the authorization info of objects),
    which DRS-Filer answers with `501` (until #98), and which would get the
    preflight requests of browsers too. These get Flask's default answer,
    with the CORS headers that FOCA adds (if CORS is enabled), as for paths
    without `OPTIONS` operations. Registered with `before_request`.

    Returns:
        Flask's default response to `OPTIONS` (`200`, with `Allow`) for
        preflight requests (`OPTIONS` with `Origin` and
        `Access-Control-Request-Method`) to known paths, `None` for other
        requests, which are routed as usual (unknown paths get `404`).
    """
    if (
        request.method == "OPTIONS"
        and request.url_rule is not None
        and "Origin" in request.headers
        and "Access-Control-Request-Method" in request.headers
    ):
        return current_app.make_default_options_response()
    return None


def create_app() -> App:
    """Create the app from the config, and register the service info.

    FOCA validates the config, including the app's own section (`custom`,
    against `drs_filer.custom_config.CustomConfig`) and the service info
    (`service_info`), so that invalid settings (e.g., character sets of
    identifiers given as expressions, or unknown keys) fail the start; so do
    sections of earlier versions (`check_removed_sections()`) and service
    info of another type than DRS (`check_service_type()`). The service
    info of the config (with the version of the package, unless set) then
    replaces the stored one. CORS preflight requests are answered before
    the API operations (`answer_cors_preflight()`). The config is the
    package's `config.yaml`, with the overlays of `FOCA_CONFIG_OVERLAY`
    merged into it by FOCA, if any (separated by `:`, in order; relative
    paths of overlays are relative to the working directory). FOCA resolves
    the relative paths of the API specifications against the package
    directory, whatever the working directory (e.g., of Gunicorn in the
    image). Gunicorn calls this in each worker, after forking (MongoDB
    clients must not be shared across forks).

    Returns:
        Connexion app.

    Raises:
        ValueError: The section `custom` is invalid (the error's cause names
            the invalid setting and the reason, not the value), the
            config has a section of an earlier version, or the service info
            isn't of type `drs`.
        pydantic.ValidationError: A section of FOCA is invalid, e.g., the
            service info.
        RuntimeError: No service info is configured (e.g., an overlay sets
            `service_info: null`).
    """
    app = Foca(
        config_file=CONFIG_FILE, custom_config_model=CUSTOM_CONFIG_MODEL
    ).create_app()
    with app.app.app_context():
        check_removed_sections()
        check_service_type()
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    app.app.before_request(answer_cors_preflight)
    return app


def main() -> None:
    """Run the app with Flask's development server, on the configured port.

    For development only; not for production.
    """
    app = create_app()
    app.run(port=app.port)


if __name__ == "__main__":  # pragma: no cover
    main()
