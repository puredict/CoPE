from __future__ import annotations

from typing import Any, Mapping, Sequence

from cope.semantic_cancellation import (
    build_oracle_cancellation_state,
    validate_oracle_cancellation_state,
)
from cope.semantic_replacement import (
    RECEPTACLE,
    FullStateValidationError,
    build_oracle_full_state,
    goal_commitment_id,
    validate_oracle_full_state,
)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FullStateValidationError(f"{label} must be an object")
    return value


def _validate_receipt(
    receipt: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    method_label: str,
    operation: str,
    operation_ids: Sequence[str],
) -> Mapping[str, Any]:
    if receipt.get("method_label") != method_label:
        raise FullStateValidationError("receipt method label does not match materializer")
    if receipt.get("oracle_operation_selection") is not True:
        raise FullStateValidationError("receipt is not an oracle-selected typed transition")
    if receipt.get("provider_called") is not False:
        raise FullStateValidationError("oracle materialization receipt must be provider-free")

    patch = _require_mapping(receipt.get("patch"), "receipt.patch")
    if patch.get("event_id") != event.get("event_id"):
        raise FullStateValidationError("receipt patch event does not match the authorized event")
    if patch.get("operation") != operation:
        raise FullStateValidationError("receipt patch operation does not match materializer")

    before = _require_mapping(receipt.get("state_before"), "receipt.state_before")
    after = _require_mapping(receipt.get("state_after"), "receipt.state_after")
    transition = _require_mapping(receipt.get("transition"), "receipt.transition")
    if transition.get("accepted") is not True:
        raise FullStateValidationError("materialization requires an accepted typed transition")
    if transition.get("before_hash") != before.get("state_hash"):
        raise FullStateValidationError("receipt before hash does not match serialized state")
    if transition.get("after_hash") != after.get("state_hash"):
        raise FullStateValidationError("receipt after hash does not match serialized state")
    if transition.get("before_hash") == transition.get("after_hash"):
        raise FullStateValidationError("accepted semantic patch did not change persistent state")
    if int(after.get("revision", -1)) != int(before.get("revision", -1)) + 1:
        raise FullStateValidationError("accepted semantic patch did not advance exactly one revision")
    if list(transition.get("applied_operation_ids") or ()) != list(operation_ids):
        raise FullStateValidationError("receipt applied-operation identity is non-canonical")

    audit = _require_mapping(transition.get("audit_record"), "receipt.transition.audit_record")
    expected_audit = {
        "accepted": True,
        "event_id": event.get("event_id"),
        "before_hash": before.get("state_hash"),
        "after_hash": after.get("state_hash"),
        "applied_operation_ids": list(operation_ids),
    }
    for key, expected in expected_audit.items():
        actual = list(audit.get(key) or ()) if key == "applied_operation_ids" else audit.get(key)
        if actual != expected:
            raise FullStateValidationError(f"receipt audit field {key!r} is inconsistent")
    return after


