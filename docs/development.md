# Development

## Setup

DRS-Filer is packaged with
[`pyproject.toml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/pyproject.toml);
all dependencies are locked in
[`uv.lock`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/uv.lock).
You need [uv](https://docs.astral.sh/uv/) and [Git](https://git-scm.com/); uv
also provides the Python version that DRS-Filer targets (see
`requires-python` in `pyproject.toml`, currently Python 3.12, the version of
the base image in the
[`Dockerfile`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/Dockerfile)).

Clone the repository and install the app with its development tools (the
`dev` extra) from the lock into a virtual environment (`.venv`):

```bash
git clone https://github.com/elixir-cloud-aai/drs-filer.git
cd drs-filer
uv sync --locked --extra dev
```

Install the [pre-commit](https://pre-commit.com/) hooks, so that the checks
run on every commit, and run them on all files once:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

The hooks
([`.pre-commit-config.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.pre-commit-config.yaml))
format and lint the code with [ruff](https://docs.astral.sh/ruff/) (Google
style docstrings), check types with [mypy](https://mypy-lang.org/) (complete
type hints), check the project's semgrep (security) and ast-grep
(anti-patterns) rules and their rule tests (see [Static analysis
rules](#static-analysis-rules)), lint the GitHub Actions workflows with
actionlint, scan for hardcoded secrets with gitleaks and run basic file
checks. CI runs the same hooks on all files.

Run the tests (see [Tests](#tests)):

```bash
uv run pytest
```

The version of the package comes from Git tags (`vX.Y.Z`) via
[setuptools-scm](https://setuptools-scm.readthedocs.io/); there is no version
to edit in the code (see [Versioning and
releases](#versioning-and-releases)).

## Development server

For development only, the app can be run with Flask's development server,
from any directory, with a MongoDB instance reachable at the host and port
set in `db` of the config, e.g., MongoDB published on the host (`ports:
["127.0.0.1:27017:27017"]` for `mongodb` in a `docker-compose.override.yaml`,
then `docker compose up --detach mongodb`) and an overlay with
`db.host: localhost` and the `custom.drs` of `config.dev.yaml`:

```bash
FOCA_CONFIG_OVERLAY=config.local.yaml uv run python -m drs_filer.app
```

The shipped config runs the development server without debug mode and
reloader. For Flask's debugger and reloader, set `server.debug: True` in a
local overlay only (`config.local.yaml` is ignored by Git), with the server
on a loopback host (`server.host: 127.0.0.1`; FOCA warns otherwise); never
commit or deploy it.

## Running without authentication

Writes need an access token of an admin (see [Access
control](access-control.md)), also with Docker Compose, whose development
overlay (`config.dev.yaml`) trusts a fictitious identity provider and
requires no admins. To set your own identity provider and admin group, see
[Docker Compose](configuration.md#docker-compose) and [Deployment
configuration](configuration.md#deployment-configuration). To try writes
locally without an identity provider, disable authentication with the
overlay
[`config.noauth.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/config.noauth.yaml),
which sets FOCA's `api.specs.drs.disable_auth` (`false` in the base
config), after `config.dev.yaml`, via `DRS_FILER_CONFIG_OVERLAY` (which
`docker-compose.yaml` passes to the app as `FOCA_CONFIG_OVERLAY`):

```bash
DRS_FILER_CONFIG_OVERLAY=/etc/drs-filer/config.dev.yaml:/etc/drs-filer/config.noauth.yaml \
  docker compose up --build --wait
```

All operations are then public, writes too, and FOCA warns on startup that
authentication is disabled (`Authentication is disabled for spec 'drs'`).
Run `docker compose up --wait` without the variable to enable it again. Only
use this on your machine (Docker Compose publishes the app on the loopback
interface only), never for deployments. The smoke test (see
[Tests](#tests)) needs it, or an admin's access token in `DRS_FILER_TOKEN`.
Access URLs need a token too, unless authentication is disabled (see
[Requiring login for reads](access-control.md#requiring-login-for-reads)).

## Tests

The tests come in three levels; `uv run pytest` runs the first two, which
must cover the code completely (`fail_under` in `pyproject.toml`, and the
same targets for Codecov in `codecov.yml`):

- **Unit tests** (`tests/ga4gh/`, `tests/test_*.py`): controllers and
  helpers with bare Flask apps, the config, the image, the chart, the
  workflows and the Read the Docs configuration.
- **App tests** (`tests/api/`, one module per group of endpoints): every
  endpoint through Flask's test client, with the app created from the
  shipped config and the test overlay (`tests/config_overlay.yaml`), so that
  request validation, authentication, access control and error handling
  are covered too. The identity provider of the test overlay is mocked
  (`mock_get()` in `tests/conftest.py`); the test client `client` sends an
  admin's access token, `anonymous_client` none, and `make_headers()` makes
  tokens of other users (`tests/api/test_auth.py`). They use an
  in-memory MongoDB (mongomock), or a real one if `MONGODB_TEST_URI` is set,
  as in CI; the tests drop database `drsStore` there and refuse to start if
  it exists already:

    ```bash
    docker run --detach --rm --name drs-filer-test-db -p 127.0.0.1:27018:27017 mongo:7.0
    MONGODB_TEST_URI=mongodb://127.0.0.1:27018 uv run pytest
    docker stop drs-filer-test-db
    ```

- **Smoke test** (`tests/smoke/`): the API of a running app, e.g., of the
  Compose stack (see [Getting started](getting-started.md)); skipped unless
  `DRS_FILER_URL` is set. It registers objects and service info, and reads
  access URLs, so it needs an admin's access token in `DRS_FILER_TOKEN`
  (sent with writes and access URLs), or an app without
  authentication (see [Running without
  authentication](#running-without-authentication)), as in CI:

    ```bash
    DRS_FILER_URL=http://localhost:8080/ga4gh/drs/v1 uv run pytest tests/smoke
    ```

The chart tests (`tests/test_chart.py`) render the Helm chart with `helm
template`; they are skipped without [Helm](https://helm.sh/) (but fail in
CI), and need the library chart, downloaded once (and after changes of
`deployment/Chart.lock`) with:

```bash
helm dependency build deployment
```

To install the chart on a local [kind](https://kind.sigs.k8s.io/) cluster
as the job `chart-install` does, see its steps in `ci.yml`.

Tests can't open connections (TCP, or connected UDP), except to the test
database (and the smoke test to the app). Shared fixtures are in
`tests/conftest.py`, request bodies in `tests/mock_data.py`.

## Static analysis rules

Besides ruff's security rules (`S`, from bandit), pre-commit runs
project-specific rules, each with tests:

- [semgrep](https://semgrep.dev/), security rules in
  [`.semgrep/drs-filer.yml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.semgrep/drs-filer.yml),
  shared with FOCA and the other FOCA apps (keep their patterns, messages and
  severities identical):
    - `flask-debug-enabled`: debug mode in the app config or the Helm chart
    - `jwt-decode-without-verification`: JWTs decoded without verifying the
      signature
    - `jwt-decode-unsafe-algorithms`: JWTs verified with the algorithm `none`
      or the one the token's header names
    - `yaml-unsafe-load`: YAML loaded with PyYAML's full or unsafe loader
    - `tls-verification-disabled`: certificate verification turned off
- [ast-grep](https://ast-grep.github.io/), anti-patterns in
  [`.ast-grep/rules/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/.ast-grep/rules)
  (configured in
  [`sgconfig.yml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/sgconfig.yml));
  all but `pydantic-v1-dict`, `root-logger-call` and `string-status-code`
  check the package (`drs_filer/`) only:
    - `foca-config-attribute`: untyped access to the FOCA config
      (`app.config.foca`)
    - `generic-exception-raised`: `Exception` or `BaseException` raised
    - `print-call`: output with `print()` instead of a logger
    - `pydantic-v1-dict`: Pydantic v1's `.dict()` instead of `.model_dump()`
    - `root-logger-call`: messages logged with the root logger
    - `string-status-code`: HTTP status codes returned as strings

pre-commit runs the rule tests when the rules change; run it with `uv run
pre-commit ...`, as the ast-grep hooks use the ast-grep of the dev
dependencies. To run the rule tests by hand: `uv run ast-grep test
--skip-snapshot-tests`, and `semgrep --test .` in `.semgrep/` (semgrep is not
a dev dependency: pre-commit installs its own, so install it separately for
this).

Add a rule together with its test cases: for semgrep in
`.semgrep/drs-filer.py` (Python rules) or `.semgrep/drs-filer.test.yaml`
(YAML rules), marked with `# ruleid: <rule-id>` and `# ok: <rule-id>`; for
ast-grep in `.ast-grep/rule-tests/<rule-id>-test.yml`, with `valid` and
`invalid` snippets.

Suppress a finding only if it is a false positive or can't be avoided yet,
with a suppression comment on its line: `# nosemgrep: <rule-id>`,
`# ast-grep-ignore: <rule-id>`, `# noqa: <code>` (ruff),
`# type: ignore[<code>]` (mypy) or `# gitleaks:allow`. Give the reason in a
comment on the line before, as most suppression comments can't hold it.

## Continuous integration

CI
([`.github/workflows/ci.yml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.github/workflows/ci.yml),
workflow `CI`) runs on pull requests and on pushes to `dev`;
`tests/test_workflows.py` checks its names, triggers, gate, publishing
condition and action pins. Its jobs, and how to run them locally:

| Job | Name | Locally |
| --- | --- | --- |
| `title` | PR title | Pull request titles follow [Conventional Commits](https://www.conventionalcommits.org/), at most 50 characters (the title becomes the commit message of the squash merge) |
| `lint` | Lint | `uv lock --check`, `uv run pre-commit run --all-files`, `pipx run --spec cffconvert==2.0.0 cffconvert --validate -i CITATION.cff` |
| `docs` | Docs | `uv run --extra docs mkdocs build --strict` (see [Documentation](#documentation)) |
| `test` | Test (mongomock), Test (MongoDB 7.0) | `uv run coverage run -m pytest && uv run coverage report`, and against MongoDB as in [Tests](#tests) |
| `chart` | Chart | `helm dependency build deployment`, `helm lint deployment --strict -f deployment/ci/test-values.yaml`, `uv run pytest tests/test_chart.py` |
| `chart-install` | Chart install | Installs the chart on kind with the image of the commit and runs the smoke test through a port forward (see [Tests](#tests)) |
| `smoke` | Smoke test | `docker compose up --build --detach --wait`, then the smoke test as in [Tests](#tests) |
| `readiness` | Release readiness | The checks of pins and release notes in [Versioning and releases](#versioning-and-releases), for the version in `CITATION.cff` while it has no tag |
| `push` | Push image | Pushes the image by digest, untagged (pushes to `dev` in this repository only) |
| `scan` | Scan image | `docker build -t drs-filer:scan .`, then `trivy image --ignorefile .trivyignore.yaml drs-filer:scan` ([Trivy](https://trivy.dev/); CI fails on fixable critical and high findings only) |
| `publish` | Publish image | Attests, signs and tags the scanned digest (pushes to `dev` in this repository only) |
| `passed` | CI passed | Passes if all other jobs passed or were skipped as intended |

`CI passed` is the only required check. Add every new job to its `needs`.

The coverage of `Test (mongomock)` is uploaded to Codecov (repository
secret `CODECOV_TOKEN`; uploads fail the run only on pushes to this
repository). On pushes to `dev`, `Push image` builds the image and pushes it
to Docker Hub by digest, untagged (with SBOM and provenance attestations);
`Scan image` scans exactly that digest (on pull requests, and in forks that
publish nothing, a local build), and `Publish image`, once all other jobs
passed, attests the digest's build provenance, signs it and tags it `dev`
and `sha-<commit>`, if the commit is still the head of `dev`. `Push image`
and `Publish image` run in the environment `dev-images`, which holds the
secrets `DOCKERHUB_LOGIN` and `DOCKERHUB_TOKEN` and allows branch `dev`
only. The organization is the repository variable `DOCKERHUB_ORG` (default
`elixircloud`); forks publish only if they set it (and the secrets). See
[Versioning and releases](#versioning-and-releases) for the scans and the
release images.

## Dependencies

After changing dependencies in `pyproject.toml`, update the lock with `uv
lock` and commit both files.

Dependabot
([`.github/dependabot.yml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.github/dependabot.yml))
opens grouped pull requests against `dev` once a month, labelled `type:
dependencies`, for the locked Python dependencies (`uv.lock`), the actions of
the workflows, the images of the `Dockerfile` and the hook revisions of
`.pre-commit-config.yaml`. Some updates are made by hand instead:

- FOCA, never by Dependabot: the image build fails unless the base image
  (`elixircloud/foca` in the `Dockerfile`) has the locked FOCA release
  (`scripts/image_requirements.py`), so change the `foca` requirement in
  `pyproject.toml`, the lock (`uv lock`) and the base image's tag and digest
  together, in one pull request.
- Major updates of connexion, which wait for a FOCA upgrade.
- uv's pin in `.readthedocs.yaml`, which must be the version that `uv.lock`
  locks (`tests/test_readthedocs.py` fails otherwise).

## Documentation

This documentation is built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), from
`docs/` and
[`mkdocs.yml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/mkdocs.yml),
by Read the Docs (configured in
[`.readthedocs.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.readthedocs.yaml))
and in CI (job `docs`), both with the versions of `uv.lock` (the `docs`
extra); warnings, e.g., of broken links, fail the build. The [API
reference](reference.md) is generated from the docstrings with
[mkdocstrings](https://mkdocstrings.github.io/). To build it locally, or
serve it with live reloading, in the dev environment set up as above, with
the docs dependencies too (`uv sync` removes the extras that it isn't given,
so `dev` stays in the command):

```bash
uv sync --locked --extra dev --extra docs
uv run mkdocs build --strict  # into `site/`, ignored by Git
uv run mkdocs serve
```

The introduction, the quick start and the citation of the home and getting
started pages are sections of `README.md` (between `--8<-- [start:<name>]`
and `--8<-- [end:<name>]` comments), so that they are written only once.
Links in these sections must be absolute, as they must also work on GitHub
and PyPI.

The docs hooks (`docs/hooks.py`, configured in `mkdocs.yml`) replace the
placeholders of the release version (see [Versioning and
releases](#versioning-and-releases)), and replace a line
`--8<-- "deployment/README.md"` in a page with the chart's README, its
links adapted to the docs (links to pages of the docs become links to these
pages, which MkDocs checks; links to files on GitHub point to the commit
that Read the Docs builds). The deployment guide includes the chart's README
this way. The hooks are tested in `tests/test_docs_hooks.py`.

## Versioning and releases

The project adopts the [semantic versioning](https://semver.org/) scheme for
versioning. Currently the service is in beta stage, so the API may change
without further notice.

The version is stored in Git tags (`vX.Y.Z`, pre-releases `vX.Y.ZrcN`):
the package version is derived from them (via
[setuptools-scm](https://setuptools-scm.readthedocs.io/)), and the service
info reports it. Builds without Git metadata, such as local Docker builds
(e.g., with Docker Compose), report `0.0.0.dev0`; the workflows pass the
version to the image build (build argument `SETUPTOOLS_SCM_PRETEND_VERSION`).
Images on Docker Hub (`elixircloud/drs-filer`) are tagged:

- `X.Y.Z`: release `X.Y.Z`; `latest`: the highest stable release (not an
  alpha, beta or release candidate) on `main`;
- `dev`: the latest commit on `dev`; `sha-<commit>`: commit `<commit>` on
  `dev` (full SHA), to deploy a fixed commit. Only commits that are still the
  head of `dev` when their CI run reaches the image job get images.

The current release version is taken from one source, so that a release
doesn't need to bump it in many places: the release tag and, on `dev`, the
`version` in `CITATION.cff` (set before tagging, see below; from then on, the
latest docs show the upcoming version, and before the first release, they
show `X.Y.Z`). The docs and the chart's README (`deployment/README.md`) write
it as a placeholder, `version` in double curly braces with a space inside
each pair, and the chart version (e.g., `1.2.3-rc1` for `1.2.3rc1`, as in the
names of the packaged charts) as `chart_version` in the same braces
(`VARIABLE` and `CHART_VARIABLE` in `scripts/chart_readme.py`; this page
can't show them, as they would be replaced), also in commands and links. The
docs hooks (`docs/hooks.py`) replace them with the version of `CITATION.cff`,
and `scripts/chart_readme.py` with the release version when the chart is
packaged; files read on GitHub (e.g., `deployment/README.md`) show the
placeholders, and sections of `README.md` included as snippets can't use
them. Comments, templates and tests use placeholders (e.g., `1.2.3`) and
refer to sections by anchor. `tests/test_version_mentions.py` fails if the
current release version is mentioned as a release of the app (as a tag,
image or chart, or as "release" or "version" in prose; not, e.g., as the
version of a dependency) anywhere else than in `CITATION.cff`,
`docs/releases/`, the tests of the release tooling, links to the notes and
assets of a release, and migration headings (e.g., "From versions before
X"), which are about that release itself.

Features and fixes are merged into `dev`. Branch `main` only ever moves
forward to commits on `dev` that are released. First, shortly before the
release, set its version and date in the citation metadata, which Zenodo
archives with each release, and merge the change into `dev`; each version,
also each pre-release (e.g., `X.Y.Zrc1`), needs its own such change:

```bash
python scripts/citation.py set X.Y.Z  # date: today (UTC), or --date YYYY-MM-DD
```

`scripts/citation.py` uses the standard library only and is tested in
`tests/test_citation.py`; `check` (below) fails unless `version` is `X.Y.Z`
and `date-released` is a date that is not in the future (UTC).

Then, to release version `X.Y.Z` from commit `<sha>` on `dev` (with that
change), after CI passed for it:

```bash
git switch --detach <sha>
# The release workflow's checks that need no tag, as it runs them
python scripts/release_version.py outputs vX.Y.Z
python scripts/citation.py check X.Y.Z
python scripts/check_release_pins.py
! grep -n TODO docs/releases/X.Y.Z.md  # curated notes, if any
[ ! -f docs/releases/X.Y.Z.md ] || python scripts/release_notes.py check docs/releases/X.Y.Z.md
readme="$(mktemp -d)/README.md" && cp deployment/README.md "${readme}"
python scripts/chart_readme.py "${readme}" vX.Y.Z  # links of the chart
helm dependency build deployment && (cd deployment && sha256sum -c charts.sha256)
helm lint deployment --strict -f deployment/ci/test-values.yaml  # as `prepare`
helm package deployment --version X.Y.Z --app-version X.Y.Z -d "$(mktemp -d)"
git push origin <sha>:main  # fails unless it is a fast-forward
git tag -s vX.Y.Z <sha> -m "vX.Y.Z"
git push origin vX.Y.Z
```

Tags can't be moved or deleted (see the repository settings below), and the
release workflow checks the tagged commit, so a check that fails after the
tag is pushed fails again on re-runs: the release then needs a new patch
version, with its own citation metadata and notes. Run these checks before
tagging, therefore. The CI job "Release readiness" runs the pin and the
notes checks, too, for the version in `CITATION.cff` while it has no tag (or
its tag is on the checked commit): on pull requests and in forks (which
often lack upstream's later tags) as warnings, on pushes to `dev` as errors,
which fail the CI run that the release workflow requires for the release
commit. The image scan of the release workflow can still fail after the
tag, e.g., on a vulnerability published since CI last scanned the image;
the remedy is the same.

The tag must be annotated and signed (`git tag -s`), with a key that GitHub can
verify (added to the tagger's GitHub account). The [release
workflow](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.github/workflows/release.yml),
triggered by the tag, checks that GitHub verified the signature, that the
signed tag object has the name of the tag, that the
tag's commit is on `main` and its `CITATION.cff` has the release version and
a date that is not in the future (UTC), that the dependencies are releases
(see below), and that the [CI
workflow](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.github/workflows/ci.yml)
passed for it (a run for the push of the commit to `dev`; if CI hasn't
finished, failed or was cancelled, e.g., the image job of a commit that a
later one superseded, re-run CI, then the release workflow). It packages
the Helm chart with the release version as `version` and `appVersion`, so
that it deploys the release image (`elixircloud/drs-filer:X.Y.Z`; the
repository's chart has the placeholder `version` 0.0.0 and `appVersion`
`dev`), with the library chart (checked against `deployment/charts.sha256`).
In the packaged README, links to the latest docs and to files on branch `dev`
point to the release (`/en/vX.Y.Z/`, `blob/vX.Y.Z/`); the release fails if
any link to a version that moves is left (`scripts/chart_readme.py`). The
chart in the repository is unchanged. After approval in the `release`
environment, it builds the image, pushes it by digest (untagged, with SBOM
and provenance attestations) and checks that the app reports the release
version; it then scans exactly that digest for vulnerabilities, in a job
without credentials. After a second approval in the `release` environment
(once the scan passed), it checks that the chart it downloads is the one it
packaged (a single file with the name and SHA-256 recorded when packaging;
if not, the job fails before it attests, signs or tags anything), attests
the build provenance of the scanned digest and signs it (see [Verifying
images and charts](operations.md#verifying-images-and-charts)), tags exactly
that image `X.Y.Z` (and `latest`, if it is the highest stable release on
`main`), attests and signs the chart, and creates a GitHub release with the
chart (`.tgz`), its Sigstore bundle (`.tgz.sigstore.json`) and the release
notes (see below). Releases are immutable (see the repository settings
below): once published, their assets can't be added, replaced or deleted.
The workflow therefore creates the release as a draft, uploads the assets
and publishes it last. A re-run finishes a draft left by an earlier attempt;
if the release is already published (e.g., by hand), it uploads nothing and
fails unless the release has exactly the assets that the run built (only the
Sigstore bundles may differ, as every attempt signs anew). It checks this
twice: right after the chart, before it attests, signs or tags anything (for
a published release, the image tag `X.Y.Z` must also point to the run's
digest already), and again before it creates the release. The error says
what to do: a new patch version, or, if releases are not immutable,
deleting the release and re-running. Add curated notes to the
[changelog](changelog.md) in `mkdocs.yml` (`nav`; the docs build fails
otherwise), and refer to pages of the docs by name rather than by relative
links, which don't work in GitHub releases. No packages are published to
PyPI. Tags of alpha, beta and release candidate versions (e.g., `vX.Y.Zrc1`,
also `aN` and `bN`) get chart version `X.Y.Z-rc1` (or `-aN`, `-bN`) and never
update the `latest` image. These and, until 1.0.0, all other releases are
GitHub pre-releases (never marked as the latest release). Digests of runs
that fail before `publish` (also in the scan) stay on Docker Hub, untagged
and unsigned; if `publish` fails after signing, the digest stays signed
(and possibly tagged), and a re-run of the failed jobs finishes it.
Re-running all jobs of the release workflow builds, scans, signs and tags a
new image digest (the image build is not reproducible); an earlier digest
that was published stays signed. Re-running only the failed jobs reuses the
digest already pushed (and scans it again if the scan failed). Re-running
all jobs also packages the chart again and replaces the chart artifact; the
release checks the new chart against its new SHA-256. Once the GitHub
release is published, re-running all jobs fails in `publish` (step "Check
release state") before it attests, signs or tags the new digest, so that
`X.Y.Z` and `latest` keep pointing to the published image; re-running the
failed jobs of a published release still passes, as it reuses the digest
and the chart. Re-runs use the workflow of the tagged commit, so releases
tagged before this step was added don't have it (check the step's name in
the run): never re-run all jobs of their runs. Images of
commits on `dev` are published by the CI workflow (environment
`dev-images`): it pushes the image by digest, scans it, and attests, signs
and tags exactly that digest once all other jobs passed.

Once `publish` has tagged the image (and created the GitHub release, in the
same job), the job "Notify Pubgrade" (`notify`) registers the image
(`elixircloud/drs-filer:X.Y.Z`, of `DOCKERHUB_ORG`), with the release tag, at
[Pubgrade](https://github.com/elixir-cloud-aai/Pubgrade) (`POST
/repositories/{id}/builds`, through Pubgrade's action
[`actions/notify`](https://github.com/elixir-cloud-aai/Pubgrade/tree/344a58adc1c871135f86c404eb33ed91011886ad/actions/notify)),
which notifies the deployments that subscribed to upgrades. It runs for
every release tag, alpha, beta and release candidate versions included, and
registers the build without a build type, so every subscription of the
repository that matches the tag (e.g., `*` for any tag) gets it, also for a
release candidate. Nothing waits for this job, so a
failed notification doesn't hold up the release. The action masks the token
and retries a request only if it never reached Pubgrade, so that one run
registers the build at most once. This needs Pubgrade's publish mode
([Pubgrade#33](https://github.com/elixir-cloud-aai/Pubgrade/issues/33)) and
these settings:

| Setting | Kind | Where | Meaning |
| --- | --- | --- | --- |
| `PUBGRADE_URL` | Variable | Repository | Base URL of the Pubgrade API, with `https://`. Switches the notification on. |
| `PUBGRADE_REPOSITORY_ID` | Variable | Repository, or the `release` environment | The identifier from registering the repository in Pubgrade |
| `PUBGRADE_TOKEN` | Secret | The `release` environment | The access token from registering the repository in Pubgrade |

Without `PUBGRADE_URL`, the job is skipped (as in forks), so releases don't
wait for its approval. Set `PUBGRADE_URL` for the repository, not in the
`release` environment: a job's condition is evaluated before the job enters
its environment, so a variable there doesn't switch the job on (and would
override the repository's URL within the job). An organization variable
would switch it on for every repository it is shared with, also those
without a Pubgrade token. With `PUBGRADE_URL`, the job waits for an approval
in the `release` environment, like pushing and publishing, and fails if one
of the other settings is missing or invalid: the identifier and the token
may only hold letters, digits, `.`, `~` and `-` (as Pubgrade issues them).
If only this job fails or is rejected, the release is published all the
same: fix the settings and re-run the job (re-running the failed jobs runs
only this one), or leave it; don't release a new version for it. Re-running
it notifies the subscribed deployments again, without a new release. Unless
it failed on an invalid setting or with "Could not reach Pubgrade (curl exit
status 6)" or "(… 7)" (no connection), Pubgrade may have registered the
build all the same: check the repository's builds (`GET
/repositories/{id}/builds`) before re-running it. If `publish` fails, the
job doesn't run; a re-run of the failed jobs that finishes `publish` runs it
too.

The chart's version is the release version from the first release on; the
hand-written chart before the move to the FOCA library chart had versions
up to 3.0.0, which no release packaged.

The CI workflow builds the image of every pull request and scans it with
[Trivy](https://trivy.dev/) (the shared action
[`scan-image`](https://github.com/elixir-cloud-aai/.github/tree/main/actions/scan-image)
of the organisation, pinned to the commit of a release), and a weekly
workflow (`scan.yml`) scans `latest`, from the first stable release on (a
published GitHub release `vX.Y.Z`; until then, `latest` is a legacy image of
2021 and the scan is skipped). For pushes to `dev` and for releases,
the workflows push the image by digest, untagged, scan exactly that digest
in a job without credentials or signing identity, and only if the scan
passes attest, sign and tag it, so that the published images are the
scanned ones. The scans fail on critical and high vulnerabilities that have
a fix, and upload the findings that have a fix (all severities) to code
scanning (Security tab; only in this repository, not for pull requests from
forks, nor in the release workflow); findings without a fix appear there
once a fix is released. The weekly scan also uploads a full report,
findings without a fix included, as the workflow artifact
`trivy-report-release-image` of each run (`trivy-report.json` and
`trivy-report.txt`, a table; Actions tab, workflow "Scan"); it is not
uploaded to code scanning. Accepted findings are left out of all results.
To accept a finding (e.g., if it doesn't affect the app), add it to
`.trivyignore.yaml` with the affected package versions (`purls`), the
reason (`statement`) and an expiry date (`expired_at`), after which the
scans fail again. Trivy also scans for secrets (critical and high ones fail
the scans too); accept those under `secrets:` in the same file. Dependabot
updates the actions, including the pins of the shared actions
(`@<commit> # vX.Y.Z`, all on the same release, see
`tests/test_workflows.py`), to new releases of `elixir-cloud-aai/.github`;
the Trivy version is the default of the shared action's `trivy-version`
input, which Dependabot doesn't bump here: change it in the shared action,
whose release then reaches this repository as a Dependabot update of the
pins. Signing needs no secrets beyond the Docker Hub ones: it uses the
workflows' OIDC tokens (permission `id-token: write`).

The release workflow derives the version, the chart version, the kind of
release (stable, GitHub pre-release), whether the image is tagged `latest`
and the previous release (for the generated notes) from the tag with
`scripts/release_version.py`, which is tested over a table of tags
(`tests/test_release_version.py`) and checked like the app (ruff, mypy,
coverage); change these rules there, not in the workflow. It finds the
GitHub release of the tag, if any, and checks the assets of a published one
with `scripts/release_assets.py` (`precheck` before signing, `state` before
creating the release; tested in `tests/test_release_assets.py`).

To test unreleased changes of FOCA, `pyproject.toml` may pin a FOCA commit
(`foca @ git+https://github.com/elixir-cloud-aai/foca@<sha>`), with FOCA's
development image of that commit as the base image (tagged by date, e.g.,
`elixircloud/foca:YYYYMMDD-py3.12`, pinned by digest, as the tag moves with
later commits of that day). Such pins are temporary: the release workflow
fails while a requirement (also an optional one, a dependency group or a
build requirement) is a direct reference or names a pre-release or a local
version (e.g., `+g<commit>`), a FOCA image has no release tag, or a
package comes from elsewhere than PyPI (`https://pypi.org/simple`, the only
package index allowed): a source of `[tool.uv.sources]` (`git`, `url`,
`path`, `workspace`, or an `index` other than PyPI), a package index other
than PyPI (`[[tool.uv.index]]`, `index-url`, `extra-index-url`,
`find-links`), or a package of `uv.lock` (from which the image is
installed; it must exist) whose source is not PyPI, the app itself excepted
(`scripts/check_release_pins.py`, tested in
`tests/test_check_release_pins.py`). So replace them by the released
versions before tagging (a FOCA commit is reported twice, in
`pyproject.toml` and in `uv.lock`). This applies to pre-releases of the
app, too: they are built on FOCA releases.

Release notes follow the format agreed for all repositories of ELIXIR
On-Cloud:

1. An intro paragraph saying what the release brings, with a link to the
   upgrade steps (e.g., on the [Upgrading](upgrading.md) page) if there are
   any.
2. Grouped sections, with empty ones left out, in this order:
   `## Breaking changes`, `## Features`, `## Security`, `## Fixes`,
   `## Documentation`, `## Maintenance`. They hold bullets only, and each
   bullet ends with its issue and pull request numbers, e.g., `(#12, #34)`
   (several pairs separated by semicolons, e.g., `(#12, #34; #56, #78)`).
3. `## Commits`: GitHub's generated notes, verbatim (including "New
   Contributors"), without their `## What's Changed` header, as they credit
   the authors.
4. Last, GitHub's generated `**Full Changelog**: ...` line (no compare link
   of our own).

The curated notes in `docs/releases/X.Y.Z.md` (for pre-releases, e.g.,
`X.Y.Zrc1.md`) hold parts 1 and 2, without a title (the release's title is
its tag); the release workflow adds parts 3 and 4 from GitHub's
[generate-notes](https://docs.github.com/en/rest/releases/releases#generate-release-notes-content-for-a-release)
API, for the changes since the previous published release in the history of
the release commit (for stable releases the previous stable release, or the
previous pre-release if there is no stable one, as the generated notes can't
start before the first tag; for alpha, beta and release candidate versions
the previous release of any kind). For the first release (no published
release before it), the API would start at an older tag of its choice, so
the workflow lists all merged pull requests in the history of the release
commit itself, in the API's format: `scripts/release_notes.py first` reads
the closed pull requests (`gh api --paginate --slurp
"repos/<owner>/<repo>/pulls?state=closed&per_page=100"`, for which the job
has `pull-requests: read`) and the commits (`git rev-list HEAD` at the
release commit); run these commands locally to preview the notes. Generated
notes in an unexpected format (without the `**Full Changelog**` line) are
kept as they are, with a warning, as the image is published by then.
Without curated notes, the release gets GitHub's generated notes alone.
Curated notes are published as written, so the release workflow fails if
they contain `TODO`, are not in this format or link to versions that move
(the latest docs, `/en/latest/`, or files on branch `dev`, `blob/dev/`; link
the release's, e.g., `/en/vX.Y.Z/`, `blob/vX.Y.Z/`, as the published notes
don't change) or have relative links (see below)
(`scripts/release_notes.py check`, tested in
`tests/test_release_notes.py`, which also checks the notes in
`docs/releases/`), and so does the CI job "Release readiness" on pushes (see
above); on re-runs, it replaces the notes of an existing release (also
overwriting manual edits).
Relative links, e.g., `../upgrading.md#service-info`, work in the docs built
from `docs/releases/`, but not in the release body: link the release's docs
with their full URL, e.g.,
`https://drs-filer.readthedocs.io/en/vX.Y.Z/upgrading/#service-info`,
or within the page with `#...`. The check reports every link target without
a scheme (such as `https:` or `mailto:`) of inline links, images, reference
definitions and the HTML attributes `href`, `src` and `srcset` (each of its
URLs), anywhere in the notes, code blocks included (and lines of paragraphs that
start like a definition, `[label]: ...`). Detailed upgrade steps belong on the
[Upgrading](upgrading.md) page, linked from the intro.

Maintainers: the workflows rely on these repository settings:

- environment `dev-images`, limited to branch `dev`;
- environment `release`, with a required reviewer, "Prevent self-review"
  and a deployment policy that allows only tags `v*`;
- the Docker Hub secrets (`DOCKERHUB_LOGIN`, `DOCKERHUB_TOKEN`) only in the
  two environments, not as repository secrets;
- for Pubgrade (optional, see above): the repository variable
  `PUBGRADE_URL` (not an environment variable, or the job never runs), the
  variable `PUBGRADE_REPOSITORY_ID` (repository or `release` environment)
  and the secret `PUBGRADE_TOKEN` in the `release` environment;
- a tag ruleset for `v*` that restricts who may create them and prevents
  moving or deleting them;
- immutable releases;
- `main` protected against non-fast-forward pushes;
- a ruleset for `dev` that requires the check `CI passed` (the gate of the
  CI workflow) only.

While `CITATION.cff` names a version that has no tag yet, findings of
"Release readiness" (e.g., a pin to an unreleased commit) also stop the
`dev` image from being published; fix them or push the tag.

The Docker Hub organization is the repository variable `DOCKERHUB_ORG` (by
default `elixircloud`; forks set it to the organization they publish to,
with the Docker Hub secrets in the environments `dev-images` and
`release`), so that the scan jobs, which have no secrets, know the image
name too, and the released chart's default image (`drsFiler.image`) is the
published one. Forks without `DOCKERHUB_ORG` publish nothing: their CI runs
the same checks (the scan of a local build included, without the upload to
code scanning) and passes without the secrets, and their weekly scan is
skipped.

On Read the Docs, the default version is `stable` (the highest release)
from the first release on, and the default branch is left empty, so that
`latest` follows the repository's default branch, `dev`; an automation
rule activates the versions of tags (`v*`), so that the docs linked from
packaged charts exist.

The release workflow and CI's jobs "Chart" and "Chart install" install a
fixed Helm version (`version:` of `azure/setup-helm` in `release.yml` and
`ci.yml`). Dependabot updates the action, but not this version: bump it by
hand, in all three places.
