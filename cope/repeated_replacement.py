"""Typed repeated-replacement helpers for persistent CoPE commitments."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from cope.operations import apply_patch
from cope.schema import (
    ConstraintSlot,
    ConstraintState,
    Insert,
    Override,
    Patch,
    PatchContext,
)
from cope.semantic_replacement import (
    ALLOWED_OBJECTS,
    RECEPTACLE,
    FullStateValidationError,
    goal_commitment_id,
)
from cope.serialization import serialize_state, thaw_json


def build_chained_replacement_event(
    *,
    pair_key: str,
    step_index: int,
    source_object: str,
    replacement_object: str,
    expected_state_revision: int,
    world_version: int,
) -> dict[str, Any]:
    if step_index <= 0:
        raise ValueError("step_index must be positive")
    if source_object not in ALLOWED_OBJECTS:
        raise ValueError(f"unknown source object {source_object!r}")
    if replacement_object not in ALLOWED_OBJECTS:
        raise ValueError(f"unknown replacement object {replacement_object!r}")
    if source_object == replacement_object:
        raise ValueError("replacement must differ from source")
    return {
        "event_id": f"semantic-replace-chain-v1:{pair_key}:step{step_index}",
        "event_type": "replace_pending_goal",
        "issuer": "task_owner",
        "authority": 100,
        "step_index": int(step_index),
        "target_commitment_id": goal_commitment_id(source_object),
        "operation": "override",
        "source_object": source_object,
        "replacement_object": replacement_object,
        "replacement_target": RECEPTACLE,
        "expected_state_revision": int(expected_state_revision),
        "world_version": int(world_version),
    }


def _goal_slot(
    object_name: str,
    *,
    event_id: str,
    parent_slot_id: str | None = None,
    overrides_slot_ids: tuple[str, ...] = (),
    lineage: tuple[str, ...] | None = None,
) -> ConstraintSlot:
    identifier = goal_commitment_id(object_name)
    return ConstraintSlot(
        slot_id=identifier,
        constraint_type="task_goal",
        content={
            "predicate": "in",
            "arguments": [object_name, RECEPTACLE],
        },
        source="task",
        mode="active",
        priority=100,
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=parent_slot_id,
        overrides_slot_ids=overrides_slot_ids,
        lineage=lineage or (identifier,),
        metadata={"semantic_role": "task_goal_commitment"},
    )


def _validate_event(
    event: Mapping[str, Any],
    *,
    state: ConstraintState,
    expected_source_object: str,
    used_objects: set[str],
) -> tuple[str, str]:
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise FullStateValidationError("event is not authorized")
    if int(event.get("expected_state_revision", -1)) != state.revision:
        raise FullStateValidationError(
            "event expected_state_revision does not match persistent state"
        )
    source_object = str(event.get("source_object"))
    replacement_object = str(event.get("replacement_object"))
    if source_object != expected_source_object:
        raise FullStateValidationError(
            f"event targets {source_object!r}, expected active chain tip "
            f"{expected_source_object!r}"
        )
    if source_object not in ALLOWED_OBJECTS or replacement_object not in ALLOWED_OBJECTS:
        raise FullStateValidationError("event contains an unknown object")
    if replacement_object in used_objects:
        raise FullStateValidationError("replacement reuses an existing chain object")
    source_id = goal_commitment_id(source_object)
    if event.get("target_commitment_id") != source_id:
        raise FullStateValidationError("event targets the wrong commitment id")
    try:
        source_slot = state.get_slot(source_id)
    except KeyError as exc:
        raise FullStateValidationError("source commitment does not exist") from exc
    if source_slot.mode.value != "active":
        raise FullStateValidationError("source commitment is not active")
    return source_object, replacement_object


def apply_oracle_replacement_chain(
    events: Sequence[Mapping[str, Any]],
    *,
    done_object: str,
    initial_pending_object: str,
    physically_true_objects: Sequence[str],
    pair_key: str,
) -> dict[str, Any]:
    """Apply one or more oracle-selected Overrides to one persistent state."""

    if not events:
        raise ValueError("replacement chain must contain at least one event")
    if done_object not in ALLOWED_OBJECTS or initial_pending_object not in ALLOWED_OBJECTS:
        raise ValueError("unknown initial task object")
    physically_true = set(physically_true_objects)
    if done_object not in physically_true:
        raise FullStateValidationError("completed progress is not physically true")
    if initial_pending_object in physically_true:
        raise FullStateValidationError("pending object is already physically complete")

    genesis_event = f"semantic-replace-chain-v1:{pair_key}:genesis"
    state = ConstraintState.empty(f"replacement-chain:{pair_key}")
    genesis = Patch(
        patch_id=f"{genesis_event}:patch",
        event_id=genesis_event,
        reason="initialize persistent atomic task commitments",
        operations=(
            Insert(
                "genesis-insert-done",
                _goal_slot(done_object, event_id=genesis_event),
            ),
            Insert(
                "genesis-insert-pending",
                _goal_slot(initial_pending_object, event_id=genesis_event),
            ),
        ),
        generator="oracle-repeated-replacement-canary",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    initialized = apply_patch(
        state,
        genesis,
        PatchContext.trusted("replacement-chain-genesis"),
    )
    if not initialized.accepted:
        raise FullStateValidationError(
            f"replacement-chain genesis rejected: {initialized.rejection_reason}"
        )
    state = initialized.state
    initial_state = serialize_state(state)
    expected_source = initial_pending_object
    used_objects = {done_object, initial_pending_object}
    receipts: list[dict[str, Any]] = []

    for chain_index, event in enumerate(events, start=1):
        source_object, replacement_object = _validate_event(
            event,
            state=state,
            expected_source_object=expected_source,
            used_objects=used_objects,
        )
        source_id = goal_commitment_id(source_object)
        replacement_id = goal_commitment_id(replacement_object)
        source_slot = state.get_slot(source_id)
        replacement_slot = _goal_slot(
            replacement_object,
            event_id=str(event["event_id"]),
            parent_slot_id=source_id,
            overrides_slot_ids=(source_id,),
            lineage=source_slot.lineage + (replacement_id,),
        )
        before = serialize_state(state)
        patch = Patch(
            patch_id=f"{event['event_id']}:oracle-cope-patch",
            event_id=str(event["event_id"]),
            reason="authorized replacement of active chain-tip commitment",
            operations=(
                Override(
                    f"override-chain-tip-{chain_index}",
                    source_id,
                    replacement_slot,
                    "task owner replaced the active pending goal",
                ),
            ),
            generator="oracle-repeated-replacement-canary",
            input_state_hash=state.state_hash,
            created_at=chain_index,
            metadata={
                "oracle_operation_selection": True,
                "provider_called": False,
                "chain_index": chain_index,
            },
        )
        context = PatchContext(
            actor="task_owner",
            authority_priority=100,
            authorized_sources=("task",),
            event_source="oracle",
            information_budget=0,
            policy_step_budget=0,
            high_level_call_count=chain_index,
            pair_key={"pair_key": pair_key, "chain_index": chain_index},
            task_progress={"physically_true_objects": sorted(physically_true)},
            manual_intervention=False,
            metadata={"oracle_repeated_patch_canary": True},
        )
        transitioned = apply_patch(state, patch, context)
        if not transitioned.accepted:
            raise FullStateValidationError(
                f"replacement chain step {chain_index} rejected: "
                f"{transitioned.rejection_code}: {transitioned.rejection_reason}"
            )
        state = transitioned.state
        receipts.append(
            {
                "chain_index": chain_index,
                "event": dict(event),
                "state_before": before,
                "state_after": serialize_state(state),
                "patch": {
                    "patch_id": patch.patch_id,
                    "operation": "Override",
                    "target_id": source_id,
                    "replacement_id": replacement_id,
                },
                "transition": {
                    "accepted": True,
                    "revision_before": state.revision - 1,
                    "revision_after": state.revision,
                    "before_hash": transitioned.before_hash,
                    "after_hash": transitioned.after_hash,
                    "applied_operation_ids": list(
                        transitioned.applied_operation_ids
                    ),
                    "audit_record": thaw_json(transitioned.audit_record),
                },
            }
        )
        expected_source = replacement_object
        used_objects.add(replacement_object)

    done_id = goal_commitment_id(done_object)
    final_id = goal_commitment_id(expected_source)
    if state.get_slot(done_id).mode.value != "active":
        raise FullStateValidationError("completed progress commitment changed mode")
    if state.get_slot(final_id).mode.value != "active":
        raise FullStateValidationError("final chain-tip commitment is not active")
    for stale_object in used_objects - {done_object, expected_source}:
        if state.get_slot(goal_commitment_id(stale_object)).mode.value != "overridden":
            raise FullStateValidationError("stale chain commitment is not overridden")

    return {
        "method_label": "oracle_cope_repeated_override",
        "oracle_operation_selection": True,
        "provider_called": False,
        "initial_state": initial_state,
        "final_state": serialize_state(state),
        "receipts": receipts,
        "chain_objects": [
            initial_pending_object,
            *[str(event["replacement_object"]) for event in events],
        ],
        "final_active_object": expected_source,
        "execution_directive": {
            "skill": "place_in",
            "arguments": [expected_source, RECEPTACLE],
        },
    }
