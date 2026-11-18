"""Models of the app's own configuration (`custom` section of the config).

FOCA validates the section against `CustomConfig` on startup (cf.
`drs_filer.app.create_app()`), so that invalid settings fail the start
instead of requests. The service info is configured in FOCA's section
`service_info`, not here.
"""

import string
from typing import Annotated, Literal

from foca.models.config import FOCABaseConfig
from foca.models.config import IdConfig as FocaIdConfig
from pydantic import Field, field_validator

# Characters allowed in generated identifiers: the unreserved characters of
# URLs (RFC 3986, section 2.3), which need no encoding in paths
UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
# Default characters of generated identifiers: all unreserved characters of
# URLs, as the expression of earlier versions
# (`string.ascii_letters + string.digits + ".-_~"`)
DEFAULT_ID_CHARSET = string.ascii_letters + string.digits + ".-_~"


class ServiceConfig(FOCABaseConfig):
    """Model for the public URL of the app.

    The URL, `<url_prefix>://<external_host>:<external_port>/<api_path>`, is
    used for the `self_uri` of objects and the `Location` of posted service
    info.

    Args:
        url_prefix: URL scheme: `http` or `https`.
        external_host: Public host name (or IP address) of the app.
        external_port: Public port of the app.
        api_path: Path of the API, without leading or trailing `/`.

    Attributes:
        url_prefix: URL scheme.
        external_host: Public host name (or IP address) of the app.
        external_port: Public port of the app.
        api_path: Path of the API.

    Raises:
        pydantic.ValidationError: The scheme is neither `http` nor `https`,
            the host is empty, the port is not an integer from 1 to 65535,
            or the API path is empty or starts or ends with `/`.

    Example:
        >>> ServiceConfig(url_prefix="https", external_host="drs.example.org").api_path
        'ga4gh/drs/v1'
    """

    url_prefix: Literal["http", "https"] = "http"
    external_host: str = Field(default="localhost", min_length=1)
    external_port: Annotated[int, Field(strict=True, ge=1, le=65535)] = 8080
    api_path: str = Field(default="ga4gh/drs/v1", min_length=1)

    @field_validator("api_path")
    @classmethod
    def check_api_path(cls, value: str) -> str:
        """Check that the API path has no leading or trailing `/`.

        The URL inserts a `/` before and after it.

        Args:
            value: API path.

        Returns:
            The API path.

        Raises:
            ValueError: The API path starts or ends with `/`.
        """
        if value.startswith("/") or value.endswith("/"):
            raise ValueError("The API path must not start or end with '/'")
        return value


class IdConfig(FocaIdConfig):
    """Model for generating identifiers of objects or access methods.

    FOCA's model (`foca.models.config.IdConfig`), for FOCA's
    `generate_id()`, with the unreserved characters of URLs as the default
    and the only characters allowed, as identifiers are part of URLs (e.g.,
    `self_uri`), and a strict length (no strings or booleans).

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
            dots only, or has characters other than unreserved characters
            of URLs (as expressions do), or the length is not a positive
            integer.

    Example:
        >>> IdConfig(charset="abc123", length=8)
        IdConfig(charset='abc123', length=8)
    """

    charset: str = DEFAULT_ID_CHARSET
    length: Annotated[int, Field(strict=True, gt=0)] = 6

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
        invalid = sorted(set(value) - UNRESERVED)
        if invalid:
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
