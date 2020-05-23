import os

from foca.config.config_parser import get_conf
from drs_filer.config.app_config import parse_app_config

# Source the WES config for defaults
flask_config = parse_app_config(config_var='DRS_CONFIG')

# # Gunicorn number of workers and threads
workers = int(os.environ.get('GUNICORN_PROCESSES', '1'))
threads = int(os.environ.get('GUNICORN_THREADS', '1'))

forwarded_allow_ips = '*'

# Gunicorn bind address
bind = '{address}:{port}'.format(
    address=get_conf(flask_config, 'server', 'host'),
    port=get_conf(flask_config, 'server', 'port'),
)

# Source the environment variables for the Gunicorn workers
raw_env = [
    "DRS_CONFIG=%s" % os.environ.get('DRS_CONFIG', ''),
    "MONGO_HOST=%s" % os.environ.get(
        'MONGO_HOST', get_conf(flask_config, 'database', 'host')),
    "MONGO_PORT=%s" % os.environ.get(
        'MONGO_PORT', get_conf(flask_config, 'database', 'port')),
    "MONGO_DBNAME=%s" % os.environ.get(
        'MONGO_DBNAME', get_conf(flask_config, 'database', 'name')),
    "MONGO_USERNAME=%s" % os.environ.get('MONGO_USERNAME', ''),
    "MONGO_PASSWORD=%s" % os.environ.get('MONGO_PASSWORD', '')
]
