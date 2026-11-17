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
locked in [`uv.lock`][uv-lock] (hash-checked), on the FOCA 0.13 image
(Python 3.12), pinned by digest. It contains only the files listed in
[`.dockerignore`][dockerignore] (an allowlist); local secret files, such as
`.env` files, are never copied into it. The image has no compilers and no
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
`FOCA_CONFIG_OVERLAY` (several files separated by `:`); the app merges the
overlays into the config on startup, in order. Mappings are merged
recursively; all other values, including lists, replace those of the base
config. Relative paths of API specifications are relative to the package.
With overlays, the app writes the merged config to a temporary file (in
`TMPDIR`, or `/tmp`) and removes it once parsed, so that directory must be
writable (e.g., an `emptyDir` volume with a read-only root file system). A
missing overlay fails the start.

A deployment's overlay sets at least its public URL, from which the app
builds the `self_uri` and access URLs of objects, and its service info
(`GET /service-info`), as the base config has placeholders for both:

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
run the linters and the unit tests:

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
reloader. For Flask's debugger and reloader, set `server.debug: True`,
`server.environment: development` and `server.use_reloader: True` in a local
overlay only (`config.local.yaml` is ignored by Git); never commit or deploy
it.

The Compose smoke test runs against a running service (`docker compose up`
above); it needs only `pytest` and `requests`:

```bash
DRS_FILER_URL=http://localhost:8080/ga4gh/drs/v1 uv run --with requests pytest tests/test.py
```

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
repository's default branch:

- **Packaging:** `setup.py` and `requirements*.txt` are gone. Install with
  `pip install .` (or `uv sync --locked --extra dev` for development); the
  package's version comes from Git tags.
- **Image:** the app is installed as a package (`drs_filer` in
  `site-packages`); there is no `/app` directory, and no
  `update-config-map.sh`, curl, jq, yq or pip in the image any more. Don't
  mount a config at `/app/drs_filer/config.yaml`: mount an overlay instead
  and set `FOCA_CONFIG_OVERLAY` (see [Configuration](#configuration)). The
  development server runs with `python -m drs_filer.app`, from any directory.
- **Docker Compose:** the app's service is `drs-filer` (was `drs`), published
  on `127.0.0.1:8080` only, and MongoDB is 7.0 (was 3.6), not published on
  the host, with its data in the volume `mongodb-data` (was the directory
  `../data/drs/db`). MongoDB 7.0 can't read the data files of MongoDB 3.6.
  To keep the data, migrate it without the app running, so that no write is
  lost:
  1. With the old checkout: `docker compose stop drs`, then
     `docker compose exec mongodb mongodump --archive > drs.archive`, then
     `docker compose down`.
  2. With the new checkout: `docker compose up --detach --wait mongodb`
     (MongoDB only), then `docker compose exec -T mongodb mongorestore
     --archive < drs.archive`, and only then
     `docker compose up --build --detach --wait`.

  Restored objects keep the `self_uri` and access URLs they were registered
  with (e.g., of an earlier public URL); `drs://` self URIs come with #97.
- **Helm chart (3.0.0):** the Job that wrote the config into the ConfigMap
  (with a service account bound to the `admin` cluster role) is replaced by
  a ConfigMap with the chart's overlay; the value `apiServer` is gone, and
  the ConfigMap is named `<appName>-config` (was `app-config`); `helm
  upgrade` removes the old resources.

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

[badge-build-status]:<https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/lint.yml/badge.svg?branch=dev>
[badge-coverage]:<https://img.shields.io/coveralls/github/elixir-cloud-aai/drs-filer>
[badge-github-tag]:<https://img.shields.io/github/v/tag/elixir-cloud-aai/drs-filer?color=C39BD3>
[badge-license]:<https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]:<https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/lint.yml>
[badge-url-coverage]:<https://coveralls.io/github/elixir-cloud-aai/drs-filer>
[badge-url-github-tag]:<https://github.com/elixir-cloud-aai/drs-filer/releases>
[badge-url-license]:<http://www.apache.org/licenses/LICENSE-2.0>
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
[uv-lock]: uv.lock
[res-ga4gh-drs]: https://github.com/ga4gh/data-repository-service-schemas
