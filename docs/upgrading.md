# Upgrading

Changes that need action when upgrading from earlier versions of the
repository's default branch, newest first.

## DRS 1.5.0

!!! warning "Breaking changes"
    Registration moved to another path, and the API is OpenAPI 3 at
    another URL.

DRS-Filer serves the GA4GH DRS specification 1.5.0 (OpenAPI 3) instead of
1.1.0 (Swagger 2.0) (#89; see [API](api.md)):

- **Registration moved** from `POST /objects` to `POST /objects/register`,
  with the same request body and response. `POST /objects` is now the bulk
  read of DRS (`GetBulkObjects`), which DRS-Filer doesn't implement: it
  answers `501 Not Implemented`, and doesn't register anything. Update
  clients and scripts that register objects, e.g.:

    ```bash
    curl -X POST "https://drs.example.org/ga4gh/drs/v1/objects/register" \
      -H "Content-Type: application/json" -d @object.json
    ```

    `PUT /objects/{object_id}`, `DELETE /objects/{object_id}`, `DELETE
    /objects/{object_id}/access/{access_id}`, `GET /objects` and `POST
    /service-info` are unchanged.
- **Specification URL:** the specification is served at
  `/ga4gh/drs/v1/openapi.json` (was `/ga4gh/drs/v1/swagger.json`, now
  `404`), as OpenAPI 3. The Swagger UI stays at `/ga4gh/drs/v1/ui/`.
- **New endpoints of DRS** answer `501`: the passport `POST` variants of the
  reads (`POST /objects/{object_id}`, `POST
  /objects/{object_id}/access/{access_id}`, `POST /objects`, `POST
  /objects/access`), which DRS-Filer won't implement (see [Passport POST
  endpoints](api.md#passport-post-endpoints)), and `OPTIONS
  /objects/{object_id}` and `OPTIONS /objects`, for now. Before, they
  answered `405`.
- **Service info:** the base config reports `type.version` `1.5.0` (was
  `1.1.0`); remove `service_info.service.type` from your overlays, if set,
  so that the version follows the app. `GET /service-info` also serves the
  fields that DRS 1.5 requires (`maxBulkRequestLength` and `drs`, see
  [Service info](api.md#service-info)). `POST /service-info` refuses these
  fields and types other than `drs` (`400`).
- **Access methods** can be registered with the DRS 1.5 fields `cloud` and
  `available`; `authorizations` is refused (`400`), as DRS-Filer sets it.
- **Errors** are problem details, as before; the served specification now
  describes them as `Problem` (was `Error`).

Stored objects and service info need no migration.

## Typed configuration

The settings of DRS-Filer itself moved from the untyped section `endpoints`
to the section `custom`, which the app validates on startup (#93,
`drs_filer/custom_config.py`), and the service info to FOCA's section
`service_info`, which FOCA validates against the service info
specification. Invalid values and unknown keys of `custom` (e.g., misspelled
ones) fail the start, with an error that names the setting, but not the
value; before, they failed requests, or were ignored. Invalid service info
fails the start too, with the value in the error; other fields are served as
extra fields (check the spelling of yours). A config with
the section `endpoints` fails the start, too, and so does a Helm value
`config.endpoints` (rendering fails), naming the new keys. Move the
settings of your overlays (and of the Helm value `config`):

| Before | Now |
| --- | --- |
| `endpoints.url_prefix`, `endpoints.external_host`, `endpoints.external_port`, `endpoints.api_path` | `custom.service.url_prefix`, `custom.service.external_host`, `custom.service.external_port`, `custom.service.api_path` |
| `endpoints.objects.id_charset`, `endpoints.objects.id_length` | `custom.objects.id.charset`, `custom.objects.id.length` |
| `endpoints.access_methods.id_charset`, `endpoints.access_methods.id_length` | `custom.access_methods.id.charset`, `custom.access_methods.id.length` |
| `endpoints.service_info` | `service_info.service` |

For example:

```yaml
custom:
  service:
    url_prefix: https
    external_host: drs.example.org
    external_port: 443
  objects:
    id:
      charset: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
      length: 8
service_info:
  service:
    id: org.example.drs
    name: DRS-Filer of Example
```

- The default public host is `localhost` (was the IP address
  `193.166.24.114`), as in the Compose overlay; deployments set their own,
  as before (the Helm chart sets it from `hostName`).
- `url_prefix` must be `http` or `https`, `external_host` a host name or IP
  address (IPv6 addresses in brackets) without scheme, port or path (e.g.,
  not `https://drs.example.org`, which gave broken `self_uri`s),
  `external_port` an integer from 1 to 65535, and `api_path` segments of
  letters, digits and `-._~` separated by `/` (not `.` or `..`), without
  leading or trailing `/`. Lengths and ports are integers or strings of
  digits (e.g., from `${VAR}`), not booleans or floats. The Helm chart
  refuses a `hostName` that isn't a host name (e.g., with a scheme or
  port).
