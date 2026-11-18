"""Checks of the Read the Docs configuration (`.readthedocs.yaml`).

Read the Docs builds the docs only after a merge, so mistakes in its
configuration would show only there; these tests catch them in pull requests.
"""

from pathlib import Path
import re
import tomllib

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".readthedocs.yaml"


def _config() -> dict[str, object]:
    """Load `.readthedocs.yaml`.

    Returns:
        Its content.
    """
    config: dict[str, object] = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return config


def _jobs() -> dict[str, list[str]]:
    """Return the commands of the build jobs (`build.jobs`).

    Returns:
        The commands of each job, in order.
    """
    build = _config()["build"]
    assert isinstance(build, dict)
    jobs: dict[str, list[str]] = build["jobs"]
    return jobs


def test_readthedocs_pins_the_locked_uv() -> None:
    """Read the Docs installs the version of uv that `uv.lock` locks."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(p["version"] for p in lock["package"] if p["name"] == "uv")
    pins = re.findall(r'"uv==([^"]+)"', CONFIG.read_text(encoding="utf-8"))
    assert pins == [locked], (
        "set the uv pin in .readthedocs.yaml to the version in uv.lock"
    )


def test_readthedocs_reshims_after_installing_uv() -> None:
    """Read the Docs installs uv and reshims asdf before creating the venv.

    Read the Docs provides Python through asdf, which only finds executables
    that have a shim; `pip install` adds none for `uv`, so the next command
    fails with "uv: not found". Running uv as `python -m uv` doesn't help
    either: once the virtual environment exists, `python` is the one of the
    environment, which has no uv.
    """
    pre = _jobs()["pre_create_environment"]
    assert len(pre) == 2
    assert '"uv==' in pre[0]
    assert pre[1] == "asdf reshim python"


def test_readthedocs_installs_the_locked_docs_extra() -> None:
    """Read the Docs installs the `docs` extra from the lock, as CI does."""
    assert _jobs()["install"] == [
        'UV_PROJECT_ENVIRONMENT="${READTHEDOCS_VIRTUALENV_PATH}" '
        "uv sync --frozen --extra docs"
    ]


def test_readthedocs_python_is_the_python_of_ci() -> None:
    """Read the Docs builds with the Python version of CI's docs job."""
    build = _config()["build"]
    assert isinstance(build, dict)
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["docs"]["steps"]
    versions = [
        step["with"]["python-version"]
        for step in steps
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert versions == [build["tools"]["python"]]


def test_readthedocs_builds_strictly() -> None:
    """Read the Docs fails on warnings, as `mkdocs build --strict` in CI."""
    mkdocs = _config()["mkdocs"]
    assert mkdocs == {"configuration": "mkdocs.yml", "fail_on_warning": True}
