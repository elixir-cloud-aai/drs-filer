"""Tests of the Docker Compose file.

They check the contract with the app: the config overlay that Compose passes
in `FOCA_CONFIG_OVERLAY`, and what Compose publishes. The Helm chart has its
own tests (`tests/test_chart.py`).
"""

from pathlib import Path
from typing import Any

import yaml

from drs_filer import app as app_module

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict[str, Any]:
    """Load the Compose file.

    Returns:
        Its content.
    """
    return yaml.safe_load((ROOT / "docker-compose.yaml").read_text())


def test_compose_overlay_mounted() -> None:
    """Compose's default overlay is the mounted `config.dev.yaml`."""
    service = _compose()["services"]["drs-filer"]
    default = service["environment"][app_module.OVERLAY_VARIABLE]
    assert default.startswith("${DRS_FILER_CONFIG_OVERLAY:-")
    path = default.removeprefix("${DRS_FILER_CONFIG_OVERLAY:-").removesuffix("}")
    assert f"./config.dev.yaml:{path}:ro" in service["volumes"]


def test_compose_noauth_overlay_mounted() -> None:
    """`config.noauth.yaml` is mounted next to `config.dev.yaml`.

    So that `DRS_FILER_CONFIG_OVERLAY` can add it (see "Running without
    authentication" in `docs/development.md`).
    """
    volumes = _compose()["services"]["drs-filer"]["volumes"]
    assert "./config.noauth.yaml:/etc/drs-filer/config.noauth.yaml:ro" in volumes
    assert (ROOT / "config.noauth.yaml").is_file()


def test_compose_published_on_loopback_only() -> None:
    """Only the app is published, on the host's loopback interface.

    The development settings accept tokens for any audience, the overlay
    `config.noauth.yaml` disables authentication, and MongoDB has none in
    Compose.
    """
    services = _compose()["services"]
    assert services["drs-filer"]["ports"] == ["127.0.0.1:8080:8080"]
    assert "ports" not in services["mongodb"]
    assert services["mongodb"]["image"] == "mongo:7.0"
    assert services["mongodb"]["healthcheck"]
    assert services["drs-filer"]["depends_on"] == {
        "mongodb": {"condition": "service_healthy"}
    }
