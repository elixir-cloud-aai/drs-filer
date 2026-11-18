"""Contract tests of the API specifications (`drs_filer/api/`).

The app serves the vendored GA4GH DRS 1.5.0 specification, unchanged, merged
with the app's additions (`additions.openapi.yaml`): its info, its local
deviations from the specification and its own endpoints. The registration
schemas of the additions (`*Register`) follow the read schemas of the
specification, without the fields that DRS-Filer sets itself; errors are
FOCA's problem details (RFC 9457).
"""

from hashlib import sha256
from importlib.resources import files
from typing import Any

import pytest
import yaml

from drs_filer.ga4gh.drs.endpoints.service_info import SERVICE_TYPE
from tests.mock_data import (
    ADDITIONS_SPEC,
    API_DIR,
    CONFIG_FILE,
    DRS_SPEC,
    load_yaml,
    validate_error,
)

# SHA-256 of `openapi.yaml` of `preview/release/drs-1.5.0/` on branch
# `gh-pages` of ga4gh/data-repository-service-schemas, the specification as
# published (bundled from tag `drs-1.5.0`, commit fe25c39)
DRS_SPEC_SHA256 = "eed6d83cb37b466efd46e3127767c4fca1898507e8a6cdf47c743f0f382ef96d"

# Registration schemas of the additions and the read schemas of the DRS
# specification they follow, with the fields of the read schemas that
# DRS-Filer sets itself and so are not registered
REGISTER_SCHEMAS: dict[str, tuple[str, set[str]]] = {
    "DrsObjectRegister": ("DrsObject", {"id", "self_uri"}),
    # `authorizations` describes how DRS-Filer authorizes requests for the
    # access URL, which registrants can't know
    "AccessMethodRegister": ("AccessMethod", {"access_id", "authorizations"}),
    "AccessURLRegister": ("AccessURL", set()),
    "ChecksumRegister": ("Checksum", set()),
    "ContentsObjectRegister": ("ContentsObject", set()),
    "ServiceRegister": ("Service", set()),
    "ServiceTypeRegister": ("ServiceType", set()),
}

# Operations of the DRS specification that DRS-Filer doesn't implement
# (`501 Not Implemented`): the passport `POST` variants of the reads, which
# need no credentials, so that every client gets the `501`, and the
# authorization info of objects (until #98)
PASSPORT_OPERATIONS = {
    "PostObject",
    "PostAccessURL",
    "GetBulkObjects",
    "GetBulkAccessURL",
}
NOT_IMPLEMENTED = PASSPORT_OPERATIONS | {"OptionsObject", "OptionsBulkObject"}

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


@pytest.fixture(scope="module")
def drs_spec() -> dict[str, Any]:
    """Get the vendored DRS specification.

    Returns:
        The specification.
    """
    return load_yaml(DRS_SPEC)


@pytest.fixture(scope="module")
def additions() -> dict[str, Any]:
    """Get the app's additions to the specification.

    Returns:
        The additions.
    """
    return load_yaml(ADDITIONS_SPEC)


