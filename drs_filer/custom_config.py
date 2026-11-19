"""Models of the app's own configuration (`custom` section of the config).

FOCA validates the section against `CustomConfig` on startup (cf.
`drs_filer.app.create_app()`), so that invalid settings fail the start
instead of requests. The service info is configured in FOCA's section
`service_info`, not here.
"""

import ipaddress
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
# Host names (RFC 1123), in lowercase (as DNS names compare, and as the Helm
# chart requires): labels of at most 63 lowercase letters, digits and `-`
# (not at either end), separated by `.`, at most 253 characters in all; the
# last label (top-level domain) not of digits only, which leaves numbers
# (e.g., ports) and dotted digits for IPv4 addresses (`IPV4_PATTERN`)
HOST_NAME_PATTERN = re.compile(
    r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"(?![0-9]+$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
)
# IPv4 addresses, in dotted decimal notation, checked by `ipaddress` too
IPV4_PATTERN = re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){3}")
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
# Largest maximum size of the pages of the object list
# (`custom.objects.list.max_page_size`), which bounds the cost of a request
MAX_PAGE_SIZE = 10000
# Non-negative integer, also as a string of digits (e.g., from `${VAR}`)
NonNegativeInteger = Annotated[int, BeforeValidator(_integer), Field(ge=0)]


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
            ValueError: The host name is empty, has a scheme, port, path,
                uppercase letters or other characters (e.g., an IPv6
                address, which DRS URIs can't have), is a number (e.g., a
                port), or an invalid IPv4 address.
        """
        if HOST_NAME_PATTERN.fullmatch(value):
            return value
        if IPV4_PATTERN.fullmatch(value):
            try:
                ipaddress.IPv4Address(value)
            except ValueError:
                pass
            else:
                return value
        raise ValueError(
            "The host name must be a lowercase host name (letters, digits and "
            "'-', in labels separated by '.', not a number) or an IPv4 "
            "address, without scheme, port or path"
        )


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


class ListConfig(FOCABaseConfig):
    """Model for the pages of the object list (`GET /objects`).

    Args:
        default_page_size: Number of objects of a page if the request has no
            `pageSize`; at most `max_page_size`.
        max_page_size: Largest number of objects of a page, at most
            `MAX_PAGE_SIZE`; larger `pageSize`s are reduced to it.

    Attributes:
        default_page_size: Number of objects of a page if the request has no
            `pageSize`.
        max_page_size: Largest number of objects of a page.

    Raises:
        pydantic.ValidationError: A setting is not a positive integer, the
            maximum is larger than `MAX_PAGE_SIZE`, or the default page size
            is larger than the maximum.

    Example:
        >>> ListConfig(default_page_size="10").default_page_size
        10
    """

    default_page_size: PositiveInteger = 50
    max_page_size: Annotated[PositiveInteger, Field(le=MAX_PAGE_SIZE)] = 200

    @model_validator(mode="after")
    def check_default_page_size(self) -> "ListConfig":
        """Refuse a default page size larger than the maximum.

        Returns:
            The settings.

        Raises:
            ValueError: The default page size is larger than the maximum.
        """
        if self.default_page_size > self.max_page_size:
            raise ValueError(
                "'default_page_size' must not be larger than 'max_page_size'"
            )
        return self


class ObjectsConfig(FOCABaseConfig):
    """Model for the settings of objects.

    Args:
        id: Generated identifiers of objects.
        list: Pages of the object list (`GET /objects`).

    Attributes:
        id: Generated identifiers of objects.
        list: Pages of the object list.
    """

    id: IdConfig = Field(default_factory=IdConfig)
    list: ListConfig = Field(default_factory=ListConfig)


class AccessMethodsConfig(FOCABaseConfig):
    """Model for the settings of access methods.

    Args:
        id: Generated identifiers of access methods.

    Attributes:
        id: Generated identifiers of access methods.
    """

    id: IdConfig = Field(default_factory=IdConfig)


class StatsConfig(FOCABaseConfig):
    """Model for the stats of the objects in the service info.

    `GET /service-info` serves `drs.objectCount` and `drs.totalObjectSize`
    (DRS 1.5.0), computed from the database and kept for `cache_seconds` in
    each app process (each Gunicorn worker), so that frequent requests to
    the public endpoint don't read all objects each time. Writes through the
    same process recompute them at once; other processes serve them up to
    `cache_seconds` late.

    Args:
        enabled: Whether the service info has the stats; `False` leaves them
            out (they are optional), e.g., where reads require login and the
            number of objects shouldn't show either.
        cache_seconds: How long the stats are kept, in seconds; `0` computes
            them for each request.

    Attributes:
        enabled: Whether the service info has the stats.
        cache_seconds: How long the stats are kept, in seconds.

    Raises:
        pydantic.ValidationError: A setting is invalid.

    Example:
        >>> StatsConfig(cache_seconds="0").cache_seconds
        0
    """

    enabled: bool = True
    cache_seconds: NonNegativeInteger = 60


class BulkConfig(FOCABaseConfig):
    """Model for bulk requests.

    The authorization info of several objects (`OPTIONS /objects`) takes at
    most `max_request_length` identifiers; requests with more get `413`. The
    maximum is served in the service info (`maxBulkRequestLength` of DRS
    1.5.0).

    Args:
        max_request_length: Maximum number of identifiers of a bulk request,
            counted as sent (duplicates too).

    Attributes:
        max_request_length: Maximum number of identifiers of a bulk request.

    Raises:
        pydantic.ValidationError: The maximum is not a positive integer.

    Example:
        >>> BulkConfig(max_request_length="50").max_request_length
        50
    """

    max_request_length: PositiveInteger = 100


class CustomConfig(FOCABaseConfig):
    """Model for the app's own configuration (`custom`).

    Unknown keys are refused, e.g., misspelled ones, the service info, which
    is configured in FOCA's section `service_info`, and the public URL of
    earlier versions (`service`), with a hint to its replacement.

    Args:
        drs: DRS host of the app; required.
        objects: Settings of objects.
        access_methods: Settings of access methods.
        stats: Stats of the objects in the service info.
        bulk: Bulk requests.

    Attributes:
        drs: DRS host of the app.
        objects: Settings of objects.
        access_methods: Settings of access methods.
        stats: Stats of the objects in the service info.
        bulk: Bulk requests.

    Raises:
        pydantic.ValidationError: A setting is missing, invalid or unknown.
    """

    drs: DrsConfig
    objects: ObjectsConfig = Field(default_factory=ObjectsConfig)
    access_methods: AccessMethodsConfig = Field(default_factory=AccessMethodsConfig)
    stats: StatsConfig = Field(default_factory=StatsConfig)
    bulk: BulkConfig = Field(default_factory=BulkConfig)

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
