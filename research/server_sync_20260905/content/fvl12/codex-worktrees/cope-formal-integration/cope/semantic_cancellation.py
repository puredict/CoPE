from __future__ import annotations

from typing import Any, Mapping, Sequence

from cope.semantic_replacement import (
    FULL_STATE_SCHEMA,
    ORIGINAL_OBJECTS,
    RECEPTACLE,
    FullStateValidationError,
    MilestoneEvent,
    goal_commitment_id,
    validate_canonical_task_sections,
)
from cope.operations import apply_patch
from cope.schema import (
    ConstraintSlot,
    ConstraintState,
    Expire,
    Insert,
    Patch,
    PatchContext,
)
from cope.serialization import serialize_state, thaw_json


def build_cancellation_event(
    milestone: MilestoneEvent,
    *,
    pair_key: str,
    previous_state_version: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": f"semantic-cancel-v1:{pair_key}",
        "event_type": "cancel_pending_goal",
        "issuer": "task_owner",
        "authority": 100,
        "target_commitment_id": goal_commitment_id(milestone.pending_object),
        "operation": "cancel",
        "done_object": milestone.done_object,
        "pending_object": milestone.pending_object,
        "valid_from_state_version": int(previous_state_version),
        "world_version": int(milestone.policy_step),
    }


def _commitment(
    object_name: str,
    *,
    status: str,
    event_id: str,
) -> dict[str, Any]:
    return {
        "id": goal_commitment_id(object_name),
        "type": "task_goal",
        "predicate": "in",
        "grounding": [object_name, RECEPTACLE],
        "lifecycle_status": status,
        "source": "task_owner",
        "owner": "task_owner",
        "authority": 100,
        "valid_from": event_id,
        "valid_until": "task_end",
        "dependencies": [],
        "support_links": [],
        "override_links": [],
        "supersession_links": [],
    }


