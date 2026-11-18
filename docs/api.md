# API

DRS-Filer serves its API under `/ga4gh/drs/v1` (e.g.,
`http://localhost:8080/ga4gh/drs/v1/` with Docker Compose), with a Swagger
UI at `/ga4gh/drs/v1/ui/` and the specification at
`/ga4gh/drs/v1/swagger.json`. The API is defined by three specifications in
[`drs_filer/api/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/drs_filer/api),
merged by FOCA:

- the [GA4GH DRS
  specification](https://github.com/ga4gh/data-repository-service-schemas)
  1.1.0 (`20200622.383121d.data_repository_service.swagger.yaml`, kept as
  published);
- the [GA4GH service info
  specification](https://github.com/ga4gh-discovery/ga4gh-service-info)
  1.0.0 (`20200131.11d2c12.service-info.yaml`);
- the endpoints that DRS-Filer adds to register and manage objects and the
  service info (`additional.data_repository_service.swagger.yaml`).

Requests and responses are validated against the specifications, including
the formats of URLs (`uri`) and timestamps (`date-time`, RFC 3339, e.g.,
`2026-01-01T00:00:00Z`); request bodies with fields that the specification
doesn't define are rejected.

!!! warning "No authentication yet"
    All endpoints, including those that change objects, are open to anyone
    who can reach the app; see [Access control](access-control.md).

## Endpoints

| Endpoint | Specification | Description |
| --- | --- | --- |
| `GET /objects/{object_id}` | DRS | Get an object: its metadata, checksums and access methods |
| `GET /objects/{object_id}/access/{access_id}` | DRS | Get the access URL of one of an object's access methods |
| `GET /service-info` | service info | Get the service info |
| `GET /objects` | DRS-Filer | List all objects |
| `POST /objects` | DRS-Filer | Register an object; DRS-Filer generates its identifier |
| `PUT /objects/{object_id}` | DRS-Filer | Register an object with the given identifier, or replace the object of that identifier |
| `DELETE /objects/{object_id}` | DRS-Filer | Delete an object |
| `DELETE /objects/{object_id}/access/{access_id}` | DRS-Filer | Delete one of an object's access methods |
| `POST /service-info` | DRS-Filer | Set the service info |

`GET /objects` returns all objects at once, without pagination
([#59](https://github.com/elixir-cloud-aai/drs-filer/issues/59)).

## Registering objects

`POST /objects` and `PUT /objects/{object_id}` take the metadata of an
object (`DrsObjectRegister`): `size`, `created_time` and at least one
checksum are required; `name`, `updated_time`, `version`, `mime_type`,
`contents` (for bundles), `description` and `aliases` are optional. The DRS
specification requires at least one access method (`access_methods`) for
single blobs (objects without `contents`); register blobs with one, as
DRS-Filer doesn't check this yet and can't serve access URLs of objects
without access methods. Both return the identifier of the object, e.g.:

```bash
curl -X POST "http://localhost:8080/ga4gh/drs/v1/objects" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample.bam",
    "size": 1024,
    "created_time": "2026-01-01T00:00:00Z",
    "checksums": [{"type": "sha-256", "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}],
    "access_methods": [{"type": "https", "access_url": {"url": "https://example.org/data/sample.bam"}}]
  }'
```

DRS-Filer sets the fields that the server owns:

- `id`: for `POST`, a random identifier, of the characters and length that
  the configuration sets (see
  [Identifiers](configuration.md#identifiers)); for `PUT`, the identifier of
  the path.
- `self_uri`: built from the public URL of the configuration and the
  identifier (see [Public URL](configuration.md#public-url)).
- `access_id` of each access method: a random identifier, of the characters
  and length that the configuration sets for access methods. Clients use it
  to get the access URL (`GET /objects/{object_id}/access/{access_id}`) or to
  delete the access method.

`PUT` replaces the whole object of that identifier, if there is one, and
gives its access methods new access identifiers. DRS-Filer stores the
metadata only: it doesn't check that access URLs work or that the checksums
match the data.

Deleting the last access method of an object fails with `409 Conflict`;
delete the object instead.

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
`parameter` (the name of an invalid parameter). The `Error` definition of
the DRS specification describes them, with `FieldError` for the entries of
`errors`. Only `title` and `status` are always set: e.g., the answer to a
body that isn't JSON has neither `code` nor `errors`. The exceptions of the
app and their problem details are listed in
[`drs_filer/errors/exceptions.py`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/errors/exceptions.py)
(see the [API reference](reference.md#errors)).
