"""Tests for the names, gates, publishing conditions and checks of the workflows."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# Job IDs and names of `ci.yml`, as in the other repositories of the org
JOBS = {
    "title": "PR title",
    "lint": "Lint",
    "docs": "Docs",
    "test": "Test (${{ matrix.database }})",
    "chart": "Chart",
    "chart-install": "Chart install",
    "smoke": "Smoke test",
    "readiness": "Release readiness",
    "push": "Push image",
    "scan": "Scan image",
    "publish": "Publish image",
    "passed": "CI passed",
}
# Job IDs and names of `release.yml`, as in the other repositories of the org
RELEASE_JOBS = {
    "prepare": "Prepare release",
    "push": "Push release image",
    "scan": "Scan release image",
    "publish": "Publish release",
}
# Third-party actions are pinned to a full commit, with the version as comment
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
SCAN_ACTION = "elixir-cloud-aai/.github/actions/scan-image"
# A chart file name as the release workflow packages it
CHART = "drs-filer-1.2.3.tgz"
# The digest of a release run's image, and another one
DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64


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


def _release() -> dict[str, Any]:
    """Load `release.yml`.

    Returns:
        The workflow.
    """
    return _load(WORKFLOWS / "release.yml")


def _steps(job: dict[str, Any], action: str) -> list[dict[str, Any]]:
    """Get the steps of a job that use an action.

    Args:
        job: The job.
        action: The action, without its ref (e.g., `actions/checkout`).

    Returns:
        The steps that use the action.
    """
    return [
        step
        for step in job.get("steps", [])
        if step.get("uses", "").startswith(f"{action}@")
    ]


def test_workflow_files() -> None:
    """The workflows are `ci.yml`, `release.yml` and `scan.yml`."""
    names = {path.name: _load(path)["name"] for path in WORKFLOWS.iterdir()}
    assert names == {"ci.yml": "CI", "release.yml": "Release", "scan.yml": "Scan"}


def test_triggers() -> None:
    """CI runs on pull requests and pushes to `dev`, without path filters."""
    # PyYAML (YAML 1.1) reads the key `on` as `True`
    workflow: dict[Any, Any] = _ci()
    triggers = workflow[True]
    assert triggers["push"] == {"branches": ["dev"]}
    assert triggers["pull_request"]["branches"] == ["dev"]
    # `edited`, so that the title check follows title changes
    assert "edited" in triggers["pull_request"]["types"]
    for trigger in triggers.values():
        assert not {"paths", "paths-ignore"} & set(trigger)


def test_release_triggers() -> None:
    """Releases run for version tags only; the scan weekly and on demand."""
    release: dict[Any, Any] = _release()
    assert release[True] == {"push": {"tags": ["v*"]}}
    scan: dict[Any, Any] = _load(WORKFLOWS / "scan.yml")
    assert set(scan[True]) == {"schedule", "workflow_dispatch"}


def test_job_names() -> None:
    """The jobs have the org's IDs and names."""
    for workflow, expected in ((_ci(), JOBS), (_release(), RELEASE_JOBS)):
        jobs = workflow["jobs"]
        assert {job_id: job["name"] for job_id, job in jobs.items()} == expected


def test_job_names_unique() -> None:
    """Job names are unique across all workflows (they name the checks)."""
    names = [
        job["name"]
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for job in _load(path)["jobs"].values()
    ]
    assert len(names) == len(set(names))


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
    """`push` and `publish` run, and may be skipped, exactly where `PUBLISH` says.

    The gate allows them to be skipped only where their condition is false.
    """
    workflow = _ci()
    publish = workflow["env"]["PUBLISH"]
    jobs = workflow["jobs"]
    condition = jobs["push"]["if"]
    assert publish == f"${{{{ {condition} }}}}"
    assert "github.event_name == 'push'" in condition
    assert jobs["publish"]["if"] == condition
    allowed = jobs["passed"]["steps"][0]["with"]["allow-skipped"]
    assert f"!({condition}) && 'push'" in allowed
    assert f"!({condition}) && 'publish'" in allowed


