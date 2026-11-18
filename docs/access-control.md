# Access control

Objects, their access URLs and the service info can be read by anyone.
Writing, i.e., registering, replacing and deleting objects and access
methods, and posting the service info (see [API](api.md#endpoints)),
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
    - [#96](https://github.com/elixir-cloud-aai/drs-filer/issues/96):
      optional login for reads;
    - [#98](https://github.com/elixir-cloud-aai/drs-filer/issues/98):
      authorization info of objects.

## Authentication

Read operations (the `GET` endpoints), the service info, the API
specification (`/ga4gh/drs/v1/openapi.json`) and the Swagger UI
(`/ga4gh/drs/v1/ui/`) are public, and ignore tokens; so are the [passport
`POST` endpoints](api.md#passport-post-endpoints), which answer `501`. All
write operations of DRS-Filer (`POST /objects/register`, `PUT` and `DELETE
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

## Network access

Authentication applies to every request that reaches the app, also from
inside the cluster. FOCA's permissions API (`/admin/access-control/`, for
admins only) is served like the DRS API; to keep it off the internet, route
only `/ga4gh/drs/v1/` through the ingress controller, the router or a proxy
in front of them (see [Access](deployment.md#access) for the Helm chart).
