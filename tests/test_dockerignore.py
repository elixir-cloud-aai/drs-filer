"""Tests of the build context of the image (`.dockerignore`)."""

import re
from pathlib import Path
from typing import List

import pytest

DOCKERIGNORE = Path(__file__).resolve().parents[1] / ".dockerignore"


def _patterns() -> List[str]:
    """Get the patterns of `.dockerignore`, without comments and blank lines.

    Returns:
        Patterns, in order.
    """
    lines = (line.strip() for line in DOCKERIGNORE.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _to_regex(pattern: str) -> "re.Pattern[str]":
    """Translate a `.dockerignore` pattern into a regular expression.

    Supports what the file uses: `**` (any number of directories), `*` and
    `?` (within a path segment), character classes, and a trailing slash.

    Args:
        pattern: Pattern, without a leading `!`.

    Returns:
        Regular expression matching a path (relative, with `/`) or any of its
        parent directories.
    """
    pattern = pattern.strip("/")
    regex = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            regex += "[^/]"
            i += 1
        elif pattern[i] == "[":
            end = pattern.index("]", i)
            regex += pattern[i:end + 1]
            i = end + 1
        else:
            regex += re.escape(pattern[i])
            i += 1
    return re.compile(f"{regex}(?:/.*)?")


def _is_excluded(path: str) -> bool:
    """Check whether a path is left out of the build context.

    As in Docker, the last matching pattern wins.

    Args:
        path: Path relative to the repository root, with `/`.

    Returns:
        Whether the path is excluded.
    """
    excluded = False
    for pattern in _patterns():
        negated = pattern.startswith("!")
        if _to_regex(pattern.lstrip("!")).fullmatch(path):
            excluded = not negated
    return excluded


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "drs_filer/.env",
        "drs_filer/.env.production",
        "drs_filer/api/secrets.env",
        "drs_filer/server.pem",
        "drs_filer/server.key",
        "drs_filer/credentials.json",
        "drs_filer/api/spec.modified.yaml",
        "drs_filer/__pycache__/app.cpython-312.pyc",
        "drs_filer/config.local.yaml",
        "drs_filer/drs.log",
        ".git/config",
        "tests/test.py",
        "deployment/values.yaml",
    ],
)
def test_excluded(path: str):
    """Secret, local and unneeded files are left out of the build context.

    Args:
        path: Path relative to the repository root.
    """
    assert _is_excluded(path)


@pytest.mark.parametrize(
    "path",
    [
        "drs_filer/app.py",
        "drs_filer/ga4gh/drs/endpoints/service_info.py",
        "drs_filer/config.yaml",
        "drs_filer/api/additional.data_repository_service.swagger.yaml",
        "setup.py",
        "requirements.txt",
        "README.md",
        "LICENSE",
        "update-config-map.sh",
    ],
)
def test_included(path: str):
    """The files the image needs are in the build context.

    Args:
        path: Path relative to the repository root.
    """
    assert not _is_excluded(path)
