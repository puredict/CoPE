"""Occurrence-addressed recurring commitment transitions.

This development schema is intentionally separate from the frozen sequential
formal-v2 schema. Predicate arguments identify what is required; occurrence
IDs identify which temporal commitment record an event edits.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from cope.compact_tx import execute_compact_transaction, parse_proposal
from cope.operations import apply_patch
from cope.schema import ConstraintSlot, ConstraintState, Expire, Insert, Override, Patch, PatchContext
from cope.semantic_replacement import ALLOWED_OBJECTS, RECEPTACLE, goal_commitment_id
from cope.serialization import serialize_state, thaw_json
from cope.types import canonical_json, stable_hash


SCHEMA = "occurrence-persistent-state-v1"
STATE_FIELDS = {
    "schema_version", "state_version", "current_goal", "entities",
    "commitments", "progress_ledger", "plan", "pending_restorations",
    "evidence_versions",
}
SEMANTIC_FIELDS = {
    "current_goal", "entities", "commitments", "progress_ledger", "plan",
    "pending_restorations",
}


class OccurrenceSemanticError(ValueError):
    pass


def _object(value: str) -> str:
    if value not in ALLOWED_OBJECTS:
        raise OccurrenceSemanticError(f"unknown basket object {value!r}")
    return value


def occurrence_id(object_name: str, occurrence: int) -> str:
    name = _object(object_name)
    if isinstance(occurrence, bool) or int(occurrence) < 1:
        raise OccurrenceSemanticError("occurrence must be a positive integer")
    return f"{goal_commitment_id(name)}@{int(occurrence)}"


def _predicate(object_name: str) -> dict[str, Any]:
    return {"predicate": "in", "arguments": [object_name, RECEPTACLE]}


def _commitment(
    object_name: str, occurrence: int, *, status: str, valid_from: str,
    valid_until: str = "task_end", override_links: Sequence[str] = (),
    supersession_links: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "id": occurrence_id(object_name, occurrence),
        "occurrence": int(occurrence),
        "type": "task_goal", "predicate": "in",
        "grounding": [object_name, RECEPTACLE],
        "lifecycle_status": status, "source": "task_owner",
        "owner": "task_owner", "authority": 100,
        "valid_from": valid_from, "valid_until": valid_until,
        "dependencies": [], "support_links": [],
        "override_links": list(override_links),
        "supersession_links": list(supersession_links),
    }


def _plan_step(object_name: str, occurrence: int, done_id: str) -> dict[str, Any]:
    identifier = occurrence_id(object_name, occurrence)
    return {
        "step_id": f"place-{identifier}", "skill": "place_in",
        "arguments": [object_name, RECEPTACLE], "status": "pending",
        "preconditions": [], "effects": [_predicate(object_name)],
        "dependencies": [done_id], "commitment_occurrence_id": identifier,
    }


def _commitments(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("commitments")
    if not isinstance(rows, list):
        raise OccurrenceSemanticError("commitments must be a list")
    mapped = {
        str(row.get("id")): row for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(mapped) != len(rows):
        raise OccurrenceSemanticError("commitments contain malformed or duplicate IDs")
    return mapped


def build_initial_state(
    *, sequence_id: str, done_object: str, pending_object: str,
    available_objects: Sequence[str], world_version: int,
) -> dict[str, Any]:
    done, pending = _object(done_object), _object(pending_object)
    available = tuple(dict.fromkeys(_object(item) for item in available_objects))
    if done == pending or done not in available or pending not in available:
        raise OccurrenceSemanticError("initial sibling objects are invalid")
    genesis = f"occurrence:{sequence_id}:genesis"
    done_id = occurrence_id(done, 1)
    return {
        "schema_version": SCHEMA, "state_version": 1,
        "current_goal": {"all": [_predicate(done), _predicate(pending)]},
        "entities": [
            *[{"id": item, "kind": "object"} for item in available],
            {"id": RECEPTACLE, "kind": "region"},
        ],
        "commitments": [
            _commitment(done, 1, status="satisfied", valid_from=genesis),
            _commitment(pending, 1, status="active", valid_from=genesis),
        ],
        "progress_ledger": [{
            "milestone_id": done_id, "achieved": True,
            "physically_valid": True, "still_goal_relevant": True,
        }],
        "plan": [_plan_step(pending, 1, done_id)],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": genesis, "world_version": int(world_version),
            "input_state_version": 0,
        },
    }


def active_pending(state: Mapping[str, Any], done_object: str) -> dict[str, Any]:
    rows = [
        row for row in state.get("commitments", [])
        if isinstance(row, Mapping) and row.get("lifecycle_status") == "active"
        and row.get("grounding", [None])[0] != done_object
    ]
    if len(rows) != 1:
        raise OccurrenceSemanticError(f"expected one active pending occurrence, found {len(rows)}")
    return dict(rows[0])


def build_event(
    state: Mapping[str, Any], *, sequence_id: str, step_index: int,
    done_object: str, event_type: str, replacement_object: str | None,
    replacement_occurrence: int | None, world_version: int,
) -> dict[str, Any]:
    source = active_pending(state, done_object)
    if event_type not in {"replace_pending_goal", "cancel_pending_goal"}:
        raise OccurrenceSemanticError("unsupported event type")
    event = {
        "event_id": f"occurrence:{sequence_id}:step{step_index}",
        "event_type": event_type, "issuer": "task_owner", "authority": 100,
        "step_index": int(step_index), "target_commitment_id": source["id"],
        "operation": "override" if event_type == "replace_pending_goal" else "cancel",
        "done_object": done_object, "pending_object": source["grounding"][0],
        "pending_occurrence": int(source["occurrence"]),
        "valid_from_state_version": int(state["state_version"]),
        "world_version": int(world_version),
    }
    if event_type == "replace_pending_goal":
        if replacement_object is None or replacement_occurrence is None:
            raise OccurrenceSemanticError("replacement occurrence is missing")
        replacement = _object(replacement_object)
        event.update({
            "replacement_object": replacement,
            "replacement_occurrence": int(replacement_occurrence),
            "replacement_commitment_id": occurrence_id(replacement, replacement_occurrence),
            "replacement_target": RECEPTACLE,
        })
    elif replacement_object is not None or replacement_occurrence is not None:
        raise OccurrenceSemanticError("cancellation must not name a replacement")
    return event


def validate_event(state: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    if set(state) != STATE_FIELDS or state.get("schema_version") != SCHEMA:
        raise OccurrenceSemanticError("pre-state fields or schema are noncanonical")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise OccurrenceSemanticError("event is unauthorized")
    if int(event.get("valid_from_state_version", -1)) != int(state["state_version"]):
        raise OccurrenceSemanticError("event base revision is stale")
    source = active_pending(state, str(event.get("done_object")))
    if event.get("target_commitment_id") != source["id"]:
        raise OccurrenceSemanticError("event targets the wrong occurrence")
    if event.get("pending_object") != source["grounding"][0] or int(
        event.get("pending_occurrence", -1)
    ) != int(source["occurrence"]):
        raise OccurrenceSemanticError("event pending occurrence is mismatched")
    if event.get("event_type") == "replace_pending_goal":
        expected_id = occurrence_id(
            str(event.get("replacement_object")), int(event.get("replacement_occurrence", -1))
        )
        if event.get("replacement_commitment_id") != expected_id:
            raise OccurrenceSemanticError("replacement occurrence ID is mismatched")
        if expected_id in _commitments(state):
            raise OccurrenceSemanticError("replacement occurrence already exists")
    elif event.get("event_type") != "cancel_pending_goal":
        raise OccurrenceSemanticError("unknown event family")


def expected_next_state(state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    validate_event(state, event)
    out = copy.deepcopy(dict(state))
    records = _commitments(out)
    source = records[str(event["target_commitment_id"])]
    source["valid_until"] = str(event["event_id"])
    source["lifecycle_status"] = (
        "superseded" if event["event_type"] == "replace_pending_goal" else "cancelled"
    )
    done = str(event["done_object"])
    done_rows = [
        row for row in out["commitments"]
        if row["grounding"][0] == done and row["lifecycle_status"] == "satisfied"
    ]
    if len(done_rows) != 1:
        raise OccurrenceSemanticError("satisfied done occurrence is missing")
    if event["event_type"] == "replace_pending_goal":
        replacement = str(event["replacement_object"])
        occurrence = int(event["replacement_occurrence"])
        replacement_id = str(event["replacement_commitment_id"])
        source["supersession_links"] = [replacement_id]
        out["commitments"].append(
            _commitment(
                replacement, occurrence, status="active",
                valid_from=str(event["event_id"]), override_links=(source["id"],),
            )
        )
        out["current_goal"] = {"all": [_predicate(done), _predicate(replacement)]}
        out["plan"] = [_plan_step(replacement, occurrence, done_rows[0]["id"])]
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
    if state["plan"] == []:
        return "HALT"
    if not isinstance(state["plan"], list) or len(state["plan"]) != 1:
        raise OccurrenceSemanticError("state plan is noncanonical")
    step = state["plan"][0]
    if step.get("skill") != "place_in" or step.get("status") != "pending":
        raise OccurrenceSemanticError("plan step is noncanonical")
    return f"place_in({step['arguments'][0]}, {step['arguments'][1]})"


def validate_transition(
    pre_state: Mapping[str, Any], post_state: Mapping[str, Any],
    event: Mapping[str, Any], physically_true_objects: Sequence[str],
) -> str:
    expected = expected_next_state(pre_state, event)
    if canonical_json(post_state) != canonical_json(expected):
        raise OccurrenceSemanticError("post-state is not the canonical occurrence transition")
    done = str(event["done_object"])
    if done not in set(physically_true_objects):
        raise OccurrenceSemanticError("completed commitment is not physically witnessed")
    return compile_directive(post_state)


def cope_oracle(event: Mapping[str, Any]) -> dict[str, Any]:
    replacement = event["event_type"] == "replace_pending_goal"
    out = {
        "event_id": event["event_id"],
        "operation": "Override" if replacement else "Expire",
        "patch_id": f"occurrence:{event['event_id']}:cope",
        "target_id": event["target_commitment_id"],
        "base_version": int(event["valid_from_state_version"]),
    }
    if replacement:
        out["replacement_id"] = event["replacement_commitment_id"]
    return out


def _typed_slot(
    object_name: str, occurrence: int, *, event_id: str,
    parent: ConstraintSlot | None = None,
) -> ConstraintSlot:
    identifier = occurrence_id(object_name, occurrence)
    return ConstraintSlot(
        slot_id=identifier, constraint_type="task_goal",
        content={
            "predicate": "in", "arguments": [object_name, RECEPTACLE],
            "occurrence": int(occurrence),
        },
        source="task", mode="active", priority=100,
        created_event_id=event_id, last_updated_event_id=event_id,
        parent_slot_id=parent.slot_id if parent else None,
        overrides_slot_ids=(parent.slot_id,) if parent else (),
        lineage=parent.lineage + (identifier,) if parent else (identifier,),
        metadata={"semantic_role": "occurrence_addressed_task_commitment"},
    )


def initialize_typed(
    *, sequence_id: str, done_object: str, pending_object: str,
) -> ConstraintState:
    genesis = f"occurrence:{sequence_id}:genesis"
    state = ConstraintState.empty(f"occurrence:{sequence_id}")
    patch = Patch(
        patch_id=f"{genesis}:loader", event_id=genesis,
        reason="load occurrence-addressed commitments",
        operations=(
            Insert("load-done", _typed_slot(done_object, 1, event_id=genesis)),
            Insert("load-pending", _typed_slot(pending_object, 1, event_id=genesis)),
        ),
        generator="trusted-occurrence-loader", input_state_hash=state.state_hash,
        created_at=0,
    )
    result = apply_patch(state, patch, PatchContext.trusted("trusted-occurrence-loader"))
    if not result.accepted:
        raise OccurrenceSemanticError("typed occurrence genesis was rejected")
    return result.state


def materialize_cope(
    proposal: Any, typed_state: ConstraintState, logical_state: Mapping[str, Any],
    event: Mapping[str, Any], physically_true_objects: Sequence[str],
) -> tuple[ConstraintState, dict[str, Any], dict[str, Any], str]:
    validate_event(logical_state, event)
    replacement = event["event_type"] == "replace_pending_goal"
    required = {"event_id", "operation", "patch_id", "target_id", "base_version"}
    if replacement:
        required.add("replacement_id")
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise OccurrenceSemanticError("CoPE proposal fields are noncanonical")
    if proposal.get("event_id") != event["event_id"] or proposal.get("target_id") != event["target_commitment_id"]:
        raise OccurrenceSemanticError("CoPE proposal identity is wrong")
    if int(proposal.get("base_version", -1)) != int(logical_state["state_version"]):
        raise OccurrenceSemanticError("CoPE proposal revision is stale")
    expected_operation = "Override" if replacement else "Expire"
    if proposal.get("operation") != expected_operation:
        raise OccurrenceSemanticError("CoPE operation is wrong")
    if typed_state.revision != int(logical_state["state_version"]):
        raise OccurrenceSemanticError("typed and logical revisions diverged")
    target = typed_state.get_slot(str(proposal["target_id"]))
    if replacement:
        if proposal.get("replacement_id") != event["replacement_commitment_id"]:
            raise OccurrenceSemanticError("CoPE replacement occurrence is wrong")
        replacement_slot = _typed_slot(
            str(event["replacement_object"]), int(event["replacement_occurrence"]),
            event_id=str(event["event_id"]), parent=target,
        )
        operation = Override(
            f"{proposal['patch_id']}:operation", target.slot_id,
            replacement_slot, "authorized recurrence",
        )
    else:
        operation = Expire(
            f"{proposal['patch_id']}:operation", target.slot_id,
            "authorized occurrence cancellation",
        )
    patch = Patch(
        patch_id=str(proposal["patch_id"]), event_id=str(proposal["event_id"]),
        reason="authorized occurrence replacement",
        operations=(operation,),
        generator="occurrence-gate", input_state_hash=typed_state.state_hash,
        created_at=int(logical_state["state_version"]),
    )
    context = PatchContext(
        actor="task_owner", authority_priority=100, authorized_sources=("task",),
        event_source="oracle", information_budget=0, policy_step_budget=0,
        high_level_call_count=0, pair_key={"event_id": str(event["event_id"])},
        task_progress={"physically_true_objects": list(physically_true_objects)},
    )
    result = apply_patch(typed_state, patch, context)
    if not result.accepted:
        raise OccurrenceSemanticError(f"typed occurrence transition rejected: {result.rejection_code}")
    candidate = expected_next_state(logical_state, event)
    directive = validate_transition(logical_state, candidate, event, physically_true_objects)
    receipt = {
        "accepted": True, "before_hash": result.before_hash,
        "after_hash": result.after_hash,
        "typed_state_before": serialize_state(typed_state),
        "typed_state_after": serialize_state(result.state),
        "audit_record": thaw_json(result.audit_record),
    }
    return result.state, candidate, receipt, directive


def neutral_oracle(
    pre_state: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any],
) -> dict[str, Any]:
    writes: list[dict[str, Any]] = []
    for root in ("current_goal", "plan", "pending_restorations"):
        if canonical_json(pre_state[root]) != canonical_json(expected[root]):
            writes.append({"op": "replace", "path": f"/{root}", "value": copy.deepcopy(expected[root])})
    before = {row["id"]: row for row in pre_state["commitments"]}
    for record in expected["commitments"]:
        identifier = record["id"]
        if identifier not in before:
            writes.append({"op": "add", "path": f"/commitments/+/{identifier}", "value": copy.deepcopy(record)})
        else:
            for field, value in record.items():
                if canonical_json(before[identifier][field]) != canonical_json(value):
                    writes.append({"op": "replace", "path": f"/commitments/{identifier}/{field}", "value": copy.deepcopy(value)})
    return {
        "schema_version": "generic-compact-transaction-v1",
        "base_version": int(pre_state["state_version"]),
        "event_id": event["event_id"], "writes": writes,
    }


def materialize_neutral(
    proposal: Any, pre_state: Mapping[str, Any], event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    parsed = parse_proposal(proposal, pre_state, event)
    expected = expected_next_state(pre_state, event)

    def finalize(staged: Mapping[str, Any], _event: Mapping[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(dict(staged))
        for key in STATE_FIELDS - SEMANTIC_FIELDS:
            out[key] = copy.deepcopy(expected[key])
        return out

    result = execute_compact_transaction(
        parsed, pre_state, event,
        lambda staged, _state, current: validate_transition(
            pre_state, staged, current, physically_true_objects
        ),
        trusted_finalize=finalize,
    )
    return result.post_state, result.receipt, result.directive


def governed_oracle(
    pre_state: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any],
) -> dict[str, Any]:
    before = {row["id"]: row for row in pre_state["commitments"]}
    after = {row["id"]: row for row in expected["commitments"]}
    changed = sorted(
        identifier for identifier, record in after.items()
        if identifier not in before or canonical_json(before[identifier]) != canonical_json(record)
    )
    return {
        "schema_version": "governed-delta-v1", "event_id": event["event_id"],
        "read_revision": int(pre_state["state_version"]), "proposal_type": "repair",
        "affected_scope": changed,
        "forest_delta": [{"node_id": identifier, "after": copy.deepcopy(after[identifier])} for identifier in changed],
        "blackboard_delta": {
            key: copy.deepcopy(expected[key])
            for key in ("current_goal", "plan", "pending_restorations")
        },
    }


def materialize_governed(
    proposal: Any, pre_state: Mapping[str, Any], event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    validate_event(pre_state, event)
    required = {
        "schema_version", "event_id", "read_revision", "proposal_type",
        "affected_scope", "forest_delta", "blackboard_delta",
    }
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise OccurrenceSemanticError("governed proposal fields are noncanonical")
    if proposal.get("schema_version") != "governed-delta-v1" or proposal.get("event_id") != event["event_id"]:
        raise OccurrenceSemanticError("governed proposal identity is wrong")
    if int(proposal.get("read_revision", -1)) != int(pre_state["state_version"]):
        raise OccurrenceSemanticError("governed proposal revision is stale")
    if proposal.get("proposal_type") != "repair":
        raise OccurrenceSemanticError("governed proposal type is wrong")
    scope = proposal.get("affected_scope")
    delta = proposal.get("forest_delta")
    if not isinstance(scope, list) or not isinstance(delta, list):
        raise OccurrenceSemanticError("governed scope or delta is malformed")
    records = {
        item.get("node_id"): copy.deepcopy(item.get("after"))
        for item in delta if isinstance(item, Mapping) and set(item) == {"node_id", "after"}
    }
    if set(scope) != set(records) or len(records) != len(delta):
        raise OccurrenceSemanticError("governed scope and records disagree")
    staged = copy.deepcopy(dict(pre_state))
    positions = {row["id"]: index for index, row in enumerate(staged["commitments"])}
    for identifier in scope:
        record = records[identifier]
        if not isinstance(record, dict) or record.get("id") != identifier:
            raise OccurrenceSemanticError("governed record identity is wrong")
        if identifier in positions:
            staged["commitments"][positions[identifier]] = record
        else:
            staged["commitments"].append(record)
    blackboard = proposal.get("blackboard_delta")
    if not isinstance(blackboard, Mapping) or set(blackboard) != {"current_goal", "plan", "pending_restorations"}:
        raise OccurrenceSemanticError("governed blackboard is malformed")
    for field in blackboard:
        staged[field] = copy.deepcopy(blackboard[field])
    expected = expected_next_state(pre_state, event)
    for field in STATE_FIELDS - SEMANTIC_FIELDS:
        staged[field] = copy.deepcopy(expected[field])
    directive = validate_transition(pre_state, staged, event, physically_true_objects)
    receipt = {
        "accepted": True, "before_hash": stable_hash(pre_state),
        "after_hash": stable_hash(staged), "affected_scope": list(scope),
    }
    return staged, receipt, directive


def fsr_oracle(expected: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(expected[key]) for key in SEMANTIC_FIELDS}


def materialize_fsr(
    proposal: Any, pre_state: Mapping[str, Any], event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], str]:
    if not isinstance(proposal, Mapping) or set(proposal) != SEMANTIC_FIELDS:
        raise OccurrenceSemanticError("FSR proposal is not one complete semantic state")
    candidate = copy.deepcopy(dict(proposal))
    expected = expected_next_state(pre_state, event)
    for key in STATE_FIELDS - SEMANTIC_FIELDS:
        candidate[key] = copy.deepcopy(expected[key])
    return candidate, validate_transition(pre_state, candidate, event, physically_true_objects)


def full_replan_oracle(expected: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "occurrence-full-replan-v1",
        "event_id": event["event_id"],
        "base_version": int(event["valid_from_state_version"]),
        "completed_facts": [_predicate(str(event["done_object"]))],
        "remaining_ordered_occurrences": [step["commitment_occurrence_id"] for step in expected["plan"]],
        "retired_commitment_occurrences": [
            row["id"] for row in expected["commitments"]
            if row["lifecycle_status"] in {"superseded", "cancelled"}
        ],
    }


def materialize_full_replan(
    proposal: Any, pre_state: Mapping[str, Any], event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], str]:
    expected = expected_next_state(pre_state, event)
    oracle = full_replan_oracle(expected, event)
    if not isinstance(proposal, Mapping) or canonical_json(proposal) != canonical_json(oracle):
        raise OccurrenceSemanticError("full replan is not occurrence-canonical")
    return expected, validate_transition(pre_state, expected, event, physically_true_objects)
