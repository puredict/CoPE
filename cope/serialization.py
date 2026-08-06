from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Mapping, Sequence

from .errors import (
    HASH_MISMATCH,
    SCHEMA_MISSING_FIELD,
    SCHEMA_UNKNOWN_FIELD,
    SCHEMA_VERSION_UNSUPPORTED,
    STATE_INVALID,
    UNKNOWN_OPERATION,
    InvariantError,
    SchemaError,
)
from .schema import (
    SCHEMA_VERSION,
    AppliedPatch,
    ConstraintSlot,
    ConstraintState,
    Demote,
    EventRecord,
    Expire,
    Insert,
    Operation,
    Override,
    Patch,
    PatchContext,
    Restore,
    Revalidate,
    Suspend,
    ValidationRecord,
)


def thaw_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_json(item) for item in value]
    return value


def _object(
    value: Any,
    *,
    path: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(STATE_INVALID, f"{path} must be an object", path=path)
    optional = optional or set()
    keys = set(value)
    missing = required - keys
    if missing:
        raise SchemaError(
            SCHEMA_MISSING_FIELD,
            f"{path} is missing required fields {sorted(missing)}",
            path=path,
            fields=sorted(missing),
        )
    unknown = keys - required - optional
    if unknown:
        raise SchemaError(
            SCHEMA_UNKNOWN_FIELD,
            f"{path} has unknown fields {sorted(unknown)}",
            path=path,
            fields=sorted(unknown),
        )
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise SchemaError(STATE_INVALID, f"{path} must be an array", path=path)
    return value


def serialize_slot(slot: ConstraintSlot) -> dict[str, Any]:
    return {
        "slot_id": slot.slot_id,
        "constraint_type": slot.constraint_type,
        "content": thaw_json(slot.content),
        "source": slot.source.value,
        "mode": slot.mode.value,
        "priority": slot.priority,
        "created_event_id": slot.created_event_id,
        "last_updated_event_id": slot.last_updated_event_id,
        "parent_slot_id": slot.parent_slot_id,
        "overrides_slot_ids": list(slot.overrides_slot_ids),
        "lineage": list(slot.lineage),
        "evidence_refs": list(slot.evidence_refs),
        "metadata": thaw_json(slot.metadata),
    }


def deserialize_slot(payload: Mapping[str, Any], *, path: str = "$.slot") -> ConstraintSlot:
    item = _object(
        payload,
        path=path,
        required={
            "slot_id",
            "constraint_type",
            "content",
            "source",
            "mode",
            "priority",
            "created_event_id",
            "last_updated_event_id",
            "parent_slot_id",
            "overrides_slot_ids",
            "lineage",
            "evidence_refs",
            "metadata",
        },
    )
    return ConstraintSlot(
        slot_id=item["slot_id"],
        constraint_type=item["constraint_type"],
        content=item["content"],
        source=item["source"],
        mode=item["mode"],
        priority=item["priority"],
        created_event_id=item["created_event_id"],
        last_updated_event_id=item["last_updated_event_id"],
        parent_slot_id=item["parent_slot_id"],
        overrides_slot_ids=tuple(_array(item["overrides_slot_ids"], f"{path}.overrides_slot_ids")),
        lineage=tuple(_array(item["lineage"], f"{path}.lineage")),
        evidence_refs=tuple(_array(item["evidence_refs"], f"{path}.evidence_refs")),
        metadata=item["metadata"],
    )


def serialize_operation(operation: Operation) -> dict[str, Any]:
    if isinstance(operation, Insert):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot": serialize_slot(operation.slot),
        }
    if isinstance(operation, Suspend):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "reason": operation.reason,
        }
    if isinstance(operation, Override):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "replacement": serialize_slot(operation.replacement),
            "reason": operation.reason,
        }
    if isinstance(operation, Demote):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "new_priority": operation.new_priority,
            "reason": operation.reason,
        }
    if isinstance(operation, Revalidate):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "validation_id": operation.validation_id,
            "validator_id": operation.validator_id,
            "evidence": thaw_json(operation.evidence),
            "result": operation.result,
            "applies_to_last_updated_event_id": operation.applies_to_last_updated_event_id,
            "reason": operation.reason,
        }
    if isinstance(operation, Restore):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "validation_id": operation.validation_id,
            "reason": operation.reason,
        }
    if isinstance(operation, Expire):
        return {
            "operation_type": operation.operation_type,
            "operation_id": operation.operation_id,
            "slot_id": operation.slot_id,
            "reason": operation.reason,
        }
    raise SchemaError(UNKNOWN_OPERATION, f"unknown operation class {type(operation).__name__}")


