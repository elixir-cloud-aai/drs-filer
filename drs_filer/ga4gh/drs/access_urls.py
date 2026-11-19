"""Access URLs of objects, and whether reading them needs login.

Access URLs (`GetAccessURL`, `GET /objects/{object_id}/access/{access_id}`)
need an access token by default: the base config applies the patch
`api/patches/login-for-access-urls.yaml` to the specification; deployments
make them public by leaving it out (see "Requiring login for reads" in
`docs/access-control.md`). As objects carry the access URLs of their access
methods too (`access_url`), objects are served without them while access
URLs need login, so that they can't be read without a token through the
object reads. Their access methods keep their `access_id`, with which
clients get the access URL (DRS requires one of `access_url` and
`access_id`). Whether access URLs need login is read from the specification
as FOCA registers it, so that it follows the patches of every overlay.
"""

from collections.abc import Iterable
import logging
from pathlib import Path
from typing import Any

from flask import current_app
from foca.config.config_parser import ConfigParser, deep_merge
from foca.models.config import SpecConfig

from drs_filer.utils import get_foca_config

logger = logging.getLogger(__name__)

# Key of the Flask config that caches whether access URLs need login
CONFIG_KEY = "DRS_FILER_ACCESS_URLS_NEED_LOGIN"
# The operation that serves access URLs, and its path
OPERATION_ID = "GetAccessURL"
ACCESS_URL_PATH = "/objects/{object_id}/access/{access_id}"
# HTTP methods of the Path Item Objects of OpenAPI 3, whose values are the
# operations (other fields, e.g., `parameters`, are not)
METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


# `_load_patch()` and `_merged_spec()` follow how FOCA assembles a
# specification in `foca.api.register_openapi.register_openapi()` (and its
# `_load_patch()`), which FOCA doesn't expose; keep them in sync when FOCA
# is upgraded. `tests/api/test_login_for_reads.py` compares the result with
# the specification that the app serves (`openapi.json`)
def _load_patch(patch: Path | dict[str, Any]) -> dict[str, Any]:
    """Load a patch of a specification, as FOCA does.

    Args:
        patch: Path to a YAML or JSON file, or a mapping.

    Returns:
        Patch; empty if the file has no content.
    """
    if isinstance(patch, dict):
        return patch
    return ConfigParser.parse_yaml(patch) or {}


def _merged_spec(spec: SpecConfig) -> dict[str, Any]:
    """Get a specification as FOCA merges and patches it.

    The files of `path`, in order, then the root fields of `append`, then
    the `patches`, deep-merged in order (mappings are merged, lists and
    other values replace earlier ones), then `add_operation_fields`, for
    operations that don't set them themselves.

    Args:
        spec: Config of the specification.

    Returns:
        Specification.
    """
    paths = spec.path if isinstance(spec.path, list) else [spec.path]
    merged: dict[str, Any] = ConfigParser.merge_yaml(*paths)
    for item in spec.append or []:
        merged.update(item)
    for patch in spec.patches or []:
        merged = deep_merge(merged, _load_patch(patch))
    for path_item in (merged.get("paths") or {}).values():
        for method, operation in (path_item or {}).items():
            if method in METHODS and isinstance(operation, dict):
                for key, value in (spec.add_operation_fields or {}).items():
                    operation.setdefault(key, value)
    return merged


def requires_login(
    spec: SpecConfig,
    path: str = ACCESS_URL_PATH,
    operation_id: str = OPERATION_ID,
) -> bool | None:
    """Check whether a specification requires a token for a read.

    The operations for the read are `GET` of its path and any `GET`
    operation of its `operationId`, so that neither a changed
    `operationId` nor a moved path makes it look public; by default, those
    of access URLs (`ACCESS_URL_PATH`, `GetAccessURL`). An operation
    requires a token if its security requirements (or, if it sets none,
    those of the specification) are not empty and have no empty alternative
    (`{}`, anonymous), and authentication isn't disabled (`disable_auth`,
    which removes them).

    Args:
        spec: Config of the specification.
        path: Path of the read.
        operation_id: `operationId` of the read.

    Returns:
        Whether an operation for the read requires a token; `None` if the
        specification has none.
    """
    merged = _merged_spec(spec)
    paths = merged.get("paths") or {}
    operations = [
        operation
        for item_path, path_item in paths.items()
        if isinstance(operation := (path_item or {}).get("get"), dict)
        and (item_path == path or operation.get("operationId") == operation_id)
    ]
    if not operations:
        return None
    return not spec.disable_auth and any(
        bool(security) and {} not in security
        for security in (
            operation.get("security", merged.get("security")) or []
            for operation in operations
        )
    )


def specs_require_login(
    specs: Iterable[SpecConfig],
    path: str = ACCESS_URL_PATH,
    operation_id: str = OPERATION_ID,
) -> bool:
    """Check whether the specifications of an app require login for a read.

    Args:
        specs: Configs of the specifications.
        path: Path of the read; by default, that of access URLs.
        operation_id: `operationId` of the read; by default, that of access
            URLs.

    Returns:
        Whether a specification has an operation for the read and requires
        a token for it; `False` if none has it (as then, for access URLs,
        they are only served with objects).
    """
    return any(requires_login(spec, path, operation_id) for spec in specs)


def access_urls_need_login() -> bool:
    """Check whether access URLs need login in the current app.

    Read from the app's specifications once, then cached in the app's
    config (`CONFIG_KEY`).

    Returns:
        Whether access URLs need login.
    """
    need_login = current_app.config.get(CONFIG_KEY)
    if need_login is None:
        need_login = specs_require_login(get_foca_config().api.specs)
        current_app.config[CONFIG_KEY] = need_login
        logger.info(
            "Access URLs %s",
            "need login; objects are served without them"
            if need_login
            else "are public, and served with objects",
        )
    return bool(need_login)


def served_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Get an object as object reads serve it.

    While access URLs need login (`access_urls_need_login()`), without the
    `access_url` of its access methods.

    Args:
        obj: Object.

    Returns:
        The object, unchanged if access URLs are public, otherwise a copy
        without access URLs.
    """
    if not access_urls_need_login() or "access_methods" not in obj:
        return obj
    return {
        **obj,
        "access_methods": [
            {key: value for key, value in method.items() if key != "access_url"}
            for method in obj["access_methods"]
        ],
    }
