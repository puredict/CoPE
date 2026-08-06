from __future__ import annotations

import copy

import pytest

from cope import ConstraintSlot, ConstraintState, SchemaError, deserialize_patch, deserialize_state, serialize_state
from cope.errors import (
    INVALID_ENUM,
    SCHEMA_MISSING_FIELD,
    SCHEMA_UNKNOWN_FIELD,
    SCHEMA_VERSION_UNSUPPORTED,
    UNKNOWN_OPERATION,
)


def _patch_payload(operation: dict) -> dict:
    return {
        "patch_id": "p",
        "event_id": "e",
        "reason": "test",
        "operations": [operation],
        "generator": "test",
        "input_state_hash": "hash",
        "created_at": 1,
        "metadata": {},
    }


def test_unknown_operation_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        deserialize_patch(_patch_payload({"operation_type": "delete", "operation_id": "op"}))
    assert caught.value.code == UNKNOWN_OPERATION


def test_missing_operation_field_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        deserialize_patch(_patch_payload({"operation_type": "suspend", "operation_id": "op", "slot_id": "s"}))
    assert caught.value.code == SCHEMA_MISSING_FIELD


def test_illegal_mode_and_source_enums_are_rejected() -> None:
    common = dict(
        slot_id="s",
        constraint_type="test",
        content={"kind": "structured"},
        priority=1,
        created_event_id="e",
        last_updated_event_id="e",
        lineage=("s",),
    )
    with pytest.raises(SchemaError) as mode_error:
        ConstraintSlot(source="task", mode="deleted", **common)
    assert mode_error.value.code == INVALID_ENUM
    with pytest.raises(SchemaError) as source_error:
        ConstraintSlot(source="anonymous", mode="active", **common)
    assert source_error.value.code == INVALID_ENUM


def test_unknown_state_field_and_unsupported_version_are_rejected() -> None:
    payload = serialize_state(ConstraintState.empty("schema"))
    with_unknown = copy.deepcopy(payload)
    with_unknown["surprise"] = True
    with pytest.raises(SchemaError) as unknown:
        deserialize_state(with_unknown)
    assert unknown.value.code == SCHEMA_UNKNOWN_FIELD

    wrong_version = copy.deepcopy(payload)
    wrong_version["schema_version"] = "99.0"
    with pytest.raises(SchemaError) as version:
        deserialize_state(wrong_version)
    assert version.value.code == SCHEMA_VERSION_UNSUPPORTED
