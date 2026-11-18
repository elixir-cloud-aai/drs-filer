[![ELIXIR On-Cloud](images/logo_elixir_on_cloud.png)](https://elixir-on.cloud/)

# DRS-Filer

--8<-- "README.md:synopsis"

## Contents

- [Getting started](getting-started.md): run DRS-Filer with Docker Compose
  and send the first requests.
- [Configuration](configuration.md): the app configuration, overlays,
  environment variables, the public URL, identifiers and the service info.
- [API](api.md): the endpoints, registering objects, and errors.
- [Access control](access-control.md): authentication and authorization.
- [Deployment](deployment.md): the Helm chart for Kubernetes and OpenShift.
- [Operations](operations.md): the components, the server, the image and
  logs.
- [Upgrading](upgrading.md): changes to existing deployments and data.
- [Development](development.md): development setup, checks, tests, CI,
  dependency updates and the documentation.
- [Contributing](contributing/index.md): how to contribute, citation metadata
  and the Python guidelines.
- [API reference](reference.md): the code, generated from its docstrings.
- [Changelog](changelog.md): release notes.

## Architecture

DRS-Filer is a [Flask](https://flask.palletsprojects.com/) app built with
[FOCA](https://github.com/elixir-cloud-aai/foca), configured declaratively in
YAML. It serves the [GA4GH DRS
API](https://github.com/ga4gh/data-repository-service-schemas) 1.1.0 and the
[GA4GH service info
API](https://github.com/ga4gh-discovery/ga4gh-service-info) 1.0.0, and adds
endpoints to register and manage objects (see [API](api.md)). It stores the
metadata of objects and the service info in a
[MongoDB](https://www.mongodb.com/) database; the data itself stays where its
access methods point to. A [Helm](https://helm.sh/) chart and a [Docker
Compose](https://docs.docker.com/compose/) setup are provided for deployments
on Kubernetes and for development, respectively.

!!! note "Work in progress"
    DRS-Filer is being aligned with the other services of ELIXIR On-Cloud:
    DRS 1.5
    ([#88](https://github.com/elixir-cloud-aai/drs-filer/issues/88),
    [#89](https://github.com/elixir-cloud-aai/drs-filer/issues/89))
    and access tokens for writes and optionally reads
    ([#94](https://github.com/elixir-cloud-aai/drs-filer/issues/94),
    [#96](https://github.com/elixir-cloud-aai/drs-filer/issues/96)).

## Citation

--8<-- "README.md:citation"

## License

This project is covered by the [Apache License
2.0](https://www.apache.org/licenses/LICENSE-2.0) also [shipped with this
repository](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/LICENSE).

## Contact

The project is a collaborative effort under the umbrella of [ELIXIR
On-Cloud](https://elixir-on.cloud/). Follow the link to get in touch with us
via chat or email. Please mention the name of this service for any inquiry,
proposal, question etc. Report bugs and request features in the [issue
tracker](https://github.com/elixir-cloud-aai/drs-filer/issues).
