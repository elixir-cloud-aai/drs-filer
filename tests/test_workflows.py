"""Tests for the names, gate and publishing conditions of the workflows."""

from pathlib import Path
import re
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# Job IDs and names of `ci.yml`, as in the other repositories of the org
JOBS = {
    "title": "PR title",
    "lint": "Lint",
    "test": "Test (${{ matrix.database }})",
    "smoke": "Smoke test",
    "push": "Push image",
    "passed": "CI passed",
}
# Third-party actions are pinned to a full commit, with the version as comment
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _load(path: Path) -> dict[str, Any]:
    """Load a workflow file.

    Args:
        path: The path of the workflow file.

    Returns:
        The workflow.
    """
    workflow: dict[str, Any] = yaml.safe_load(path.read_text())
    return workflow


def _ci() -> dict[str, Any]:
    """Load `ci.yml`.

    Returns:
        The workflow.
    """
    return _load(WORKFLOWS / "ci.yml")


def test_workflow_files() -> None:
    """The only workflow is `ci.yml`, named `CI`."""
    names = {path.name: _load(path)["name"] for path in WORKFLOWS.iterdir()}
    assert names == {"ci.yml": "CI"}


def test_triggers() -> None:
    """CI runs on pull requests and pushes to `dev`, without path filters."""
    # PyYAML (YAML 1.1) reads the key `on` as `True`
    workflow: dict[Any, Any] = _ci()
    triggers = workflow[True]
    assert triggers["push"] == {"branches": ["dev"]}
    assert triggers["pull_request"]["branches"] == ["dev"]
    for trigger in triggers.values():
        assert not {"paths", "paths-ignore"} & set(trigger)


def test_job_names() -> None:
    """The jobs have the org's IDs and names."""
    jobs = _ci()["jobs"]
    assert {job_id: job["name"] for job_id, job in jobs.items()} == JOBS


def test_gate_needs_all_jobs() -> None:
    """The gate needs every other job and runs whatever their results."""
    jobs = _ci()["jobs"]
    gate = jobs["passed"]
    assert set(gate["needs"]) == set(jobs) - {"passed"}
    assert gate["if"] == "always()"
    step = gate["steps"][0]
    assert step["uses"].startswith("elixir-cloud-aai/.github/actions/gate@")
    assert step["with"]["needs"] == "${{ toJSON(needs) }}"


def test_publish_condition() -> None:
    """`push` runs, and may be skipped, exactly where `PUBLISH` says.

    The gate allows `push` to be skipped only where its condition is false.
    """
    workflow = _ci()
    publish = workflow["env"]["PUBLISH"]
    condition = workflow["jobs"]["push"]["if"]
    assert publish == f"${{{{ {condition} }}}}"
    assert "github.event_name == 'push'" in condition
    allowed = workflow["jobs"]["passed"]["steps"][0]["with"]["allow-skipped"]
    assert f"!({condition}) && 'push'" in allowed


def test_push_after_checks() -> None:
    """The image is pushed only after all checks passed, from `dev-images`."""
    push = _ci()["jobs"]["push"]
    assert set(push["needs"]) == {"lint", "test", "smoke"}
    assert push["environment"] == "dev-images"
    assert push["permissions"] == {"contents": "read"}


def test_secrets_only_in_environments() -> None:
    """Only jobs in an environment use secrets, except Codecov's token."""
    for job_id, job in _ci()["jobs"].items():
        text = yaml.safe_dump(job)
        secrets = set(re.findall(r"secrets\.(\w+)", text)) - {"CODECOV_TOKEN"}
        if secrets:
            assert "environment" in job, job_id


def test_actions_pinned() -> None:
    """All actions are pinned to a full commit."""
    for path in WORKFLOWS.glob("*.yml"):
        for job in _load(path)["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step:
                    assert PINNED.match(step["uses"]), step["uses"]


def test_python_of_image() -> None:
    """All jobs use the Python version of the base image."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    match = re.search(r"-py(\d+\.\d+)@", dockerfile)
    assert match
    versions = [
        step["with"]["python-version"]
        for job in _ci()["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert versions
    assert set(versions) == {match[1]}


def test_citation_validated() -> None:
    """The lint job validates `CITATION.cff` with a pinned cffconvert."""
    commands = [step.get("run", "") for step in _ci()["jobs"]["lint"]["steps"]]
    assert (
        "pipx run --spec cffconvert==2.0.0 cffconvert --validate -i CITATION.cff"
        in commands
    )
    assert (ROOT / "CITATION.cff").is_file()


def test_no_job_concurrency() -> None:
    """No job has a concurrency group of its own.

    A pending job in a group is cancelled when another one arrives, which
    would fail the gate of its run.
    """
    for job in _ci()["jobs"].values():
        assert "concurrency" not in job
