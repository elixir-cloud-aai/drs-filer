# Access control

Objects and the service info can be read by anyone; access URLs need an
access token of any user, by default (see [Requiring login for
reads](#requiring-login-for-reads), also for how to make them public, or
to require login for all reads). Writing, i.e., registering, replacing and
deleting objects and access methods, and posting the service info (see
[API](api.md#endpoints)),
requires an access token of an OpenID Connect provider that the deployment
trusts (see [Authentication](#authentication)), and, for now, the role
`admin` (see [Admins](#admins)). The identity provider, its claims and the
groups mapped to `admin` are deployment configuration, without defaults
(see [Deployment configuration](configuration.md#deployment-configuration)).
Authentication and access control are implemented with
[FOCA](https://foca.readthedocs.io/en/latest/access-control/), as in
[TRS-Filer](https://trs-filer.readthedocs.io/en/latest/access-control/) and
[Cloud
Registry](https://cloud-registry.readthedocs.io/en/latest/access-control/);
see the `security` section of the
[configuration](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/config.yaml).

!!! note "Work in progress"
    Access control follows the other registries of ELIXIR On-Cloud step by
    step:

    - [#95](https://github.com/elixir-cloud-aai/drs-filer/issues/95):
      owners and maintainers of objects, so that users other than admins
      can register objects and change their own;
    - [#98](https://github.com/elixir-cloud-aai/drs-filer/issues/98):
      authorization info of objects;
    - [#92](https://github.com/elixir-cloud-aai/drs-filer/issues/92): the
      security patterns of the other registries of ELIXIR On-Cloud.

## Authentication

Access URLs (`GET /objects/{object_id}/access/{access_id}`) require an
access token by default, of any user (see [Requiring login for
reads](#requiring-login-for-reads)). The other read operations (the `GET`
endpoints), the service info, the API specification
(`/ga4gh/drs/v1/openapi.json`) and the Swagger UI (`/ga4gh/drs/v1/ui/`) are
public, and ignore tokens; so are the [passport `POST`
endpoints](api.md#passport-post-endpoints), which answer `501`. All write
operations of DRS-Filer (`POST /objects/register`, `PUT` and `DELETE
/objects/{object_id}`, `DELETE /objects/{object_id}/access/{access_id}`,
`POST /service-info`) require an access token of a trusted issuer, sent as
a bearer token (the scheme `BearerAuth` of the DRS specification):

```bash
curl -X POST "http://localhost:8080/ga4gh/drs/v1/objects/register" \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d @object.json
```

Requests without a valid token are rejected with `401 Unauthorized` and a
Bearer challenge (`WWW-Authenticate: Bearer`, RFC 6750; with
`error="invalid_token"` for invalid tokens), before their body is validated;
requests with a valid token, but without the required role, with `403
Forbidden`. Both are [problem details](api.md#errors).

Tokens are obtained by logging in with the identity provider through an app
registered as its client (OpenID Connect), e.g., a portal or gateway, or a
client of your own for scripts. DRS-Filer accepts tokens only:

- that are access tokens as per [RFC
  9068](https://www.rfc-editor.org/rfc/rfc9068) (`typ` header `at+jwt`);
  other tokens, such as ID tokens, are rejected;
- of the issuers in `security.auth.issuers` (none by default: each
  deployment sets its identity provider, and the app refuses to start
  without one);
- for the client IDs in `security.auth.audience` (the `aud` claim), which
  each deployment sets to the apps that call it (see
  [Configuration](configuration.md#deployment-configuration)); the Docker
  Compose setup accepts tokens for any audience;
- that haven't expired and are signed with a key of the issuer (RS256).

DRS-Filer reads the user's group memberships from the group claim
(`security.access_control.claim_groups`, needed for the [admin
role](#admins)). Claims in `security.auth.userinfo_claims` are read from the
identity provider's user info endpoint with the token, for identity
providers that don't put them in access tokens, so the token must be allowed
to release them (e.g., request the corresponding scopes when logging in).
Tokens are validated by
[FOCA](https://foca.readthedocs.io/en/latest/authentication/).

For local development without an identity provider, authentication can be
disabled with a config overlay (see [Running without
authentication](development.md#running-without-authentication)); never do
this in deployments.

## Admins

Members of the groups that the deployment maps to the role `admin`
(`security.access_control.group_mapping`) are **admins**: they can do
everything, i.e., register, replace and delete all objects and access
methods, and post the service info. Until objects have owners
([#95](https://github.com/elixir-cloud-aai/drs-filer/issues/95)), only
admins can write: no policy rule allows writes to other users, who get `403
Forbidden`. E.g., with the group claim `groups`:

```yaml
security:
    access_control:
        claim_groups: groups
        group_mapping:
            drs-admins: admin
```

The app refuses to start without a group mapped to `admin`
(`security.access_control.require_admin`, FOCA), unless a deployment sets
`require_admin: false` (as the Docker Compose setup does): then nobody can
write. On startup, FOCA logs the groups mapped to `admin`.

To let other users write, map a group to a role of your own and give the
role write rules in a config overlay, e.g., for editors who may register,
replace and delete all objects:

```yaml title="editors.yaml"
security:
    access_control:
        group_mapping:
            drs-admins: admin
            drs-editors: editor
        policies:
            editors-register-objects: [p, editor, /ga4gh/drs/v1/objects/register, POST]
            editors-change-objects: [p, editor, "/ga4gh/drs/v1/objects/:object_id", "(PUT)|(DELETE)"]
            editors-delete-access-methods: [p, editor, "/ga4gh/drs/v1/objects/:object_id/access/:access_id", DELETE]
```

Mappings are merged with those of the base config, but `group_mapping` has
no entries there, so an overlay that sets it lists the admin groups, too.

### Group membership changes

Group memberships are those of the token: if the group claim is in the
access token, users removed from a group keep its roles, also the role
`admin`, until the token expires. If it is read from the user info
(`security.auth.userinfo_claims`), FOCA caches the user info per token for
up to `security.auth.cache_ttl` seconds (default: 300, but not beyond the
token's expiry; per worker process). So users removed from a group keep its
roles for up to 5 minutes, and users added to a group get them only after
that time (or with a new token). To shorten the delay, lower `cache_ttl`
(which also sets how long the issuers' discovery documents and keys are
cached), or set `security.auth.validate_userinfo: true`, which fetches the
user info for every request with a token (and so also rejects revoked
tokens), at the cost of a request to the identity provider each time (see
FOCA's [authentication](https://foca.readthedocs.io/en/latest/authentication/)).

## Requiring login for reads

Access URLs, which may carry credentials (e.g., the `headers` of an
`access_url`, or presigned URLs), require login by default, and deployments
can make them public, or require login for all reads, except `GET
/service-info`. Both use FOCA's [spec
patches](https://foca.readthedocs.io/en/latest/configuration/api/#patching-specifications)
and [named
entries](https://foca.readthedocs.io/en/latest/configuration/#named-entries),
as TRS-Filer does. DRS-Filer ships two patches, which set the security
requirements of read operations to a bearer token (`BearerAuth`, the
scheme of DRS):

- [`drs_filer/api/patches/login-for-access-urls.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/api/patches/login-for-access-urls.yaml),
  for access URLs (`GET /objects/{object_id}/access/{access_id}`), which
  the base config applies:

    ```yaml
    --8<-- "drs_filer/api/patches/login-for-access-urls.yaml"
    ```

- [`drs_filer/api/patches/login-for-reads.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/api/patches/login-for-reads.yaml),
  for the other reads (`GET /objects`, `GET /objects/{object_id}`), which
  deployments add:

    ```yaml
    --8<-- "drs_filer/api/patches/login-for-reads.yaml"
    ```

Requests to the patched reads without a valid token are rejected with `401
Unauthorized` (also for objects and access methods that don't exist, so
that their existence doesn't show); any authenticated user may read, by the
default policies (in `security.access_control.policies`, which are only
evaluated for reads that require login): `get-access-urls` (`GET
/objects/{object_id}/access/{access_id}`), `list-objects` (`GET /objects`)
and `get-objects` (`GET /objects/{object_id}`). `GET /service-info`, the API
specification (`openapi.json`) and the Swagger UI (`ui/`) stay public. The
rules allow `HEAD` too, which Flask serves from the `GET` operations and
which access control checks as `HEAD`.

### Objects without access URLs

Objects carry the access URLs of their access methods, too (`access_url`).
While access URLs require login, `GET /objects` and `GET
/objects/{object_id}` serve objects without them, also to logged-in users
and admins, so that they can't be read without a token through the
objects; the stored objects stay unchanged. Each access method keeps its
`access_id` (DRS requires one of `access_url` and `access_id`), with which
clients get its access URL, with a token:

```bash
curl "https://drs.example.org/ga4gh/drs/v1/objects/<object_id>/access/<access_id>" \
  -H "Authorization: Bearer <token>"
```

So, while access URLs require login, an object as `GET` serves it is no
body for `PUT /objects/{object_id}`: it would replace the object with one
whose access methods have no access URLs. Build the body from the object as
registered instead.

With public access URLs, objects are served with them, as registered.
DRS-Filer reads whether access URLs require login from the specification as
patched by all config files, and logs it on startup ("Access URLs need
login" or "Access URLs are public").

### Public access URLs

To make access URLs public, leave the patch out of the patches of the
specification (named `drs` in the base config) in an overlay. FOCA merges
mappings of overlays into the base config, but replaces lists, so an
overlay that sets `patches` replaces those of the base config:

```yaml title="public-access-urls.yaml"
api:
    specs:
        drs:
            patches: []
```

With the Helm chart, put the same in the `config` value. Overlays that set
patches of their own (e.g., to change the `info` of the specification) must
list `api/patches/login-for-access-urls.yaml` too, or access URLs become
public: check the startup log.

### Login for all reads

To require login for all reads, list both patches in an overlay (the paths
are relative to the directory of the base config, where the patches are
installed):

```yaml title="login-for-reads.yaml"
api:
    specs:
        drs:
            patches:
                - api/patches/login-for-access-urls.yaml
                - api/patches/login-for-reads.yaml
```

With only `api/patches/login-for-reads.yaml`, objects require login, but
access URLs are public, and objects are served with them.

### Readers

To allow reads for some users only, replace the rules by name in an
overlay, e.g., with rules for a role that a group is mapped to, in addition
to the deployment's admin groups (`null` removes a rule; admins may always
read):

```yaml title="readers.yaml"
security:
    access_control:
        group_mapping:
            drs-admins: admin
            drs-readers: reader
        policies:
            get-access-urls: [p, reader, "/ga4gh/drs/v1/objects/:object_id/access/:access_id", "GET|HEAD"]
            list-objects: [p, reader, /ga4gh/drs/v1/objects, "GET|HEAD"]
            get-objects: [p, reader, "/ga4gh/drs/v1/objects/:object_id", "GET|HEAD"]
```

The rules only apply to the reads that require login: with the default
patches, `list-objects` and `get-objects` have no effect, and objects stay
public. If an overlay of the deployment gives the policies as a list, which
replaces the rules of the base config, add these rules to the list (FOCA
refuses named rules after a list).

!!! danger "With great power comes great responsibility"
    Patches and rules in overlays can weaken or remove authentication and
    access control as easily as they add them. Review them like code, keep
    them as small as possible, and check the startup logs, which list the
    applied patches, say whether access URLs need login, and warn of
    operations that patches make public (see FOCA's [patching
    specifications](https://foca.readthedocs.io/en/latest/configuration/api/#patching-specifications)).

## Network access

Authentication applies to every request that reaches the app, also from
inside the cluster; to keep FOCA's permissions API (`/admin/access-control/`,
for admins only) off the internet, see [Access](deployment.md#access).
