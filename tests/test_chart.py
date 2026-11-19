"""Tests of the Helm chart (`deployment/`), a thin chart on FOCA's library chart.

They render the chart with `helm template`. Without Helm, they are skipped,
except in CI (`CI` set), where they fail: GitHub's Ubuntu runners have Helm.
The library chart (`foca-common`) must be downloaded first (`helm dependency
build deployment`), or they fail.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from typing import Any

from foca.config.config_parser import ConfigParser
import pytest
import yaml

from drs_filer import app as app_module
from drs_filer.custom_config import CustomConfig

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment"
# Values of CI's lint: a host name and the Secret of MongoDB's credentials
TEST_VALUES = CHART / "ci" / "test-values.yaml"
HELM = shutil.which("helm")
RELEASE = "drs-filer"
# Names of the app's and MongoDB's resources of the release `drs-filer`
APP = "drs-filer"
MONGODB = "drs-filer-mongodb"
HOST = "drs.example.org"
SECRET = "drs-filer-mongodb-credentials"  # noqa: S105 (a Secret's name)
ROUTE_API = ("--api-versions", "route.openshift.io/v1")
OPENSHIFT_API = ("--api-versions", "security.openshift.io/v1")
NO_INGRESS = ("--set", "drsFiler.ingress.enabled=false")
LIBRARY = "foca-common"

pytestmark = pytest.mark.skipif(
    HELM is None and not os.environ.get("CI"), reason="Helm is not installed"
)

Manifest = dict[str, Any]


def helm_template(chart: Path, *args: str, release: str = RELEASE) -> str:
    """Render a chart with `helm template`, with the values of CI's lint.

    Args:
        chart: Directory of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.
        release: Name of the release.

    Returns:
        The rendered manifests.

    Raises:
        RuntimeError: The library chart is missing.
    """
    assert HELM is not None, "Helm is not installed"
    if not list((chart / "charts").glob(f"{LIBRARY}-*.tgz")):
        raise RuntimeError(
            "The library chart is missing: run `helm dependency build deployment`"
        )
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [
            HELM,
            "template",
            release,
            str(chart),
            "--namespace",
            "drs",
            "--values",
            str(TEST_VALUES),
            *args,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def render(*args: str, release: str = RELEASE) -> list[Manifest]:
    """Render the chart's resources.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.
        release: Name of the release.

    Returns:
        The rendered resources.
    """
    rendered = helm_template(CHART, *args, release=release)
    return [doc for doc in yaml.safe_load_all(rendered) if doc]


def render_error(*args: str) -> str:
    """Render the chart, expecting Helm to fail.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        Helm's error output.
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        helm_template(CHART, *args)
    stderr: str = error.value.stderr
    return stderr


def copy_chart(tmp_path: Path, templates: dict[str, str]) -> Path:
    """Copy the chart, with additional templates.

    Args:
        tmp_path: Directory for the copy of the chart.
        templates: Contents of the additional templates, by file name.

    Returns:
        The copy of the chart.
    """
    chart = tmp_path / "chart"
    shutil.copytree(CHART, chart)
    for name, template in templates.items():
        (chart / "templates" / name).write_text(template, encoding="utf-8")
    return chart


def render_notes(tmp_path: Path, *args: str) -> str:
    """Render the chart's `NOTES.txt`, which `helm template` leaves out.

    A template of a copy of the chart renders `NOTES.txt` into a document.

    Args:
        tmp_path: Directory for the copy of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered notes.
    """
    chart = copy_chart(
        tmp_path,
        {"notes.yaml": 'notes: {{ tpl (.Files.Get "NOTES.raw") . | toJson }}\n'},
    )
    (chart / "templates" / "NOTES.txt").rename(chart / "NOTES.raw")
    manifests = helm_template(chart, "--show-only", "templates/notes.yaml", *args)
    notes: str = yaml.safe_load(manifests)["notes"]
    return notes


def find(resources: list[Manifest], kind: str, name: str) -> Manifest:
    """Get the resource of a kind and name.

    Args:
        resources: Rendered resources.
        kind: Kind of the resource, e.g., `Deployment`.
        name: Name of the resource.

    Returns:
        The resource.
    """
    (resource,) = [
        resource
        for resource in resources
        if resource["kind"] == kind and resource["metadata"]["name"] == name
    ]
    return resource


