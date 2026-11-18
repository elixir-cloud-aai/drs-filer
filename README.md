<!-- markdownlint-disable MD033 MD041 -- logo first; <picture> for dark mode -->
<a href="https://elixir-on.cloud/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo_elixir_on_cloud_night.png">
    <img src="docs/images/logo_elixir_on_cloud.png" alt="ELIXIR On-Cloud">
  </picture>
</a>
<!-- markdownlint-enable MD033 MD041 -->

# DRS-Filer

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]
[![Docs][badge-docs]][badge-url-docs]
[![Coverage][badge-coverage]][badge-url-coverage]

<!-- --8<-- [start:synopsis] -->
An implementation of the [GA4GH Data Repository Service (DRS)
API](https://github.com/ga4gh/data-repository-service-schemas), brought to
you by [ELIXIR On-Cloud](https://elixir-on.cloud/). Clients such as workflow
engines and execution services resolve data objects by their identifiers and
get their metadata, checksums and the URLs to access them; additional
endpoints list, register, update and delete objects and set the service
info. DRS-Filer stores the metadata only, not the data itself. It is built
with [FOCA](https://github.com/elixir-cloud-aai/foca). Run it with Docker
Compose for development and testing; a Helm chart for Kubernetes is in
[`deployment/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/deployment).
<!-- --8<-- [end:synopsis] -->

**Read the [documentation][docs]** for the configuration, the API, access
control, the deployment, operations, upgrades and development.

## Quick start

<!-- --8<-- [start:quick-start] -->
With [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and
[Docker](https://docs.docker.com/get-docker/) with the [Compose
plugin](https://docs.docker.com/compose/install/) (version 2.24 or later)
installed, clone the repository and start DRS-Filer with its MongoDB
database, waiting until their health checks pass:

```bash
git clone https://github.com/elixir-cloud-aai/drs-filer.git
cd drs-filer
docker compose up --build --detach --wait
```

The DRS API is then served at `http://localhost:8080/ga4gh/drs/v1/`, with a
Swagger UI at
[http://localhost:8080/ga4gh/drs/v1/ui/](http://localhost:8080/ga4gh/drs/v1/ui/):

```bash
curl -X GET "http://localhost:8080/ga4gh/drs/v1/service-info" -H "accept: application/json"
```

Reads are public; registering, changing and deleting objects needs an access
token of an admin of a trusted identity provider. The Compose setup trusts
a fictitious one, so to try writes locally, disable authentication (see
[Running without
authentication](https://drs-filer.readthedocs.io/en/latest/development/#running-without-authentication));
Docker Compose publishes the app on the host's loopback interface only.
<!-- --8<-- [end:quick-start] -->

## Citation

<!-- --8<-- [start:citation] -->
If you use DRS-Filer, please cite it with the metadata in
[`CITATION.cff`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/CITATION.cff):
on GitHub, "Cite this repository" in the sidebar of the repository formats it
as APA or BibTeX. A DOI follows with the first release archived on
[Zenodo](https://zenodo.org/).
<!-- --8<-- [end:citation] -->

## Contributing

Contributions are welcome! See [Contributing][docs-contributing] in the
documentation and the organisation's [contributing guide][contributing], and
mind our [code of conduct][code-of-conduct].

[badge-build-status]: <https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/ci.yml/badge.svg?branch=dev>
[badge-coverage]: <https://codecov.io/gh/elixir-cloud-aai/drs-filer/branch/dev/graph/badge.svg?branch=dev>
[badge-docs]: <https://img.shields.io/readthedocs/drs-filer>
[badge-license]: <https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]: <https://github.com/elixir-cloud-aai/drs-filer/actions/workflows/ci.yml?query=branch%3Adev>
[badge-url-coverage]: <https://codecov.io/gh/elixir-cloud-aai/drs-filer?branch=dev>
[badge-url-docs]: <https://drs-filer.readthedocs.io/en/latest/>
[badge-url-license]: <https://www.apache.org/licenses/LICENSE-2.0>
[code-of-conduct]: <https://github.com/elixir-cloud-aai/.github/blob/main/CODE_OF_CONDUCT.md>
[contributing]: <https://github.com/elixir-cloud-aai/.github/blob/main/CONTRIBUTING.md>
[docs]: <https://drs-filer.readthedocs.io/en/latest/>
[docs-contributing]: <https://drs-filer.readthedocs.io/en/latest/contributing/>
