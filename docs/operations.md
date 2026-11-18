# Operations

## Components

A deployment of DRS-Filer consists of:

- **the app**, served by Gunicorn (see [Server](#server)), which serves the
  [API](api.md);
- **MongoDB** (Docker Compose runs 7.0), which stores the objects (collection
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

Images are published to Docker Hub as `elixircloud/drs-filer`: CI tags the
image of every commit to `dev` as `dev` and `sha-<commit>` (see [Continuous
integration](development.md#continuous-integration)), and the release
workflow the image of each release as `X.Y.Z` (and `latest`, for the highest
stable release; see [Versioning and
releases](development.md#versioning-and-releases)). All of them are scanned
for vulnerabilities before they are tagged, and signed (see [Verifying
images and charts](#verifying-images-and-charts)).

## Secrets

Secrets (e.g., passwords, tokens, private keys) are never part of the image:
pass them only at runtime, as environment variables or mounted secrets (e.g.,
Kubernetes Secrets), never as build arguments, which are recorded in the
image history. The image build receives only the files it needs (an
allowlist in
[`.dockerignore`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/.dockerignore));
as a safety net, common secret files (e.g., `.env` files, keys and
certificates) are left out even within the included paths.

## Verifying images and charts

From the first release on, images on Docker Hub (`elixircloud/drs-filer`)
are built by this repository's workflows on GitHub Actions, with an SBOM and
the build provenance attached as attestations, a [GitHub artifact
attestation](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
of their provenance, and a keyless [Sigstore](https://www.sigstore.dev/)
signature. To check that an image was built by the release workflow, run
(with the [GitHub CLI](https://cli.github.com/) or
[cosign](https://docs.sigstore.dev/cosign/system_config/installation/) 3 or
later, which reads the signatures in the Sigstore bundle format):

```bash
gh attestation verify oci://docker.io/elixircloud/drs-filer:{{ version }} \
    --repo elixir-cloud-aai/drs-filer \
    --signer-workflow elixir-cloud-aai/drs-filer/.github/workflows/release.yml \
    --source-ref refs/tags/v{{ version }}
cosign verify docker.io/elixircloud/drs-filer:{{ version }} \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity https://github.com/elixir-cloud-aai/drs-filer/.github/workflows/release.yml@refs/tags/v{{ version }}
```

These are the commands for the latest release, `{{ version }}`: replace it
with the version to verify (before the first release, the docs show
`X.Y.Z`). `--source-ref` and the ref in `--certificate-identity` check that
the workflow ran for the release tag, not for another branch. Images of
commits on `dev` (`dev`, `sha-<commit>`) are signed and attested by the CI
workflow instead: use `--signer-workflow
elixir-cloud-aai/drs-filer/.github/workflows/ci.yml`,
`--source-ref refs/heads/dev` and `--certificate-identity
https://github.com/elixir-cloud-aai/drs-filer/.github/workflows/ci.yml@refs/heads/dev`.
Images published before the workflows signed them (all images of earlier
versions, and `dev` and `sha-<commit>` images built before signing was
added, see [#85](https://github.com/elixir-cloud-aai/drs-filer/issues/85))
have no signature or attestation. To show an image's SBOM or provenance,
run:

```bash
docker buildx imagetools inspect docker.io/elixircloud/drs-filer:{{ version }} \
    --format '{{ json .SBOM }}'
docker buildx imagetools inspect docker.io/elixircloud/drs-filer:{{ version }} \
    --format '{{ json .Provenance }}'
```

The Helm chart attached to a release (`drs-filer-{{ chart_version }}.tgz`)
has a GitHub artifact attestation of its provenance and a Sigstore bundle
with its signature (`drs-filer-{{ chart_version }}.tgz.sigstore.json`,
attached too):

```bash
gh release download v{{ version }} --repo elixir-cloud-aai/drs-filer \
    --pattern 'drs-filer-{{ chart_version }}.tgz*'
gh attestation verify drs-filer-{{ chart_version }}.tgz \
    --repo elixir-cloud-aai/drs-filer \
    --signer-workflow elixir-cloud-aai/drs-filer/.github/workflows/release.yml \
    --source-ref refs/tags/v{{ version }}
cosign verify-blob drs-filer-{{ chart_version }}.tgz \
    --bundle drs-filer-{{ chart_version }}.tgz.sigstore.json \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity https://github.com/elixir-cloud-aai/drs-filer/.github/workflows/release.yml@refs/tags/v{{ version }}
```

Images are scanned for known vulnerabilities with [Trivy](https://trivy.dev/)
in CI and again before a release is published (both fail on fixable
critical and high vulnerabilities), and the `latest` image weekly. The
repository's code scanning alerts show the findings that have a fix, which
the maintainers can act on; findings without a fix (often OS packages of
the base image) appear there once a fix is released. The weekly scan also
keeps a full report, those findings included, as a workflow artifact of
each run. The published images (releases and `dev`) are the scanned ones:
the workflows push each image by digest, untagged, scan exactly that
digest, and only if the scan passes (no fixable critical or high
vulnerabilities, except accepted ones) sign and tag it (see [Versioning and
releases](development.md#versioning-and-releases)).

Images published to another Docker Hub organization (forks that set
`DOCKERHUB_ORG`) are verified the same way, with that organization and the
fork's repository in place of `elixircloud` and `elixir-cloud-aai/drs-filer`.