def build_oracle_cancellation_state(
    event: Mapping[str, Any],
    *,
    previous_state_version: int = 0,
) -> dict[str, Any]:
    event_id = str(event["event_id"])
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    return {
        "schema_version": FULL_STATE_SCHEMA,
        "state_version": int(previous_state_version) + 1,
        "current_goal": {
            "all": [{"predicate": "in", "arguments": [done_object, RECEPTACLE]}]
        },
        "entities": [
            {"id": done_object, "kind": "object"},
            {"id": pending_object, "kind": "object"},
            {"id": RECEPTACLE, "kind": "region"},
        ],
        "commitments": [
            _commitment(done_object, status="satisfied", event_id=event_id),
            _commitment(pending_object, status="cancelled", event_id=event_id),
        ],
        "progress_ledger": [
            {
                "milestone_id": goal_commitment_id(done_object),
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": event_id,
            "world_version": int(event["world_version"]),
            "input_state_version": int(event["valid_from_state_version"]),
        },
        "execution_directive": "HALT",
        "controller_prompt": "diagnostic-only; no controller call is permitted",
    }


def validate_oracle_cancellation_state(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    previous_state_version: int,
    physically_true_objects: Sequence[str],
) -> None:
    if state.get("schema_version") != FULL_STATE_SCHEMA:
        raise FullStateValidationError("wrong full-state schema")
    if int(state.get("state_version", -1)) != int(previous_state_version) + 1:
        raise FullStateValidationError("state version is stale or skips a revision")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise FullStateValidationError("event is not authorized to cancel the task goal")
    done_object = str(event.get("done_object"))
    pending_object = str(event.get("pending_object"))
    if {done_object, pending_object} != set(ORIGINAL_OBJECTS):
        raise FullStateValidationError("event does not identify one done and one pending sibling")
    if event.get("target_commitment_id") != goal_commitment_id(pending_object):
        raise FullStateValidationError("event targets the wrong commitment")
    if done_object not in set(physically_true_objects):
        raise FullStateValidationError("claimed completed milestone is not physically true")
    if pending_object in set(physically_true_objects):
        raise FullStateValidationError("pending commitment is already physically satisfied")

    commitments = state.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 2:
        raise FullStateValidationError("full state must contain exactly two commitments")
    by_id = {item.get("id"): item for item in commitments if isinstance(item, Mapping)}
    if len(by_id) != 2:
        raise FullStateValidationError("commitment IDs must be unique")
    expected = {
        goal_commitment_id(done_object): "satisfied",
        goal_commitment_id(pending_object): "cancelled",
    }
    if {key: by_id.get(key, {}).get("lifecycle_status") for key in expected} != expected:
        raise FullStateValidationError("commitment lifecycle statuses do not match cancellation")
    expected_goal = {
        "all": [{"predicate": "in", "arguments": [done_object, RECEPTACLE]}]
    }
    if state.get("current_goal") != expected_goal:
        raise FullStateValidationError("current goal does not match cancellation")
    if state.get("plan") != [] or state.get("execution_directive") != "HALT":
        raise FullStateValidationError("cancelled terminal state must compile to HALT")

    canonical = build_oracle_cancellation_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_canonical_task_sections(state, canonical)


def compile_execution_directive(state: Mapping[str, Any]) -> str:
    if state.get("plan") != [] or state.get("execution_directive") != "HALT":
        raise FullStateValidationError("state does not permit HALT")
    return "HALT"


def cancellation_compliance(
    event: Mapping[str, Any],
    predicates: Mapping[str, bool],
) -> bool:
    return bool(predicates.get(str(event["done_object"]), False)) and not bool(
        predicates.get(str(event["pending_object"]), False)
    )


def apply_oracle_cancellation_patch(
    event: Mapping[str, Any],
    *,
    physically_true_objects: Sequence[str],
) -> dict[str, Any]:
    """Exercise the production typed-patch engine with an oracle Expire choice.

    This is an oracle patch canary, not a provider-generated CoPE result.
    """

    previous_state_version = int(event.get("valid_from_state_version", 0))
    oracle_state = build_oracle_cancellation_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_oracle_cancellation_state(
        oracle_state,
        event,
        previous_state_version=previous_state_version,
        physically_true_objects=physically_true_objects,
    )
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    genesis_event = f"{event['event_id']}:genesis"
    state = ConstraintState.empty(f"cancellation:{event['event_id']}")

    def goal_slot(object_name: str) -> ConstraintSlot:
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
            created_event_id=genesis_event,
            last_updated_event_id=genesis_event,
            lineage=(identifier,),
            metadata={"semantic_role": "original_goal_commitment"},
        )

    genesis = Patch(
        patch_id=f"{event['event_id']}:genesis-patch",
        event_id=genesis_event,
        reason="initialize two atomic task commitments",
        operations=(
            Insert("genesis-insert-done", goal_slot(done_object)),
            Insert("genesis-insert-pending", goal_slot(pending_object)),
        ),
        generator="oracle-cancellation-canary",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    initialized = apply_patch(
        state,
        genesis,
        PatchContext.trusted("cancellation-genesis"),
    )
    if not initialized.accepted:
        raise FullStateValidationError(
            f"cancellation genesis patch rejected: {initialized.rejection_reason}"
        )
    state = initialized.state
    state_before = serialize_state(state)
    cancellation_patch = Patch(
        patch_id=f"{event['event_id']}:oracle-cope-patch",
        event_id=str(event["event_id"]),
        reason="authorized cancellation of pending task commitment",
        operations=(
            Expire(
                "expire-cancelled-pending-goal",
                goal_commitment_id(pending_object),
                "task owner cancelled the pending goal",
            ),
        ),
        generator="oracle-cope-patch-canary",
        input_state_hash=state.state_hash,
        created_at=1,
        metadata={
            "oracle_operation_selection": True,
            "provider_called": False,
        },
    )
    context = PatchContext(
        actor="task_owner",
        authority_priority=100,
        authorized_sources=("task",),
        event_source="oracle",
        information_budget=0,
        policy_step_budget=0,
        high_level_call_count=0,
        pair_key={"event_id": str(event["event_id"])},
        task_progress={
            "physically_true_objects": list(physically_true_objects),
        },
        manual_intervention=False,
        metadata={"oracle_patch_canary": True},
    )
    transitioned = apply_patch(state, cancellation_patch, context)
    if not transitioned.accepted:
        raise FullStateValidationError(
            f"oracle CoPE cancellation patch rejected: "
            f"{transitioned.rejection_code}: {transitioned.rejection_reason}"
        )
    state_after = transitioned.state
    if state_after.get_slot(goal_commitment_id(pending_object)).mode.value != "expired":
        raise FullStateValidationError("pending commitment did not become an expired tombstone")
    if state_after.get_slot(goal_commitment_id(done_object)).mode.value != "active":
        raise FullStateValidationError("unaffected completed commitment did not remain active")
    unsatisfied_active = [
        slot
        for slot in state_after.slots
        if slot.mode.value in {"active", "demoted"}
        and str(slot.content["arguments"][0]) not in set(physically_true_objects)
    ]
    if unsatisfied_active:
        raise FullStateValidationError("patched state still has an unsatisfied active goal")
    return {
        "method_label": "oracle_cope_patch_halt",
        "oracle_operation_selection": True,
        "provider_called": False,
        "state_before": state_before,
        "state_after": serialize_state(state_after),
        "patch": {
            "patch_id": cancellation_patch.patch_id,
            "event_id": cancellation_patch.event_id,
            "operation": "Expire",
            "target_id": goal_commitment_id(pending_object),
        },
        "transition": {
            "accepted": True,
            "before_hash": transitioned.before_hash,
            "after_hash": transitioned.after_hash,
            "applied_operation_ids": list(transitioned.applied_operation_ids),
            "audit_record": thaw_json(transitioned.audit_record),
        },
        "execution_directive": "HALT",
    }
