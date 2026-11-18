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
to edit in the code.

## Development server

For development only, the app can be run with Flask's development server,
from any directory, with a MongoDB instance reachable at the host and port
set in `db` of the config, e.g., MongoDB published on the host (`ports:
["127.0.0.1:27017:27017"]` for `mongodb` in a `docker-compose.override.yaml`,
then `docker compose up --detach mongodb`) and an overlay with
`db.host: localhost` and the `endpoints` of `config.dev.yaml`:

```bash
FOCA_CONFIG_OVERLAY=config.local.yaml uv run python -m drs_filer.app
```

The shipped config runs the development server without debug mode and
reloader. For Flask's debugger and reloader, set `server.debug: True` in a
local overlay only (`config.local.yaml` is ignored by Git), with the server
on a loopback host (`server.host: 127.0.0.1`; FOCA warns otherwise); never
commit or deploy it.

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
  request validation and error handling are covered too. They use an
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
  `DRS_FILER_URL` is set. It registers objects and service info:

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
| `push` | Push image | Pushes to `dev` in this repository only |
| `passed` | CI passed | Passes if all other jobs passed or were skipped as intended |

`CI passed` is the only required check. Add every new job to its `needs`.

The coverage of `Test (mongomock)` is uploaded to Codecov (repository
secret `CODECOV_TOKEN`; uploads fail the run only on pushes to this
repository). `Push image` runs on pushes to `dev` only, once all other jobs
passed, and pushes the image to Docker Hub, tagged `dev` and
`sha-<commit>`. It runs in the environment `dev-images`, which holds the
secrets `DOCKERHUB_LOGIN` and `DOCKERHUB_TOKEN` and allows branch `dev`
only. The organization is the repository variable `DOCKERHUB_ORG` (default
`elixircloud`); forks publish only if they set it (and the secrets).

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
