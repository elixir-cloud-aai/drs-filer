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
    IdConfig,
    ServiceConfig,
)


def test_defaults() -> None:
    """Without settings, the defaults are those of the base config.

    The base config lists them anyway, so that operators see them.
    """
    base = yaml.safe_load(Path(CONFIG_FILE).read_text())["custom"]
    assert CustomConfig().model_dump() == base
    assert CustomConfig(**base) == CustomConfig()


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
        {"url_prefix": "ftp"},
        {"url_prefix": "HTTPS"},
        {"external_host": ""},
        {"external_port": 0},
        {"external_port": 65536},
        {"external_port": "https"},
        {"external_port": True},
        {"external_host": "https://drs.example.org"},
        {"external_host": "drs.example.org:443"},
        {"external_host": "drs.example.org/x"},
        {"external_host": "a b"},
        {"external_host": "::1"},
        {"api_path": "a b"},
        {"api_path": "x?y"},
        {"api_path": "a//b"},
        {"api_path": ""},
        {"api_path": "/ga4gh/drs/v1"},
        {"api_path": "ga4gh/drs/v1/"},
        {"host": "drs.example.org"},
    ],
)
def test_service_config_invalid(settings: dict[str, Any]) -> None:
    """Invalid and unknown settings of the public URL are refused.

    Args:
        settings: Invalid settings of the public URL.
    """
    with pytest.raises(ValidationError):
        ServiceConfig(**settings)


@pytest.mark.parametrize(
    "settings",
    [
        {"service_info": {"id": "org.example.drs"}},
        {"objects": {"id_charset": "abc"}},
        {"access_methods": {"id_length": 6}},
        {"url_prefix": "https"},
    ],
    ids=["service-info", "objects-legacy", "access-legacy", "flat-url"],
)
def test_custom_config_unknown_keys(settings: dict[str, Any]) -> None:
    """Unknown keys are refused, e.g., those of earlier versions.

    Args:
        settings: Settings with an unknown key.
    """
    with pytest.raises(ValidationError):
        CustomConfig(**settings)


def test_custom_config_partial() -> None:
    """Settings that are set are merged with the defaults of the others."""
    config = CustomConfig.model_validate(
        {
            "service": {"url_prefix": "https", "external_host": "drs.example.org"},
            "access_methods": {"id": {"length": 12}},
        }
    )
    assert config.service.url_prefix == "https"
    assert config.service.external_host == "drs.example.org"
    assert config.service.external_port == 8080
    assert config.access_methods.id.length == 12
    assert config.access_methods.id.charset == DEFAULT_ID_CHARSET
    assert config.objects.id == IdConfig()


@pytest.mark.parametrize(
    "settings",
    [
        {"external_host": "drs.example.org"},
        {"external_host": "192.0.2.1"},
        {"external_host": "[2001:db8::1]"},
        {"external_host": "drs_filer"},
        {"api_path": "drs"},
        {"api_path": "ga4gh/drs/v1.1"},
    ],
)
def test_service_config_valid(settings: dict[str, Any]) -> None:
    """Host names, IP addresses and paths of unreserved characters are valid.

    Args:
        settings: Valid settings of the public URL.
    """
    config = ServiceConfig.model_validate(settings)
    for key, value in settings.items():
        assert getattr(config, key) == value


def test_integers_in_strings() -> None:
    """Integers in strings are taken, as from environment variables (`${VAR}`).

    FOCA interpolates variables into strings.
    """
    assert ServiceConfig.model_validate({"external_port": "8443"}).external_port == 8443
    assert IdConfig.model_validate({"length": "12"}).length == 12
