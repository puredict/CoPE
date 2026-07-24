from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from cope import ConstraintState, serialize_state


ROOT = Path(__file__).resolve().parents[2]
STATE_SCHEMA_PATH = ROOT / "schemas" / "cope-state-v1.schema.json"
TRACE_SCHEMA_PATH = ROOT / "schemas" / "cope-trace-v1.schema.json"
VALID_TRACE_PATH = ROOT / "tests" / "fixtures" / "cope" / "minimal_valid_trace.json"
INVALID_TRACE_PATH = ROOT / "tests" / "fixtures" / "cope" / "invalid_trace.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator() -> jsonschema.Draft202012Validator:
    state_schema = _load(STATE_SCHEMA_PATH)
    trace_schema = _load(TRACE_SCHEMA_PATH)
    registry = Registry().with_resource(
        state_schema["$id"],
        Resource.from_contents(state_schema),
    )
    registry = registry.with_resource(
        "https://github.com/puredict/CoPE/schemas/cope-state-v1.schema.json",
        Resource.from_contents(state_schema),
    )
    return jsonschema.Draft202012Validator(trace_schema, registry=registry)


def test_machine_readable_schemas_are_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(_load(STATE_SCHEMA_PATH))
    jsonschema.Draft202012Validator.check_schema(_load(TRACE_SCHEMA_PATH))


def test_serialized_empty_state_conforms_to_state_schema() -> None:
    jsonschema.Draft202012Validator(_load(STATE_SCHEMA_PATH)).validate(
        serialize_state(ConstraintState.empty("schema-fixture"))
    )


def test_minimal_trace_fixture_is_valid() -> None:
    _validator().validate(_load(VALID_TRACE_PATH))


def test_invalid_trace_fixture_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_load(INVALID_TRACE_PATH))