def test_publish_after_checks() -> None:
    """The `dev` image is tagged only after all checks passed, from `dev-images`.

    `push` pushes by digest alongside the checks; `publish` needs every
    other job but the title check and the gate.
    """
    jobs = _ci()["jobs"]
    assert set(jobs["publish"]["needs"]) == set(jobs) - {"title", "publish", "passed"}
    for job_id in ("push", "publish"):
        assert jobs[job_id]["environment"] == "dev-images"
    assert jobs["push"]["permissions"] == {"contents": "read"}
    assert jobs["publish"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }


def test_upstream_owner() -> None:
    """`ci.yml` marks upstream runs by the owner `elixir-cloud-aai` only.

    A typo in, or an inverted, owner check would quietly change upstream runs
    (e.g., release readiness findings to warnings), so every check compares
    with `==`.
    """
    text = (WORKFLOWS / "ci.yml").read_text()
    checks = re.findall(r"github\.repository_owner\s*(\S+)\s*'([^']*)'", text)
    assert checks
    assert len(checks) == text.count("github.repository_owner")
    assert set(checks) == {("==", "elixir-cloud-aai")}


def test_secrets_in_environments() -> None:
    """Only jobs in the `dev-images` or `release` environment use secrets.

    The Docker Hub secrets are kept in these environments (branch `dev` and
    required reviewers), not as repository secrets; Codecov's token is the
    only repository secret.
    """
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name, job in _load(path)["jobs"].items():
            text = yaml.safe_dump(job)
            used = set(re.findall(r"secrets\.([A-Z_]+)", text)) - {"CODECOV_TOKEN"}
            if used:
                environment = job.get("environment")
                if isinstance(environment, dict):
                    environment = environment["name"]
                expected = "release" if path.name == "release.yml" else "dev-images"
                assert environment == expected, f"{path.name}: {name}"


def test_release_environment() -> None:
    """Both release jobs with credentials need approval in `release`."""
    jobs = _release()["jobs"]
    assert jobs["push"]["environment"] == "release"
    assert jobs["publish"]["environment"]["name"] == "release"
    assert "environment" not in jobs["prepare"]
    assert "environment" not in jobs["scan"]


def test_image_name() -> None:
    """The workflows publish and scan the same image, of `DOCKERHUB_ORG`."""
    expected = "docker.io/${{ vars.DOCKERHUB_ORG || 'elixircloud' }}/drs-filer"
    for name in ("ci.yml", "release.yml", "scan.yml"):
        assert _load(WORKFLOWS / name)["env"]["IMAGE_NAME"] == expected


def test_scan_jobs() -> None:
    """Images are scanned in jobs without credentials or signing identity.

    The Trivy action resolves the Trivy binary at run time, so the jobs that
    run it have no environment (and so no Docker Hub secrets), no secrets
    and no permissions beyond reading the repository and uploading to code
    scanning. Each workflow has exactly one such job, `scan`.
    """
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = _load(path)["jobs"]
        scanning = [name for name, job in jobs.items() if _steps(job, SCAN_ACTION)]
        assert scanning == ["scan"], path.name
        job = jobs["scan"]
        assert "environment" not in job, path.name
        assert "secrets." not in yaml.safe_dump(job), path.name
        assert set(job["permissions"].items()) <= {
            ("contents", "read"),
            ("security-events", "write"),
        }, path.name


