"""Tests of the models of the app's own config (`drs_filer.custom_config`)."""

from pathlib import Path
import string
from typing import Any

from pydantic import ValidationError
import pytest
import yaml

from drs_filer.app import CONFIG_FILE
from drs_filer.custom_config import (
    DEFAULT_ID_CHARSET,
    UNRESERVED,
    CustomConfig,
    DrsConfig,
    IdConfig,
    ListConfig,
    StatsConfig,
)

# The required settings, which have no defaults
REQUIRED: dict[str, Any] = {"drs": {"hostname": "drs.example.org"}}


def test_defaults() -> None:
    """Without settings, the defaults are those of the base config.

    The base config lists them anyway, so that operators see them; it has no
    DRS host name, which each deployment must set.
    """
    base = yaml.safe_load(Path(CONFIG_FILE).read_text())["custom"]
    assert "drs" not in base
    assert CustomConfig(**REQUIRED).model_dump() == {**base, **REQUIRED}
    assert CustomConfig(**base, **REQUIRED) == CustomConfig(**REQUIRED)


def test_hostname_required() -> None:
    """Without the DRS host name, the config is refused."""
    with pytest.raises(ValidationError, match="drs"):
        CustomConfig.model_validate({})


def test_service_section_removed() -> None:
    """The public URL of earlier versions is refused, naming its replacement.

    `custom.service` built `self_uri` as an HTTP(S) URL, which is now a DRS
    URI of `custom.drs.hostname`.
    """
    with pytest.raises(ValidationError, match=r"custom\.drs\.hostname"):
        CustomConfig.model_validate(
            {"service": {"external_host": "drs.example.org"}, **REQUIRED}
        )


def test_default_charset() -> None:
    """Identifiers are drawn from all unreserved characters of URLs by default.

    The same characters as the expression of earlier versions,
    `string.ascii_letters + string.digits + ".-_~"`.
    """
    assert string.ascii_letters + string.digits + ".-_~" == DEFAULT_ID_CHARSET
    assert set(DEFAULT_ID_CHARSET) == UNRESERVED
    assert IdConfig().charset == DEFAULT_ID_CHARSET
    assert IdConfig().length == 6


@pytest.mark.parametrize(
    "settings",
    [
        {"charset": "string.ascii_letters"},
        {"charset": "'ab' + 'cd'"},
        {"charset": "ab/"},
        {"charset": "a b"},
        {"charset": ".."},
        {"charset": ""},
        {"charset": None},
        {"charset": ["a", "b"]},
        {"charset": 123},
        {"length": 0},
        {"length": -1},
        {"length": 2.5},
        {"length": "six"},
        {"length": 2.0},
        {"length": "1_000"},
        {"length": " 8"},
        {"length": "+8"},
        {"length": True},
        {"size": 6},
    ],
)
def test_id_config_invalid(settings: dict[str, Any]) -> None:
    """Expressions, other invalid and unknown settings are refused.

    Args:
        settings: Invalid settings of identifiers.
    """
    with pytest.raises(ValidationError):
        IdConfig(**settings)


def test_id_config_expression_message() -> None:
    """The error of an expression says to list the characters themselves."""
    with pytest.raises(ValidationError, match="not an expression"):
        IdConfig(charset="'ab' + 'cd'")


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"hostname": ""},
        {"hostname": None},
        {"hostname": 443},
        {"hostname": "drs://drs.example.org"},
        {"hostname": "https://drs.example.org"},
        {"hostname": "drs.example.org:443"},
        {"hostname": "drs.example.org/x"},
        {"hostname": "drs.example.org."},
        {"hostname": "a b"},
        {"hostname": "::1"},
        {"hostname": "[2001:db8::1]"},
        {"hostname": "."},
        {"hostname": "a..b"},
        {"hostname": "-drs"},
        {"hostname": "drs-"},
        {"hostname": "drs_filer"},
        {"hostname": "user@drs.example.org"},
        {"hostname": "a" * 64},
        {"hostname": ".".join(["a" * 63] * 4)},
        {"hostname": "drs.example.org", "port": 443},
        {"hostname": "DRS.Example.org"},
        {"hostname": "8080"},
        {"hostname": "1"},
        {"hostname": "drs.123"},
        {"hostname": "999.999.1.1"},
        {"hostname": "1.2.3"},
        {"hostname": "01.2.3.4"},
    ],
)
def test_drs_config_invalid(settings: dict[str, Any]) -> None:
    """Missing, invalid and unknown settings of the DRS host are refused.

    The host name is required. DRS URIs (`drs://<hostname>/<id>`) have a
    host name only, without scheme, port (always 443), user or path; it is
    lowercase, as the chart requires (so that the URIs of a host compare
    equal), and not a number (e.g., a port) or an invalid IPv4 address.

    Args:
        settings: Invalid settings of the DRS host.
    """
    with pytest.raises(ValidationError):
        DrsConfig(**settings)


