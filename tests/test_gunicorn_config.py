"""Tests of the Gunicorn settings of the image."""

from pathlib import Path

from drs_filer import gunicorn_config


def test_bind():
    """Gunicorn serves the app on the port the chart and Compose expect."""
    assert gunicorn_config.bind == ["0.0.0.0:8080"]


def test_worker_tmp_dir_writable(tmp_path: Path):
    """A writable memory-backed directory is used for heartbeat files.

    Args:
        tmp_path: Temporary directory, standing in for `/dev/shm`.
    """
    assert gunicorn_config._worker_tmp_dir(shm=tmp_path) == str(tmp_path)


def test_worker_tmp_dir_missing(tmp_path: Path):
    """Gunicorn's default is used if there is no memory-backed directory.

    Args:
        tmp_path: Temporary directory, holding no `/dev/shm` stand-in.
    """
    assert gunicorn_config._worker_tmp_dir(shm=tmp_path / "missing") is None