def test_publish_after_scan() -> None:
    """Images are attested, signed and tagged only after the scan passed.

    `push` pushes the image by digest with SBOM and provenance attestations;
    `publish` needs `scan` (which scans that digest), attests the digest's
    build provenance and signs it (keyless, with the job's OIDC token)
    before it tags it.
    """
    for name in ("ci.yml", "release.yml"):
        jobs = _load(WORKFLOWS / name)["jobs"]
        assert "push" in jobs["scan"]["needs"], name
        (scan,) = _steps(jobs["scan"], SCAN_ACTION)
        image = scan["with"]["image"]
        if name == "release.yml":
            assert image == "${{ env.IMAGE_NAME }}@${{ needs.push.outputs.digest }}"
        else:
            # The pushed digest where `push` runs (see "Determine image")
            assert image == "${{ steps.image.outputs.image }}"
            (determine,) = (s for s in jobs["scan"]["steps"] if s.get("id") == "image")
            assert determine["env"]["DIGEST"] == "${{ needs.push.outputs.digest }}"
            assert 'echo "image=${IMAGE_NAME}@${DIGEST}"' in determine["run"]
        assert "scan" in jobs["publish"]["needs"], name
        (build,) = _steps(jobs["push"], "docker/build-push-action")
        assert build["with"]["sbom"] is True, name
        assert build["with"]["provenance"] == "mode=max", name
        assert "push-by-digest=true" in build["with"]["outputs"], name
        assert "tags" not in build["with"], name
        publish = jobs["publish"]
        assert publish["permissions"]["id-token"] == "write", name
        assert publish["permissions"]["attestations"] == "write", name
        steps = {step["name"]: step for step in publish["steps"]}
        attest = steps["Attest build provenance"]
        assert attest["uses"].startswith("actions/attest-build-provenance@")
        assert attest["with"]["subject-digest"] == "${{ env.DIGEST }}", name
        assert attest["with"]["push-to-registry"] is True, name
        sign = steps["Sign image"]
        assert sign["run"] == 'cosign sign --yes "${IMAGE_NAME}@${DIGEST}"', name
        # Steps of `ci.yml` run only for the head of the branch, as the tags
        assert attest.get("if") == sign.get("if") == steps["Tag image"].get("if")
        names = list(steps)
        assert names.index("Attest build provenance") < names.index("Tag image")
        assert names.index("Sign image") < names.index("Tag image")


def test_release_chart_checked() -> None:
    """The release workflow checks the chart before attesting and signing it.

    `publish` downloads the chart artifact, which any job of the run could
    replace, so it checks that `dist/` holds exactly the file that `prepare`
    packaged (its name and SHA-256, as outputs of `prepare`) before anything,
    the image included, is attested or signed. Only that file is attested and
    signed; the Sigstore bundle (`<chart>.tgz.sigstore.json`) is written to
    `dist/`, so that it is uploaded with the chart. The wiring and order of
    the steps are checked here, the script itself by
    `test_release_chart_check_runs`.
    """
    release = _release()["jobs"]
    prepare = release["prepare"]
    assert prepare["outputs"]["chart_file"] == "${{ steps.chart.outputs.file }}"
    assert prepare["outputs"]["chart_sha256"] == "${{ steps.chart.outputs.sha256 }}"
    packaging = {step["name"]: step for step in prepare["steps"]}
    assert packaging["Package chart"]["id"] == "chart"
    # Re-runs of all jobs replace the chart, so its checksum is the new one
    assert packaging["Upload chart"]["with"]["overwrite"] is True
    steps = {step["name"]: step for step in release["publish"]["steps"]}
    assert steps["Download chart"]["with"] == {"name": "chart", "path": "dist/"}
    check = steps["Check chart"]
    # A failed check stops the job
    assert "continue-on-error" not in check
    assert "if" not in check
    assert check["env"]["FILE"] == "${{ needs.prepare.outputs.chart_file }}"
    assert check["env"]["SHA256"] == "${{ needs.prepare.outputs.chart_sha256 }}"
    chart = "dist/${{ needs.prepare.outputs.chart_file }}"
    assert steps["Attest chart provenance"]["with"]["subject-path"] == chart
    assert steps["Sign chart"]["env"]["CHART"] == chart
    sign = steps["Sign chart"]["run"]
    assert sign == 'cosign sign-blob --yes --bundle "${CHART}.sigstore.json" "${CHART}"'
    names = list(steps)
    assert names.index("Download chart") < names.index("Check chart")
    # A rejected chart leaves the image (pushed untagged by `push`) without
    # GitHub attestation, signature and tags too
    assert names.index("Check chart") < names.index("Attest build provenance")
    assert names.index("Check chart") < names.index("Sign image")
    assert names.index("Check chart") < names.index("Attest chart provenance")
    assert names.index("Check chart") < names.index("Sign chart")
    assert names.index("Attest chart provenance") < names.index("Create release")
    assert names.index("Sign chart") < names.index("Create release")
    assert 'gh release upload "${TAG}" dist/*' in steps["Create release"]["run"]