@pytest.mark.parametrize(
    "hostname",
    [
        "drs.example.org",
        "localhost",
        "drs-1.example.org",
        "1drs.example.org",
        "drs.example.o1",
        "192.0.2.1",
        "a" * 63,
        ".".join(["a" * 63] * 3 + ["a" * 61]),
    ],
)
def test_drs_config_valid(hostname: str) -> None:
    """Lowercase host names and IPv4 addresses are valid.

    Args:
        hostname: Valid host name.
    """
    assert DrsConfig(hostname=hostname).hostname == hostname


@pytest.mark.parametrize(
    "settings",
    [
        {"service_info": {"id": "org.example.drs"}},
        {"objects": {"id_charset": "abc"}},
        {"access_methods": {"id_length": 6}},
        {"url_prefix": "https"},
        {"hostname": "drs.example.org"},
    ],
    ids=["service-info", "objects-legacy", "access-legacy", "flat-url", "flat-host"],
)
def test_custom_config_unknown_keys(settings: dict[str, Any]) -> None:
    """Unknown keys are refused, e.g., those of earlier versions.

    Args:
        settings: Settings with an unknown key.
    """
    with pytest.raises(ValidationError):
        CustomConfig(**settings, **REQUIRED)


def test_custom_config_partial() -> None:
    """Settings that are set are merged with the defaults of the others."""
    config = CustomConfig.model_validate(
        {
            **REQUIRED,
            "access_methods": {"id": {"length": 12}},
        }
    )
    assert config.drs.hostname == "drs.example.org"
    assert config.access_methods.id.length == 12
    assert config.access_methods.id.charset == DEFAULT_ID_CHARSET
    assert config.objects.id == IdConfig()


def test_integers_in_strings() -> None:
    """Integers in strings are taken, as from environment variables (`${VAR}`).

    FOCA interpolates variables into strings.
    """
    assert IdConfig.model_validate({"length": "12"}).length == 12
    assert StatsConfig.model_validate({"cache_seconds": "0"}).cache_seconds == 0


@pytest.mark.parametrize(
    "settings",
    [
        {"cache_seconds": -1},
        {"cache_seconds": "1.5"},
        {"cache_seconds": True},
        {"enabled": "maybe"},
        {"ttl": 60},
    ],
)
def test_stats_config_invalid(settings: dict[str, Any]) -> None:
    """Invalid or unknown settings of the stats are refused."""
    with pytest.raises(ValidationError):
        StatsConfig.model_validate(settings)


def test_stats_config_defaults() -> None:
    """The stats are served, and kept for 60 s."""
    config = CustomConfig(**REQUIRED).stats
    assert config.enabled is True
    assert config.cache_seconds == 60
    assert StatsConfig.model_validate({"enabled": "false"}).enabled is False


def test_list_config_defaults() -> None:
    """Pages of `GET /objects` have 50 objects by default, at most 200."""
    config = CustomConfig(**REQUIRED).objects.list
    assert config.default_page_size == 50
    assert config.max_page_size == 200
    assert ListConfig.model_validate(
        {"default_page_size": "10", "max_page_size": "10"}
    ) == ListConfig(default_page_size=10, max_page_size=10)
    assert ListConfig(max_page_size=10000).max_page_size == 10000


@pytest.mark.parametrize(
    "settings",
    [
        {"default_page_size": 0},
        {"max_page_size": 0},
        {"max_page_size": -1},
        {"max_page_size": "1.5"},
        {"max_page_size": True},
        {"default_page_size": 201},
        {"default_page_size": 20, "max_page_size": 10},
        {"max_page_size": 10001},
        {"max_page_size": 2**63},
        {"page_size": 10},
    ],
)
def test_list_config_invalid(settings: dict[str, Any]) -> None:
    """Invalid or unknown settings of the pages are refused.

    The default page size can't be larger than the maximum.

    Args:
        settings: Invalid settings of `custom.objects.list`.
    """
    with pytest.raises(ValidationError):
        ListConfig.model_validate(settings)
