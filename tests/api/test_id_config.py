"""App tests of the identifier settings (`endpoints.*.id_charset`).

Identifiers of objects and access methods are drawn from the configured
characters themselves, which must be unreserved characters of URLs;
expressions, which earlier versions evaluated, fail the start of the app.
"""

from pathlib import Path
from typing import Any

from pymongo import MongoClient
import pytest
import yaml

from drs_filer.app import create_app
from tests.mock_data import API, body, drs_object


def _write_ids(overlay: Path, objects: dict[str, Any], access: dict[str, Any]) -> None:
    """Write identifier settings to the overlay.

    Args:
        overlay: Config overlay of the test.
        objects: Settings of object identifiers (`endpoints.objects`).
        access: Settings of access identifiers (`endpoints.access_methods`).
    """
    overlay.write_text(
        yaml.safe_dump({"endpoints": {"objects": objects, "access_methods": access}})
    )


def test_literal_charsets(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Identifiers consist of the configured characters, of the set length.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
    """
    _write_ids(
        overlay,
        objects={"id_charset": "ab", "id_length": 12},
        access={"id_charset": "xyz", "id_length": 8},
    )
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects", json=drs_object(2))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    assert len(object_id) == 12
    assert set(object_id) <= set("ab")
    obj = body(client.get(f"{API}/objects/{object_id}"))
    for method in obj["access_methods"]:
        assert len(method["access_id"]) == 8
        assert set(method["access_id"]) <= set("xyz")


@pytest.mark.parametrize("section", ["objects", "access_methods"])
@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("id_charset", 'string.ascii_letters + string.digits + ".-_~"'),
        ("id_charset", "string.digits"),
        ("id_charset", "'0123456789abcdef'"),
        ("id_charset", "ab/"),
        ("id_charset", "a b"),
        ("id_charset", ""),
        ("id_charset", 123),
        ("id_length", 0),
        ("id_length", "6"),
        ("id_length", True),
    ],
)
def test_invalid_settings_fail_start(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    section: str,
    setting: str,
    value: Any,
) -> None:
    """Expressions and other invalid settings fail the start of the app.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        section: Section of the identifier settings.
        setting: Name of the invalid setting.
        value: Invalid value.
    """
    valid = {"id_charset": "abc", "id_length": 6}
    settings = {"objects": dict(valid), "access_methods": dict(valid)}
    settings[section][setting] = value
    _write_ids(overlay, settings["objects"], settings["access_methods"])
    with pytest.raises(ValueError, match=rf"endpoints\.{section}"):
        create_app()


@pytest.mark.parametrize("section", ["objects", "access_methods"])
def test_expression_not_evaluated(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    tmp_path: Path,
    section: str,
) -> None:
    """Other expressions fail the start, too, and are never evaluated.

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        tmp_path: Directory that an evaluated expression would write to.
        section: Section of the identifier settings with the expression.
    """
    marker = tmp_path / "evaluated"
    expression = f"open({str(marker)!r}, 'w').close() or 'ab'"
    settings = {
        "objects": {"id_charset": "abc", "id_length": 6},
        "access_methods": {"id_charset": "abc", "id_length": 6},
    }
    settings[section]["id_charset"] = expression
    _write_ids(overlay, settings["objects"], settings["access_methods"])
    with pytest.raises(ValueError, match="not unreserved characters"):
        create_app()
    assert not marker.exists()