def of_kind(resources: list[Manifest], kind: str) -> list[Manifest]:
    """Select the resources of a kind.

    Args:
        resources: Rendered resources.
        kind: Kind to select, e.g., `Route`.

    Returns:
        The resources of that kind.
    """
    return [resource for resource in resources if resource["kind"] == kind]


def overlay(resources: list[Manifest], name: str = APP) -> dict[str, Any]:
    """Get the app's config overlay.

    Args:
        resources: Rendered resources.
        name: Name of the app's resources.

    Returns:
        The overlay of the ConfigMap `<app>-config`.
    """
    config_map = find(resources, "ConfigMap", f"{name}-config")
    config: dict[str, Any] = yaml.safe_load(config_map["data"]["overlay.yaml"])
    return config


def pod_spec(resources: list[Manifest], name: str = APP) -> Manifest:
    """Get the pod spec of a Deployment.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        Its pod spec.
    """
    spec: Manifest = find(resources, "Deployment", name)["spec"]["template"]["spec"]
    return spec


def container(resources: list[Manifest], name: str = APP) -> Manifest:
    """Get the container of a Deployment.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        Its only container.
    """
    (only,) = pod_spec(resources, name)["containers"]
    return only


def env(resources: list[Manifest], name: str = APP) -> dict[str, Any]:
    """Get the environment variables of a Deployment's container.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        The variables, by name: their values, or their `valueFrom`.
    """
    return {
        var["name"]: var.get("value", var.get("valueFrom"))
        for var in container(resources, name).get("env", [])
    }


def test_resources() -> None:
    """The chart renders the library's resources, without the config Job.

    No Job, ServiceAccount or RBAC: Helm renders the config overlay.
    """
    resources = render()
    names = {(r["kind"], r["metadata"]["name"]) for r in resources}
    assert names == {
        ("ConfigMap", f"{APP}-config"),
        ("ConfigMap", f"{MONGODB}-init-script"),
        ("Deployment", APP),
        ("Deployment", MONGODB),
        ("Service", APP),
        ("Service", MONGODB),
        ("PersistentVolumeClaim", MONGODB),
        ("NetworkPolicy", MONGODB),
        ("Ingress", APP),
    }
    for resource in resources:
        labels = resource["metadata"]["labels"]
        assert labels["app.kubernetes.io/instance"] == RELEASE
        assert labels["app.kubernetes.io/name"] == "drs-filer"


def test_names_from_release() -> None:
    """Resource names are derived from the release name."""
    resources = render(release="prod")
    assert find(resources, "Deployment", "prod-drs-filer")
    assert find(resources, "Deployment", "prod-drs-filer-mongodb")
    config = overlay(resources, "prod-drs-filer")
    assert config["db"]["host"] == "prod-drs-filer-mongodb"


def test_config_overlay() -> None:
    """The overlay has the host name, MongoDB's host and the `config` value.

    The host name of the `self_uri` of objects (`custom.drs.hostname`) is
    `hostName`.
    """
    config = overlay(render("--set", "config.service_info.service.name=My DRS"))
    assert config["custom"] == {
        "drs": {"hostname": HOST},
    }
    assert config["service_info"] == {"service": {"name": "My DRS"}}
    assert config["db"] == {"host": MONGODB}


def test_overlay_merged_by_app(tmp_path: Path) -> None:
    """The app merges the overlay into its base config, as mounted.

    The Deployment points `FOCA_CONFIG_OVERLAY` to the mounted ConfigMap; the
    merged config has the host name (`custom.drs.hostname`) and the MongoDB
    host, and keeps the defaults of the base config (e.g., the length of
    identifiers).

    Args:
        tmp_path: Directory for the rendered overlay.
    """
    resources = render()
    path = Path(env(resources)[app_module.OVERLAY_VARIABLE])
    (mount,) = [
        mount
        for mount in container(resources)["volumeMounts"]
        if Path(mount["mountPath"]) == path.parent
    ]
    assert mount["readOnly"] is True
    (volume,) = [
        v for v in pod_spec(resources)["volumes"] if v["name"] == mount["name"]
    ]
    assert volume["configMap"]["name"] == f"{APP}-config"

    file = tmp_path / path.name
    file.write_text(yaml.safe_dump(overlay(resources)), encoding="utf-8")
    config = ConfigParser.merge_yaml(app_module.CONFIG_FILE, file)
    custom = CustomConfig(**config["custom"])
    assert custom.drs.hostname == HOST
    assert custom.objects.id.length == 6
    assert config["db"]["host"] == MONGODB


