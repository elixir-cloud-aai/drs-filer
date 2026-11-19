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
# The operation that serves access URLs
OPERATION_ID = "GetAccessURL"


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
    other values replace earlier ones).

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
    return merged


def requires_login(spec: SpecConfig) -> bool | None:
    """Check whether a specification requires a token for access URLs.

    An operation requires a token if its security requirements (or, if it
    sets none, those of the specification) are not empty and have no empty
    alternative (`{}`, anonymous), and authentication isn't disabled
    (`disable_auth`, which removes them).

    Args:
        spec: Config of the specification.

    Returns:
        Whether the operation `GetAccessURL` requires a token; `None` if the
        specification has no such operation.
    """
    merged = _merged_spec(spec)
    for path_item in (merged.get("paths") or {}).values():
        operation = (path_item or {}).get("get") or {}
        if operation.get("operationId") != OPERATION_ID:
            continue
        security = operation.get("security", merged.get("security")) or []
        return not spec.disable_auth and bool(security) and {} not in security
    return None


def specs_require_login(specs: Iterable[SpecConfig]) -> bool:
    """Check whether the specifications of an app require login for access URLs.

    Args:
        specs: Configs of the specifications.

    Returns:
        Whether a specification has the operation `GetAccessURL` and requires
        a token for it; `False` if none has it (as then access URLs are only
        served with objects).
    """
    return any(requires_login(spec) for spec in specs)


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