def deserialize_operation(payload: Mapping[str, Any], *, path: str = "$.operation") -> Operation:
    if not isinstance(payload, Mapping):
        raise SchemaError(STATE_INVALID, f"{path} must be an object", path=path)
    operation_type = payload.get("operation_type")
    common = {"operation_type", "operation_id"}
    if operation_type == "insert":
        item = _object(payload, path=path, required=common | {"slot"})
        return Insert(item["operation_id"], deserialize_slot(item["slot"], path=f"{path}.slot"))
    if operation_type in {"suspend", "expire"}:
        item = _object(payload, path=path, required=common | {"slot_id", "reason"})
        cls = Suspend if operation_type == "suspend" else Expire
        return cls(item["operation_id"], item["slot_id"], item["reason"])
    if operation_type == "override":
        item = _object(payload, path=path, required=common | {"slot_id", "replacement", "reason"})
        return Override(
            item["operation_id"],
            item["slot_id"],
            deserialize_slot(item["replacement"], path=f"{path}.replacement"),
            item["reason"],
        )
    if operation_type == "demote":
        item = _object(payload, path=path, required=common | {"slot_id", "new_priority", "reason"})
        return Demote(item["operation_id"], item["slot_id"], item["new_priority"], item["reason"])
    if operation_type == "revalidate":
        item = _object(
            payload,
            path=path,
            required=common
            | {
                "slot_id",
                "validation_id",
                "validator_id",
                "evidence",
                "result",
                "applies_to_last_updated_event_id",
                "reason",
            },
        )
        return Revalidate(
            operation_id=item["operation_id"],
            slot_id=item["slot_id"],
            validation_id=item["validation_id"],
            validator_id=item["validator_id"],
            evidence=item["evidence"],
            result=item["result"],
            applies_to_last_updated_event_id=item["applies_to_last_updated_event_id"],
            reason=item["reason"],
        )
    if operation_type == "restore":
        item = _object(payload, path=path, required=common | {"slot_id", "validation_id", "reason"})
        return Restore(item["operation_id"], item["slot_id"], item["validation_id"], item["reason"])
    raise SchemaError(
        UNKNOWN_OPERATION,
        f"{path}.operation_type {operation_type!r} is unknown",
        path=f"{path}.operation_type",
        operation_type=operation_type,
    )


def serialize_patch(patch: Patch) -> dict[str, Any]:
    return {
        "patch_id": patch.patch_id,
        "event_id": patch.event_id,
        "reason": patch.reason,
        "operations": [serialize_operation(operation) for operation in patch.operations],
        "generator": patch.generator,
        "input_state_hash": patch.input_state_hash,
        "created_at": patch.created_at,
        "metadata": thaw_json(patch.metadata),
    }


def deserialize_patch(payload: Mapping[str, Any], *, path: str = "$.patch") -> Patch:
    item = _object(
        payload,
        path=path,
        required={
            "patch_id",
            "event_id",
            "reason",
            "operations",
            "generator",
            "input_state_hash",
            "created_at",
            "metadata",
        },
    )
    operations = tuple(
        deserialize_operation(operation, path=f"{path}.operations[{index}]")
        for index, operation in enumerate(_array(item["operations"], f"{path}.operations"))
    )
    return Patch(
        patch_id=item["patch_id"],
        event_id=item["event_id"],
        reason=item["reason"],
        operations=operations,
        generator=item["generator"],
        input_state_hash=item["input_state_hash"],
        created_at=item["created_at"],
        metadata=item["metadata"],
    )