def test_release_chart_packaged() -> None:
    """The release packages the chart with the library and the published image.

    The package has the release version as `version` and `appVersion` (the
    default tag of the image), the library chart in the version of
    `Chart.lock`, and the published image (`IMAGE_NAME`, also in forks with
    another `DOCKERHUB_ORG`) without a tag of its own; the packaged files are
    checked, not only the copy that is packaged.
    """
    steps = _release()["jobs"]["prepare"]["steps"]
    step = {step["name"]: step for step in steps}["Package chart"]
    assert step["env"] == {
        "VERSION": "${{ steps.version.outputs.version }}",
        "CHART_VERSION": "${{ steps.version.outputs.chart_version }}",
    }
    script = " ".join(step["run"].replace("\\\n", " ").split())
    assert "helm dependency build deployment" in script
    assert "(cd deployment && sha256sum -c charts.sha256)" in script
    assert '--version "${CHART_VERSION}" --app-version "${VERSION}"' in script
    assert 'image="${IMAGE_NAME}"' in script
    assert (
        "IMAGE=\"${image}\" yq -i '.drsFiler.image = strenv(IMAGE)'"
        ' "${chart}/values.yaml"'
    ) in script
    assert 'python scripts/chart_readme.py "${chart}/README.md" "v${VERSION}"' in script
    assert 'helm lint "${chart}" --strict -f deployment/ci/test-values.yaml' in script
    packaged = 'tar -xzOf "${package}" drs-filer/'
    assert f'{packaged}README.md | cmp - "${{chart}}/README.md"' in script
    assert (
        f'{packaged}charts/foca-common/Chart.yaml | yq .version)"' in script
        and "\"$(yq '.dependencies[0].version' deployment/Chart.lock)\"" in script
    )
    assert f'{packaged}values.yaml | yq .drsFiler.image)" == "${{image}}" ]]' in script
    assert f'{packaged}values.yaml | yq .drsFiler.tag)" == "" ]]' in script
    assert f'{packaged}Chart.yaml | yq .appVersion)" == "${{VERSION}}" ]]' in script
    # No legacy value is set
    assert "drs_filer" not in step["run"]


def test_release_chart_image_value() -> None:
    """The values that the release checks are those of the chart's app image."""
    values = yaml.safe_load((ROOT / "deployment" / "values.yaml").read_text())
    assert values["drsFiler"]["image"] == "docker.io/elixircloud/drs-filer"
    assert values["drsFiler"]["tag"] == ""


