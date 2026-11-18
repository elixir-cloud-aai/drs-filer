# Access control

!!! warning "No authentication yet"
    DRS-Filer currently serves its API **without authentication**: anyone
    who can reach it can read, register, change and delete objects and set
    the service info. Don't expose it to untrusted networks; Docker Compose
    publishes it on the host's loopback interface only. Access control
    follows with:

    - [#94](https://github.com/elixir-cloud-aai/drs-filer/issues/94):
      access tokens for writes;
    - [#96](https://github.com/elixir-cloud-aai/drs-filer/issues/96):
      optional login for reads;
    - [#95](https://github.com/elixir-cloud-aai/drs-filer/issues/95):
      owners and maintainers of objects;
    - [#98](https://github.com/elixir-cloud-aai/drs-filer/issues/98):
      authorization info of objects;
    - [#92](https://github.com/elixir-cloud-aai/drs-filer/issues/92): the
      security patterns of the other registries of ELIXIR On-Cloud.

    This page will then describe them.

## Protecting a deployment until then

The API specifications of DRS-Filer declare no security schemes (`security`
and `securityDefinitions` are commented out in the DRS specification), so
FOCA checks no tokens. Until access control is in place, restrict access in
front of the app, e.g., with network policies, or with a reverse proxy that
authenticates clients, and allow only trusted clients to write.
