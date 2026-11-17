"""App factory, and entry point for development.

The image serves the app with Gunicorn (`drs_filer.app:create_app()`, see
`drs_filer.gunicorn_config`); `python -m drs_filer.app` runs it with Flask's
development server, for development only.
"""

from collections.abc import Mapping
import contextlib
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from connexion import App
from foca import Foca
import yaml

from drs_filer.ga4gh.drs.endpoints.service_info import RegisterServiceInfo

logger = logging.getLogger(__name__)

# The package, with the base config and the API specifications
PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PACKAGE_DIR / "config.yaml"
# Config overlays, separated by `:`, as in later FOCA versions, which merge
# them themselves: remove `_merge()`, `_merged_config()` and the temporary
# config of `_foca()` with the FOCA upgrade (#87)
OVERLAY_VARIABLE = "FOCA_CONFIG_OVERLAY"


def _merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Merge a config overlay into a config.

    Mappings are merged recursively; all other values of the overlay,
    including lists and `null`, replace those of the base.

    Args:
        base: Config; left as is.
        overlay: Overlay.

    Returns:
        The merged config.
    """
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merged_config(overlays: str) -> dict[str, Any]:
    """Get the base config with overlays merged into it.

    Args:
        overlays: Paths of the overlays, separated by `:`, in the order in
            which they are merged; empty paths are skipped. Relative paths
            are relative to the working directory.

    Returns:
        The merged config.

    Raises:
        ValueError: An overlay is not a mapping.
    """
    config = yaml.safe_load(CONFIG_FILE.read_text())
    for path in filter(None, overlays.split(":")):
        overlay = yaml.safe_load(Path(path).read_text())
        if overlay is None:
            continue
        if not isinstance(overlay, Mapping):
            raise ValueError(f"Config overlay '{path}' is not a mapping")
        config = _merge(config, overlay)
    return config


def _foca() -> Foca:
    """Parse the config, with the overlays of `FOCA_CONFIG_OVERLAY`, if any.

    FOCA 0.13 resolves the relative paths of the API specifications against
    the working directory when it parses the config, so it parses it in the
    package directory: the paths are relative to the package, whatever the
    working directory (e.g., of Gunicorn in the image). The overlays are read
    before, so that their relative paths are relative to the working
    directory. FOCA 0.13 reads its config from a file only, so a config with
    overlays is merged into a temporary file, which is removed once FOCA has
    parsed it.

    Returns:
        FOCA, with the parsed config.
    """
    overlays = os.environ.get(OVERLAY_VARIABLE, "")
    if not overlays.strip(":"):
        with contextlib.chdir(PACKAGE_DIR):
            return Foca(config_file=CONFIG_FILE)
    config = _merged_config(overlays)
    with tempfile.NamedTemporaryFile(
        "w", prefix="drs-filer-config-", suffix=".yaml"
    ) as merged:
        yaml.safe_dump(config, merged)
        merged.flush()
        with contextlib.chdir(PACKAGE_DIR):
            foca = Foca(config_file=Path(merged.name))
    # Logged once FOCA has configured logging
    logger.info("Config overlays merged: %s", overlays)
    return foca


def create_app() -> App:
    """Create the app from the config, and register the service info.

    The config is the package's `config.yaml`, with the overlays of
    `FOCA_CONFIG_OVERLAY` merged into it, if any. Gunicorn calls this in each
    worker, after forking (MongoDB clients must not be shared across forks).

    Returns:
        Connexion app.
    """
    app = _foca().create_app()
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


if __name__ == "__main__":  # pragma: no cover
    main()
