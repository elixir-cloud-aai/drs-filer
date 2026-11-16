##### BASE IMAGE #####
FROM elixircloud/foca:20240520-py3.12


##### METADATA #####

LABEL software="DRS-filer"
LABEL software.description="Flask Connexion implementation of Data Repository Schema"
LABEL software.website="https://github.com/elixir-cloud-aai/drs-filer"
LABEL software.license="https://spdx.org/licenses/Apache-2.0"
LABEL maintainer="sarthakgupta072@gmail.com"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"


## Copy app files (only those listed in `.dockerignore`)
COPY ./ /app

## Install dependencies (including Gunicorn) and app; the app files stay owned
## by root and read-only for the app's user (whatever the umask of the build
## host), so that the app cannot change its own code or config; the code is
## compiled here, as the app's user cannot write bytecode caches
RUN cd /app \
  && pip install --no-cache-dir -r requirements.txt yq \
  && python setup.py develop \
  && python -m compileall -q /app/drs_filer \
  && cd / \
  && chmod -R go-w /app

## Run as non-root user (group 0, as for arbitrary user IDs, e.g., on
## OpenShift)
USER 1000:0

## The API specifications in the config are relative to the working directory
WORKDIR /app/drs_filer

## Serve with Gunicorn (settings in `drs_filer/gunicorn_config.py`; override
## them via `GUNICORN_CMD_ARGS`, e.g., `--workers 2`). For development,
## `python app.py` runs Flask's development server instead
CMD ["gunicorn", "--config", "python:drs_filer.gunicorn_config", \
  "drs_filer.app:create_app()"]
