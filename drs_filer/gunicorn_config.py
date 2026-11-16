"""Gunicorn settings of the image (production WSGI server).

The image runs ``gunicorn --config python:drs_filer.gunicorn_config
'drs_filer.app:create_app()'``. Override the settings via
``GUNICORN_CMD_ARGS`` (e.g., ``--workers 2 --threads 8``), which takes
precedence over this module (cf.
https://docs.gunicorn.org/en/stable/settings.html).

The app is not preloaded (no ``preload_app``): each worker creates it after
forking, as MongoDB clients must not be shared across forks.

Forwarded headers (``X-Forwarded-*``) are trusted from Gunicorn's default
(``127.0.0.1``, or ``FORWARDED_ALLOW_IPS``) only, not from any client; behind
a proxy that sets them, set ``FORWARDED_ALLOW_IPS`` to its addresses.
"""

import os
from pathlib import Path
from typing import Optional

# Address of the app; the Helm chart's Service and Docker Compose expect port
# 8080 (the app config's `server` settings apply to the development server
# only)
bind = ["0.0.0.0:8080"]

# One process with a few threads, as each worker loads the whole app
worker_class = "gthread"
workers = 1
threads = 4

# Workers whose main loop does not report to Gunicorn for `timeout` seconds
# are killed and restarted; on shutdown (e.g., SIGTERM from Kubernetes),
# workers get `graceful_timeout` seconds to finish requests, i.e., less than
# the termination grace period of the pod (30 seconds)
timeout = 30
graceful_timeout = 20
# Idle keep-alive connections are closed after this many seconds; longer than
# the keep-alive timeout of proxies in front of the app (60 seconds for
# ingress-nginx, 90 seconds for Traefik), so that a proxy does not reuse a
# connection just as it is closed (failing the request with `502`)
keepalive = 100

# Error log to stderr, as for the app's logs; no access log (enable it with
# `--access-logfile -`)
accesslog = None
errorlog = "-"


def _worker_tmp_dir(shm: Path = Path("/dev/shm")) -> Optional[str]:
    """Get the directory for the heartbeat files of workers.

    The files are updated on each heartbeat, so a memory-backed directory
    (``/dev/shm``) is preferred; otherwise, the default temporary directory
    (``TMPDIR``, or ``/tmp``) is used.

    Args:
        shm: Memory-backed directory.

    Returns:
        ``shm`` if it is a writable directory, else ``None`` (Gunicorn's
        default).
    """
    if shm.is_dir() and os.access(shm, os.W_OK | os.X_OK):
        return str(shm)
    return None


worker_tmp_dir = _worker_tmp_dir()
