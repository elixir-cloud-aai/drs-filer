##### TOOLS #####
## uv, to export the locked requirements (`uv.lock`) for the image build, and
## to install them; mounted into the steps that use it only, so that the
## image doesn't contain it. Pinned by digest
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

##### BASE IMAGE #####
## Pinned by digest, so that rebuilds use the same base image. The image of
## the locked FOCA release, whose tag names it (checked by
## `tests/test_image_build.py`), with Python 3.12. It has no pip, no build
## tools (compilers, headers, Git, curl, jq), and runs as a non-root user
## (UID 1000, group 0)
FROM elixircloud/foca:0.22.0-py3.12@sha256:32219208c5b4254f877f78d40cb7bc7969d055dafc2e8cb1cdaf3fe578cd6fb6 AS base

##### BUILD #####
## Build the app's wheel, in a stage of its own, so that the image doesn't
## contain the build requirements. They (`build-system.requires` of
## `pyproject.toml`) are locked in `uv.lock`, as the dependency group
## `build-system`, and installed from there, as the runtime dependencies are
## below: at the exact versions of the lock, checked against its hashes, as
## wheels only, into a virtual environment of their own (created by uv for
## the Python of the base image, without pip). The wheel is then built with
## them by uv, without an isolated build environment (which would be filled
## with downloads that aren't hash-checked), offline and without network, so
## that it downloads nothing
FROM base AS build
USER root
COPY pyproject.toml uv.lock /tmp/src/
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
  export UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never \
  && uv export --frozen --only-group build-system --no-emit-project \
    --project /tmp/src --output-file /tmp/build-requirements.txt \
  && uv venv --python /usr/local/bin/python /tmp/build-env \
  && uv pip install --python /tmp/build-env --require-hashes \
    --only-binary :all: --no-deps -r /tmp/build-requirements.txt
## (`README.md` is the package's long description; the license text is
## installed with the package metadata, e.g.,
## `site-packages/drs_filer-<version>.dist-info/licenses/LICENSE`)
## The build context has no Git metadata, so the version is passed as a build
## argument (e.g., `--build-arg SETUPTOOLS_SCM_PRETEND_VERSION=1.2.3`);
## without it, the app reports version `0.0.0.dev0`
COPY README.md LICENSE /tmp/src/
COPY drs_filer /tmp/src/drs_filer
ARG SETUPTOOLS_SCM_PRETEND_VERSION
RUN --network=none --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
  export UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never \
  && uv build --wheel --offline --no-build-isolation \
    --python /tmp/build-env/bin/python --out-dir /tmp/dist /tmp/src

##### IMAGE #####
FROM base

##### METADATA #####
## OCI annotations; images built from the FOCA image inherit its own, so all
## static ones are set here
LABEL org.opencontainers.image.title="DRS-Filer"
LABEL org.opencontainers.image.description="GA4GH Data Repository Service (DRS) implementation by ELIXIR On-Cloud"
LABEL org.opencontainers.image.url="https://github.com/elixir-cloud-aai/drs-filer"
LABEL org.opencontainers.image.source="https://github.com/elixir-cloud-aai/drs-filer"
LABEL org.opencontainers.image.documentation="https://github.com/elixir-cloud-aai/drs-filer#readme"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.authors="ELIXIR On-Cloud <cloud-service@elixir-europe.org>"
LABEL org.opencontainers.image.vendor="ELIXIR On-Cloud"

## Install dependencies first, so that code changes do not reinstall them;
## the FOCA image runs as non-root user. Only the locked ones are installed:
## the runtime dependencies (`project.dependencies` of `pyproject.toml`; the
## export leaves out the extras and the dependency group `build-system`),
## with all their own dependencies, at the exact versions of `uv.lock`,
## checked against its hashes, as wheels only, and without resolving
## anything else (`--no-deps`), and compiled, as the root file system of
## deployments may be read-only; as root (back to user 1000 below).
## `--frozen` takes the lock as is, unchecked against `pyproject.toml` (CI's
## `uv lock --check` checks it). A direct reference to a FOCA commit
## (temporary) has no hash and is left out, as the image has no Git: the
## build fails unless the base image has FOCA of that commit. It also fails
## unless the base image has the locked FOCA release, if one is locked
## (`scripts/image_requirements.py`). uv installs them into the Python of the
## base image (`--system`), and its lock file in `/tmp` is removed. Packages
## that the base image already has at the locked version are kept as they
## are (trusted through its digest), not checked against the hashes again
USER root
COPY pyproject.toml uv.lock scripts/image_requirements.py /tmp/src/
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
  export UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never \
  && uv export --frozen --no-dev --no-emit-project \
    --project /tmp/src --output-file /tmp/src/locked.txt \
  && python /tmp/src/image_requirements.py /tmp/src/locked.txt > /tmp/src/requirements.txt \
  && uv pip install --system --require-hashes --only-binary :all: --no-deps \
    --compile-bytecode -r /tmp/src/requirements.txt \
  && rm -f /tmp/uv-*.lock

## Install app from the wheel of the build stage (non-editable; the base
## config and the API specifications are installed with the package, and
## deployments override the config via `FOCA_CONFIG_OVERLAY`), without its
## dependencies, installed above, and without an index and without network,
## so that nothing is downloaded; then uv checks that the installed packages
## (with those of the base image) meet each other's requirements, as nothing
## was resolved. The installed files are owned by root, so the app's user
## can't change its own code, config or specifications
RUN --network=none --mount=from=build,source=/tmp/dist,target=/tmp/dist \
  --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
  export UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never \
  && uv pip install --system --offline --no-index --no-deps \
    --compile-bytecode /tmp/dist/*.whl \
  && uv pip check --system \
  && rm -rf /tmp/src /tmp/uv-*.lock

## Run as non-root user (group 0, as for arbitrary user IDs, e.g., on
## OpenShift)
USER 1000:0

## Probe the Swagger UI, which needs neither authentication nor the database;
## set `HEALTHCHECK_URL` if Gunicorn's `--bind` changes the port, or the config
## changes the API base path or the Swagger UI setting
ENV HEALTHCHECK_URL=http://localhost:8080/ga4gh/drs/v1/ui/
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(os.environ['HEALTHCHECK_URL'], timeout=4)"]

## Serve with Gunicorn (settings in `drs_filer/gunicorn_config.py`; override
## them via `GUNICORN_CMD_ARGS`, e.g., `--workers 2`); each worker creates the
## app (no preloading). `python -m drs_filer.app` runs Flask's development
## server instead
CMD ["gunicorn", "--config", "python:drs_filer.gunicorn_config", \
  "drs_filer.app:create_app()"]