def test_config_overrides_generated() -> None:
    """`config` takes precedence over the generated config, merged by key."""
    config = overlay(
        render(
            "--set",
            "config.custom.drs.hostname=drs.example.net",
            "--set",
            "config.custom.objects.id.length=8",
        )
    )
    assert config["custom"]["drs"] == {"hostname": "drs.example.net"}
    assert config["custom"]["objects"] == {"id": {"length": 8}}


def test_config_custom_null() -> None:
    """`config.custom: null` keeps the generated host name."""
    config = overlay(render("--set-json", "config.custom=null"))
    assert config["custom"]["drs"] == {"hostname": HOST}


@pytest.mark.parametrize(
    "args",
    [
        ("--set", "config.custom.service.external_host=drs.example.org"),
        ("--set-json", "config.custom.service=null"),
    ],
)
def test_config_custom_service_fails(args: tuple[str, ...]) -> None:
    """The public URL of earlier versions, `config.custom.service`, fails.

    The app would fail to start with it; the error names `hostName`, which
    sets the host name of the `self_uri` of objects.

    Args:
        args: Arguments that set `config.custom.service`.
    """
    error = render_error(*args)
    assert "config.custom.service was removed" in error
    assert "hostName" in error


def test_auth_settings() -> None:
    """The overlay has the identity provider and admin group of the values."""
    security = overlay(render())["security"]
    assert security["auth"]["issuers"] == ["https://login.example.org/oidc/"]
    assert security["auth"]["audience"] == ["test-client"]
    assert security["access_control"]["group_mapping"] == {"test-admins": "admin"}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--set-json", "config.security.auth.issuers=[]"), "issuers"),
        (("--set-json", "config.security.auth.audience=null"), "audience"),
        (("--set-json", "config.security.access_control.group_mapping={}"), "admin"),
        (("--set", "config.security.access_control.enforce=false"), "enforce"),
    ],
)
def test_access_control_required(args: tuple[str, ...], message: str) -> None:
    """Rendering fails without what the app needs to start (as on startup).

    Args:
        args: Arguments that unset a required setting.
        message: Expected part of the error.
    """
    assert message in render_error(*args)


def test_access_control_without_admins() -> None:
    """Without required admins, no admin group is needed."""
    resources = render(
        "--set-json",
        "config.security.access_control.group_mapping={}",
        "--set",
        "config.security.access_control.require_admin=false",
    )
    assert overlay(resources)["security"]["access_control"]["require_admin"] is False


def test_deployment() -> None:
    """The app reads the overlay, and MongoDB's app user from the Secret.

    The chart sets no database (`MONGO_DBNAME`): the app uses that of its
    base config (`drsStore`). It trusts no forwarded headers by default.
    """
    resources = render()
    variables = env(resources)
    assert variables["FOCA_CONFIG_OVERLAY"] == "/etc/drs-filer/overlay.yaml"
    assert variables["MONGO_USERNAME"] == {
        "secretKeyRef": {"name": SECRET, "key": "username"}
    }
    assert variables["MONGO_PASSWORD"] == {
        "secretKeyRef": {"name": SECRET, "key": "password"}
    }
    assert variables["GUNICORN_CMD_ARGS"] == (
        "--workers 1 --threads 4 --timeout 30 --graceful-timeout 20 --keep-alive 100"
    )
    for name in ("MONGO_DBNAME", "MONGO_HOST", "FORWARDED_ALLOW_IPS"):
        assert name not in variables
    spec = pod_spec(resources)
    assert spec["automountServiceAccountToken"] is False
    assert "serviceAccountName" not in spec


def test_image() -> None:
    """The image is tagged with `appVersion` (`dev`), unless a tag is set."""
    app = container(render())
    assert app["image"] == "docker.io/elixircloud/drs-filer:dev"
    assert app["imagePullPolicy"] == "Always"
    tagged = container(render("--set", "drsFiler.tag=1.2.3"))
    assert tagged["image"] == "docker.io/elixircloud/drs-filer:1.2.3"


def test_probes() -> None:
    """The app's probes request the Swagger UI."""
    app = container(render())
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert app[probe]["httpGet"] == {"path": "/ga4gh/drs/v1/ui/", "port": 8080}


