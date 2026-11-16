# DRS-filer

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]
[![Coverage][badge-coverage]][badge-url-coverage]

## Synopsis

Microservice implementing the [Global Alliance for Genomics and
Health][org-ga4gh] (GA4GH) [Data Repository Service][res-ga4gh-drs] (DRS)
API specification.


## Description


## Usage

Once [deployed](#installation), the API is served here:

```console
http://localhost:8080/ga4gh/drs/v1/
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

_**That's it!**_

You should now be able to use/explore the API as described in the [usage
section](#usage).

The image (and thus Docker Compose and the Helm chart) serves the app with
[Gunicorn][res-gunicorn], as a non-root user (UID 1000, group 0). Its
settings are in [`drs_filer/gunicorn_config.py`][drs-filer-gunicorn-config];
override them with the environment variable `GUNICORN_CMD_ARGS`, e.g.,
`GUNICORN_CMD_ARGS="--workers 2"`. Behind a reverse proxy that sets
`X-Forwarded-*` headers, set `FORWARDED_ALLOW_IPS` to the proxy's addresses.
The shipped config ([`drs_filer/config.yaml`][drs-filer-config]) disables
Flask's debug mode; never enable it in a deployment, as the debugger allows
code execution for anyone who can reach an error page.

The image contains only the files listed in [`.dockerignore`][dockerignore]
(an allowlist); local secret files, such as `.env` files, are never copied
into it.

### Running locally for development

For development only, the app can be run with Flask's development server,
from the `drs_filer/` directory (the paths of the API specifications in the
config are relative to it), with a MongoDB instance reachable at the host
and port set in `db` of the config (e.g., `docker-compose up -d mongodb` and
`db.host: localhost`):

```bash
pip install -r requirements.txt
pip install -e .
cd drs_filer
python app.py
```

### Other useful commands

To shut down the service, run:

```bash
docker-compose down
```

If you need to inspect the logs, call:

```bash
docker-compose logs
```

## Contributing

This project is a community effort and lives off your contributions, be it in
the form of bug reports, feature requests, discussions, or fixes and other code
changes. Please refer to our organization's [contributing
guidelines][res-elixir-cloud-contributing] if you are interested to contribute.
Please mind the [code of conduct][res-elixir-cloud-coc] for all interactions
with the community.

## Versioning

The project adopts the [semantic versioning][res-semver] scheme for versioning.
Currently the service is in beta stage, so the API may change without further
notice.

## License

This project is covered by the [Apache License 2.0][license-apache] also
[shipped with this repository][license].

## Contact

The project is a collaborative effort under the umbrella of [ELIXIR Cloud &
AAI][org-elixir-cloud]. Follow the link to get in touch with us via chat or
email. Please mention the name of this service for any inquiry, proposal,
question etc.

[badge-build-status]:<https://travis-ci.com/elixir-cloud-aai/drs-filer.svg?branch=dev>
[badge-coverage]:<https://img.shields.io/coveralls/github/elixir-cloud-aai/drs-filer>
[badge-github-tag]:<https://img.shields.io/github/v/tag/elixir-cloud-aai/drs-filer?color=C39BD3>
[badge-license]:<https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]:<https://travis-ci.com/elixir-cloud-aai/drs-filer>
[badge-url-coverage]:<https://coveralls.io/github/elixir-cloud-aai/drs-filer>
[badge-url-github-tag]:<https://github.com/elixir-cloud-aai/drs-filer/releases>
[badge-url-license]:<http://www.apache.org/licenses/LICENSE-2.0>
[dockerignore]: .dockerignore
[drs-filer-config]: drs_filer/config.yaml
[drs-filer-gunicorn-config]: drs_filer/gunicorn_config.py
[license]: LICENSE
[license-apache]: <https://www.apache.org/licenses/LICENSE-2.0>
[org-elixir-cloud]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai>
[org-ga4gh]: <https://www.ga4gh.org/>
[res-elixir-cloud-coc]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CODE_OF_CONDUCT.md>
[res-elixir-cloud-contributing]: <https://github.com/elixir-cloud-aai/elixir-cloud-aai/blob/dev/CONTRIBUTING.md>
[res-gunicorn]: <https://gunicorn.org/>
[res-semver]: <https://semver.org/>
[res-ga4gh-drs]: https://github.com/ga4gh/data-repository-service-schemas
