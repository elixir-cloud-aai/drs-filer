# Operations

## Components

A deployment of DRS-Filer consists of:

- **the app**, served by Gunicorn (see [Server](#server)), which serves the
  [API](api.md);
- **MongoDB** (Docker Compose and the Helm chart run 7.0, the chart with
  authentication), which stores the objects (collection
  `objects`) and the service info (collection `service_info`) in the database
  `drsStore`.

The app holds no state of its own besides the database: back up the
database to back up a deployment, e.g., with `mongodump`.

## Server

The image serves the app with [Gunicorn](https://gunicorn.org/), as a
non-root user (UID 1000, group 0; any UID with group 0 works, e.g., on
OpenShift). Its settings are in
[`drs_filer/gunicorn_config.py`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/gunicorn_config.py):
port 8080, one worker with four threads, a timeout of 30 seconds and a
graceful timeout of 20 seconds (less than the termination grace period of
Kubernetes pods), and no access log. Override them with the environment
variable `GUNICORN_CMD_ARGS`, e.g., `GUNICORN_CMD_ARGS="--workers 2"` (not
`--bind`, which would break the published port and the health check). Each
worker creates the app after forking (no preloading), as MongoDB clients
must not be shared across forks.

Behind a reverse proxy that sets `X-Forwarded-*` headers, set
`FORWARDED_ALLOW_IPS` to the proxy's addresses; Gunicorn trusts them from
`127.0.0.1` only otherwise. The `host` and `port` of the section `server` of
the configuration apply to Flask's development server only.

The shipped config disables Flask's debug mode; never enable it in a
deployment, as the debugger allows code execution for anyone who can reach
an error page.

## Logs

The app logs to standard error, in the format of the section `log` of the
configuration (`[<time>: <level>] <message> [<logger>]`), and Gunicorn its
errors; there is no access log unless Gunicorn is started with
`--access-logfile -`. With Docker Compose, `docker compose logs` shows them.

## Image

The
[`Dockerfile`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/Dockerfile)
builds the image on FOCA's image (`elixircloud/foca:0.22.0-py3.12`, with the
FOCA release that `uv.lock` locks, Python 3.12), pinned by digest:

- **Locked installs**: the runtime dependencies and the build requirements
  (dependency group `build-system` of `pyproject.toml`) are installed at the
  versions of `uv.lock`, checked against their hashes, as wheels only; the
  app is built as a wheel in a separate stage, offline, and installed without
  its build tools. The image has no compilers and no pip.
- **User**: the image runs as the non-root user `1000` (group `0`); the
  app's files are owned by root and can't be changed by the app's user.
- **Command**: `gunicorn --config python:drs_filer.gunicorn_config
  'drs_filer.app:create_app()'`; `python -m drs_filer.app` runs Flask's
  development server instead (for development only).
- **Health check**: probes the Swagger UI
  (`http://localhost:8080/ga4gh/drs/v1/ui/`), which needs neither
  authentication nor the database; set `HEALTHCHECK_URL` if the port, the
  base path or the Swagger UI setting change.
- **Version**: the build argument `SETUPTOOLS_SCM_PRETEND_VERSION` sets the
  version of the package (the build gets no Git metadata), e.g.,
  `SETUPTOOLS_SCM_PRETEND_VERSION=1.2.3 docker compose build`; without it,
  `0.0.0.dev0`.
- **Labels**: OCI annotations (`org.opencontainers.image.*`).

CI pushes the image of every commit to `dev` to Docker Hub as
`elixircloud/drs-filer`, tagged `dev` and `sha-<commit>` (see [Continuous
integration](development.md#continuous-integration)); there are no release
images yet ([#85](https://github.com/elixir-cloud-aai/drs-filer/issues/85)).

## Secrets

Secrets (e.g., passwords, tokens, private keys) are never part of the image:
pass them only at runtime, as environment variables or mounted secrets (e.g.,
Kubernetes Secrets), never as build arguments, which are recorded in the
image history. The image build receives only the files it needs (an
allowlist in
[`.dockerignore`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.dockerignore));
as a safety net, common secret files (e.g., `.env` files, keys and
certificates) are left out even within the included paths.