def serialize_context(context: PatchContext) -> dict[str, Any]:
    return {
        "actor": context.actor,
        "authority_priority": context.authority_priority,
        "authorized_sources": [source.value for source in context.authorized_sources],
        "allow_safety_override": context.allow_safety_override,
        "event_source": context.event_source.value if context.event_source else None,
        "information_budget": context.information_budget,
        "policy_step_budget": context.policy_step_budget,
        "high_level_call_count": context.high_level_call_count,
        "pair_key": thaw_json(context.pair_key),
        "task_progress": thaw_json(context.task_progress),
        "termination_reason": context.termination_reason,
        "manual_intervention": context.manual_intervention,
        "git_commit": context.git_commit,
        "config_hash": context.config_hash,
        "checkpoint_id": context.checkpoint_id,
        "metadata": thaw_json(context.metadata),
    }


def deserialize_context(payload: Mapping[str, Any], *, path: str = "$.context") -> PatchContext:
    fields = {
        "actor",
        "authority_priority",
        "authorized_sources",
        "allow_safety_override",
        "event_source",
        "information_budget",
        "policy_step_budget",
        "high_level_call_count",
        "pair_key",
        "task_progress",
        "termination_reason",
        "manual_intervention",
        "git_commit",
        "config_hash",
        "checkpoint_id",
        "metadata",
    }
    item = _object(payload, path=path, required=fields)
    return PatchContext(
        actor=item["actor"],
        authority_priority=item["authority_priority"],
        authorized_sources=tuple(_array(item["authorized_sources"], f"{path}.authorized_sources")),
        allow_safety_override=item["allow_safety_override"],
        event_source=item["event_source"],
        information_budget=item["information_budget"],
        policy_step_budget=item["policy_step_budget"],
        high_level_call_count=item["high_level_call_count"],
        pair_key=item["pair_key"],
        task_progress=item["task_progress"],
        termination_reason=item["termination_reason"],
        manual_intervention=item["manual_intervention"],
        git_commit=item["git_commit"],
        config_hash=item["config_hash"],
        checkpoint_id=item["checkpoint_id"],
        metadata=item["metadata"],
    )


def _serialize_event(record: EventRecord) -> dict[str, Any]:
    return {
        "event_id": record.event_id,
        "patch_id": record.patch_id,
        "revision": record.revision,
        "reason": record.reason,
        "generator": record.generator,
        "applied_operation_ids": list(record.applied_operation_ids),
        "affected_slot_ids": list(record.affected_slot_ids),
        "details": thaw_json(record.details),
    }


def _deserialize_event(payload: Mapping[str, Any], path: str) -> EventRecord:
    fields = {
        "event_id",
        "patch_id",
        "revision",
        "reason",
        "generator",
        "applied_operation_ids",
        "affected_slot_ids",
        "details",
    }
    item = _object(payload, path=path, required=fields)
    return EventRecord(
        event_id=item["event_id"],
        patch_id=item["patch_id"],
        revision=item["revision"],
        reason=item["reason"],
        generator=item["generator"],
        applied_operation_ids=tuple(_array(item["applied_operation_ids"], f"{path}.applied_operation_ids")),
        affected_slot_ids=tuple(_array(item["affected_slot_ids"], f"{path}.affected_slot_ids")),
        details=item["details"],
    )


def _serialize_validation(record: ValidationRecord) -> dict[str, Any]:
    return {
        "validation_id": record.validation_id,
        "slot_id": record.slot_id,
        "validator_id": record.validator_id,
        "result": record.result,
        "evidence": thaw_json(record.evidence),
        "state_revision": record.state_revision,
        "applies_to_last_updated_event_id": record.applies_to_last_updated_event_id,
        "event_id": record.event_id,
        "operation_id": record.operation_id,
    }


