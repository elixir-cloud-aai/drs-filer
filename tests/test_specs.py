"""Tests of the API specifications (`drs_filer/api/`).

Errors are answered with FOCA's problem details (RFC 9457); the `Error`
and `FieldError` definitions of the DRS specification describe them. They
are FOCA's `Problem` and `FieldError` schemas (`foca/api/problem-details.yaml`,
OpenAPI 3), translated to Swagger 2.0: references to `#/definitions/`, and
without `oneOf`, which Swagger 2.0 lacks (its description says it instead).
"""

from copy import deepcopy
from importlib.resources import files
from typing import Any

import pytest
import yaml

from tests.mock_data import DRS_SPEC, validate_error

API_DIR = DRS_SPEC.parent


def _definitions() -> dict[str, Any]:
    """Get the definitions of the DRS specification.

    Returns:
        Definitions by name.
    """
    definitions: dict[str, Any] = yaml.safe_load(DRS_SPEC.read_text())["definitions"]
    return definitions


def _foca_schemas() -> dict[str, Any]:
    """Get FOCA's problem details schemas, as Swagger 2.0 definitions.

    Returns:
        FOCA's `Problem` (as `Error`) and `FieldError`, with references to
        `#/definitions/` and without `oneOf`.
    """
    text = (files("foca") / "api" / "problem-details.yaml").read_text()
    text = text.replace("#/components/schemas/", "#/definitions/")
    schemas: dict[str, Any] = yaml.safe_load(text)["components"]["schemas"]
    field_error = deepcopy(schemas["FieldError"])
    assert "oneOf" in field_error
    del field_error["oneOf"]
    return {"Error": schemas["Problem"], "FieldError": field_error}


@pytest.mark.parametrize("name", ["Error", "FieldError"])
def test_error_definitions_are_foca_schemas(name: str) -> None:
    """`Error` and `FieldError` are FOCA's schemas, except the descriptions.

    `FieldError` says in its description that it has either `pointer` or
    `parameter` (FOCA's `oneOf`).
    """
    expected = _foca_schemas()[name]
    actual = _definitions()[name]
    assert {key: value for key, value in actual.items() if key != "description"} == {
        key: value for key, value in expected.items() if key != "description"
    }
    if name == "FieldError":
        assert "either `pointer` or `parameter`" in actual["description"]


def test_error_definitions_only_in_drs_spec() -> None:
    """Only the DRS specification defines the errors; the others refer to them.

    The specifications are merged by FOCA, so a second, different definition
    would replace the first.
    """
    for path in API_DIR.glob("*.yaml"):
        if path == DRS_SPEC:
            continue
        definitions = yaml.safe_load(path.read_text()).get("definitions", {})
        assert not {"Error", "FieldError"} & definitions.keys(), path


def test_validate_error() -> None:
    """Problem details validate; the old error bodies don't."""
    validate_error({"title": "Not found", "status": 404})
    validate_error(
        {
            "title": "Bad request",
            "status": 400,
            "code": "invalid-request",
            "errors": [{"detail": "Required", "code": "required", "pointer": "#/id"}],
        }
    )
    with pytest.raises(AssertionError):
        validate_error({"msg": "Not found", "status_code": 404})
    with pytest.raises(AssertionError):
        validate_error(
            {"title": "Bad request", "status": 400, "errors": [{"detail": "x"}]}
        )
