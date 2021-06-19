# DRS-Filer

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]
[![Coverage][badge-coverage]][badge-url-coverage]

Lightweight, flexible implementation of the [Global Alliance for Genomics &
Health's (GA4GH)][ga4gh] [Tool Registry Service (DRS) API][ga4gh-drs] for
listing and describing tools and workflows.

## Description

_**DRS-Filer is complete**_

Next to the endpoints defined by the GA4GH DRS API (see
[specification][ga4gh-drs], DRS-Filer provides endpoints to register
tools, tool versions, tool classes and update the service info.

_**DRS-Filer is extensible**_

DRS-Filer makes use of the [FOCA][res-foca] microservice archetype, which is
based on the [Flask][res-flask] / [OpenAPI][res-openapi] /
[Connexion][res-connexion] tool stack. As FOCA abstracts a lot of boilerplate
code away, the DRS-Filer codebase is very small and consists almost exlusively
of business logic, making it easy to [adapt, extend and maintain](#extension).

_**DRS-Filer is versatile**_

DRS-Filer was not built on top of a specific data repository. In cases where the
[DRS specification][ga4gh-drs] leaves things up for implementers, we tried
our best to support multiple [configurable options](#configuration).

You can use DRS-Filer as a ready-made, low maintenance shim around your own
data repository and thus make it available to the [GA4GH Cloud][ga4gh-cloud]
community. But you can just as well use it to index an available third-party
data repository to have it integrate seamlessly with your [GA4GH
Cloud][ga4gh-cloud] ecosystem.

_**DRS-Filer is free**_

DRS-Filer is released under a [permissive license][license] that lets everyone
use it, in every way, for whatever purpose, including commercial.

## Usage

Once [deployed](#installation), the API is served here:

```console
http://localhost:8080/ga4gh/drs/v2/
```

> Note that host (`localhost`) and port (`8080`) in the URL above may differ,
> depending on how the service was deployed. Indicated values are for
> `docker-compose`-based installations using the default
> [configuration][drs-filer-compose-config].

The easiest way to explore available endpoints is via the
[Swagger UI][res-swagger-ui]:

```console
http://localhost:8080/ga4gh/drs/v1/ui
```

You can also access DRS-Filer's [OpenAPI][res-openapi] specification:

```console
http://localhost:8080/ga4gh/drs/v1/swagger.json
``` 

DRS-Filer endpoints can be queried by sending appropriate HTTP requests to URLs
composed of the root API path and an endpoint-specific suffix. For instance,
you can list available tools in a DRS-Filer deployment by sending a `GET` HTTP
request to the `/tools` route, e.g., via `curl`:

```bash
curl -X GET "http://localhost:8080/ga4gh/drs/v2/tools" -H "accept: application/json"
```

> Convenient clients that help with sending HTTP requests and processing
> responses are available for any major programming language. If you are new
> to web programming, we recommend you to read up on
> [HTTP methods][res-http-methods] and [web APIs][res-web-apis].

## Installation

To quickly install the service for development/testing purposes, we recommend
deployment via [`docker-compose`][res-docker-compose], as described below. For
more durable deployments on cloud native infrastructure, we also provide a
[Helm][res-helm] chart and [basic deployment instructions][drs-filer-
deployment] (details may need to be adapted for your specific infrastructure).

### Requirements

The following software needs to be available on your system:

- [`git`][res-git] `v2.17.1`
- [`docker`][res-docker] `v18.09.6`
- [`docker-compose`][res-docker-compose] `v1.23.1`

> Indicated versions were used during development. Other versions may work as
> well, especially newer ones.

### Deployment

First, clone the repository and traverse into the service's root directory
with:

```bash
git clone git@github.com:elixir-cloud-aai/drs-filer.git
cd drs-filer
```

Then simply start up the service with:

```bash
docker-compose up --build -d
```

_**That't it!**_

You should now be able to use/explore the API as described in the [usage
section](#usage).

### Other useful commands

To shut down the service, run:

```bash
docker-compose down
```

If you need to inspect the logs, call:

```bash
docker-compose logs
```

## Configuration

The app's configuration is centralized in the file
[`drs_filer/config.yaml`][drs-filer-config]. As the format follows the one
expected by [FOCA][res-foca], refer to the FOCA documentation for a description
of the various configuration options.

The only exception to this is the custom section `endpoints`, which lists all
the configuration options that are specific to DRS-Filer. These are:

* `service`: The parameters in this section are used to construct self
  references/anchors as required by the [DRS specification][ga4gh-drs] and need
  to be replaced with the corresponding values of each individual DRS-Filer
  deployment.
* `service-info`: The parameters in this section are used to populate the
  service info database collection if such a collection does not yet exist,
  usually when a new app instance is deployed. The default values should be
  replaced for each individual deployment, in accordance with the schemas and
  documentation provided in the [GA4GH Service Info
  specification][ga4gh-service-info].
* `objects` & `access_methods`: The parameters in these sections define the
  behavior for generating the `id` identifier for objects and access methods, 
  respectively, as required by the [DRS specification][ga4gh-drs].
  * For `id`-type identifiers, random strings of a specified `length` are
    generated from a set of allowed characters (`charset`). The latter option
    accepts either a string, indicating the allowed characters, or a Python
    expression that evaluates to such a string.

## Extension

It is easy to add additional endpoints or modify the behavior of existing ones.

All OpenAPI specifications are available in [`drs_filer.api`][drs-filer-api].
Custom endpoints, i.e., those that are not specified in either the [GA4GH
DRS][ga4gh-drs] or the [GA4GH Service Info][ga4gh-service-info] specifications,
are included in file [`additional.data_repository_service.swagger.yaml`][drs-filer-api-custom].

When specifying new endpoints, the `operationId` directive indicates the name
of the corresponding controller. By default, all controllers need to be
implemented in the [`ga4gh.drs.server`][drs-filer-controllers] module. For
example, when specifying an `operationId` of `myController` for a new endpoint
in [`additional.data_repository_service.swagger.yaml`][drs-filer-api-custom], the application would
expect the corresponding controller to be implemented in function/class
`ga4gh.drs.server.myController()`.

> If necessary, the default location of the module containing the controllers
> can be customized following instructions provided by [FOCA][res-foca],
> [Connexion][res-connexion] and [OpenAPI][res-openapi].

Custom errors can be specified in module
[`errors.exceptions`][drs-filer-exceptions]. Just follow the existing structure
and refer the [FOCA][res-foca] documentation on exception handling in case of
doubt.

## Contributing

This project is a community effort and lives off your contributions, be it in
the form of bug reports, feature requests, discussions, or fixes and other code
changes. Please refer to our organization's [contribution
guidelines][elixir-cloud-contributing] if you are interested in contributing.
Please mind the [code of conduct][elixir-cloud-coc] for all interactions with
the community.

## Versioning

The project adopts the [semantic versioning][res-semver] scheme for versioning.
Currently the service is in beta stage, so the API may change without further
notice.

## License

This project is covered by the [Apache License 2.0][license-apache] also
[shipped with this repository][license].

## Contact

The project is a collaborative effort under the umbrella of [ELIXIR Cloud &
AAI][elixir-cloud]. Follow the link to get in touch with us via chat or email.
Please mention the name of this service for any inquiry, proposal, question
etc. Alternatively, you can also make use of the [issue
tracker][drs-filer-issues] to request features or report bugs.

![Logo_banner][img-logo-banner]

[badge-build-status]:<https://travis-ci.com/github/elixir-cloud-aai/drs-filer.svg?branch=dev>
[badge-coverage]:<https://img.shields.io/coveralls/github/elixir-cloud-aai/drs-filer>
[badge-license]:<https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]:<https://travis-ci.com/elixir-cloud-aai/drs-filer>
[badge-url-coverage]:<https://coveralls.io/github/elixir-cloud-aai/drs-filer>
[badge-url-license]:<http://www.apache.org/licenses/LICENSE-2.0>
[elixir-cloud]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai>
[elixir-cloud-coc]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CODE_OF_CONDUCT.md>
[elixir-cloud-contributing]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CONTRIBUTING.md>
[ga4gh]: <https://ga4gh.org>
[ga4gh-cloud]: <https://www.ga4gh.org/work_stream/cloud/>
[ga4gh-service-info]: <https://github.com/ga4gh-discovery/ga4gh-service-info>
[ga4gh-drs]: <https://github.com/ga4gh/data-repository-service-schemas>
[ga4gh-drs-docs]: <https://ga4gh.github.io/tool-registry-service-schemas/>
[img-logo-banner]: images/logo-banner.svg
[license]: LICENSE
[license-apache]: <https://www.apache.org/licenses/LICENSE-2.0>
[res-connexion]: <https://github.com/zalando/connexion>
[res-docker]: <https://docs.docker.com/get-docker/>
[res-docker-compose]: <https://docs.docker.com/compose/install/>
[res-flask]: <https://flask.palletsprojects.com/>
[res-foca]: <https://github.com/elixir-cloud-aai/foca>
[res-git]: <https://git-scm.com/book/en/v2/Getting-Started-Installing-Git>
[res-helm]: <https://helm.sh/>
[res-http-methods]: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods>
[res-openapi]: <https://www.openapis.org/>
[res-semver]: <https://semver.org/>
[res-swagger-ui]: <https://swagger.io/tools/swagger-ui/>
[res-web-apis]: <https://developer.mozilla.org/en-US/docs/Learn/JavaScript/Client-side_web_APIs/Introduction>
[drs-filer-api]: drs_filer/api
[drs-filer-api-custom]: drs_filer/api/additional.data_repository_service.swagger.yaml
[drs-filer-compose-config]: docker-compose.yaml
[drs-filer-config]: drs_filer/config.yaml
[drs-filer-controllers]: drs_filer/ga4gh/drs/server.py
[drs-filer-controllers-subpackage]: drs_filer/ga4gh/drs/endpoints
[drs-filer-deployment]: deployment/README.md
[drs-filer-exceptions]: drs_filer/errors/exceptions.py
[drs-filer-issues]: <https://github.com/elixir-cloud-aai/drs-filer/issues>