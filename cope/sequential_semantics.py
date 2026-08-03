"""Persistent two-event semantic transitions shared by formal live arms."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from cope.operations import apply_patch
from cope.schema import (
    ConstraintSlot,
    ConstraintState,
    Expire,
    Insert,
    Override,
    Patch,
    PatchContext,
)
from cope.semantic_replacement import ALLOWED_OBJECTS, RECEPTACLE, goal_commitment_id
from cope.serialization import serialize_state, thaw_json
from cope.types import canonical_json, stable_hash


SCHEMA = "sequential-persistent-state-v1"
SEMANTIC_FIELDS = {
    "current_goal",
    "entities",
    "commitments",
    "progress_ledger",
    "plan",
    "pending_restorations",
}
STATE_FIELDS = SEMANTIC_FIELDS | {
    "schema_version",
    "state_version",
    "evidence_versions",
}


class SequentialSemanticError(ValueError):
    pass


def _require_object(value: str) -> str:
    if value not in ALLOWED_OBJECTS:
        raise SequentialSemanticError(f"unknown basket object {value!r}")
    return value


def _commitment(
    object_name: str,
    *,
    status: str,
    valid_from: str,
    valid_until: str = "task_end",
    override_links: Sequence[str] = (),
    supersession_links: Sequence[str] = (),
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
        "valid_from": valid_from,
        "valid_until": valid_until,
        "dependencies": [],
        "support_links": [],
        "override_links": list(override_links),
        "supersession_links": list(supersession_links),
    }


def _predicate(object_name: str) -> dict[str, Any]:
    return {"predicate": "in", "arguments": [object_name, RECEPTACLE]}


def _plan_step(object_name: str, done_object: str) -> dict[str, Any]:
    return {
        "step_id": f"place-{object_name}",
        "skill": "place_in",
        "arguments": [object_name, RECEPTACLE],
        "status": "pending",
        "preconditions": [],
        "effects": [_predicate(object_name)],
        "dependencies": [goal_commitment_id(done_object)],
    }


def build_initial_sequence_state(
    *,
    sequence_id: str,
    done_object: str,
    pending_object: str,
    available_objects: Sequence[str],
    world_version: int,
) -> dict[str, Any]:
    done = _require_object(done_object)
    pending = _require_object(pending_object)
    available = tuple(dict.fromkeys(_require_object(item) for item in available_objects))
    if done == pending or done not in available or pending not in available:
        raise SequentialSemanticError("initial sibling objects are invalid")
    genesis = f"sequential:{sequence_id}:genesis"
    return {
        "schema_version": SCHEMA,
        "state_version": 1,
        "current_goal": {"all": [_predicate(done), _predicate(pending)]},
        "entities": [
            *[{"id": item, "kind": "object"} for item in available],
            {"id": RECEPTACLE, "kind": "region"},
        ],
        "commitments": [
            _commitment(done, status="satisfied", valid_from=genesis),
            _commitment(pending, status="active", valid_from=genesis),
        ],
        "progress_ledger": [
            {
                "milestone_id": goal_commitment_id(done),
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [_plan_step(pending, done)],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": genesis,
            "world_version": int(world_version),
            "input_state_version": 0,
        },
    }


def active_pending_object(state: Mapping[str, Any], done_object: str) -> str:
    active = [
        str(row["grounding"][0])
        for row in state.get("commitments", [])
        if isinstance(row, Mapping)
        and row.get("lifecycle_status") == "active"
        and str(row.get("grounding", [""])[0]) != done_object
    ]
    if len(active) != 1:
        raise SequentialSemanticError(
            f"expected one active pending commitment, found {len(active)}"
        )
    return active[0]


def build_sequence_event(
    state: Mapping[str, Any],
    *,
    sequence_id: str,
    step_index: int,
    done_object: str,
    event_type: str,
    replacement_object: str | None,
    world_version: int,
) -> dict[str, Any]:
    source = active_pending_object(state, done_object)
    if event_type not in {"replace_pending_goal", "cancel_pending_goal"}:
        raise SequentialSemanticError(f"unsupported event type {event_type!r}")
    event = {
        "event_id": f"sequential:{sequence_id}:step{step_index}",
        "event_type": event_type,
        "issuer": "task_owner",
        "authority": 100,
        "step_index": int(step_index),
        "target_commitment_id": goal_commitment_id(source),
        "operation": "override" if event_type == "replace_pending_goal" else "cancel",
        "done_object": done_object,
        "pending_object": source,
        "valid_from_state_version": int(state["state_version"]),
        "world_version": int(world_version),
    }
    if event_type == "replace_pending_goal":
        if replacement_object is None:
            raise SequentialSemanticError("replacement event lacks replacement object")
        replacement = _require_object(replacement_object)
        if replacement == source:
            raise SequentialSemanticError("replacement equals active source")
        event["replacement_object"] = replacement
        event["replacement_target"] = RECEPTACLE
    elif replacement_object is not None:
        raise SequentialSemanticError("cancellation must not name a replacement")
    return event


def _commitment_map(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("commitments")
    if not isinstance(rows, list):
        raise SequentialSemanticError("commitments must be a list")
    mapped = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(mapped) != len(rows):
        raise SequentialSemanticError("commitments contain malformed or duplicate IDs")
    return mapped


def validate_event_against_state(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    if set(state) != STATE_FIELDS or state.get("schema_version") != SCHEMA:
        raise SequentialSemanticError("pre-state fields or schema are noncanonical")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise SequentialSemanticError("event is unauthorized")
    if int(event.get("valid_from_state_version", -1)) != int(state["state_version"]):
        raise SequentialSemanticError("event base revision is stale")
    done = _require_object(str(event.get("done_object")))
    source = active_pending_object(state, done)
    if event.get("pending_object") != source:
        raise SequentialSemanticError("event does not target the active chain tip")
    source_id = goal_commitment_id(source)
    if event.get("target_commitment_id") != source_id:
        raise SequentialSemanticError("event target commitment is mismatched")
    if event.get("event_type") == "replace_pending_goal":
        replacement = _require_object(str(event.get("replacement_object")))
        if goal_commitment_id(replacement) in _commitment_map(state):
            raise SequentialSemanticError("replacement reuses historical commitment")
    elif event.get("event_type") != "cancel_pending_goal":
        raise SequentialSemanticError("unknown event family")


def build_expected_next_state(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    validate_event_against_state(state, event)
    out = copy.deepcopy(dict(state))
    done = str(event["done_object"])
    source = str(event["pending_object"])
    source_id = goal_commitment_id(source)
    commitments = _commitment_map(out)
    source_row = commitments[source_id]
    source_row["valid_until"] = str(event["event_id"])
    source_row["lifecycle_status"] = (
        "superseded" if event["event_type"] == "replace_pending_goal" else "cancelled"
    )
    if event["event_type"] == "replace_pending_goal":
        replacement = str(event["replacement_object"])
        replacement_id = goal_commitment_id(replacement)
        source_row["supersession_links"] = [replacement_id]
        out["commitments"].append(
            _commitment(
                replacement,
                status="active",
                valid_from=str(event["event_id"]),
                override_links=(source_id,),
            )
        )
        out["current_goal"] = {"all": [_predicate(done), _predicate(replacement)]}
        out["plan"] = [_plan_step(replacement, done)]
    else:
        out["current_goal"] = {"all": [_predicate(done)]}
        out["plan"] = []
    out["state_version"] = int(state["state_version"]) + 1
    out["evidence_versions"] = {
        "event_id": str(event["event_id"]),
        "world_version": int(event["world_version"]),
        "input_state_version": int(state["state_version"]),
    }
    return out


def compile_directive(state: Mapping[str, Any]) -> str:
    plan = state.get("plan")
    if plan == []:
        return "HALT"
    if not isinstance(plan, list) or len(plan) != 1:
        raise SequentialSemanticError("state must compile to HALT or one pending action")
    step = plan[0]
    if step.get("skill") != "place_in" or step.get("status") != "pending":
        raise SequentialSemanticError("remaining plan is noncanonical")
    arguments = step.get("arguments")
    if not isinstance(arguments, list) or len(arguments) != 2:
        raise SequentialSemanticError("remaining action arguments are malformed")
    return f"place_in({arguments[0]}, {arguments[1]})"


def validate_sequence_transition(
    pre_state: Mapping[str, Any],
    post_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> str:
    expected = build_expected_next_state(pre_state, event)
    if canonical_json(post_state) != canonical_json(expected):
        raise SequentialSemanticError("post-state is not the canonical incremental transition")
    done = str(event["done_object"])
    if done not in set(physically_true_objects):
        raise SequentialSemanticError("completed commitment is not physically witnessed")
    if str(event["pending_object"]) in set(physically_true_objects):
        raise SequentialSemanticError("pending commitment was already physically complete")
    by_id = _commitment_map(post_state)
    if by_id[goal_commitment_id(done)]["lifecycle_status"] != "satisfied":
        raise SequentialSemanticError("completed progress was not preserved")
    return compile_directive(post_state)


def sparse_oracle_proposal(event: Mapping[str, Any], *, neutral: bool) -> dict[str, Any]:
    replacement = event["event_type"] == "replace_pending_goal"
    proposal = {
        "event_id": event["event_id"],
        "operation": (
            "N01" if neutral and replacement else
            "N02" if neutral else
            "Override" if replacement else "Expire"
        ),
        "patch_id": f"sequential:{event['event_id']}:{'neutral' if neutral else 'cope'}",
        "target_id": event["target_commitment_id"],
        "base_version": int(event["valid_from_state_version"]),
    }
    if replacement:
        proposal["replacement_id"] = goal_commitment_id(str(event["replacement_object"]))
    return proposal


def parse_sparse_proposal(
    proposal: Any,
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    neutral: bool,
) -> dict[str, Any]:
    validate_event_against_state(state, event)
    replacement = event["event_type"] == "replace_pending_goal"
    required = {"event_id", "operation", "patch_id", "target_id", "base_version"}
    if replacement:
        required.add("replacement_id")
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise SequentialSemanticError("sparse proposal fields are noncanonical")
    expected_operation = (
        "N01" if neutral and replacement else
        "N02" if neutral else
        "Override" if replacement else "Expire"
    )
    if proposal.get("operation") != expected_operation:
        raise SequentialSemanticError("sparse operation is wrong")
    if proposal.get("event_id") != event["event_id"]:
        raise SequentialSemanticError("sparse event ID is wrong")
    if int(proposal.get("base_version", -1)) != int(state["state_version"]):
        raise SequentialSemanticError("sparse base version is stale")
    if proposal.get("target_id") != event["target_commitment_id"]:
        raise SequentialSemanticError("sparse target is wrong")
    if replacement and proposal.get("replacement_id") != goal_commitment_id(
        str(event["replacement_object"])
    ):
        raise SequentialSemanticError("sparse replacement is wrong")
    parsed = copy.deepcopy(dict(proposal))
    if neutral:
        parsed["operation"] = "Override" if replacement else "Expire"
    return parsed


def _typed_slot(
    object_name: str,
    *,
    event_id: str,
    parent: ConstraintSlot | None = None,
) -> ConstraintSlot:
    identifier = goal_commitment_id(object_name)
    return ConstraintSlot(
        slot_id=identifier,
        constraint_type="task_goal",
        content={"predicate": "in", "arguments": [object_name, RECEPTACLE]},
        source="task",
        mode="active",
        priority=100,
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=parent.slot_id if parent else None,
        overrides_slot_ids=(parent.slot_id,) if parent else (),
        lineage=parent.lineage + (identifier,) if parent else (identifier,),
        metadata={"semantic_role": "sequential_task_goal_commitment"},
    )


def initialize_typed_sequence_state(
    *, sequence_id: str, done_object: str, pending_object: str
) -> ConstraintState:
    genesis = f"sequential:{sequence_id}:genesis"
    state = ConstraintState.empty(f"sequential:{sequence_id}")
    patch = Patch(
        patch_id=f"{genesis}:trusted-loader",
        event_id=genesis,
        reason="load witnessed persistent task commitments",
        operations=(
            Insert("load-done", _typed_slot(done_object, event_id=genesis)),
            Insert("load-pending", _typed_slot(pending_object, event_id=genesis)),
        ),
        generator="trusted-sequential-loader",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    result = apply_patch(state, patch, PatchContext.trusted("trusted-sequential-loader"))
    if not result.accepted:
        raise SequentialSemanticError("typed sequence genesis was rejected")
    return result.state


def execute_typed_sparse_transition(
    typed_state: ConstraintState,
    logical_state: Mapping[str, Any],
    event: Mapping[str, Any],
    proposal: Any,
    *,
    neutral: bool,
    physically_true_objects: Sequence[str],
) -> tuple[ConstraintState, dict[str, Any], dict[str, Any], str]:
    parsed = parse_sparse_proposal(proposal, logical_state, event, neutral=neutral)
    if typed_state.revision != int(logical_state["state_version"]):
        raise SequentialSemanticError("typed and logical revisions diverged")
    target_id = str(parsed["target_id"])
    target = typed_state.get_slot(target_id)
    if target.mode.value != "active":
        raise SequentialSemanticError("typed target is not active")
    if parsed["operation"] == "Override":
        replacement = _typed_slot(
            str(event["replacement_object"]),
            event_id=str(event["event_id"]),
            parent=target,
        )
        operation = Override(
            f"{parsed['patch_id']}:operation",
            target_id,
            replacement,
            "authorized sequential replacement",
        )
    else:
        operation = Expire(
            f"{parsed['patch_id']}:operation",
            target_id,
            "authorized sequential cancellation",
        )
    patch = Patch(
        patch_id=str(parsed["patch_id"]),
        event_id=str(parsed["event_id"]),
        reason="provider-selected persistent semantic transition",
        operations=(operation,),
        generator="sequential-live-provider",
        input_state_hash=typed_state.state_hash,
        created_at=int(logical_state["state_version"]),
        metadata={"provider_called": False, "oracle_fixture": True},
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
        task_progress={"physically_true_objects": list(physically_true_objects)},
        metadata={"sequential_capability_gate": True},
    )
    transitioned = apply_patch(typed_state, patch, context)
    if not transitioned.accepted:
        raise SequentialSemanticError(
            f"typed transition rejected: {transitioned.rejection_code}:"
            f"{transitioned.rejection_reason}"
        )
    candidate = build_expected_next_state(logical_state, event)
    directive = validate_sequence_transition(
        logical_state, candidate, event, physically_true_objects
    )
    receipt = {
        "accepted": True,
        "revision_before": typed_state.revision,
        "revision_after": transitioned.state.revision,
        "before_hash": transitioned.before_hash,
        "after_hash": transitioned.after_hash,
        "typed_state_before": serialize_state(typed_state),
        "typed_state_after": serialize_state(transitioned.state),
        "audit_record": thaw_json(transitioned.audit_record),
    }
    return transitioned.state, candidate, receipt, directive


def fsr_oracle_proposal(expected: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(expected[key]) for key in SEMANTIC_FIELDS}


def materialize_fsr_proposal(
    proposal: Any,
    pre_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], str]:
    if not isinstance(proposal, Mapping) or set(proposal) != SEMANTIC_FIELDS:
        raise SequentialSemanticError("FSR-PC proposal is not one complete semantic state")
    candidate = copy.deepcopy(dict(proposal))
    expected = build_expected_next_state(pre_state, event)
    for key in STATE_FIELDS - SEMANTIC_FIELDS:
        candidate[key] = copy.deepcopy(expected[key])
    directive = validate_sequence_transition(
        pre_state, candidate, event, physically_true_objects
    )
    return candidate, directive


def full_replan_oracle_proposal(
    expected: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    remaining = [str(step["arguments"][0]) for step in expected["plan"]]
    retired = [
        str(row["id"])
        for row in expected["commitments"]
        if row["lifecycle_status"] in {"superseded", "cancelled"}
    ]
    return {
        "schema_version": "full-replan-v1",
        "event_id": event["event_id"],
        "base_version": int(event["valid_from_state_version"]),
        "completed_facts": [_predicate(str(event["done_object"]))],
        "remaining_ordered_objects": remaining,
        "retired_commitment_ids": retired,
    }


def materialize_full_replan_proposal(
    proposal: Any,
    pre_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], str]:
    required = {
        "schema_version",
        "event_id",
        "base_version",
        "completed_facts",
        "remaining_ordered_objects",
        "retired_commitment_ids",
    }
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise SequentialSemanticError("full-replan proposal fields are noncanonical")
    expected = build_expected_next_state(pre_state, event)
    oracle_shape = full_replan_oracle_proposal(expected, event)
    if canonical_json(proposal) != canonical_json(oracle_shape):
        raise SequentialSemanticError("full replan does not encode the canonical remaining task")
    directive = validate_sequence_transition(
        pre_state, expected, event, physically_true_objects
    )
    return expected, directive


def sequence_state_hash(state: Mapping[str, Any]) -> str:
    return stable_hash(state)
