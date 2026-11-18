# Configuration

DRS-Filer is configured with a [FOCA](https://foca.readthedocs.io/)
configuration (FOCA 0.22; see [FOCA's configuration
reference](https://foca.readthedocs.io/en/latest/configuration/)):
[`drs_filer/config.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/config.yaml),
which is installed with the package and part of the image. The comments in
the file describe each section; the section `endpoints` holds the settings
of DRS-Filer itself.

## Overlays

To override some values, write them to a config overlay file and list it in
the environment variable `FOCA_CONFIG_OVERLAY` (several files separated by
`:`); FOCA merges the overlays into the config on startup, in order.
Mappings are merged recursively; all other values, including lists and
`null`, replace those of the base config. Relative paths of API
specifications are relative to the package, relative paths of overlays
relative to the working directory. A missing overlay fails the start, and so
do keys that FOCA removed (see [Upgrading](upgrading.md)).

Config files can reference environment variables: `${VAR}`,
`${VAR:-default}` and `${VAR:?message}`; the app refuses to start if a
referenced variable without default isn't set. Write a literal `$` before
`{` or `$` as `$$` (e.g., `$${VAR}`).

## Settings

The settings that deployments usually change:

| Setting | Default | Description |
| --- | --- | --- |
| `endpoints.url_prefix`, `endpoints.external_host`, `endpoints.external_port` | `http`, placeholder, `8080` | Public URL of the app, see [Public URL](#public-url) |
| `endpoints.api_path` | `ga4gh/drs/v1` | Path of the API in the public URL |
| `endpoints.service_info` | placeholders | Service info (`GET /service-info`), see [Service info](#service-info) |
| `endpoints.objects`, `endpoints.access_methods` | 6 characters, letters, digits and `.-_~` | Generated identifiers, see [Identifiers](#identifiers) |
| `db.host`, `db.port` | `mongodb`, `27017` | MongoDB |
| `server.debug` | `False` | Flask's debug mode, which allows executing arbitrary code: only for local development, see [Development](development.md#development-server) |
| `log` | console, level `INFO` | Logging (Python's `logging.config` dictionary) |

## Public URL

A deployment's overlay sets at least its public URL, from which the app
builds the `self_uri` and access URLs of objects, and its service info, as
the base config has placeholders for both:

```yaml
endpoints:
  url_prefix: https
  external_host: drs.example.org
  external_port: 443
```

## Service info

The service info (`GET /service-info`) is served from
`endpoints.service_info`. The config takes precedence: on each start, the
app serves the service info of its config, and replaces any service info
stored in the database with it, also service info with another `id`.
Service info posted with `POST /service-info` is served until the app
starts again: when a pod or container restarts, but also when Gunicorn
starts a worker (each worker creates the app, e.g., after a worker timed
out). To change the service info for good, set it in the deployment's
overlay, not with `POST /service-info`. It is served as it is, so its URLs
and timestamps must have the formats of the specification
(`GET /service-info` fails with `500 Internal Server Error` otherwise):

```yaml
endpoints:
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
    documentationUrl: https://drs-filer.readthedocs.io/
    createdAt: "2026-01-01T00:00:00Z"
    updatedAt: "2026-01-01T00:00:00Z"
    environment: prod
    version: 0.1.0
```

## Identifiers

Objects registered without an identifier (`POST /objects`) and their access
methods get random identifiers of `id_length` characters (default 6), drawn
from `id_charset` (default: letters, digits and `.-_~`), in
`endpoints.objects` and `endpoints.access_methods`. `id_charset` lists the
characters themselves, which must be unreserved characters of URLs (letters,
digits and `.-_~`); other characters and expressions such as
`string.ascii_letters + string.digits` fail the start (see
[Upgrading](upgrading.md#identifier-character-sets)):

```yaml
endpoints:
  objects:
    id_charset: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    id_length: 8
```

## Docker Compose

Docker Compose uses the overlay
[`config.dev.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/config.dev.yaml)
(public URL `http://localhost:8080`). To use your own overlays instead, set
`DRS_FILER_CONFIG_OVERLAY` on the host to their paths in the container, and
mount them in a `docker-compose.override.yaml`, e.g.:

```yaml
services:
  drs-filer:
    environment:
      FOCA_CONFIG_OVERLAY: /etc/drs-filer/config.dev.yaml:/etc/drs-filer/config.local.yaml
    volumes:
      - ./config.local.yaml:/etc/drs-filer/config.local.yaml:ro
```

## Helm chart

The Helm chart writes its overlay (public URL and MongoDB host) to a
ConfigMap, from the value `host_name`; it doesn't set the service info (see
[Deployment](deployment.md)).
