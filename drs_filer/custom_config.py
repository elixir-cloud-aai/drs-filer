"""Models of the app's own configuration (`custom` section of the config).

FOCA validates the section against `CustomConfig` on startup (cf.
`drs_filer.app.create_app()`), so that invalid settings fail the start
instead of requests. The service info is configured in FOCA's section
`service_info`, not here.
"""

import re
import string
from typing import Annotated, Any

from foca.models.config import FOCABaseConfig
from foca.models.config import IdConfig as FocaIdConfig
from pydantic import BeforeValidator, Field, field_validator, model_validator

# Characters allowed in generated identifiers: the unreserved characters of
# URLs (RFC 3986, section 2.3), which need no encoding in paths
UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
# Default characters of generated identifiers: all unreserved characters of
# URLs, as the expression of earlier versions
# (`string.ascii_letters + string.digits + ".-_~"`)
DEFAULT_ID_CHARSET = string.ascii_letters + string.digits + ".-_~"
# Host names (RFC 1123): labels of at most 63 letters, digits and `-` (not
# at either end), separated by `.`, at most 253 characters in all; IPv4
# addresses match too
HOST_NAME_PATTERN = re.compile(
    r"(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
# Integers in strings: digits only
INTEGER_PATTERN = re.compile(r"[0-9]+")


def _integer(value: object) -> object:
    """Take integers, and strings of digits, for integer settings.

    Strings are taken, as config values that reference environment
    variables (`${VAR}`) are strings. Other values that pydantic would take
    as integers are refused (e.g., booleans, floats, `"1_000"`).

    Args:
        value: Value of the setting.

    Returns:
        The value, as an integer.

    Raises:
        ValueError: The value is neither an integer nor a string of digits.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and INTEGER_PATTERN.fullmatch(value):
        return int(value)
    raise ValueError("Must be an integer (or a string of digits)")


# Positive integer, also as a string of digits (e.g., from `${VAR}`)
PositiveInteger = Annotated[int, BeforeValidator(_integer), Field(gt=0)]


class DrsConfig(FOCABaseConfig):
    """Model for the DRS host of the app.

    The `self_uri` of each object is the hostname-based DRS URI of the host,
    `drs://<hostname>/<id>` (with the identifier percent-encoded), computed
    when the object is served. DRS clients resolve it to
    `https://<hostname>/ga4gh/drs/v1/objects/<id>`, always on port 443.

    Args:
        hostname: Public host name of the app, without scheme, port or path;
            required.

    Attributes:
        hostname: Public host name of the app.

    Raises:
        pydantic.ValidationError: The host name is missing, or is not a host
            name.

    Example:
        >>> DrsConfig(hostname="drs.example.org").hostname
        'drs.example.org'
    """

    hostname: str

    @field_validator("hostname")
    @classmethod
    def check_hostname(cls, value: str) -> str:
        """Check that the host name is a host name only.

        Args:
            value: Host name.

        Returns:
            The host name.

        Raises:
            ValueError: The host name is empty, or has a scheme, port, path
                or other characters (e.g., an IPv6 address, which DRS URIs
                can't have).
        """
        if not HOST_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "The host name must be a host name (letters, digits and '-', "
                "in labels separated by '.'), without scheme, port or path"
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

    Unknown keys are refused, e.g., misspelled ones, the service info, which
    is configured in FOCA's section `service_info`, and the public URL of
    earlier versions (`service`), with a hint to its replacement.

    Args:
        drs: DRS host of the app; required.
        objects: Settings of objects.
        access_methods: Settings of access methods.

    Attributes:
        drs: DRS host of the app.
        objects: Settings of objects.
        access_methods: Settings of access methods.

    Raises:
        pydantic.ValidationError: A setting is missing, invalid or unknown.
    """

    drs: DrsConfig
    objects: ObjectsConfig = Field(default_factory=ObjectsConfig)
    access_methods: AccessMethodsConfig = Field(default_factory=AccessMethodsConfig)

    @model_validator(mode="before")
    @classmethod
    def check_removed(cls, data: Any) -> Any:
        """Refuse the public URL of earlier versions, naming its replacement.

        Args:
            data: Settings.

        Returns:
            The settings.

        Raises:
            ValueError: The settings have the section `service`.
        """
        if isinstance(data, dict) and "service" in data:
            raise ValueError(
                "'custom.service' was removed: the 'self_uri' of objects is a "
                "DRS URI of the host name in 'custom.drs.hostname' (see "
                "'Upgrading' in the documentation)"
            )
        return data