- The service info reports the version of the installed app (of the image)
  as `version`, unless `service_info.service.version` is set (the base
  config had the placeholder `0.0.0`). The base config no longer sets
  `createdAt` and `updatedAt` (placeholders of 2020); they are served only
  if set. Service info that doesn't conform to the specification (e.g., a
  `documentationUrl` that isn't a URL) fails the start, instead of
  `GET /service-info`. FOCA warns on startup of placeholder values in
  reserved example domains (e.g., `example.org`), as those of the base
  config.
- Code that read the config with `drs_filer.utils.get_endpoints_config()`
  or `get_id_settings()` uses `drs_filer.utils.get_custom_config()`.
- Upgrade the image and the config together, and don't register objects
  while the upgrade rolls out: an app of an earlier version that starts (or
  starts a Gunicorn worker) with the new config ignores `custom` and
  `service_info`, so it builds the `self_uri` of objects it registers from
  its default host and serves its placeholder service info until an app of
  the new version starts. With the Helm chart, both change in one
  `helm upgrade`; pods of the earlier version still read the updated
  ConfigMap until they are replaced. Objects registered meanwhile with
  another host in `self_uri` can be registered again (`PUT
  /objects/{object_id}`, see [Access methods without
  identifiers](#access-methods-without-identifiers)).

## Helm chart on foca-common

The Helm chart is rebuilt on FOCA's library chart `foca-common` (#86), as
the charts of the other FOCA apps: camelCase values (`hostName`,
`drsFiler.*`), resource names derived from the release name (e.g.,
`drs-filer-mongodb` for MongoDB), MongoDB 7.0 with authentication (a Secret
named by `mongodb.auth.existingSecret`), a claim kept on uninstall, an
Ingress, Gateway API HTTPRoute or OpenShift Route, and NetworkPolicies. The
library chart is downloaded with `helm dependency build deployment` before
installing from the repository. From the first release on, the chart's
version is the release version (see [Versioning and
releases](development.md#versioning-and-releases)), which may be lower than
the version of the earlier charts (up to 3.0.0).

- Rendering fails for the values of the earlier charts (`host_name`,
  `drs_filer.*`, `apiServer`, `clusterType`, `mongodb.volumeSize`), with the
  value that replaces each.
- Releases of the earlier charts can't be upgraded (their names and
  selectors differ; `helm upgrade` fails): dump the database, uninstall the
  release, which **deletes the earlier claim `mongodb` with the data**,
  install the current chart and restore the dump, as described in [From
  earlier charts](deployment.md#from-earlier-charts).
- Set `mongodb.image` to an image pinned to a minor version (default
  `docker.io/library/mongo:7.0`), not `mongo:noble`.

## Access methods without identifiers

Before #121, an access identifier that duplicated one of an earlier access
method of the same object left the method without `access_id`. Every
access method gets a unique identifier now; methods stored without one stay
as they are. They can't be addressed by
`GET /objects/{object_id}/access/{access_id}`, but no longer break it for
the other access methods of the object (#123), which failed with
`500 Internal Server Error`. Objects without access methods (e.g.,
bundles) and access methods registered without `access_url` have no access
URL: requests for them get `404 Not Found` (was `500`). Likewise, objects
without access methods have none to delete:
`DELETE /objects/{object_id}/access/{access_id}` gets `404 Not Found` for
them (was `500`, #127).

- List the affected objects in the app's container, e.g., in the Compose
  stack (with the Helm chart: `kubectl exec deploy/drs-filer -- python -c
  ...`):

  ```bash
  docker compose exec drs-filer python -c '
  from drs_filer.app import create_app
  from drs_filer.utils import get_collection

  with create_app().app.app_context():
      query = {"access_methods": {"$elemMatch": {"access_id": {"$exists": False}}}}
      for obj in get_collection("objects").find(query, {"_id": 0, "id": 1}):
          print(obj["id"])
  ' 2>/dev/null
  ```

  It prints the identifier of each such object. Like any start of the app,
  it serves the service info of the config again (see
  [Service info](#service-info)).
- To make their access methods addressable, register them again
  (`PUT /objects/{object_id}`, with the object as `GET /objects/{object_id}`
  returns it, without `id`, `self_uri` and the `access_id` of each access
  method, which registrations don't accept): this generates new
  identifiers for all access methods of the object, so clients that stored
  the earlier ones look them up again. `PUT` replaces the whole object:
  changes to it between the `GET` and the `PUT` are lost, so don't change
  the affected objects in the meantime (e.g., pause the clients that
  register objects).

## Service info

On each start, the app serves the service info of its config (#119), also
if service info with another `id` was posted (`POST /service-info`) or
stored by an earlier version: those stayed the ones served, which could make
`GET /service-info` answer `500 Internal Server Error` with a valid config.
The service info is now stored as a single record, and the records of
earlier versions are removed on the first start. Posted service info is
served until the app starts again (also when Gunicorn starts a worker); to
keep it, put it in the config (`service_info.service`, see
[Configuration](configuration.md#service-info) and [Typed
configuration](#typed-configuration)).

## Identifier character sets

The character sets of generated identifiers (`endpoints.objects.id_charset`
and `endpoints.access_methods.id_charset`, now `custom.objects.id.charset`
and `custom.access_methods.id.charset`, see [Typed
configuration](#typed-configuration)) list the characters themselves
and are never evaluated (#54): Python expressions, which earlier versions
evaluated with `eval()`, could run any code. Only unreserved characters of
URLs are allowed (letters, digits and `.-_~`), as identifiers are part of
URLs. Identifiers are generated with FOCA's `generate_id()`, from a
cryptographically secure source.

- Expressions (e.g., `string.ascii_letters + string.digits` or
  `'0123456789abcdef'`, with quotes) and other characters (e.g., spaces or
  `/`) fail the start, with an error that names the setting (e.g.,
  `objects.id.charset`). Replace expressions with the characters, e.g., the
  former default `'string.ascii_letters + string.digits + ".-_~"'` with:

  ```yaml
  custom:
    objects:
      id:
        charset: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_~"
    access_methods:
      id:
        charset: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_~"
  ```

  This is the default of the base config now, with the same characters as
  before: overlays that don't set the character sets need no change.
- Character sets of unreserved characters (e.g., `"abc123"`) keep working
  for object identifiers. They now work for access identifiers, too, and
  so do those that happened to be valid Python (e.g., digits only); both
  failed requests with `500 Internal Server Error`.
- An empty or non-string character set (`id_charset`, now `charset`; e.g.,
  a YAML list, which worked for object identifiers), or a length
  (`id_length`, now `length`) that isn't a positive integer, also
  fails the start (before, `0` and negative lengths gave empty identifiers,
  and `true` identifiers of one character).
- Identifiers registered before the upgrade stay as they are.

## FOCA 0.22

DRS-Filer is upgraded from FOCA 0.13 to FOCA 0.22 (#87), on the FOCA image
`elixircloud/foca:0.22.0-py3.12` (Python 3.12, as before). DRS-Filer is no
gateway app, so FOCA's plugin engine doesn't apply to it; it stays on
Connexion 2, as FOCA does.

### Errors

Errors are problem details (RFC 9457), sent as `application/problem+json`
(was `application/json`): `title`, `status` and `detail`, e.g.:

```json
{"title": "Not found", "detail": "The requested `DrsObject` wasn't found.", "status": 404}
```

They replace `msg` and `status_code` (`{"msg": "...", "status_code": 404}`):
clients that read `msg` read `detail` instead, and `status` instead of
`status_code`. Requests that fail the validation of their body or parameters
against the API specification (`400 Bad Request`) also have `type`
(FOCA's problem type, a URL ending in `/problems/invalid-request/`), `code`
(`invalid-request`) and `errors`, which lists the invalid fields, each with
`detail`, `code` and `pointer` (a JSON Pointer into the request body, e.g.,
`#/created_time`) or `parameter` (the name of an invalid parameter). The
`Error` definition of the API specification
(`drs_filer/api/20200622.383121d.data_repository_service.swagger.yaml`)
describes them, with `FieldError` for the entries of `errors`; only `title`
and `status` are always set (e.g., a body that isn't JSON gets neither
`code` nor `errors`).

### Formats of URLs and timestamps

Requests and responses are validated against the formats of the API
specification, which FOCA 0.13 didn't check: URLs (`uri`, e.g., of the
service info) and timestamps (`date-time`, RFC 3339, e.g.,
`2026-01-01T00:00:00Z`; `created_time` and `updated_time` of objects, and
`createdAt` and `updatedAt` of the service info).

- Requests with other values are rejected with `400 Bad Request` (e.g., an
  object with `created_time: 2024-06-12`, or service info with
  `documentationUrl: docs/abc`).
- The service info of the config is served as it is, so it must conform
  too: check the service info of your overlay (now
  `service_info.service`, which is validated on startup, see [Typed
  configuration](#typed-configuration)). The
  placeholders of the base config (`drs_filer/config.yaml`) conform now; a
  deployment still replaces them (see
  [Configuration](configuration.md)).
- Objects stored before the upgrade with other values fail the validation
  of responses, too (`500 Internal Server Error`); one
  such object also fails `GET /objects`, which lists all objects. Once the
  upgrade has rolled out (no old instance left that could still store such
  values), list the objects whose timestamps FOCA refuses, with FOCA's own
  check (which also refuses dates and times that don't exist, e.g.,
  `2024-02-30T00:00:00Z`), in the app's container, e.g., in the Compose
  stack (with the Helm chart: `kubectl exec deploy/drs-filer -- python -c
  ...`):

  ```bash
  docker compose exec drs-filer python -c '
  from foca.utils.service_info import is_date_time
  from drs_filer.app import create_app
  from drs_filer.utils import get_collection

  with create_app().app.app_context():
      for obj in get_collection("objects").find({}, {"_id": 0, "id": 1, "created_time": 1, "updated_time": 1}):
          invalid = {key: value for key, value in obj.items() if key != "id" and not is_date_time(value)}
          if invalid:
              print(obj["id"], invalid)
  ' 2>/dev/null
  ```

  It prints the identifier and the invalid timestamps of each such object
  (e.g., `abc123 {'created_time': '2024-06-12'}`); register them again with
  valid timestamps (`PUT /objects/{object_id}`). Stored service info
  doesn't matter: the app serves that of its config after each start (see
  [Service info](#service-info)).

### Configuration

FOCA refuses to start with keys that it removed; drop them from your
overlays:

- `server.environment` and `server.use_reloader`, without replacement:
  `server.debug: True` enables Flask's debugger and reloader (for local
  development only, on a loopback host).
- `exceptions.exceptions`, `exceptions.required_members` and
  `exceptions.status_member`: the base config maps the app's exceptions to
  problem details in `exceptions.mapping`
  (`drs_filer.errors.exceptions.exceptions`); problem details have fixed
  members.

Also changed:

- `api.specs[].add_operation_fields` is no longer set: each operation of
  the API specifications names its controllers
  (`x-swagger-router-controller: drs_filer.ga4gh.drs.server`), as FOCA no
  longer changes fields that operations set. Overlays that replace
  `api.specs` with their own specifications must name the controllers in
  each operation, too.
- Config overlays (`FOCA_CONFIG_OVERLAY`) are merged by FOCA, with the same
  merge rules as before (mappings merged recursively; lists and `null`
  replace values; relative paths of overlays relative to the working
  directory). The app no longer writes the merged config to a temporary
  file, so `TMPDIR` needn't be writable for it.
- FOCA replaces references to environment variables in the config and the
  overlays: `${VAR}`, `${VAR:-default}` and `${VAR:?message}`; the app
  refuses to start if a referenced variable without default isn't set.
  Write a literal `$` before `{` or `$` as `$$` (e.g., `$${VAR}`, `$$5`).

### Image

The image is built on FOCA's image of the release, which runs as a non-root
user (UID 1000, group 0, as before) and has no pip, compilers, Git, curl or
jq. The app runs as UID 1000 with group 0, as before; nothing changes for
deployments.

## Before the FOCA 0.22 upgrade

- **Error responses:** `status_code` in error bodies is an integer (e.g.,
  `404`), as the API specification defines; it was a string (`"404"`). (With
  FOCA 0.22, errors are problem details, see [Errors](#errors).)
- **Packaging:** `setup.py` and `requirements*.txt` are gone. Install with
  `pip install .` (or `uv sync --locked --extra dev` for development); the
  package's version comes from Git tags.
- **Image:** the app is installed as a package (`drs_filer` in
  `site-packages`); there is no `/app` directory, and no
  `update-config-map.sh`, curl, jq, yq or pip in the image any more. Don't
  mount a config at `/app/drs_filer/config.yaml`: mount an overlay instead
  and set `FOCA_CONFIG_OVERLAY` (see
  [Configuration](configuration.md)). The development server runs
  with `python -m drs_filer.app`, from any directory.
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