def test_gunicorn() -> None:
    """The Gunicorn values are passed to the image."""
    variables = env(render("--set", "drsFiler.gunicorn.workers=2"))
    assert variables["GUNICORN_CMD_ARGS"].startswith("--workers 2 ")


def test_extra_env() -> None:
    """`drsFiler.extraEnv` sets further variables, e.g., `FORWARDED_ALLOW_IPS`."""
    extra = [{"name": "FORWARDED_ALLOW_IPS", "value": "192.0.2.0/24"}]
    variables = env(render("--set-json", f"drsFiler.extraEnv={json.dumps(extra)}"))
    assert variables["FORWARDED_ALLOW_IPS"] == "192.0.2.0/24"


def test_extra_env_from() -> None:
    """`drsFiler.extraEnvFrom` passes the keys of Secrets as variables."""
    secret = [{"secretRef": {"name": "drs-filer-extra"}}]
    resources = render("--set-json", f"drsFiler.extraEnvFrom={json.dumps(secret)}")
    assert container(resources)["envFrom"] == secret


def test_extra_env_reserved() -> None:
    """`drsFiler.extraEnv` must not set the chart's variables."""
    extra = [{"name": "FOCA_CONFIG_OVERLAY", "value": "/etc/other.yaml"}]
    error = render_error("--set-json", f"drsFiler.extraEnv={json.dumps(extra)}")
    assert "FOCA_CONFIG_OVERLAY" in error


def test_init_script() -> None:
    """MongoDB's init script creates the app user in the app's database."""
    resources = render()
    config_map = find(resources, "ConfigMap", f"{MONGODB}-init-script")
    script = config_map["data"]["create-app-user.js"]
    assert "getSiblingDB('drsStore').createUser(" in script
    assert "roles: [{ role: 'readWrite', db: 'drsStore' }]" in script


def test_mongodb_auth_needs_secret() -> None:
    """Rendering fails without the Secret of MongoDB's credentials."""
    error = render_error("--set", "mongodb.auth.existingSecret=")
    assert "mongodb.auth.existingSecret" in error


def test_mongodb_auth_disabled() -> None:
    """Without authentication, the chart creates no users and passes none."""
    resources = render(
        "--set", "mongodb.auth.enabled=false", "--set", "mongodb.auth.existingSecret="
    )
    names = [r["metadata"]["name"] for r in of_kind(resources, "ConfigMap")]
    assert names == [f"{APP}-config"]
    assert "MONGO_USERNAME" not in env(resources)