def test_release_tag_checked_first() -> None:
    """The release tag is checked before any script of the tagged commit runs.

    The step that checks the tag (annotated, signature verified by GitHub,
    commit on `main`) holds a token and runs no code of the tagged commit;
    the scripts run in later steps, the version's without the token.
    """
    prepare = _release()["jobs"]["prepare"]
    steps = {step["name"]: step for step in prepare["steps"]}
    # From the list, so that a second step of the same name is seen
    names = [step["name"] for step in prepare["steps"]]
    assert len(names) == len(steps)
    # Only the checkout and Python come first; Python with a fixed version
    # only (no `python-version-file` or cache, which read files of the commit)
    assert names[:3] == [
        "Check out repository",
        "Set up Python",
        "Check release tag and commit",
    ]
    assert set(steps["Set up Python"]["with"]) == {"python-version"}
    check = steps["Check release tag and commit"]
    assert check["id"] == "commit"
    assert "GH_TOKEN" in check["env"]
    assert ".verification.verified" in check["run"]
    assert "git merge-base --is-ancestor HEAD origin/main" in check["run"]
    # Neither scripts nor Python nor other files of the commit
    for code in ("scripts/", "python", "./"):
        assert code not in check["run"]
    assert prepare["outputs"]["sha"] == "${{ steps.commit.outputs.sha }}"
    derive = steps["Derive release version"]
    assert derive["id"] == "version"
    assert "scripts/release_version.py outputs" in derive["run"]
    assert "GH_TOKEN" not in derive["env"]
    assert "GH_TOKEN" not in prepare.get("env", {})


def test_release_checks() -> None:
    """`prepare` checks the citation, notes, pins and CI run of the commit."""
    runs = " ".join(
        step.get("run", "") for step in _release()["jobs"]["prepare"]["steps"]
    )
    assert 'python scripts/citation.py check "${VERSION}"' in runs
    assert 'python scripts/release_notes.py check "${notes}"' in runs
    assert "python scripts/check_release_pins.py" in runs
    assert "actions/workflows/ci.yml/runs?head_sha=${SHA}&event=push" in runs


def test_release_prerelease_until_1_0() -> None:
    """The GitHub release is created as a draft and flagged by `prerelease`."""
    steps = _release()["jobs"]["publish"]["steps"]
    create = {step["name"]: step for step in steps}["Create release"]
    assert create["env"]["PRERELEASE"] == "${{ needs.prepare.outputs.prerelease }}"
    assert "--draft" in create["run"]
    assert '--prerelease="${PRERELEASE}"' in create["run"]
    assert "--draft=false" in create["run"]


@pytest.mark.parametrize(
    ("extra", "rename", "tamper", "empty", "file", "sha256", "passes"),
    [
        pytest.param(None, None, False, False, CHART, None, True, id="good"),
        pytest.param(None, None, True, False, CHART, None, False, id="wrong-hash"),
        # Sorts before the chart
        pytest.param("other.tgz", None, False, False, CHART, None, False, id="extra"),
        # Sorts after the chart, so only the count rejects it
        pytest.param("zzz", None, False, False, CHART, None, False, id="extra-after"),
        pytest.param(".hidden", None, False, False, CHART, None, False, id="hidden"),
        pytest.param(
            None, "drs-filer-9.9.9.tgz", False, False, CHART, None, False, id="renamed"
        ),
        pytest.param(None, None, False, True, CHART, None, False, id="empty"),
        pytest.param(None, None, False, False, "../x.tgz", None, False, id="bad-name"),
        pytest.param(
            None,
            "drs-filer-1.tar",
            False,
            False,
            "drs-filer-1.tar",
            None,
            False,
            id="not-tgz",
        ),
        pytest.param(None, None, False, False, CHART, "abc", False, id="bad-hash"),
        pytest.param(None, None, False, False, CHART, "", False, id="no-hash"),
        pytest.param(None, None, False, False, CHART, "A" * 64, False, id="upper-hash"),
    ],
)
def test_release_chart_check_runs(
    tmp_path: Path,
    extra: str | None,
    rename: str | None,
    tamper: bool,
    empty: bool,
    file: str,
    sha256: str | None,
    passes: bool,
) -> None:
    """The chart check of `publish` passes only for the chart of `prepare`.

    The step's script runs with the options of GitHub's default shell for
    steps without `shell:` (`bash -e`, no `pipefail`) in a directory whose
    `dist/` holds the downloaded artifact. It needs `bash`
    and GNU `sha256sum`, as on the GitHub runners.

    Args:
        tmp_path: The working directory of the step.
        extra: A file added to the artifact, if any.
        rename: The name the chart is renamed to in the artifact, if any.
        tamper: Whether the chart's content is changed after packaging.
        empty: Whether the artifact holds no file at all.
        file: The chart file name output by `prepare`.
        sha256: The checksum output by `prepare` (that of the chart if None).
        passes: Whether the check passes.
    """
    bash = shutil.which("bash")
    assert bash
    steps = _release()["jobs"]["publish"]["steps"]
    script = {step["name"]: step for step in steps}["Check chart"]["run"]
    dist = tmp_path / "dist"
    dist.mkdir()
    chart = dist / CHART
    chart.write_bytes(b"chart")
    digest = hashlib.sha256(chart.read_bytes()).hexdigest()
    if tamper:
        chart.write_bytes(b"other chart")
    if rename:
        chart.rename(dist / rename)
    if extra:
        (dist / extra).write_bytes(b"extra")
    if empty:
        chart.unlink()
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [bash, "--noprofile", "--norc", "-e", "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "FILE": file,
            "SHA256": digest if sha256 is None else sha256,
        },
        check=False,
    )
    assert (result.returncode == 0) == passes, result.stdout + result.stderr


