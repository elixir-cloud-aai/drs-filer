"""Tests of the build context of the image (`.dockerignore`)."""

from pathlib import Path
from typing import List

DOCKERIGNORE = Path(__file__).resolve().parents[1] / ".dockerignore"


def _patterns() -> List[str]:
    """Get the patterns of `.dockerignore`, without comments and blank lines.

    Returns:
        Patterns, in order.
    """
    lines = (line.strip() for line in DOCKERIGNORE.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def test_allowlist():
    """The build context is an allowlist: everything is excluded first."""
    assert _patterns()[0] == "*"


def test_secret_files_excluded():
    """Local secret files are excluded, also within the included paths."""
    patterns = _patterns()
    for pattern in ("**/.env*", "**/*.env", "**/*.pem", "**/*.key"):
        assert pattern in patterns


def test_no_secret_files_included():
    """No exception re-includes secret files."""
    for pattern in _patterns():
        if pattern.startswith("!"):
            assert ".env" not in pattern
            assert not pattern.endswith((".pem", ".key"))
