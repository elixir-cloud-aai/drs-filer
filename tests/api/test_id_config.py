"""App tests of the identifier settings (`custom.*.id`).

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
from tests.mock_data import API, body, drs_object, error_messages


def _write_ids(overlay: Path, objects: dict[str, Any], access: dict[str, Any]) -> None:
    """Write identifier settings to the overlay.

    Args:
        overlay: Config overlay of the test.
        objects: Settings of object identifiers (`custom.objects.id`).
        access: Settings of access identifiers (`custom.access_methods.id`).
    """
    overlay.write_text(
        yaml.safe_dump(
            {
                "custom": {
                    "objects": {"id": objects},
                    "access_methods": {"id": access},
                }
            }
        )
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
        objects={"charset": "ab", "length": 12},
        # Long enough that the two access identifiers practically never
        # collide (a duplicate one is left unset)
        access={"charset": "xyz", "length": 40},
    )
    client = create_app().app.test_client()
    response = client.post(f"{API}/objects/register", json=drs_object(2))
    assert response.status_code == 200, body(response)
    object_id = body(response)
    assert len(object_id) == 12
    assert set(object_id) <= set("ab")
    obj = body(client.get(f"{API}/objects/{object_id}"))
    assert len(obj["access_methods"]) == 2
    for method in obj["access_methods"]:
        assert len(method["access_id"]) == 40
        assert set(method["access_id"]) <= set("xyz")


@pytest.mark.parametrize("section", ["objects", "access_methods"])
@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("charset", 'string.ascii_letters + string.digits + ".-_~"'),
        ("charset", "string.digits"),
        ("charset", "'0123456789abcdef'"),
        ("charset", "ab/"),
        ("charset", "a b"),
        ("charset", ""),
        ("charset", 123),
        ("length", 0),
        ("length", "six"),
        ("length", True),
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

    The error names the invalid setting (not the value).

    Args:
        mongo_client: MongoDB client of the app.
        overlay: Config overlay of the test.
        section: Section of the identifier settings.
        setting: Name of the invalid setting.
        value: Invalid value.
    """
    valid = {"charset": "abc", "length": 6}
    settings = {"objects": dict(valid), "access_methods": dict(valid)}
    settings[section][setting] = value
    _write_ids(overlay, settings["objects"], settings["access_methods"])
    with pytest.raises(ValueError, match="custom configuration") as info:
        create_app()
    assert f"{section}.id.{setting}" in error_messages(info.value)


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
        "objects": {"charset": "abc", "length": 6},
        "access_methods": {"charset": "abc", "length": 6},
    }
    settings[section]["charset"] = expression
    _write_ids(overlay, settings["objects"], settings["access_methods"])
    with pytest.raises(ValueError, match="custom configuration") as info:
        create_app()
    assert f"{section}.id.charset" in error_messages(info.value)
    assert not marker.exists()
