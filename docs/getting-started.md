# Getting started

To quickly run the service for development or testing, use [Docker
Compose](https://docs.docker.com/compose/install/), as described below. For
deployments on Kubernetes, a [Helm](https://helm.sh/) chart is in the
[`deployment/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/deployment)
directory (see [Deployment](deployment.md)). The [FOCA deployment
guide](https://foca.readthedocs.io/en/latest/deployment/) explains how FOCA
apps, such as this one, are configured with Docker Compose and Helm.

## Quick start

--8<-- "README.md:quick-start"

Docker Compose runs two services, both with health checks: `drs-filer`,
published on `127.0.0.1:8080`, and `mongodb` (MongoDB 7.0), reachable from
the app only, with its data in the Compose project's named volume
`mongodb-data` (e.g., `drs-filer_mongodb-data`, see `docker volume ls`). To
publish DRS-Filer elsewhere, override `ports` in a
`docker-compose.override.yaml`. The comments in
[`docker-compose.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/docker-compose.yaml)
describe the settings.

The app uses the configuration overlay
[`config.dev.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/config.dev.yaml),
which sets its public URL to `http://localhost:8080` (for the `self_uri` of
objects); see [Configuration](configuration.md#docker-compose) to use your
own overlays.

The image reports version `0.0.0.dev0` unless you set
`SETUPTOOLS_SCM_PRETEND_VERSION` on the host (e.g.,
`SETUPTOOLS_SCM_PRETEND_VERSION=1.2.3 docker compose build`).

Docker Compose is for local development and testing; for deployments, see
[Deployment](deployment.md).

### Other useful commands

To shut down the service, run:

```bash
docker compose down
```

Add `--volumes` to also delete the database.

To inspect the logs, run:

```bash
docker compose logs
```

## Usage

Register an object (see [Registering objects](api.md#registering-objects)),
which returns its identifier, then get it by that identifier. Registering
needs an access token of an admin (see [Access control](access-control.md));
without an identity provider, start the app without authentication first
(see [Running without
authentication](development.md#running-without-authentication)), and leave
out the `Authorization` header:

```bash
curl -X POST "http://localhost:8080/ga4gh/drs/v1/objects/register" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample.bam",
    "size": 1024,
    "created_time": "2026-01-01T00:00:00Z",
    "checksums": [{"type": "sha-256", "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}],
    "access_methods": [{"type": "https", "access_url": {"url": "https://example.org/data/sample.bam"}}]
  }'
curl -X GET "http://localhost:8080/ga4gh/drs/v1/objects/<object_id>"
```

All [endpoints](api.md) can also be tried in the Swagger UI. See
[Configuration](configuration.md) to change the configuration, e.g., the
[service info](configuration.md#service-info) that describes your
deployment: the defaults are placeholders.