def test_mongodb_persistence() -> None:
    """MongoDB's claim is kept when the release is uninstalled."""
    claim = find(render(), "PersistentVolumeClaim", MONGODB)
    assert claim["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert claim["spec"]["resources"]["requests"]["storage"] == "1Gi"


def test_mongodb_volume_size_deprecated() -> None:
    """`mongodb.volumeSize` of the earlier charts fails with `persistence.size`."""
    assert "volumeSize" in render_error("--set", "mongodb.volumeSize=2Gi")


def test_security_contexts() -> None:
    """The pods run as non-root users, with a read-only root file system."""
    resources = render()
    for name in (APP, MONGODB):
        assert pod_spec(resources, name)["securityContext"]["runAsNonRoot"] is True
        context = container(resources, name)["securityContext"]
        assert context["readOnlyRootFilesystem"] is True
    mongodb = pod_spec(resources, MONGODB)["securityContext"]
    assert mongodb["runAsUser"] == 999
    assert mongodb["fsGroupChangePolicy"] == "OnRootMismatch"


def test_security_contexts_openshift() -> None:
    """On OpenShift, user and group IDs are left to OpenShift."""
    mongodb = pod_spec(render(*OPENSHIFT_API), MONGODB)["securityContext"]
    for key in ("runAsUser", "runAsGroup", "fsGroup"):
        assert key not in mongodb


def test_route_without_ingress() -> None:
    """Without the Ingress, the chart creates a Route on OpenShift."""
    resources = render(*ROUTE_API, *NO_INGRESS)
    assert of_kind(resources, "Ingress") == []
    assert find(resources, "Route", APP)["spec"]["host"] == HOST
    assert of_kind(render(*NO_INGRESS), "Route") == []
    assert of_kind(render(*ROUTE_API), "Route") == []


def test_http_route() -> None:
    """With the Ingress disabled, the chart can attach an HTTPRoute."""
    parents = [{"name": "gateway", "namespace": "gateway-system"}]
    resources = render(
        *NO_INGRESS,
        "--set",
        "drsFiler.httpRoute.enabled=true",
        "--set-json",
        f"drsFiler.httpRoute.parentRefs={json.dumps(parents)}",
    )
    assert find(resources, "HTTPRoute", APP)["spec"]["hostnames"] == [HOST]


def test_app_network_policy() -> None:
    """The app's NetworkPolicy admits the peers in `ingressFrom`, required."""
    peers = [{"namespaceSelector": {"matchLabels": {"name": "ingress"}}}]
    resources = render(
        "--set",
        "drsFiler.networkPolicy.enabled=true",
        "--set-json",
        f"drsFiler.networkPolicy.ingressFrom={json.dumps(peers)}",
    )
    policy = find(resources, "NetworkPolicy", APP)
    assert policy["spec"]["ingress"][0]["from"] == peers
    assert "ingressFrom" in render_error("--set", "drsFiler.networkPolicy.enabled=true")


def test_replicas() -> None:
    """Several replicas get a PodDisruptionBudget."""
    resources = render("--set", "drsFiler.replicas=2")
    assert find(resources, "Deployment", APP)["spec"]["replicas"] == 2
    assert find(resources, "PodDisruptionBudget", APP)


def test_autoscaling_rejected() -> None:
    """The chart has no HorizontalPodAutoscaler, so the schema refuses it."""
    assert "autoscaling" in render_error("--set", "drsFiler.autoscaling.enabled=true")


def test_host_name_required() -> None:
    """Rendering fails without `hostName`, which sets the host name."""
    assert "hostName must be set" in render_error("--set", "hostName=")


@pytest.mark.parametrize(
    "host",
    [
        "https://drs.example.org",
        "drs.example.org:443",
        "drs.example.org/x",
        "DRS.example.org",
        "drs_filer.example.org",
    ],
)
def test_host_name_invalid(host: str) -> None:
    """Rendering fails for a `hostName` that isn't a lowercase DNS name.

    Kubernetes requires lowercase DNS names (RFC 1123) as hosts, and the
    app would refuse hosts with a scheme, port or path on startup.

    Args:
        host: Invalid host name.
    """
    assert "hostName" in render_error("--set", f"hostName={host}")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--set", "host_name=drs.example.org"), "host_name was renamed to hostName"),
        (("--set", "drs_filer.ingress=true"), "drs_filer was renamed to drsFiler"),
        (("--set", "apiServer=kubernetes.default.svc:443"), "apiServer was removed"),
        (("--set", "clusterType=openshift"), "clusterType was removed"),
        (("--set", "drsFiler.appName=drs"), "drsFiler.appName was removed"),
        (("--set", "drsFiler.config.x=1"), "drsFiler.config was removed"),
    ],
)
def test_legacy_values(args: tuple[str, ...], message: str) -> None:
    """Values of the charts before foca-common fail, instead of being ignored.

    Args:
        args: Arguments that set a legacy value.
        message: Expected part of the error.
    """
    error = render_error(*args)
    assert message in error
    assert "From earlier charts" in error


@pytest.mark.parametrize(
    "args",
    [
        ("--set", "config.endpoints.external_port=8443"),
        ("--set", "config.endpoints.service_info.name=My DRS"),
        ("--set-json", "config.endpoints=null"),
    ],
)
def test_config_endpoints_fails(args: tuple[str, ...]) -> None:
    """The app's config section of earlier versions, `endpoints`, fails.

    The app would fail to start with it; the error names the new sections.

    Args:
        args: Arguments that set `config.endpoints`.
    """
    error = render_error(*args)
    assert "config.endpoints was replaced" in error
    assert "hostName" in error
    assert "config.service_info.service" in error


def test_legacy_values_before_host_name() -> None:
    """A renamed `host_name` is reported instead of the missing `hostName`."""
    error = render_error("--set", "hostName=", "--set", "host_name=drs.example.org")
    assert "host_name was renamed" in error


