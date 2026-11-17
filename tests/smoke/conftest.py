"""Fixtures of the smoke test, which needs network access."""

import pytest


@pytest.fixture(autouse=True)
def _isolate() -> None:
    """Replace the isolation of the other tests: the app is reached over HTTP."""
    # Overrides `_isolate()` of `tests/conftest.py` by name, doing nothing
