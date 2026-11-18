# Upgrading

Changes that need action when upgrading from earlier versions of the
repository's default branch, newest first.

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
keep it, put it in the config (`endpoints.service_info`, see
[Configuration](configuration.md#service-info)).

## Identifier character sets

The character sets of generated identifiers (`endpoints.objects.id_charset`
and `endpoints.access_methods.id_charset`) list the characters themselves
and are never evaluated (#54): Python expressions, which earlier versions
evaluated with `eval()`, could run any code. Only unreserved characters of
URLs are allowed (letters, digits and `.-_~`), as identifiers are part of
URLs. Identifiers are generated with FOCA's `generate_id()`, from a
cryptographically secure source.

- Expressions (e.g., `string.ascii_letters + string.digits` or
  `'0123456789abcdef'`, with quotes) and other characters (e.g., spaces or
  `/`) fail the start, with an error that names the setting (e.g.,
  `Invalid 'endpoints.objects': ...`). Replace expressions with the
  characters, e.g., the former default
  `'string.ascii_letters + string.digits + ".-_~"'` with:

  ```yaml
  endpoints:
    objects:
      id_charset: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_~"
    access_methods:
      id_charset: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_~"
  ```

  This is the default of the base config now, with the same characters as
  before: overlays that don't set `id_charset` need no change.
- Character sets of unreserved characters (e.g., `"abc123"`) keep working
  for object identifiers. They now work for access identifiers, too, and
  so do those that happened to be valid Python (e.g., digits only); both
  failed requests with `500 Internal Server Error`.
- An empty or non-string `id_charset` (e.g., a YAML list, which worked for
  object identifiers), or an `id_length` that isn't a positive integer, also
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
  too: check the `endpoints.service_info` of your overlay, as
  `GET /service-info` fails with `500 Internal Server Error` otherwise. The
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