def _deserialize_validation(payload: Mapping[str, Any], path: str) -> ValidationRecord:
    fields = {
        "validation_id",
        "slot_id",
        "validator_id",
        "result",
        "evidence",
        "state_revision",
        "applies_to_last_updated_event_id",
        "event_id",
        "operation_id",
    }
    item = _object(payload, path=path, required=fields)
    return ValidationRecord(
        validation_id=item["validation_id"],
        slot_id=item["slot_id"],
        validator_id=item["validator_id"],
        result=item["result"],
        evidence=item["evidence"],
        state_revision=item["state_revision"],
        applies_to_last_updated_event_id=item["applies_to_last_updated_event_id"],
        event_id=item["event_id"],
        operation_id=item["operation_id"],
    )


def serialize_state(state: ConstraintState) -> dict[str, Any]:
    """Return the canonical JSON-compatible state representation."""
    return {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "revision": state.revision,
        "slots": [serialize_slot(slot) for slot in sorted(state.slots, key=lambda item: item.slot_id)],
        "event_history": [_serialize_event(record) for record in state.event_history],
        "patch_history": [
            {"patch": serialize_patch(record.patch), "context": serialize_context(record.context)}
            for record in state.patch_history
        ],
        "validation_history": [_serialize_validation(record) for record in state.validation_history],
        "state_hash": state.state_hash,
    }


def canonical_state_json(state: ConstraintState) -> str:
    payload = serialize_state(state)
    payload.pop("state_hash", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_state_hash(state: ConstraintState) -> str:
    return hashlib.sha256(canonical_state_json(state).encode("utf-8")).hexdigest()


def deserialize_state(payload: Mapping[str, Any]) -> ConstraintState:
    fields = {
        "schema_version",
        "state_id",
        "revision",
        "slots",
        "event_history",
        "patch_history",
        "validation_history",
        "state_hash",
    }
    item = _object(payload, path="$", required=fields)
    if item["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(
            SCHEMA_VERSION_UNSUPPORTED,
            f"schema version {item['schema_version']!r} is unsupported; expected {SCHEMA_VERSION!r}",
            version=item["schema_version"],
        )
    state = ConstraintState(
        schema_version=item["schema_version"],
        state_id=item["state_id"],
        revision=item["revision"],
        slots=tuple(
            deserialize_slot(slot, path=f"$.slots[{index}]")
            for index, slot in enumerate(_array(item["slots"], "$.slots"))
        ),
        event_history=tuple(
            _deserialize_event(record, f"$.event_history[{index}]")
            for index, record in enumerate(_array(item["event_history"], "$.event_history"))
        ),
        patch_history=tuple(
            AppliedPatch(
                patch=deserialize_patch(
                    _object(
                        record,
                        path=f"$.patch_history[{index}]",
                        required={"patch", "context"},
                    )["patch"],
                    path=f"$.patch_history[{index}].patch",
                ),
                context=deserialize_context(
                    record["context"],
                    path=f"$.patch_history[{index}].context",
                ),
            )
            for index, record in enumerate(_array(item["patch_history"], "$.patch_history"))
        ),
        validation_history=tuple(
            _deserialize_validation(record, f"$.validation_history[{index}]")
            for index, record in enumerate(_array(item["validation_history"], "$.validation_history"))
        ),
        state_hash=item["state_hash"],
    )
    actual = canonical_state_hash(state)
    if actual != state.state_hash:
        raise InvariantError(
            HASH_MISMATCH,
            "state_hash does not match canonical state content",
            expected=actual,
            actual=state.state_hash,
        )
    from .validator import validate_state

    report = validate_state(state)
    if not report.valid:
        first = report.errors[0]
        raise InvariantError(first.code, first.message, path=first.path)
    return state
