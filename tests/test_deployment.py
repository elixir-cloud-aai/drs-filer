"""Tests of the deployment files: Docker Compose and the Helm chart.

They check the contract with the app: the config overlays that Compose and
the chart pass in `FOCA_CONFIG_OVERLAY`, and what Compose publishes.
"""

from pathlib import Path
import shutil
import subprocess
from typing import Any

from foca.config.config_parser import ConfigParser
import pytest
import yaml

from drs_filer import app as app_module

ROOT = Path(__file__).resolve().parents[1]
HELM = shutil.which("helm")


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


def test_compose_published_on_loopback_only() -> None:
    """Only the app is published, on the host's loopback interface.

    DRS-Filer has no authentication, and MongoDB none in Compose.
    """
    services = _compose()["services"]
    assert services["drs-filer"]["ports"] == ["127.0.0.1:8080:8080"]
    assert "ports" not in services["mongodb"]
    assert services["mongodb"]["image"] == "mongo:7.0"
    assert services["mongodb"]["healthcheck"]
    assert services["drs-filer"]["depends_on"] == {
        "mongodb": {"condition": "service_healthy"}
    }


def _render(*args: str) -> list[dict[str, Any]]:
    """Render the Helm chart.

    Args:
        *args: Further arguments of `helm template` (e.g., `--set`).

    Returns:
        The rendered manifests.
    """
    assert HELM is not None
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [HELM, "template", "drs-filer", str(ROOT / "deployment"), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.mark.skipif(HELM is None, reason="helm not installed")
def test_chart_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The chart's overlay sets the public URL and MongoDB host of the app.

    The Deployment mounts the ConfigMap and points `FOCA_CONFIG_OVERLAY` to
    it, and the app merges it.

    Args:
        monkeypatch: Fixture to change the working directory with.
        tmp_path: Directory for the rendered overlay.
    """
    manifests = _render("--set", "host_name=drs.example.org")
    (config_map,) = [
        m
        for m in manifests
        if m["kind"] == "ConfigMap" and m["metadata"]["name"] == "drs-filer-config"
    ]
    (deployment,) = [
        m
        for m in manifests
        if m["kind"] == "Deployment" and m["metadata"]["name"] == "drs-filer"
    ]
    pod = deployment["spec"]["template"]["spec"]
    (container,) = pod["containers"]
    env = {e["name"]: e["value"] for e in container["env"]}
    path = Path(env[app_module.OVERLAY_VARIABLE])
    (mount,) = container["volumeMounts"]
    assert Path(mount["mountPath"]) == path.parent
    assert mount["readOnly"] is True
    (volume,) = [v for v in pod["volumes"] if v["name"] == mount["name"]]
    assert volume["configMap"]["name"] == "drs-filer-config"
    assert path.name in [item["path"] for item in volume["configMap"]["items"]]

    overlay = tmp_path / path.name
    overlay.write_text(config_map["data"][path.name])
    config = ConfigParser.merge_yaml(app_module.CONFIG_FILE, overlay)
    assert config["endpoints"]["url_prefix"] == "https"
    assert config["endpoints"]["external_host"] == "drs.example.org"
    assert config["endpoints"]["external_port"] == 443
    assert config["db"]["host"] == "mongodb"


@pytest.mark.skipif(HELM is None, reason="helm not installed")
def test_chart_without_config_job() -> None:
    """The chart has no Job, and no service account with cluster roles.

    The Job that wrote the config needed the `admin` cluster role.
    """
    kinds = {m["kind"] for m in _render()}
    assert not kinds & {"Job", "ServiceAccount", "RoleBinding"}