def _slot_map(state_after: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    slots = state_after.get("slots")
    if not isinstance(slots, list):
        raise FullStateValidationError("serialized typed state must contain a slot list")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(slots):
        slot = _require_mapping(raw, f"state_after.slots[{index}]")
        slot_id = slot.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            raise FullStateValidationError("materialized slot requires a stable ID")
        if slot_id in result:
            raise FullStateValidationError(f"duplicate materialized slot {slot_id!r}")
        result[slot_id] = slot
    return result


def _validate_slot(
    slot: Mapping[str, Any],
    *,
    slot_id: str,
    object_name: str,
    mode: str,
    created_event_id: str,
    last_updated_event_id: str,
    parent_slot_id: str | None,
    overrides_slot_ids: Sequence[str],
    lineage: Sequence[str],
    semantic_role: str,
) -> None:
    expected = {
        "slot_id": slot_id,
        "constraint_type": "task_goal",
        "content": {"predicate": "in", "arguments": [object_name, RECEPTACLE]},
        "source": "task",
        "mode": mode,
        "priority": 100,
        "created_event_id": created_event_id,
        "last_updated_event_id": last_updated_event_id,
        "parent_slot_id": parent_slot_id,
        "overrides_slot_ids": list(overrides_slot_ids),
        "lineage": list(lineage),
        "evidence_refs": [],
        "metadata": {"semantic_role": semantic_role},
    }
    for key, expected_value in expected.items():
        if slot.get(key) != expected_value:
            raise FullStateValidationError(
                f"materialized slot {slot_id!r} has non-canonical {key}"
            )


def materialize_replacement_receipt(
    receipt: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    physically_true_objects: Sequence[str],
) -> dict[str, Any]:
    after = _validate_receipt(
        receipt,
        event,
        method_label="oracle_cope_patch_override",
        operation="Override",
        operation_ids=("override-pending-goal-with-replacement",),
    )
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    replacement_object = str(event["replacement_object"])
    event_id = str(event["event_id"])
    genesis_event = f"{event_id}:genesis"
    done_id = goal_commitment_id(done_object)
    pending_id = goal_commitment_id(pending_object)
    replacement_id = goal_commitment_id(replacement_object)
    patch = _require_mapping(receipt.get("patch"), "receipt.patch")
    if patch.get("target_id") != pending_id or patch.get("replacement_id") != replacement_id:
        raise FullStateValidationError("receipt replacement identity does not match event")
    if receipt.get("execution_directive") != {
        "skill": "place_in",
        "arguments": [replacement_object, RECEPTACLE],
    }:
        raise FullStateValidationError("receipt execution directive is non-canonical")

    slots = _slot_map(after)
    if set(slots) != {done_id, pending_id, replacement_id}:
        raise FullStateValidationError("replacement typed state has unexpected task slots")
    _validate_slot(
        slots[done_id],
        slot_id=done_id,
        object_name=done_object,
        mode="active",
        created_event_id=genesis_event,
        last_updated_event_id=genesis_event,
        parent_slot_id=None,
        overrides_slot_ids=(),
        lineage=(done_id,),
        semantic_role="task_goal_commitment",
    )
    _validate_slot(
        slots[pending_id],
        slot_id=pending_id,
        object_name=pending_object,
        mode="overridden",
        created_event_id=genesis_event,
        last_updated_event_id=event_id,
        parent_slot_id=None,
        overrides_slot_ids=(),
        lineage=(pending_id,),
        semantic_role="task_goal_commitment",
    )
    _validate_slot(
        slots[replacement_id],
        slot_id=replacement_id,
        object_name=replacement_object,
        mode="active",
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=pending_id,
        overrides_slot_ids=(pending_id,),
        lineage=(pending_id, replacement_id),
        semantic_role="task_goal_commitment",
    )

    previous_state_version = int(event.get("valid_from_state_version", 0))
    materialized = build_oracle_full_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_oracle_full_state(
        materialized,
        event,
        previous_state_version=previous_state_version,
        physically_true_objects=physically_true_objects,
    )
    return materialized


def materialize_cancellation_receipt(
    receipt: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    physically_true_objects: Sequence[str],
) -> dict[str, Any]:
    after = _validate_receipt(
        receipt,
        event,
        method_label="oracle_cope_patch_halt",
        operation="Expire",
        operation_ids=("expire-cancelled-pending-goal",),
    )
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    event_id = str(event["event_id"])
    genesis_event = f"{event_id}:genesis"
    done_id = goal_commitment_id(done_object)
    pending_id = goal_commitment_id(pending_object)
    patch = _require_mapping(receipt.get("patch"), "receipt.patch")
    if patch.get("target_id") != pending_id:
        raise FullStateValidationError("receipt cancellation identity does not match event")
    if receipt.get("execution_directive") != "HALT":
        raise FullStateValidationError("receipt cancellation directive is not HALT")

    slots = _slot_map(after)
    if set(slots) != {done_id, pending_id}:
        raise FullStateValidationError("cancellation typed state has unexpected task slots")
    _validate_slot(
        slots[done_id],
        slot_id=done_id,
        object_name=done_object,
        mode="active",
        created_event_id=genesis_event,
        last_updated_event_id=genesis_event,
        parent_slot_id=None,
        overrides_slot_ids=(),
        lineage=(done_id,),
        semantic_role="original_goal_commitment",
    )
    _validate_slot(
        slots[pending_id],
        slot_id=pending_id,
        object_name=pending_object,
        mode="expired",
        created_event_id=genesis_event,
        last_updated_event_id=event_id,
        parent_slot_id=None,
        overrides_slot_ids=(),
        lineage=(pending_id,),
        semantic_role="original_goal_commitment",
    )

    previous_state_version = int(event.get("valid_from_state_version", 0))
    materialized = build_oracle_cancellation_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_oracle_cancellation_state(
        materialized,
        event,
        previous_state_version=previous_state_version,
        physically_true_objects=physically_true_objects,
    )
    return materialized