def test_release_state_checked_first() -> None:
    """A re-run that a published release rejects fails before it signs.

    `publish` checks the state of the release (`release_assets.py
    precheck`) and, for a published release, the digest of the `X.Y.Z`
    image tag right after the chart, before it logs in to Docker Hub,
    attests, signs or tags anything, so that a re-run of all jobs (new
    digest, new chart) leaves the tags of the published release alone.
    "Create release" checks the release again (`state`). The script itself
    is tested by `test_release_state_check_runs`.
    """
    publish = _release()["jobs"]["publish"]
    steps = {step["name"]: step for step in publish["steps"]}
    names = [step["name"] for step in publish["steps"]]
    assert len(names) == len(steps)
    check = steps["Check release state"]
    assert "if" not in check
    assert "continue-on-error" not in check
    assert check["env"]["TAG"] == "${{ github.ref_name }}"
    assert check["env"]["GH_REPO"] == "${{ github.repository }}"
    assert "release_assets.py precheck" in check["run"]
    assert '--releases "${releases}" dist/*' in check["run"]
    assert '"${IMAGE_NAME}:${VERSION}"' in check["run"]
    assert '"${actual}" != "${DIGEST}"' in check["run"]
    assert names.index("Check chart") < names.index("Check release state")
    for later in (
        "Log in to Docker Hub",
        "Attest build provenance",
        "Sign image",
        "Tag image",
        "Attest chart provenance",
        "Sign chart",
    ):
        assert names.index("Check release state") < names.index(later), later
    assert "release_assets.py state" in steps["Create release"]["run"]


