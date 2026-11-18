# DRS-filer

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]
[![Coverage][badge-coverage]][badge-url-coverage]

## Synopsis

Microservice implementing the [Global Alliance for Genomics and
Health][org-ga4gh] (GA4GH) [Data Repository Service][res-ga4gh-drs] (DRS)
API specification.


## Description


## Usage

Once [deployed](#installation), the API is served here:

```console
http://localhost:8080/ga4gh/drs/v1/
```

> Note that host (`localhost`) and port (`8080`) in the URL above may differ,
> depending on how the service was deployed. Indicated values are for
> Docker Compose-based installations using the default
> [configuration][drs-filer-compose-config].

The easiest way to explore available endpoints is via the
[Swagger UI][res-swagger-ui]:

```console
http://localhost:8080/ga4gh/drs/v1/ui
```

## Installation

To quickly install the service for development/testing purposes, we recommend
deployment via [Docker Compose][res-docker-compose], as described below. For
more durable deployments on cloud native infrastructure, we also provide a
[Helm][res-helm] chart and [basic deployment
instructions][drs-filer-deployment] (details may need to be adapted for your
specific infrastructure).

> DRS-Filer has no authentication: anybody who can reach it can register,
> change and delete objects. Docker Compose therefore publishes it on the
> host's loopback interface only.

### Requirements

The following software needs to be available on your system:

- [Git][res-git]
- [Docker][res-docker] with the [Compose plugin][res-docker-compose]
  (`docker compose`) 2.24 or later

### Deployment with Docker Compose

First, clone the repository and traverse into the service's root directory
with:

```bash
git clone https://github.com/elixir-cloud-aai/drs-filer.git
cd drs-filer
```

Then start up the service, and wait until it's ready, with:

```bash
docker compose up --build --detach --wait
```

_**That's it!**_

You should now be able to use/explore the API as described in the [usage
section](#usage). Docker Compose runs two services: `drs-filer`, published on
`127.0.0.1:8080`, and `mongodb` (MongoDB 7.0, reachable from the app only,
with its data in the volume `mongodb-data`). Both have health checks.

The image builds the app's wheel and installs it, with the dependencies
locked in [`uv.lock`][uv-lock] (hash-checked), on the image of FOCA 0.22
(`elixircloud/foca:0.22.0-py3.12`, Python 3.12), pinned by digest. It
contains only the files listed in [`.dockerignore`][dockerignore] (an
allowlist); local secret files, such as `.env` files, are never copied into
it. The image has no compilers and no
pip; the app's files are owned by root and can't be changed by the app's
user. Its version is set at build time (the build gets no Git metadata),
e.g., `SETUPTOOLS_SCM_PRETEND_VERSION=1.2.3 docker compose build`; it is
`0.0.0.dev0` otherwise.

The image (and thus Docker Compose and the Helm chart) serves the app with
[Gunicorn][res-gunicorn], as a non-root user (UID 1000, group 0; any UID with
group 0 works, e.g., on OpenShift). Its settings are in
[`drs_filer/gunicorn_config.py`][drs-filer-gunicorn-config]; override them
with the environment variable `GUNICORN_CMD_ARGS`, e.g.,
`GUNICORN_CMD_ARGS="--workers 2"`. Behind a reverse proxy that sets
`X-Forwarded-*` headers, set `FORWARDED_ALLOW_IPS` to the proxy's addresses.
The shipped config ([`drs_filer/config.yaml`][drs-filer-config]) disables
Flask's debug mode; never enable it in a deployment, as the debugger allows
code execution for anyone who can reach an error page.

### Configuration

The app's base config is [`drs_filer/config.yaml`][drs-filer-config], which
is installed with the package. To override some values, write them to a
config overlay file and list it in the environment variable
`FOCA_CONFIG_OVERLAY` (several files separated by `:`); FOCA merges the
overlays into the config on startup, in order. Mappings are merged
recursively; all other values, including lists and `null`, replace those of
the base config. Relative paths of API specifications are relative to the
package. A missing overlay fails the start, and so do keys that FOCA removed
(see [Upgrading][upgrading]). Config files can reference environment
variables (`${VAR}`, `${VAR:-default}`, `${VAR:?message}`); write a literal
`$` before `{` or `$` as `$$`.

Errors are answered with problem details (RFC 9457), as
`application/problem+json`: `title`, `status` and `detail`, and, for
invalid requests, the invalid fields in `errors` (the `Error` definition of
the API specification). Requests and responses are validated against the
API specification, including the formats of URLs (`uri`) and timestamps
(`date-time`, RFC 3339, e.g., `2026-01-01T00:00:00Z`).

A deployment's overlay sets at least its public URL, from which the app
builds the `self_uri` and access URLs of objects, and its service info
(`GET /service-info`), as the base config has placeholders for both. The
service info is served as configured, so its URLs and timestamps must have
the formats of the specification (`GET /service-info` fails with `500`
otherwise):

```yaml
endpoints:
  url_prefix: https
  external_host: drs.example.org
  external_port: 443
  service_info:
    id: org.example.drs
    name: DRS-Filer of Example
    type:
      group: org.ga4gh
      artifact: drs
      version: 1.1.0
    description: Data Repository Service of Example
    organization:
      name: Example
      url: https://example.org
    contactUrl: mailto:drs@example.org
    documentationUrl: https://github.com/elixir-cloud-aai/drs-filer
    createdAt: "2026-01-01T00:00:00Z"
    updatedAt: "2026-01-01T00:00:00Z"
    environment: prod
    version: 0.1.0
```

Objects registered without an identifier (`POST /objects`) and their access
methods get random identifiers of `id_length` characters (default 6), drawn
from `id_charset` (default: letters, digits and `.-_~`), in
`endpoints.objects` and `endpoints.access_methods`. `id_charset` lists the
characters themselves, which must be unreserved characters of URLs (letters,
digits and `.-_~`); other characters and expressions such as
`string.ascii_letters + string.digits` fail the start (see
[Upgrading][upgrading]):

```yaml
endpoints:
  objects:
    id_charset: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    id_length: 8
```

Docker Compose uses the overlay [`config.dev.yaml`][drs-filer-config-dev]
(public URL `http://localhost:8080`, for the `self_uri` of objects). To use
your own overlays instead, set `DRS_FILER_CONFIG_OVERLAY` on the host to
their paths in the container, and mount them in a
`docker-compose.override.yaml`, e.g.:

```yaml
services:
  drs-filer:
    environment:
      FOCA_CONFIG_OVERLAY: /etc/drs-filer/config.dev.yaml:/etc/drs-filer/config.local.yaml
    volumes:
      - ./config.local.yaml:/etc/drs-filer/config.local.yaml:ro
```

The Helm chart writes its overlay (public URL and MongoDB host) to a
ConfigMap, from the value `host_name`; it doesn't set the service info.

### Running locally for development

For development, install the app with its locked dependencies, including the
`dev` extra, with [uv][res-uv] (into `.venv`), install the Git hooks, and
run the linters and the tests:

```bash
uv sync --locked --extra dev
uv run pre-commit install
uv run pre-commit run --all-files
uv run pytest
```

The hooks (`.pre-commit-config.yaml`) run on every commit: ruff (linting and
formatting), mypy (complete type hints), semgrep and ast-grep with the
project's rules (`.semgrep/`, `.ast-grep/`) and their rule tests, gitleaks,
actionlint and basic file checks. CI runs the same hooks on all files.
Docstrings follow the Google style, at all levels, tests included.

To change dependencies, edit `pyproject.toml` and update the lock with
`uv lock`.

Dependabot ([`.github/dependabot.yml`][dependabot-config]) opens grouped
pull requests against `dev` once a month, labelled `type: dependencies`, for
the locked Python dependencies (`uv.lock`), the actions of the workflows, the
images of the `Dockerfile` and the hook revisions of
`.pre-commit-config.yaml`. FOCA is bumped by hand, never by Dependabot: the
image build fails unless the base image (`elixircloud/foca` in the
`Dockerfile`) has the locked FOCA release (`scripts/image_requirements.py`),
so change the `foca` requirement in `pyproject.toml`, the lock (`uv lock`)
and the base image's tag and digest together, in one pull request. Major
updates of connexion wait for a FOCA upgrade, too.

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
local overlay only (`config.local.yaml` is ignored by Git), with the
server on a loopback host (`server.host: 127.0.0.1`; FOCA warns otherwise);
never commit or deploy it.

### Tests

The tests come in three levels; `uv run pytest` runs the first two, which
must cover the code completely (`fail_under` in `pyproject.toml`, and the
same targets for Codecov in `codecov.yml`):

- **Unit tests** (`tests/ga4gh/`, `tests/test_*.py`): controllers and
  helpers with bare Flask apps, the config, the image and the chart.
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
  Compose stack (`docker compose up` above); skipped unless
  `DRS_FILER_URL` is set. It registers objects and service info:

  ```bash
  DRS_FILER_URL=http://localhost:8080/ga4gh/drs/v1 uv run pytest tests/smoke
  ```

Tests can't open connections (TCP, or connected UDP), except to the test
database (and the smoke test to the app). Shared fixtures are in `tests/conftest.py`,
request bodies in `tests/mock_data.py`.

### Continuous integration

One workflow, `.github/workflows/ci.yml` (`CI`), runs on pull requests and
pushes to `dev`; `tests/test_workflows.py` checks its names, triggers,
gate, publishing condition and action pins. Its jobs:

- **PR title** (`title`): Conventional Commits, at most 50 characters (the
  title becomes the commit message of the squash merge).
- **Lint** (`lint`): checks the lock file, runs all hooks of
  `.pre-commit-config.yaml`, scans the whole checkout for secrets and
  validates `CITATION.cff` (cffconvert).
- **Test** (`test`): `Test (mongomock)` with coverage, uploaded to Codecov
  (repository secret `CODECOV_TOKEN`; uploads fail the run only on pushes
  to this repository), and `Test (MongoDB 7.0)` against a real MongoDB.
- **Smoke test** (`smoke`): the Compose stack, built from the checkout, with
  the smoke test against its API.
- **Push image** (`push`): on pushes to `dev` only, once all other jobs
  passed, the image is pushed to Docker Hub, tagged `dev` and
  `sha-<commit>`. It runs in the environment `dev-images`, which holds the
  secrets `DOCKERHUB_LOGIN` and `DOCKERHUB_TOKEN` and allows branch `dev`
  only. The organization is the repository variable `DOCKERHUB_ORG`
  (default `elixircloud`); forks publish only if they set it (and the
  secrets).
- **CI passed** (`passed`): the gate, the only required check; it fails if
  any other job failed, or was skipped where it should have run.

### Other useful commands

To shut down the service, run:

```bash
docker compose down
```

If you need to inspect the logs, call:

```bash
docker compose logs
```

### Upgrading

Changes that need action when upgrading from earlier versions of the
repository's default branch are listed in
[`docs/upgrading.md`][upgrading], newest first: the upgrade to FOCA 0.22
changes error responses (problem details), validates the formats of URLs and
timestamps, and removes some config keys.

## Citation

If you use DRS-Filer, please cite it with the metadata in
[`CITATION.cff`][citation]: on GitHub, "Cite this repository" in the sidebar
of the repository formats it as APA or BibTeX. Its `version` and
`date-released` are set shortly before each release, with
`python scripts/citation.py set <version>`; `python scripts/citation.py check
<version>` checks them.

## Contributing

This project is a community effort and lives off your contributions, be it in
the form of bug reports, feature requests, discussions, or fixes and other code
changes. Please refer to our organization's [contributing
guidelines][res-elixir-cloud-contributing] if you are interested to contribute.
Please mind the [code of conduct][res-elixir-cloud-coc] for all interactions
with the community.

## Versioning

The project adopts the [semantic versioning][res-semver] scheme for versioning.
Currently the service is in beta stage, so the API may change without further
notice.

## License

This project is covered by the [Apache License 2.0][license-apache] also
[shipped with this repository][license].

## Contact

The project is a collaborative effort under the umbrella of [ELIXIR Cloud &
AAI][org-elixir-cloud]. Follow the link to get in touch with us via chat or
email. Please mention the name of this service for any inquiry, proposal,
question etc.

[badge-build-status]:<https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/ci.yml/badge.svg?branch=dev>
[badge-coverage]:<https://img.shields.io/codecov/c/github/elixir-cloud-aai/drs-filer/dev>
[badge-github-tag]:<https://img.shields.io/github/v/tag/elixir-cloud-aai/drs-filer?color=C39BD3>
[badge-license]:<https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]:<https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/ci.yml>
[badge-url-coverage]:<https://codecov.io/gh/elixir-cloud-aai/drs-filer>
[badge-url-github-tag]:<https://github.com/elixir-cloud-aai/drs-filer/releases>
[badge-url-license]:<http://www.apache.org/licenses/LICENSE-2.0>
[citation]: CITATION.cff
[dependabot-config]: .github/dependabot.yml
[dockerignore]: .dockerignore
[drs-filer-compose-config]: docker-compose.yaml
[drs-filer-config]: drs_filer/config.yaml
[drs-filer-config-dev]: config.dev.yaml
[drs-filer-deployment]: deployment/README.md
[drs-filer-gunicorn-config]: drs_filer/gunicorn_config.py
[license]: LICENSE
[license-apache]: <https://www.apache.org/licenses/LICENSE-2.0>
[org-elixir-cloud]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai>
[org-ga4gh]: <https://www.ga4gh.org/>
[res-elixir-cloud-coc]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CODE_OF_CONDUCT.md>
[res-elixir-cloud-contributing]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CONTRIBUTING.md>
[res-docker]: <https://docs.docker.com/engine/install/>
[res-docker-compose]: <https://docs.docker.com/compose/install/>
[res-git]: <https://git-scm.com/>
[res-gunicorn]: <https://gunicorn.org/>
[res-helm]: <https://helm.sh/>
[res-semver]: <https://semver.org/>
[res-swagger-ui]: <https://swagger.io/tools/swagger-ui/>
[res-uv]: <https://docs.astral.sh/uv/>
[upgrading]: docs/upgrading.md
[uv-lock]: uv.lock
[res-ga4gh-drs]: https://github.com/ga4gh/data-repository-service-schemas
