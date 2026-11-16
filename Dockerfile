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

## Install dependencies (including Gunicorn) and app; FOCA writes the modified
## API specifications into `drs_filer/api/` at startup, so the app's user
## (1000, group 0 for arbitrary user IDs, e.g., on OpenShift) may write there
RUN cd /app \
  && pip install --no-cache-dir -r requirements.txt yq \
  && python setup.py develop \
  && cd / \
  && chown -R 1000:0 /app/drs_filer/api/ \
  && chmod -R g+w /app/drs_filer/api/

## Run as non-root user
USER 1000:0

## The API specifications in the config are relative to the working directory
WORKDIR /app/drs_filer

## Serve with Gunicorn (settings in `drs_filer/gunicorn_config.py`; override
## them via `GUNICORN_CMD_ARGS`, e.g., `--workers 2`). For development,
## `python app.py` runs Flask's development server instead
CMD ["gunicorn", "--config", "python:drs_filer.gunicorn_config", \
  "drs_filer.app:create_app()"]