def test_test_values_not_packaged(tmp_path: Path) -> None:
    """The packaged chart has the library, but not the CI values and digest.

    Args:
        tmp_path: Directory for the package.
    """
    assert HELM is not None
    subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [HELM, "package", str(CHART), "--destination", str(tmp_path)],
        capture_output=True,
        check=True,
    )
    (package,) = tmp_path.glob("drs-filer-*.tgz")
    with tarfile.open(package) as archive:
        names = archive.getnames()
    assert "drs-filer/values.schema.json" in names
    assert [name for name in names if name.startswith(f"drs-filer/charts/{LIBRARY}")]
    assert not [name for name in names if "/ci/" in name]
    assert "drs-filer/charts.sha256" not in names


def test_library_versions() -> None:
    """Chart, lock, digest and schema name the same library version."""
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    lock = yaml.safe_load((CHART / "Chart.lock").read_text())
    (dependency,) = chart["dependencies"]
    (locked,) = lock["dependencies"]
    assert dependency["name"] == locked["name"] == LIBRARY
    assert dependency["version"] == locked["version"]
    version = dependency["version"]
    digest = (CHART / "charts.sha256").read_text()
    assert digest.rstrip().endswith(f"  charts/{LIBRARY}-{version}.tgz")
    schema = json.loads((CHART / "values.schema.json").read_text())
    assert f"{LIBRARY} {version} " in schema["$comment"]


# Calls the check of upgrades with a Deployment as `lookup` returns it
LEGACY_CHECK = """{{- include "drs-filer.failIfLegacy" (dict "root" . "resource" (dict
  "metadata" (dict
    "name" "NAME"
    "annotations" (dict "meta.helm.sh/release-name" "RELEASE")
    "labels" (dict LABELS)
  )
)) }}
"""


INSTANCE = (
    '"app.kubernetes.io/instance" "drs-filer" "app.kubernetes.io/name" "drs-filer"'
)
MONGODB_LABELS = f'{INSTANCE} "app.kubernetes.io/component" "mongodb"'
EXISTING_CLAIM = ("--set", "mongodb.persistence.existingClaim=old-claim")


@pytest.mark.parametrize(
    ("release", "name", "labels", "args", "error"),
    [
        # A Deployment of a chart before foca-common, of this release
        ("drs-filer", APP, '"app" "drs-filer"', (), "uninstall it and install"),
        # Ones of this chart
        ("drs-filer", APP, INSTANCE, (), None),
        ("drs-filer", MONGODB, MONGODB_LABELS, (), None),
        # Another name label (a changed nameOverride), with the same names
        (
            "drs-filer",
            APP,
            '"app.kubernetes.io/instance" "drs-filer" "app.kubernetes.io/name" "filer"',
            (),
            "a changed nameOverride",
        ),
        # Its MongoDB under another name (a changed fullnameOverride)
        ("drs-filer", "old-mongodb", MONGODB_LABELS, (), "new, empty claim"),
        # ... which keeps its data with an existing claim, or has none
        ("drs-filer", "old-mongodb", MONGODB_LABELS, EXISTING_CLAIM, None),
        (
            "drs-filer",
            "old-mongodb",
            MONGODB_LABELS,
            ("--set", "mongodb.persistence.enabled=false"),
            None,
        ),
        (
            "drs-filer",
            "old-mongodb",
            MONGODB_LABELS,
            ("--set", "mongodb.enabled=false", "--set", "config.db.host=db.local"),
            None,
        ),
        # Ones of another release
        ("other", APP, '"app" "drs-filer"', (), None),
        ("other", "old-mongodb", MONGODB_LABELS, (), None),
    ],
)
def test_fail_if_legacy(
    tmp_path: Path,
    release: str,
    name: str,
    labels: str,
    args: tuple[str, ...],
    error: str | None,
) -> None:
    """Upgrades fail for earlier charts' Deployments and for renames.

    `lookup` finds nothing in `helm template`, so the check is called with a
    Deployment of the release as `lookup` would return it.

    Args:
        tmp_path: Directory for the copy of the chart.
        release: Release that the Deployment belongs to.
        name: Name of the Deployment.
        labels: Labels of the Deployment (template arguments of `dict`).
        args: Further arguments of `helm template`.
        error: Expected part of the error, or None if the check passes.
    """
    template = (
        LEGACY_CHECK.replace("RELEASE", release)
        .replace("NAME", name)
        .replace("LABELS", labels)
    )
    chart = copy_chart(tmp_path, {"legacy-check.yaml": template})
    if error:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            helm_template(chart, *args)
        assert error in failure.value.stderr
    else:
        helm_template(chart, *args)