@pytest.mark.parametrize(
    ("release", "chart", "tagged", "passes"),
    [
        pytest.param(None, True, None, True, id="none"),
        pytest.param("draft", False, None, True, id="draft"),
        pytest.param("published", True, DIGEST, True, id="rerun-failed-jobs"),
        pytest.param("published", True, OTHER_DIGEST, False, id="new-digest"),
        pytest.param("published", True, None, False, id="no-image-tag"),
        pytest.param("published", False, DIGEST, False, id="new-chart"),
        pytest.param("no-bundle", True, DIGEST, False, id="no-bundle"),
        pytest.param("mutable", True, DIGEST, True, id="mutable-rerun-failed"),
        pytest.param("mutable", False, DIGEST, False, id="mutable-new-chart"),
    ],
)
def test_release_state_check_runs(
    tmp_path: Path,
    release: str | None,
    chart: bool,
    tagged: str | None,
    passes: bool,
) -> None:
    """The release state check of `publish` rejects re-runs of all jobs.

    The step's script runs as in `test_release_chart_check_runs`, with
    stand-ins for `gh` (the releases) and `docker` (the digest of the image
    tag); `python` runs `scripts/release_assets.py`, and `jq` is needed, as
    on the GitHub runners.

    Args:
        tmp_path: The working directory of the step.
        release: The release of the tag, if any: `draft`, `published`
            (immutable), `no-bundle` (published without the chart's
            Sigstore bundle) or `mutable` (published, not immutable).
        chart: Whether the release has this run's chart (else another).
        tagged: The digest that the image tag points to; no tag if `None`.
        passes: Whether the check passes.
    """
    bash = shutil.which("bash")
    assert bash and shutil.which("jq")
    steps = _release()["jobs"]["publish"]["steps"]
    script = {step["name"]: step for step in steps}["Check release state"]["run"]
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "release_assets.py", tmp_path / "scripts")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / CHART).write_bytes(b"chart")
    digest = hashlib.sha256(b"chart" if chart else b"other chart").hexdigest()
    assets = [
        {"name": CHART, "digest": f"sha256:{digest}", "state": "uploaded"},
        {"name": f"{CHART}.sigstore.json", "digest": None, "state": "uploaded"},
    ]
    releases = [{"tag_name": "v1.2.2", "draft": False, "immutable": True, "assets": []}]
    if release is not None:
        draft = release == "draft"
        releases.append(
            {
                "tag_name": "v1.2.3",
                "draft": draft,
                "immutable": release in ("published", "no-bundle"),
                "assets": assets[:1] if release == "no-bundle" else assets,
            }
        )
    (tmp_path / "releases.json").write_text(json.dumps([releases]))
    (tmp_path / "manifest.json").write_text(json.dumps({"digest": tagged}))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)
    stubs = {
        # Only the request of the step gets the releases (`$GH_REPO` is
        # this test's, see below)
        "gh": (
            '[[ "$*" == "api --paginate --slurp '
            'repos/$GH_REPO/releases?per_page=100" ]] && '
            f'cat "{tmp_path}/releases.json"'
        ),
        "docker": (
            '[[ "$*" == "buildx imagetools inspect $IMAGE_NAME:1.2.3 '
            '--format {{ json .Manifest }}" ]] && '
            + (f'cat "{tmp_path}/manifest.json"' if tagged else "exit 1")
        ),
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(f"#!/usr/bin/env bash\n{body}\n")
        stub.chmod(0o755)
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [bash, "--noprofile", "--norc", "-e", "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GH_REPO": "elixir-cloud-aai/drs-filer",
            "TAG": "v1.2.3",
            "VERSION": "1.2.3",
            "DIGEST": DIGEST,
            "IMAGE_NAME": "docker.io/elixircloud/drs-filer",
        },
        check=False,
    )
    assert (result.returncode == 0) == passes, result.stdout + result.stderr
    if release in ("published", "no-bundle") and not passes:
        assert "release a new patch version" in result.stdout + result.stderr
    if release == "mutable" and not passes:
        assert "gh release delete v1.2.3" in result.stdout + result.stderr
    if tagged is None and release == "published":
        assert "can't be inspected" in result.stdout + result.stderr


def test_scheduled_scan_waits_for_release() -> None:
    """The weekly scan of `latest` runs only once a stable release exists."""
    steps = _load(WORKFLOWS / "scan.yml")["jobs"]["scan"]["steps"]
    names = [step["name"] for step in steps]
    check = steps[names.index("Check for a stable release")]
    (scan,) = (step for step in steps if step.get("uses", "").startswith(SCAN_ACTION))
    assert names.index(check["name"]) < names.index(scan["name"])
    assert scan["if"] == f"steps.{check['id']}.outputs.found == 'true'"
    assert scan["with"]["image"] == "${{ env.IMAGE_NAME }}:latest"


