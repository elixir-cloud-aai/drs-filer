"""Models of the app's own configuration (`custom` section of the config).

FOCA validates the section against `CustomConfig` on startup (cf.
`drs_filer.app.create_app()`), so that invalid settings fail the start
instead of requests. The service info is configured in FOCA's section
`service_info`, not here.
"""

import re
import string
from typing import Annotated, Literal

from foca.models.config import FOCABaseConfig
from foca.models.config import IdConfig as FocaIdConfig
from pydantic import BeforeValidator, Field, field_validator

# Characters allowed in generated identifiers: the unreserved characters of
# URLs (RFC 3986, section 2.3), which need no encoding in paths
UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
# Default characters of generated identifiers: all unreserved characters of
# URLs, as the expression of earlier versions
# (`string.ascii_letters + string.digits + ".-_~"`)
DEFAULT_ID_CHARSET = string.ascii_letters + string.digits + ".-_~"
# Public hosts: host names and IPv4 addresses (letters, digits, `.`, `-` and
# `_`), or IPv6 addresses in brackets
HOST_PATTERN = re.compile(r"[A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\]")
# API paths: segments of unreserved characters of URLs, separated by `/`
API_PATH_PATTERN = re.compile(r"[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*")


def _not_bool(value: object) -> object:
    """Refuse booleans for integer settings, which pydantic takes as 0 and 1.

    Integers in strings are taken, as config values that reference
    environment variables (`${VAR}`) are strings.

    Args:
        value: Value of the setting.

    Returns:
        The value.

    Raises:
        ValueError: The value is a boolean.
    """
    if isinstance(value, bool):
        raise ValueError("Must be an integer, not a boolean")
    return value


# Positive integer, also in a string (e.g., from `${VAR}`), not a boolean
PositiveInteger = Annotated[int, BeforeValidator(_not_bool), Field(gt=0)]
# Port number, also in a string (e.g., from `${VAR}`), not a boolean
Port = Annotated[int, BeforeValidator(_not_bool), Field(ge=1, le=65535)]


class ServiceConfig(FOCABaseConfig):
    """Model for the public URL of the app.

    The URL, `<url_prefix>://<external_host>:<external_port>/<api_path>`, is
    used for the `self_uri` of objects and the `Location` of posted service
    info.

    Args:
        url_prefix: URL scheme: `http` or `https`.
        external_host: Public host name or IP address of the app (IPv6
            addresses in brackets), without scheme, port or path.
        external_port: Public port of the app.
        api_path: Path of the API: segments of unreserved characters of URLs
            (letters, digits and `-._~`), separated by `/`, without leading
            or trailing `/`.

    Attributes:
        url_prefix: URL scheme.
        external_host: Public host name or IP address of the app.
        external_port: Public port of the app.
        api_path: Path of the API.

    Raises:
        pydantic.ValidationError: The scheme is neither `http` nor `https`,
            the host is not a host name or IP address, the port is not an
            integer from 1 to 65535, or the API path is not a path of
            unreserved characters of URLs.

    Example:
        >>> ServiceConfig(url_prefix="https", external_host="drs.example.org").api_path
        'ga4gh/drs/v1'
    """

    url_prefix: Literal["http", "https"] = "http"
    external_host: str = "localhost"
    external_port: Port = 8080
    api_path: str = "ga4gh/drs/v1"

    @field_validator("external_host")
    @classmethod
    def check_external_host(cls, value: str) -> str:
        """Check that the host is a host name or IP address.

        Args:
            value: Host.

        Returns:
            The host.

        Raises:
            ValueError: The host is empty, or has a scheme, port, path or
                other characters (e.g., an IPv6 address without brackets).
        """
        if not HOST_PATTERN.fullmatch(value):
            raise ValueError(
                "The host must be a host name or IP address (IPv6 addresses in "
                "brackets), without scheme, port or path"
            )
        return value

    @field_validator("api_path")
    @classmethod
    def check_api_path(cls, value: str) -> str:
        """Check that the API path has unreserved characters of URLs only.

        The URL inserts a `/` before and after it.

        Args:
            value: API path.

        Returns:
            The API path.

        Raises:
            ValueError: The API path is empty, starts or ends with `/`, has
                empty segments or other characters.
        """
        if not API_PATH_PATTERN.fullmatch(value):
            raise ValueError(
                "The API path must consist of letters, digits and '-._~', in "
                "segments separated by '/', without leading or trailing '/'"
            )
        return value


class IdConfig(FocaIdConfig):
    """Model for generating identifiers of objects or access methods.

    FOCA's model (`foca.models.config.IdConfig`), for FOCA's
    `generate_id()`, narrowed: FOCA's checks of the character set apply
    (not empty, no `/`, not dots only, no expression it recognizes), and
    only the unreserved characters of URLs are allowed, which are also the
    default, as identifiers are part of URLs (e.g., `self_uri`); this also
    refuses expressions that FOCA doesn't recognize. The length is an
    integer, also in a string (e.g., from an environment variable), but not
    a boolean.

    Args:
        charset: The allowed characters (duplicates are ignored); not an
            expression (e.g., `string.ascii_letters + string.digits`), which
            earlier versions evaluated.
        length: Length of generated identifiers.

    Attributes:
        charset: The allowed characters.
        length: Length of generated identifiers.

    Raises:
        pydantic.ValidationError: The character set is empty, consists of
            dots only, or has characters other than letters, digits and
            `-._~`, or the length is not a positive integer.

    Example:
        >>> IdConfig(charset="abc123", length=8)
        IdConfig(charset='abc123', length=8)
    """

    charset: str = DEFAULT_ID_CHARSET
    length: PositiveInteger = 6

    @field_validator("charset")
    @classmethod
    def check_unreserved(cls, value: str) -> str:
        """Check that the character set has unreserved characters of URLs only.

        Args:
            value: Character set.

        Returns:
            The character set.

        Raises:
            ValueError: The character set has other characters, e.g., as an
                expression.
        """
        if not set(value) <= UNRESERVED:
            raise ValueError(
                "The character set has characters that are not unreserved "
                "characters of URLs (letters, digits and '-._~'): list the "
                "characters themselves, e.g., 'abc123', not an expression"
            )
        return value


class ObjectsConfig(FOCABaseConfig):
    """Model for the settings of objects.

    Args:
        id: Generated identifiers of objects.

    Attributes:
        id: Generated identifiers of objects.
    """

    id: IdConfig = Field(default_factory=IdConfig)


class AccessMethodsConfig(FOCABaseConfig):
    """Model for the settings of access methods.

    Args:
        id: Generated identifiers of access methods.

    Attributes:
        id: Generated identifiers of access methods.
    """

    id: IdConfig = Field(default_factory=IdConfig)


class CustomConfig(FOCABaseConfig):
    """Model for the app's own configuration (`custom`).

    Unknown keys are refused, e.g., misspelled ones, and the service info,
    which is configured in FOCA's section `service_info`.

    Args:
        service: Public URL of the app.
        objects: Settings of objects.
        access_methods: Settings of access methods.

    Attributes:
        service: Public URL of the app.
        objects: Settings of objects.
        access_methods: Settings of access methods.

    Raises:
        pydantic.ValidationError: A setting is invalid or unknown.
    """

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    objects: ObjectsConfig = Field(default_factory=ObjectsConfig)
    access_methods: AccessMethodsConfig = Field(default_factory=AccessMethodsConfig)
