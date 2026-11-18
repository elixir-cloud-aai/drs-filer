"""App tests of the app's own config (`custom`) and the service info config.

Invalid settings fail the start of the app, instead of requests, and so do
the config sections of earlier versions, which would otherwise be ignored.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pymongo import MongoClient
import pytest
import yaml

from drs_filer.app import OVERLAY_VARIABLE, create_app
from tests.mock_data import API, body, drs_object, error_messages


@pytest.mark.parametrize(
    ("custom", "setting"),
    [
        ({"drs": {"hostname": "https://SENTINEL"}}, "drs.hostname"),
        ({"drs": {"hostname": "SENTINEL:443"}}, "drs.hostname"),
        ({"drs": {"hostname": None}}, "drs.hostname"),
        ({"drs": {"host": "SENTINEL"}}, "drs.host"),
        ({"service": {"external_host": "SENTINEL"}}, "custom.drs.hostname"),
        ({"objects": {"id_charset": "SENTINEL"}}, "objects.id_charset"),
        ({"objects": {"id": {"charset": "SENTINEL/"}}}, "objects.id.charset"),
        ({"service_info": {"id": "SENTINEL"}}, "service_info"),
    ],
)
def test_invalid_custom_config_fails_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    custom: dict[str, Any],
    setting: str,
) -> None:
    """Invalid and unknown settings of `custom` fail the start of the app.

    The error names the setting, but not the value (which may be a secret
    from the environment).

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        custom: Invalid custom config, with the value `SENTINEL`, if any.
        setting: Name of the invalid setting.
    """
    overlay.write_text(yaml.safe_dump({"custom": custom}))
    with pytest.raises(ValueError, match="custom configuration") as info:
        create_app()
    messages = error_messages(info.value)
    assert setting in messages
    assert "SENTINEL" not in messages


def test_no_service_info_fails_start(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Without service info (`service_info: null`), the app doesn't start.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
    """
    overlay.write_text(yaml.safe_dump({"service_info": None}))
    with pytest.raises(RuntimeError, match="service_info"):
        create_app()


@pytest.mark.parametrize(
    "service_type",
    [
        {"group": "org.ga4gh", "artifact": "trs", "version": "2.0.2"},
        {"group": "org.ga4gh", "artifact": "drs", "version": "1.2.0"},
        {"group": "org.example", "artifact": "drs", "version": "1.5.0"},
    ],
)
def test_service_info_not_drs_fails_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    service_type: dict[str, str],
) -> None:
    """Service info of another type than DRS 1.5.0 fails the start.

    `GET /service-info` serves `DrsService`, of type `drs`, so that another
    artifact would fail every response instead, and another group or
    version would describe another API.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        service_type: Service type of the config.
    """
    overlay.write_text(
        yaml.safe_dump({"service_info": {"service": {"type": service_type}}})
    )
    with pytest.raises(ValueError, match=r"service\.type"):
        create_app()


@pytest.mark.parametrize(
    "endpoints",
    [
        {"external_host": "drs.example.org"},
        {"service_info": {"id": "org.example.drs"}},
        None,
    ],
    ids=["public-url", "service-info", "null"],
)
def test_endpoints_section_fails_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    endpoints: dict[str, Any] | None,
) -> None:
    """The section `endpoints` of earlier versions fails the start.

    It would otherwise be ignored, and the app would serve the default public
    URL and the placeholder service info. The error names the new sections.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        endpoints: Section of an earlier version.
    """
    overlay.write_text(yaml.safe_dump({"endpoints": endpoints}))
    with pytest.raises(ValueError, match="'endpoints' was replaced") as info:
        create_app()
    for section in (
        "custom.drs.hostname",
        "custom.objects.id",
        "service_info.service",
    ):
        assert section in str(info.value)


def test_hostname_from_custom_config(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The `self_uri` of objects is the DRS URI of `custom.drs.hostname`.

    Not of the host that the request was sent to, which clients set (#97);
    objects registered before the host name changed get the new one.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
    """
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects/register", json=drs_object(1))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    overlay.write_text(
        yaml.safe_dump({"custom": {"drs": {"hostname": "drs.example.net"}}})
    )
    client = create_app().app.test_client()
    for host in ("localhost", "drs.example.org", "attacker.example.com"):
        obj = body(
            client.get(
                f"{API}/objects/{object_id}",
                headers={"Host": host, "X-Forwarded-Host": host},
            )
        )
        assert obj["self_uri"] == f"drs://drs.example.net/{object_id}"


def test_no_hostname_fails_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without `custom.drs.hostname`, which has no default, the start fails.

    Only the base config (`config.yaml`), without the test overlay.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        monkeypatch: Fixture to set the overlays with.
    """
    monkeypatch.setenv(OVERLAY_VARIABLE, str(overlay))
    with pytest.raises(ValueError, match="custom configuration") as info:
        create_app()
    assert "drs" in error_messages(info.value)


def test_service_info_version_from_package(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The service info has the version of the package, unless set.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
    """
    client = create_app().app.test_client()
    info = body(client.get(f"{API}/service-info"))
    assert info["version"] == version("drs-filer")
    assert info["type"] == {"group": "org.ga4gh", "artifact": "drs", "version": "1.5.0"}
    overlay.write_text(
        yaml.safe_dump({"service_info": {"service": {"version": "1.2.3"}}})
    )
    client = create_app().app.test_client()
    assert body(client.get(f"{API}/service-info"))["version"] == "1.2.3"


@pytest.mark.parametrize(
    ("service", "field"),
    [
        ({"documentationUrl": "docs/abc"}, "documentationUrl"),
        ({"createdAt": "2020-01-01"}, "createdAt"),
        ({"id": None}, "id"),
        ({"organization": {"url": "example.org"}}, "organization"),
    ],
    ids=["url", "date-time", "no-id", "organization-url"],
)
def test_invalid_service_info_fails_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    service: dict[str, Any],
    field: str,
) -> None:
    """Service info that doesn't conform to the specification fails the start.

    Only the invalid field of the base config's service info is changed, and
    the error names it. Earlier versions only failed the responses of
    `GET /service-info`.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        service: Invalid fields of the service info.
        field: Name of the invalid field.
    """
    overlay.write_text(yaml.safe_dump({"service_info": {"service": service}}))
    with pytest.raises(ValidationError, match=rf"service_info\.service\b.*{field}"):
        create_app()


def test_integers_from_environment(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host name and identifier lengths can be set from the environment.

    FOCA interpolates `${VAR}` into strings, which the integer settings take.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        monkeypatch: Fixture to set the variables with.
    """
    monkeypatch.setenv("DRS_TEST_HOSTNAME", "drs.example.net")
    monkeypatch.setenv("DRS_TEST_ID_LENGTH", "9")
    overlay.write_text(
        "custom:\n"
        "  drs:\n"
        "    hostname: ${DRS_TEST_HOSTNAME}\n"
        "  objects:\n"
        "    id:\n"
        "      length: ${DRS_TEST_ID_LENGTH}\n"
    )
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects/register", json=drs_object(1))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    assert len(object_id) == 9
    obj = body(client.get(f"{API}/objects/{object_id}"))
    assert obj["self_uri"] == f"drs://drs.example.net/{object_id}"
