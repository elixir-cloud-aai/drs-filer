# Configuration

DRS-Filer is configured with a [FOCA](https://foca.readthedocs.io/)
configuration (FOCA 0.22; see [FOCA's configuration
reference](https://foca.readthedocs.io/en/latest/configuration/)):
[`drs_filer/config.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/config.yaml),
which is installed with the package and part of the image. The comments in
the file describe each section; the section `custom` holds the settings of
DRS-Filer itself, and FOCA's section `service_info` the service info.

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
| `security.auth.issuers`, `security.auth.audience` | none (required) | Trusted token issuers and the client IDs of their tokens, see [Deployment configuration](#deployment-configuration) |
| `security.access_control.claim_groups`, `security.access_control.group_mapping` | none (required) | Claim with the groups of users, and the groups whose members are admins, see [Deployment configuration](#deployment-configuration) |
| `custom.service.url_prefix`, `custom.service.external_host`, `custom.service.external_port` | `http`, `localhost`, `8080` | Public URL of the app, see [Public URL](#public-url) |
| `custom.service.api_path` | `ga4gh/drs/v1` | Path of the API in the public URL |
| `service_info.service` | placeholders | Service info (`GET /service-info`), see [Service info](#service-info) |
| `custom.objects.id`, `custom.access_methods.id` | 6 characters, letters, digits and `.-_~` | Generated identifiers, see [Identifiers](#identifiers) |
| `db.host`, `db.port` | `mongodb`, `27017` | MongoDB |
| `server.debug` | `False` | Flask's debug mode, which allows executing arbitrary code: only for local development, see [Development](development.md#development-server) |
| `log` | console, level `INFO` | Logging (Python's `logging.config` dictionary) |

The app validates its settings on startup
([`drs_filer/custom_config.py`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/custom_config.py)
for `custom`, FOCA for the other sections): invalid values and unknown keys
of `custom` (e.g., misspelled ones) fail the start, with an error that names
the setting and the reason, but not the value. So does the section
`endpoints` of earlier versions (see
[Upgrading](upgrading.md#typed-configuration)). The service info is
checked against the service info specification instead, which allows other
fields (a misspelled field is served as an extra field), and its errors
show the invalid value.

## Deployment configuration

Writes need an access token of an admin (see [Access
control](access-control.md)). DRS-Filer works with any OpenID Connect
provider that issues access tokens as per [RFC
9068](https://www.rfc-editor.org/rfc/rfc9068) (JWTs). The identity provider,
its claims and the groups mapped to the role `admin` are deployment
configuration: the base config has no defaults for them, so each deployment
sets them in an overlay (or in the Helm chart's `config` value), otherwise
the app refuses to start (and the chart refuses to render):

- `security.auth.issuers`: the trusted token issuers (the `iss` claim of
  their tokens, e.g., `https://login.example.org/oidc/`); tokens of other
  issuers are rejected (see
  [Authentication](access-control.md#authentication));
- `security.auth.audience`: the client IDs of the apps whose tokens are
  accepted (the `aud` claim, e.g., of a portal or gateway that registers
  objects, or of a client for scripts), unless
  `security.auth.verify_audience` is `false`, which accepts tokens for any
  audience (not recommended);
- `security.access_control.claim_groups`: the claim with the groups of users
  (e.g., `groups`), needed for admins; add it to
  `security.auth.userinfo_claims` if the identity provider releases it via
  user info only, not in access tokens;
- `security.access_control.group_mapping`: the group(s) whose members are
  admins (values of the group claim, see
  [Admins](access-control.md#admins)), or
  `security.access_control.require_admin: false` to run without admins
  (nobody can write then).

For example:

```yaml
security:
    auth:
        issuers:
            - https://login.example.org/oidc/
        audience:
            - drs-portal
        userinfo_claims:
            - groups
    access_control:
        claim_groups: groups
        group_mapping:
            drs-admins: admin
```

Notes:

- Groups that contain `:` or `#` (e.g., entitlements, which are URNs) must
  be quoted as keys in YAML.
- Without the group claim in the token or in `userinfo_claims`, no user gets
  the role `admin`. Clients must request the scope that releases the claim
  when logging in, and the identity provider must allow it for the client.
- DRS-Filer accepts only access tokens with the `typ` header `at+jwt`
  (`security.auth.verify_token_type`, enabled by default). Before going live,
  check that the identity provider issues such tokens to the clients, and
  that their `aud` matches `audience`: otherwise writes fail with `401
  Unauthorized`.
- To accept tokens of some clients only (e.g., of a portal in front of
  DRS-Filer), list their client IDs in `security.auth.clients` (FOCA
  compares them with the `client_id` claim of tokens, or `azp` without it).

The policy rules (`security.access_control.policies`, see FOCA's [access
control](https://foca.readthedocs.io/en/latest/access-control/#configuring-policies))
say what each role may do. The base config has none, so only admins can
write; they are named, so that an overlay can add, change or remove single
rules by name (FOCA's [named
entries](https://foca.readthedocs.io/en/latest/configuration/#named-entries)).
Settings for specific identity providers belong to the documentation of the
deployment, not here.

## Public URL

A deployment's overlay sets at least its public URL, from which the app
builds the `self_uri` of objects
(`<url_prefix>://<external_host>:<external_port>/<api_path>/<id>`), and its
service info, as the base config has defaults for local development
(`http://localhost:8080`) and placeholders for the service info:

```yaml
custom:
  service:
    url_prefix: https
    external_host: drs.example.org
    external_port: 443
```

`url_prefix` is `http` or `https`; `external_host` a host name or IP
address (IPv6 addresses in brackets), without scheme, port or path;
`external_port` an integer from 1 to 65535; and `api_path` segments of
letters, digits and `-._~`, separated by `/` (not `.` or `..`), without
leading or trailing `/`. Integer settings (the port, the lengths of
identifiers) take integers or strings of digits, so they can be set from
environment variables (e.g., `external_port: ${PUBLIC_PORT}`).

## Service info

The service info (`GET /service-info`) is configured in FOCA's section
`service_info`: the fields in `service_info.service`, and the package whose
version is served as `version` (`service_info.package: drs-filer`, i.e., the
version of the installed app, or of the image), unless
`service_info.service.version` is set. FOCA validates it on startup against
the service info specification, including the formats of URLs and
timestamps, and warns of values in reserved example domains (e.g.,
`example.org`), as the placeholders of the base config. Fields set to `null`
in an overlay are removed (e.g., `createdAt: null`). The optional timestamps
`createdAt` and `updatedAt` are served only if set.

The config takes precedence: on each start, the app serves the service info
of its config, and replaces any service info stored in the database with it,
also service info with another `id`. Service info posted with `POST
/service-info` is served until the app starts again: when a pod or container
restarts, but also when Gunicorn starts a worker (each worker creates the
app, e.g., after a worker timed out). To change the service info for good,
set it in the deployment's overlay, not with `POST /service-info`:

```yaml
service_info:
  service:
    id: org.example.drs
    name: DRS-Filer of Example
    description: Data Repository Service of Example
    organization:
      name: Example
      url: https://example.org
    contactUrl: mailto:drs@example.org
    documentationUrl: https://drs-filer.readthedocs.io/
    createdAt: "2026-01-01T00:00:00Z"
    environment: prod
```

The base config sets `type` (`org.ga4gh`, `drs`, `1.5.0`: the version of
the DRS specification that the app serves), which mappings in overlays are
merged with; don't set `type` in overlays: it must be the type of the API
that the app serves, and other types fail the start.
The app adds the fields that DRS 1.5 requires (`maxBulkRequestLength`,
`drs`), which it computes (see [Service info](api.md#service-info) in the
API docs); don't set them in the config.

## Identifiers

Objects registered without an identifier (`POST /objects/register`) and
their access methods get random identifiers of `length` characters (default
6), drawn from `charset` (default: letters, digits and `.-_~`), in
`custom.objects.id` and `custom.access_methods.id`. `charset` lists the
characters themselves, which must be unreserved characters of URLs (letters,
digits and `.-_~`); other characters and expressions such as
`string.ascii_letters + string.digits` fail the start, and so does a
`length` that is not a positive integer (see
[Upgrading](upgrading.md#identifier-character-sets)):

```yaml
custom:
  objects:
    id:
      charset: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
      length: 8
```

## Docker Compose

Docker Compose uses the overlay
[`config.dev.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/config.dev.yaml)
(public URL `http://localhost:8080`; a fictitious token issuer, tokens for
any audience, and no admins required, so that the app starts, but nobody
can write until you set your identity provider and admin group, or disable
authentication, see [Running without
authentication](development.md#running-without-authentication)). If your
overlay sets your own identity provider, also set
`security.auth.audience` (your client ID) and
`security.auth.verify_audience: True`, as `config.dev.yaml` accepts tokens
for any audience, i.e., also those issued for other apps of that provider,
and map an admin group (`security.access_control.group_mapping`), as it
requires none. To use your own overlays instead, set
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

The Helm chart writes its overlay to a ConfigMap: the public URL
(`custom.service`, from the value `hostName`) and the MongoDB host, merged
with the value `config`, which takes the settings of this page (e.g., the
service info, `service_info.service`; see
[Configuration](deployment.md#configuration) in the deployment guide).
