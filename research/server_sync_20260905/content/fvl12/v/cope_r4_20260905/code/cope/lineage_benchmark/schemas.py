"""Static, event-independent model-output schemas for both methods."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from .models import PATCH_SCHEMA, STATE_SCHEMA, VALID_KINDS, VALID_MODES
from .operations import IDENTIFIER, OPERATIONS, object_schema, validate_schema_value


_MODE = {"type": "string", "enum": sorted(VALID_MODES)}
_LINEAGE = object_schema({
    "parent_id": {"anyOf": [IDENTIFIER, {"type": "null"}]},
    "root_id": IDENTIFIER,
    "depth": {"type": "integer", "minimum": 0},
    "child_ids": {"type": "array", "items": IDENTIFIER},
})
_HISTORY_ENTRY = object_schema({
    "seq": {"type": "integer", "minimum": 1},
    "event_id": IDENTIFIER,
    "operation": {"type": "string"},
    "mode_before": {"anyOf": [_MODE, {"type": "null"}]},
    "mode_after": _MODE,
    "detail": {"type": "string"},
})
_SLOT = object_schema({
    "slot_id": IDENTIFIER,
    "logical_id": IDENTIFIER,
    "kind": {"type": "string", "enum": sorted(VALID_KINDS)},
    "mode": _MODE,
    "priority": {"type": "string", "enum": ["hard", "soft"]},
    "grounding": {"type": "string"},
    "payload": {"type": "object", "additionalProperties": True},
    "lineage": _LINEAGE,
    "history": {"type": "array", "items": _HISTORY_ENTRY},
})

COPE_PATCH_SCHEMA = object_schema({
    "schema_version": {"type": "string", "enum": [PATCH_SCHEMA]},
    "event_id": IDENTIFIER,
    "base_revision": {"type": "integer", "minimum": 0},
    "ops": {
        "type": "array", "minItems": 1, "maxItems": 1,
        "items": {"anyOf": [definition.schema() for definition in OPERATIONS.values()]},
    },
})
FSRPC_STATE_SCHEMA = object_schema({
    "schema_version": {"type": "string", "enum": [STATE_SCHEMA]},
    "revision": {"type": "integer", "minimum": 0},
    "slots": {"type": "array", "items": _SLOT},
})


def _strict_schema(method: str) -> Dict[str, Any]:
    if method == "CoPE":
        return deepcopy(COPE_PATCH_SCHEMA)
    if method == "FSR-PC":
        return deepcopy(FSRPC_STATE_SCHEMA)
    raise ValueError(f"unknown method {method!r}")


def output_schema(method: str) -> Dict[str, Any]:
    """Static vLLM 0.8.5-compatible grammar, without answer-specific narrowing.

    vLLM's xgrammar compatibility guard rejects length/item bounds even when the
    installed xgrammar version can compile them. Project these bounds out of
    the shared schema for decoding, and enforce them locally after decoding.
    Types, field requirements, and operation enums are preserved unchanged.
    """
    unsupported = {"minLength", "maxLength", "minItems", "maxItems"}

    def project(value):
        if isinstance(value, dict):
            return {key: project(item) for key, item in value.items() if key not in unsupported}
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    return project(_strict_schema(method))


def validate_output_document(method: str, document: Mapping[str, Any]) -> None:
    validate_schema_value(document, _strict_schema(method))