@pytest.mark.parametrize(
    ("tags", "status", "found"),
    [
        pytest.param("", 0, False, id="no-release"),
        pytest.param("v1.2.3rc1\nv0.3.0b1", 0, False, id="pre-releases-only"),
        pytest.param("v1.2.3rc1\nv1.2.3", 0, True, id="stable"),
        pytest.param("xv1.2.3\nv1.2.3.4\nv1.2", 0, False, id="not-versions"),
        pytest.param("v1.2.3", 1, False, id="lookup-fails"),
    ],
)
def test_scheduled_scan_release_check_runs(
    tmp_path: Path, tags: str, status: int, found: bool
) -> None:
    """The release check finds stable releases and fails if the lookup does.

    The step's script runs as GitHub runs it (`bash -e`), with a stub of
    `gh` that prints the tags of the published releases (or fails).

    Args:
        tmp_path: Directory of the stub and the output file.
        tags: Tags that the stub prints, one per line.
        status: Exit status of the stub.
        found: Whether the step reports a stable release.
    """
    bash = shutil.which("bash")
    assert bash
    steps = _load(WORKFLOWS / "scan.yml")["jobs"]["scan"]["steps"]
    step = {step["name"]: step for step in steps}["Check for a stable release"]
    stub = tmp_path / "gh"
    (tmp_path / "tags").write_text(tags)
    stub.write_text(f'#!{bash}\ncat "{tmp_path / "tags"}"\nexit {status}\n')
    stub.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [bash, "--noprofile", "--norc", "-e", "-c", step["run"]],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
        },
        check=False,
    )
    assert (result.returncode == 0) == (status == 0), result.stderr
    assert ("found=true" in output.read_text()) == found


def test_verification_commands() -> None:
    """The verification commands name the workflows that sign the images.

    `docs/operations.md` verifies release images and charts with the
    identity of `release.yml` at the release tag (`gh attestation verify`
    and `cosign verify` of the image, both of the chart), and `dev` images
    with that of `ci.yml` at `refs/heads/dev`, so renaming a workflow must
    update them.
    """
    text = " ".join((ROOT / "docs" / "operations.md").read_text().split())
    workflows = re.findall(r"drs-filer/\.github/workflows/([a-z-]+\.yml)", text)
    assert sorted(set(workflows)) == ["ci.yml", "release.yml"]
    assert all((WORKFLOWS / workflow).is_file() for workflow in workflows)
    release = "drs-filer/.github/workflows/release.yml"
    assert text.count(f"{release}@refs/tags/v{{{{ version }}}}") == 2
    assert text.count(f"--signer-workflow elixir-cloud-aai/{release}") == 2
    assert text.count("--source-ref refs/tags/v{{ version }}") == 2
    assert "drs-filer/.github/workflows/ci.yml@refs/heads/dev" in text
    assert "--source-ref refs/heads/dev" in text


def test_actions_pinned() -> None:
    """All actions are pinned to a full commit."""
    for path in WORKFLOWS.glob("*.yml"):
        for job in _load(path)["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step:
                    assert PINNED.match(step["uses"]), step["uses"]


def test_shared_actions_same_release() -> None:
    """The shared actions of `elixir-cloud-aai/.github` are on one commit."""
    pins = {
        step["uses"].split("@", 1)[1]
        for path in WORKFLOWS.glob("*.yml")
        for job in _load(path)["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("elixir-cloud-aai/.github/")
    }
    assert len(pins) == 1


def test_python_of_image() -> None:
    """All jobs use the Python version of the base image."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    match = re.search(r"-py(\d+\.\d+)@", dockerfile)
    assert match
    versions = [
        step["with"]["python-version"]
        for path in WORKFLOWS.glob("*.yml")
        for job in _load(path)["jobs"].values()
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
    """No job of `ci.yml` has a concurrency group of its own.

    A pending job in a group is cancelled when another one arrives, which
    would fail the gate of its run.
    """
    for job in _ci()["jobs"].values():
        assert "concurrency" not in job
