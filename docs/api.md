# API

DRS-Filer implements the [GA4GH Data Repository Service (DRS)
API](https://github.com/ga4gh/data-repository-service-schemas) 1.5.0. It
serves the API under `/ga4gh/drs/v1` (e.g.,
`http://localhost:8080/ga4gh/drs/v1/` with Docker Compose), with a Swagger
UI at `/ga4gh/drs/v1/ui/` and the specification (OpenAPI 3) at
`/ga4gh/drs/v1/openapi.json`. The API is defined by two files in
[`drs_filer/api/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/drs_filer/api),
merged by FOCA:

- the GA4GH DRS specification 1.5.0
  (`20250324.fe25c39.openapi.yaml`), as published: the bundled
  `openapi.yaml` of the
  [release](https://ga4gh.github.io/data-repository-service-schemas/preview/release/drs-1.5.0/docs/)
  (commit `fe25c39`, tag `drs-1.5.0`), unchanged. It includes the schemas
  of the [GA4GH service info
  specification](https://github.com/ga4gh-discovery/ga4gh-service-info)
  1.0.0;
- DRS-Filer's additions (`additions.openapi.yaml`): the endpoints that it
  adds to register and manage objects and the service info, and its
  [deviations from the specification](#deviations-from-the-specification).

Requests and responses are validated against the specification, including
the formats of URLs (`uri`) and timestamps (`date-time`, RFC 3339, e.g.,
`2026-01-01T00:00:00Z`). Request bodies of DRS-Filer's endpoints
(registration, service info) with fields that the specification doesn't
define are rejected; those of the [passport `POST`
endpoints](#passport-post-endpoints) follow the DRS schemas, which allow
other fields.

Reads (the `GET` endpoints), the service info, the API specification and
the Swagger UI are public, except access URLs (`GET
/objects/{object_id}/access/{access_id}`), which need an access token of
any user by default; while they do, objects are served without the
`access_url` of their access methods (see [Requiring login for
reads](access-control.md#requiring-login-for-reads), also to make them
public, or to require login for all reads); the authorization info of
objects (`OPTIONS`) and the `authorizations` of access methods tell clients
which reads need a token (see [Authorization
info](access-control.md#authorization-info)). The endpoints of DRS-Filer that
change objects and the service info (`POST /objects/register`, `PUT` and
`DELETE` of objects, `DELETE` of access methods, `POST /service-info`) need
an access token of an admin, sent as a bearer token (`Authorization: Bearer
<token>`); see [Access control](access-control.md).

## Endpoints

| Endpoint | Specification | Description |
| --- | --- | --- |
| `GET /objects/{object_id}` | DRS | Get an object: its metadata, checksums and access methods |
| `GET /objects/{object_id}/access/{access_id}` | DRS | Get the access URL of one of an object's access methods |
| `GET /service-info` | DRS | Get the service info |
| `POST /objects/{object_id}` | DRS | Not implemented (`501`), see [Passport POST endpoints](#passport-post-endpoints) |
| `POST /objects/{object_id}/access/{access_id}` | DRS | Not implemented (`501`), see [Passport POST endpoints](#passport-post-endpoints) |
| `POST /objects` | DRS | Not implemented (`501`), see [Passport POST endpoints](#passport-post-endpoints) |
| `POST /objects/access` | DRS | Not implemented (`501`), see [Passport POST endpoints](#passport-post-endpoints) |
| `OPTIONS /objects/{object_id}` | DRS | Get the authorization info of an object: how to authorize `GET /objects/{object_id}`, see [Authorization info](access-control.md#authorization-info) |
| `OPTIONS /objects` | DRS | Get the authorization info of several objects (bulk), see [Authorization info](access-control.md#authorization-info) |
| `GET /objects` | DRS-Filer | List the objects, one page at a time, see [Listing objects](#listing-objects) |
| `POST /objects/register` | DRS-Filer | Register an object; DRS-Filer generates its identifier |
| `PUT /objects/{object_id}` | DRS-Filer | Register an object with the given identifier, or replace the object of that identifier |
| `DELETE /objects/{object_id}` | DRS-Filer | Delete an object |
| `DELETE /objects/{object_id}/access/{access_id}` | DRS-Filer | Delete one of an object's access methods |
| `POST /service-info` | DRS-Filer | Replace the service info until the next start, see [Service info](configuration.md#service-info) |

## Listing objects

`GET /objects` lists the objects one page at a time (`DrsObjectPage`),
newest registered first. DRS doesn't define the listing, so its parameters
are those of the lists of the other ELIXIR On-Cloud services, named as in
GA4GH APIs:

- `pageSize`: the maximum number of objects of the page, a positive
  integer. By default 50, and at most 200; larger values are reduced to
  the maximum. Deployments set both
  (`custom.objects.list.default_page_size` and `max_page_size`, see
  [Settings](configuration.md#settings)).
- `pageToken`: the `nextPageToken` of the previous page, to get the next
  one.

A page has its `objects`, served as `GET /objects/{object_id}` serves them,
and a `nextPageToken`, unless it is the last page:

```bash
curl "https://drs.example.org/ga4gh/drs/v1/objects?pageSize=2"
```

```json
{
  "objects": [
    {"id": "b2c3d4", "...": "..."},
    {"id": "a1b2c3", "...": "..."}
  ],
  "nextPageToken": "<token>"
}
```

```bash
curl "https://drs.example.org/ga4gh/drs/v1/objects?pageSize=2&pageToken=<token>"
```

Tokens are opaque: pass them on as they are, don't build or change them.
Malformed tokens and page sizes that aren't positive integers get `400 Bad
Request`, with the parameter in `errors`; the problem details don't quote
the token. A token stays valid when objects are registered, replaced or
deleted: no object of the next pages is skipped or listed twice, and
objects registered while a client pages through the list come before the
first page, so they are not on the next pages. The order is that of the
time of registration to the second only: an object registered in the same
second as the last object of a page (or, with several app instances, whose
clocks differ) may still show up on a later page. Replacing an object (`PUT
/objects/{object_id}`) keeps its place in the list. While reads need login
(see [Requiring login for
reads](access-control.md#requiring-login-for-reads)), the list does too,
and the token is no substitute for it.

## Registering objects

`POST /objects/register` and `PUT /objects/{object_id}` take the metadata
of an object (`DrsObjectRegister`): `size`, `created_time` and at least one
checksum are required; `name`, `updated_time`, `version`, `mime_type`,
`contents` (for bundles), `description` and `aliases` are optional. Access
methods (`AccessMethodRegister`) need a `type`, and can have an
`access_url`, `cloud`, `region` and `available` (DRS 1.5: the cloud
provider and region of the copy, and whether it can be read at once, i.e.,
`false` for copies in cold or archival storage that need to be restored
first); DRS-Filer serves these three as registered. The DRS
specification requires at least one access method (`access_methods`) for
single blobs (objects without `contents`); register blobs with one, as
DRS-Filer doesn't check this yet and can't serve access URLs of objects
without access methods. Both need an admin's access token, and return the
identifier of the object, e.g.:

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
```

`POST /objects/register` is the path of the registration endpoint of the
proposed DRS write extension
([ga4gh/data-repository-service-schemas#418](https://github.com/ga4gh/data-repository-service-schemas/pull/418)),
with DRS-Filer's own request body until the extension is adopted
([#99](https://github.com/elixir-cloud-aai/drs-filer/issues/99)). `POST
/objects`, where DRS-Filer registered objects before, is the bulk read of
DRS 1.4 and later (see [Upgrading](upgrading.md#drs-150)).

DRS-Filer sets the fields that the server owns:

- `id`: for `POST`, a random identifier, of the characters and length that
  the configuration sets (see
  [Identifiers](configuration.md#identifiers)); for `PUT`, the identifier of
  the path.
- `self_uri`: the DRS URI of the object, `drs://<hostname>/<id>`, of the
  configured host name, with the identifier percent-encoded (see [Host
  name](configuration.md#host-name)). It is computed when the object is
  served, not stored, and replaces the `self_uri` that earlier versions
  stored.
- `access_id` of each access method: a random identifier, of the characters
  and length that the configuration sets for access methods. Clients use it
  to get the access URL (`GET /objects/{object_id}/access/{access_id}`) or to
  delete the access method. While access URLs need login (the default),
  objects are served without their `access_url`, so the `access_id` is the
  way to get it.
- `authorizations` of access methods: how to authorize requests for the
  access URL, which only DRS-Filer knows; requests that set it are
  rejected. It is computed when the object is served, for each access
  method with an `access_id`, from whether access URLs need login (see
  [Authorization info](access-control.md#authorization-info)).

`PUT` replaces the whole object of that identifier, if there is one, and
gives its access methods new access identifiers. While access URLs need
login, objects are served without them, so don't send an object as `GET`
returns it back with `PUT`: its access methods would lose their access URLs
(see [Objects without access
URLs](access-control.md#objects-without-access-urls)). DRS-Filer stores the
metadata only: it doesn't check that access URLs work or that the checksums
match the data.

Deleting the last access method of an object fails with `409 Conflict`;
delete the object instead.

## Service info

`GET /service-info` serves the service info of the configuration (see
[Service info](configuration.md#service-info)), of type `org.ga4gh:drs:1.5.0`,
with the fields that DRS 1.5 adds (`DrsService`), which DRS-Filer computes:

- `maxBulkRequestLength` and `drs.maxBulkRequestLength`: the maximum number
  of identifiers of bulk requests, `custom.bulk.max_request_length` (100 by
  default, see [Service info](configuration.md#service-info) in the
  configuration). The only bulk operation that DRS-Filer implements is the
  authorization info of objects (`OPTIONS /objects`, see [Authorization
  info](access-control.md#authorization-info)); the bulk reads are [passport
  `POST` endpoints](#passport-post-endpoints), which answer `501`.
- `drs.objectCount`: the number of registered objects, blobs and bundles.
- `drs.totalObjectSize`: the total `size` of the registered blobs (objects
  without `contents`), in bytes. Bundles aren't added, as their size is
  that of their contents, and each blob is counted once, however many
  access methods (e.g., cloud mirrors) it has, as the specification
  recommends. Blobs registered more than once, under different
  identifiers, are counted each time: DRS-Filer doesn't compare checksums.

The stats are computed from the database, never stored, and kept by each
process for 60 seconds by default; writes through a process recompute its
stats at once, other processes (Gunicorn workers, replicas) serve theirs up
to that long (see [Service info](configuration.md#service-info) in the
configuration, also to leave them out). They are under `drs`, as the
`DrsService` schema of DRS 1.5.0 defines them, not under `drs.stats`, as
the example in the specification's description of the service info shows.
Like the rest of the service info, they are public, also where a deployment
requires login for all other reads (see [Requiring login for
reads](access-control.md#requiring-login-for-reads)). Totals beyond the
64-bit range (8 EiB) lose precision, as MongoDB adds them up as
floating-point numbers then.

`POST /service-info` takes the fields of the GA4GH `Service` schema, with
the `type` of the served API (`org.ga4gh`, `drs`, `1.5.0`); it can't set the
computed fields. It answers `201` with the `Location` `service-info`, a
relative reference to the URL it was posted to (that of `GET
/service-info`).

## Passport POST endpoints

DRS defines `POST` variants of its reads that take [GA4GH
Passports](https://github.com/ga4gh-duri/ga4gh-duri.github.io/tree/master/researcher_ids)
in the request body, to authorize access with passports too large for
headers:

| Operation | Endpoint | Read it replaces |
| --- | --- | --- |
| `PostObject` | `POST /objects/{object_id}` | `GET /objects/{object_id}` |
| `PostAccessURL` | `POST /objects/{object_id}/access/{access_id}` | `GET /objects/{object_id}/access/{access_id}` |
| `GetBulkObjects` | `POST /objects` | `GET /objects/{object_id}`, for several objects |
| `GetBulkAccessURL` | `POST /objects/access` | `GET /objects/{object_id}/access/{access_id}`, for several access methods |

The bulk reads (DRS 1.4) declare passports (`PassportAuth`) as their only
security scheme, so they belong to the same group.

DRS-Filer doesn't implement them. They answer `501 Not Implemented`, with
problem details whose `detail` links to this section, to every client and
without checking credentials. They stay in the served specification, so
that clients get a defined answer instead of `405 Method Not Allowed`. The
request bodies are still validated, so a malformed one gets `400 Bad
Request`. DRS-Filer doesn't log request bodies, which here carry
credentials; only at log level `DEBUG`, the reason for rejecting a
malformed body may quote the rejected value (the console handler of the
shipped config logs from `INFO`).

They go against REST semantics and OAuth 2.0 practice:

- They use `POST` for reads: `POST` is neither safe nor idempotent, and
  responses to it aren't cached.
- They carry credentials in the request body instead of the `Authorization`
  header. Request bodies are more likely than headers to end up in logs,
  caches and error reports of clients, proxies and servers.

Clients get objects and access URLs with the `GET` operations, with a bearer
access token in the `Authorization` header where needed (see [Access
control](access-control.md)). DRS-Filer will follow when GA4GH addresses
large passports differently.

## Deviations from the specification

DRS-Filer serves the specification unchanged, but for these deviations
(`additions.openapi.yaml`):

- **Not implemented:** the [passport `POST`
  endpoints](#passport-post-endpoints), by design, answer `501`.
- **Authorization info of unknown objects:** while object reads require
  login, `OPTIONS /objects/{object_id}` and `OPTIONS /objects` answer for
  unknown objects as for registered ones, instead of with `404` or as
  unresolved, so that their existence doesn't show; see [Authorization
  info](access-control.md#authorization-info).
- **Errors** are problem details (see [Errors](#errors)), not the `Error`
  schema of DRS (`msg`, `status_code`); the error responses of the served
  specification refer to `Problem`, as `application/problem+json` (which
  DRS-Filer sends) and `application/json` (which the specification declares).
- **Authentication:** reads take no credentials: the served specification
  declares no security requirements for them, instead of optional basic and
  bearer authentication; except access URLs, and other reads that a
  deployment requires login for, which require bearer authentication
  (`BearerAuth`), as do DRS-Filer's write endpoints (see [Access
  control](access-control.md)).
- **Access URLs in objects:** while access URLs need login (the default),
  objects are served without the `access_url` of their access methods,
  which keep their `access_id` (DRS requires one of them); see [Objects
  without access URLs](access-control.md#objects-without-access-urls).
- **Bundles** are served as registered: `expand` of `GET
  /objects/{object_id}` is accepted, but ignored.
- **Service info:** `GET /service-info` can answer `404` before service info
  is set.
- **CORS preflight requests** (`OPTIONS` with `Origin` and
  `Access-Control-Request-Method`) get `200` with the CORS headers, not the
  authorization info of the `OPTIONS` operations (whose bulk variant needs a
  request body, which preflight requests don't have), so that browsers can
  call the API.
- **Object identifiers `register` and `access`** can be used with `GET`,
  `PUT` and `DELETE`, but `POST /objects/register` and `POST /objects/access`
  are the registration and the bulk read of access URLs, not the passport
  reads of these objects; `OPTIONS /objects/register` and `OPTIONS
  /objects/access` get Flask's answer (`200` with `Allow`, no body), not
  the authorization info of these objects, which is that of any object
  (see [Authorization info](access-control.md#authorization-info)).

## Errors

Errors are answered with problem details (RFC 9457), as
`application/problem+json`: `title`, `status` and `detail`, e.g.:

```json
{"title": "Not found", "detail": "The requested `DrsObject` wasn't found.", "status": 404}
```

Requests that fail the validation of their body or parameters against the
API specification (`400 Bad Request`) also have `type`, `code` (`invalid-request`) and
`errors`, which lists the invalid fields, each with `detail`, `code` and
`pointer` (a JSON Pointer into the request body, e.g., `#/created_time`) or
`parameter` (the name of an invalid parameter). The `Problem` schema of the
served specification describes them, with `FieldError` for the entries of
`errors`. Only `title` and `status` are always set: e.g., the answer to a
body that isn't JSON has neither `code` nor `errors`. Writes without a valid
access token get `401 Unauthorized`, with a Bearer challenge
(`WWW-Authenticate: Bearer`, with `error="invalid_token"` for invalid
tokens), before their body is validated; writes with a valid token of a
user without the required role get `403 Forbidden` (see
[Authentication](access-control.md#authentication)). The exceptions of the
app and their problem details are listed in
[`drs_filer/errors/exceptions.py`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/errors/exceptions.py)
(see the [API reference](reference.md#errors)).