def _operations(spec: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Get the paths and methods of the operations of a specification.

    Args:
        spec: OpenAPI specification.

    Returns:
        Path and method of each operation with an identifier, by identifier.
    """
    return {
        operation["operationId"]: (path, method)
        for path, path_item in spec["paths"].items()
        for method, operation in path_item.items()
        if method in METHODS and "operationId" in operation
    }


def _without_description(schema: dict[str, Any]) -> dict[str, Any]:
    """Get a schema without its description.

    Args:
        schema: Schema.

    Returns:
        The schema without its top-level `description`.
    """
    return {key: value for key, value in schema.items() if key != "description"}


def test_drs_spec_vendored_unchanged() -> None:
    """The vendored DRS specification is the published one, unchanged."""
    assert sha256(DRS_SPEC.read_bytes()).hexdigest() == DRS_SPEC_SHA256


def test_only_drs_1_5_0_spec_vendored() -> None:
    """DRS 1.5.0 and the additions are the only specifications, in this order.

    The Swagger 2.0 specifications of DRS 1.1.0 and of the service info are
    gone; the DRS bundle has the service info schemas.
    """
    assert sorted(path.name for path in API_DIR.glob("*.yaml")) == sorted(
        [DRS_SPEC.name, ADDITIONS_SPEC.name]
    )
    spec_config = load_yaml(CONFIG_FILE)["api"]["specs"]["drs"]
    assert spec_config["path"] == [
        f"api/{DRS_SPEC.name}",
        f"api/{ADDITIONS_SPEC.name}",
    ]


def test_drs_spec_version(drs_spec: dict[str, Any], additions: dict[str, Any]) -> None:
    """The specification is DRS 1.5.0, and the service info says so."""
    assert drs_spec["openapi"].startswith("3.")
    assert drs_spec["info"]["version"] == "1.5.0"
    assert "version" not in additions["info"]
    assert {
        "group": "org.ga4gh",
        "artifact": "drs",
        "version": drs_spec["info"]["version"],
    } == SERVICE_TYPE
    service_type = load_yaml(CONFIG_FILE)["service_info"]["service"]["type"]
    assert service_type == SERVICE_TYPE


def test_additions_keep_spec_operations(
    drs_spec: dict[str, Any], additions: dict[str, Any]
) -> None:
    """The additions don't rename operations of the specification.

    The operations of DRS-Filer have identifiers that the specification
    doesn't use (e.g., registration is `RegisterObject`, not `PostObject`).
    """
    spec_operations = _operations(drs_spec)
    for path, path_item in additions["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            if method in drs_spec["paths"].get(path, {}):
                assert "operationId" not in operation, (path, method)
            else:
                assert operation["operationId"] not in spec_operations, (path, method)


def test_registration_path(drs_spec: dict[str, Any], additions: dict[str, Any]) -> None:
    """Objects are registered at `POST /objects/register`.

    `POST /objects` is the bulk read of the specification.
    """
    register = additions["paths"]["/objects/register"]["post"]
    assert register["operationId"] == "RegisterObject"
    assert drs_spec["paths"]["/objects"]["post"]["operationId"] == "GetBulkObjects"


def test_not_implemented_operations(
    drs_spec: dict[str, Any], additions: dict[str, Any]
) -> None:
    """Operations that DRS-Filer doesn't implement document their `501`."""
    operations = _operations(drs_spec)
    for operation_id in NOT_IMPLEMENTED:
        path, method = operations[operation_id]
        operation = additions["paths"][path][method]
        assert operation["responses"]["501"] == {
            "$ref": "#/components/responses/501NotImplemented"
        }, operation_id
        if operation_id in PASSPORT_OPERATIONS:
            assert operation["security"] == [], operation_id


@pytest.mark.parametrize("name", sorted(REGISTER_SCHEMAS))
def test_register_schema_follows_spec(
    name: str, drs_spec: dict[str, Any], additions: dict[str, Any]
) -> None:
    """Registration schemas have the fields of the read schemas.

    Without the fields that DRS-Filer sets, with the same types, formats,
    enumerations, items and required fields, and no other fields.
    """
    read_name, server_fields = REGISTER_SCHEMAS[name]
    read = drs_spec["components"]["schemas"][read_name]
    register = additions["components"]["schemas"][name]
    assert register["additionalProperties"] is False
    expected = set(read["properties"]) - server_fields
    assert set(register["properties"]) == expected
    assert set(register["required"]) == set(read.get("required", [])) - server_fields
    for field in expected:
        read_field = read["properties"][field]
        register_field = register["properties"][field]
        for key in ("type", "format"):
            assert register_field.get(key) == read_field.get(key), (field, key)
        # `ServiceTypeRegister` restricts `artifact` to `drs`
        # (`test_service_type_register_is_drs`)
        if "enum" in read_field:
            assert register_field["enum"] == read_field["enum"], field
        refs = [read_field, read_field.get("items", {}), *read_field.get("allOf", [])]
        read_ref = next((ref["$ref"] for ref in refs if "$ref" in ref), None)
        if read_ref is not None:
            register_ref = register_field.get("$ref") or register_field["items"]["$ref"]
            assert register_ref == f"{read_ref}Register", field
        elif "items" in read_field:
            assert register_field["items"] == read_field["items"], field


def _object_schemas(schema: Any, where: str) -> list[tuple[str, dict[str, Any]]]:
    """Find the object schemas (with `properties`) in a schema, nested too.

    Args:
        schema: A schema or part of one.
        where: Where `schema` is, for messages.

    Returns:
        The object schemas, with where they are.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(schema, dict):
        if "properties" in schema:
            found.append((where, schema))
        for key, value in schema.items():
            found.extend(_object_schemas(value, f"{where}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            found.extend(_object_schemas(value, f"{where}[{index}]"))
    return found


def test_register_schemas_closed(additions: dict[str, Any]) -> None:
    """Request bodies of DRS-Filer's endpoints reject undefined fields.

    Each object schema of the registration and service info schemas, nested
    ones too (e.g., `organization`), sets `additionalProperties: false`.
    """
    schemas = additions["components"]["schemas"]
    found = [
        item
        for name, schema in schemas.items()
        if name.endswith("Register")
        for item in _object_schemas(schema, name)
    ]
    assert any(where == "ServiceRegister.properties.organization" for where, _ in found)
    for where, schema in found:
        assert schema.get("additionalProperties") is False, where


def test_service_type_register_is_drs(additions: dict[str, Any]) -> None:
    """Posted service info must be of the type of the served API.

    `GetServiceInfo` serves `DrsService`, whose `type.artifact` is `drs`;
    the group and version are those of the served specification.
    """
    schemas = additions["components"]["schemas"]
    properties = schemas["ServiceTypeRegister"]["properties"]
    assert {key: value["enum"] for key, value in properties.items()} == {
        key: [value] for key, value in SERVICE_TYPE.items()
    }


def _foca_schemas() -> dict[str, Any]:
    """Get FOCA's problem details schemas.

    Returns:
        FOCA's `Problem` and `FieldError`, by name.
    """
    text = (files("foca") / "api" / "problem-details.yaml").read_text()
    schemas: dict[str, Any] = yaml.safe_load(text)["components"]["schemas"]
    return schemas


@pytest.mark.parametrize("name", ["Problem", "FieldError"])
def test_error_schemas_are_foca_schemas(name: str, additions: dict[str, Any]) -> None:
    """`Problem` and `FieldError` are FOCA's schemas, except the descriptions."""
    actual = additions["components"]["schemas"][name]
    expected = _foca_schemas()[name]
    assert _without_description(actual) == _without_description(expected)


def test_error_responses_are_problems(
    drs_spec: dict[str, Any], additions: dict[str, Any]
) -> None:
    """All error responses of the specification are problem details.

    The additions replace the `Error` schema (`msg`, `status_code`) of each
    error response of the specification with `Problem`, and add the media
    type that FOCA sends (`application/problem+json`); the specification's
    `application/json` can't be removed (merged). The error responses that
    only the additions define declare `application/problem+json` only.
    """
    problem = {"schema": {"$ref": "#/components/schemas/Problem"}}
    errors = {
        name
        for name, response in drs_spec["components"]["responses"].items()
        if response.get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
        == "#/components/schemas/Error"
    }
    assert errors
    replaced = additions["components"]["responses"]
    for name in errors:
        assert replaced[name]["content"] == {
            "application/json": problem,
            "application/problem+json": problem,
        }, name
    for name in replaced.keys() - drs_spec["components"]["responses"].keys():
        assert replaced[name]["content"] == {"application/problem+json": problem}, name
    for path, operations in additions["paths"].items():
        for method, operation in operations.items():
            for code, response in operation.get("responses", {}).items():
                if "content" in response and code.startswith(("4", "5")):
                    assert response["content"] == {
                        "application/problem+json": problem
                    }, (path, method, code)


def test_validate_error() -> None:
    """Problem details validate; the error bodies of DRS don't."""
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