def test_upgrade_check_included() -> None:
    """The check of upgrades runs on upgrades, once, in the app's ConfigMap.

    `lookup` finds nothing in `helm template`, so an upgrade renders; the
    check itself is tested by `test_fail_if_legacy`.
    """
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in (CHART / "templates").glob("*.yaml")
    }
    assert [
        name for name, text in templates.items() if "drs-filer.checkUpgrade" in text
    ] == ["configmap.yaml"]
    helpers = (CHART / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    check = helpers.split('{{- define "drs-filer.checkUpgrade" -}}')[1]
    assert check.lstrip().startswith("{{- if .Release.IsUpgrade -}}")
    assert find(render("--is-upgrade"), "ConfigMap", f"{APP}-config")


def test_readme_references() -> None:
    """The chart's references to sections of its README name existing ones.

    References (e.g., "see deployment/README.md, Server") may span lines of
    comments, which are joined first.
    """
    readme = (CHART / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^#+ (.+)$", readme, re.MULTILINE)
    prefix = "deployment/README.md, "
    files = [
        CHART / "values.yaml",
        CHART / "values.schema.json",
        *(CHART / "templates").iterdir(),
    ]
    sections = []
    for path in files:
        text = re.sub(r"\s*\n\s*#?\s*", " ", path.read_text(encoding="utf-8"))
        for part in text.split(prefix)[1:]:
            matches = [
                heading
                for heading in headings
                if re.match(rf"{re.escape(heading)}\b", part)
            ]
            assert matches, f"{path.name}: {prefix}{part[:40]}"
            sections.extend(matches)
    assert {
        "Configuration",
        "From earlier charts",
        "Several replicas",
    } <= set(sections)


def test_notes(tmp_path: Path) -> None:
    """The notes show the API's URL, that the Ingress has no TLS, and who may write.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(tmp_path)
    assert f"https://{HOST}/ga4gh/drs/v1/service-info" in notes
    assert "The Ingress has no TLS" in notes
    assert "writes (POST, PUT and DELETE) need an access token of" in notes
    assert "WARNING" not in notes


@pytest.mark.parametrize(
    ("value", "disabled"),
    [
        ("true", True),
        ('"yes"', True),
        ('"1"', True),
        ("false", False),
        ('"false"', False),
        ('"no"', False),
        ("0", False),
    ],
)
def test_notes_auth_disabled(tmp_path: Path, value: str, disabled: bool) -> None:
    """The notes warn of disabled authentication, as the app parses booleans.

    Args:
        tmp_path: Directory for the copy of the chart.
        value: JSON value of `disable_auth`.
        disabled: Whether the value disables authentication.
    """
    notes = render_notes(
        tmp_path, "--set-json", f"config.api.specs.drs.disable_auth={value}"
    )
    warning = "authentication is disabled (config.api.specs.drs.disable_auth)"
    assert (warning in notes) is disabled


@pytest.mark.parametrize("value", ["config.api.specs=null", "config.api=null"])
def test_notes_config_not_maps(tmp_path: Path, value: str) -> None:
    """The notes render with sections of `config` that are null.

    Args:
        tmp_path: Directory for the copy of the chart.
        value: Value that sets a section to null.
    """
    notes = render_notes(tmp_path, "--set-json", value)
    assert "authentication is disabled" not in notes


def test_notes_mongodb_without_auth(tmp_path: Path) -> None:
    """The notes warn of MongoDB without authentication.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(
        tmp_path,
        "--set",
        "mongodb.auth.enabled=false",
        "--set",
        "mongodb.auth.existingSecret=",
    )
    assert "MongoDB runs without authentication" in notes


def test_notes_not_exposed(tmp_path: Path) -> None:
    """Without an Ingress, HTTPRoute or Route, the notes show a port forward.

    Args:
        tmp_path: Directory for the copies of the chart.
    """
    notes = render_notes(tmp_path / "plain", *NO_INGRESS)
    assert f"kubectl port-forward svc/{APP} 8080:8080 -n drs" in notes
    assert "http://localhost:8080/ga4gh/drs/v1/ui/" in notes
    notes = render_notes(tmp_path / "route", *NO_INGRESS, *ROUTE_API)
    assert "port-forward" not in notes
    assert f"https://{HOST}/ga4gh/drs/v1/ui/" in notes
