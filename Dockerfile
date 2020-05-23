##### BASE IMAGE #####
FROM python:3.6-slim-stretch

##### METADATA ##### 
LABEL base.image="python:3.6-slim-stretch"
LABEL software="drs-filer"
LABEL software.version="0.1.0"
LABEL software.description="Lightweight, flexible Flask/Gunicorn-based GA4GH DRS implementation"
LABEL software.website="https://github.com/elixir-cloud-aai/drs-filer"
LABEL software.documentation="https://github.com/elixir-cloud-aai/drs-filer"
LABEL software.license="https://github.com/elixir-cloud-aai/drs-filer/blob/master/LICENSE"
LABEL software.tags="General"
LABEL maintainer="sarthakgupta072@gmail.com"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"
LABEL maintainer.license="https://spdx.org/licenses/Apache-2.0"

# Python UserID workaround for OpenShift/K8S
ENV LOGNAME=ipython
ENV USER=ipython
ENV HOME=/tmp/user

# Install general dependencies
RUN apt-get update && apt-get install -y nodejs openssl git build-essential python3-dev curl jq

## Set working directory
WORKDIR /app

## Copy Python requirements
COPY ./requirements.txt /app/requirements.txt

## Install Python dependencies
RUN cd /app \
  && pip install -r requirements.txt \
  && cd /

## Copy remaining app files
COPY ./ /app

## Install app
RUN cd /app \
  && python setup.py develop \
  && cd / \
  && chmod g+w /app/drs_filer/api/