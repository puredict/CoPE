"""Single source for model-visible typed operations and their syntax.

This module describes syntax only. It never receives an evaluation event or
oracle answer; choosing an operation and its target remains model work.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping


def object_schema(properties: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object", "properties": deepcopy(dict(properties)),
        "required": list(properties), "additionalProperties": False,
    }


IDENTIFIER = {"type": "string", "minLength": 1}
NEW_SLOT_SCHEMA = object_schema({
    "slot_id": IDENTIFIER,
    "logical_id": IDENTIFIER,
    "grounding": {"type": "string"},
    "priority": {"type": "string", "enum": ["hard", "soft"]},
    "payload": {"type": "object", "additionalProperties": True},
})


@dataclass(frozen=True)
class OperationDefinition:
    event_kind: str
    name: str
    arguments: Mapping[str, Any]

    def schema(self) -> Dict[str, Any]:
        return object_schema({
            "op": {"type": "string", "enum": [self.name]},
            **self.arguments,
        })


OPERATIONS = {
    definition.name: definition for definition in (
        OperationDefinition("suspend_current", "suspend", {"slot_id": IDENTIFIER}),
        OperationDefinition("restore_current", "restore", {"slot_id": IDENTIFIER}),
        OperationDefinition("override_current", "override", {
            "slot_id": IDENTIFIER, "new_slot": NEW_SLOT_SCHEMA,
        }),
        OperationDefinition("restore_root", "restore_root", {"from_slot_id": IDENTIFIER}),
    )
}
EVENT_TO_OPERATION = {
    definition.event_kind: definition.name for definition in OPERATIONS.values()
}


def validate_schema_value(value: Any, schema: Mapping[str, Any], path: str = "$" ) -> None:
    """Validate the small JSON Schema subset used in this benchmark.

    The exact same schemas are sent to vLLM. This is intentionally not a general
    JSON Schema implementation: schemas here use no refs or conditional logic.
    """
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                validate_schema_value(value, branch, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: does not match any allowed schema branch")
    expected = schema.get("type")
    checks = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "null": lambda: value is None,
    }
    if expected is not None and not checks[expected]():
        raise ValueError(f"{path}: must be {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid enum value {value!r}")
    if expected == "integer" and value < schema.get("minimum", value):
        raise ValueError(f"{path}: below minimum")
    if expected == "string" and len(value) < schema.get("minLength", 0):
        raise ValueError(f"{path}: empty identifier")
    if expected == "object":
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise ValueError(f"{path}: missing fields {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                raise ValueError(f"{path}: extra fields {sorted(extra)}")
        for key in value.keys() & props.keys():
            validate_schema_value(value[key], props[key], f"{path}.{key}")
    if expected == "array":
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path}: too many items")
        for index, item in enumerate(value):
            validate_schema_value(item, schema.get("items", {}), f"{path}[{index}]")


def validate_operation(operation: Mapping[str, Any]) -> None:
    if not isinstance(operation, Mapping):
        raise ValueError("patch operation must be an object")
    name = operation.get("op")
    if not isinstance(name, str) or name not in OPERATIONS:
        raise ValueError(f"unsupported patch operation {name!r}")
    validate_schema_value(dict(operation), OPERATIONS[name].schema(), "operation")
