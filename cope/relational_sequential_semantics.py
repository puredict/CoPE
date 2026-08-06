"""Full-atom persistent commitment semantics for relational task sequences.

This module is intentionally separate from the frozen basket-specific formal
runner.  A commitment identity binds predicate, object, and target, allowing a
later event to replace only the target without inventing a task-specific
operation type.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
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
from cope.serialization import serialize_state, thaw_json
from cope.types import canonical_json, stable_hash


SCHEMA = "relational-sequential-persistent-state-v1"
TASK_SUITE = "libero_10"
TASK_ID = 6
TASK_NAME = (
    "LIVING_ROOM_SCENE6_put_the_white_mug_on_the_plate_and_put_the_"
    "chocolate_pudding_to_the_right_of_the_plate"
)

PORCELAIN_MUG = "porcelain_mug_1"
PUDDING = "chocolate_pudding_1"
RED_MUG = "red_coffee_mug_1"
PLATE = "plate_1"
RIGHT_REGION = "living_room_table_plate_right_region"
LEFT_REGION = "living_room_table_plate_left_region"

ALLOWED_PREDICATES = frozenset({"on"})
ALLOWED_OBJECTS = frozenset({PORCELAIN_MUG, PUDDING, RED_MUG})
ALLOWED_TARGETS = frozenset({PLATE, RIGHT_REGION, LEFT_REGION})
STATE_FIELDS = {
    "schema_version",
    "state_version",
    "current_goal",
    "entities",
    "commitments",
    "progress_ledger",
    "plan",
    "pending_restorations",
    "evidence_versions",
}


class RelationalSemanticError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class RelationalAtom:
    predicate: str
    object_name: str
    target_name: str

    def __post_init__(self) -> None:
        predicate = str(self.predicate).strip().lower()
        object_name = str(self.object_name).strip()
        target_name = str(self.target_name).strip()
        if predicate not in ALLOWED_PREDICATES:
            raise RelationalSemanticError(f"unknown predicate {predicate!r}")
        if object_name not in ALLOWED_OBJECTS:
            raise RelationalSemanticError(f"unknown task object {object_name!r}")
        if target_name not in ALLOWED_TARGETS:
            raise RelationalSemanticError(f"unknown task target {target_name!r}")
        if object_name == PORCELAIN_MUG and target_name != PLATE:
            raise RelationalSemanticError("porcelain mug is licensed only for plate_1")
        if object_name in {PUDDING, RED_MUG} and target_name == PLATE:
            raise RelationalSemanticError("replacement objects are licensed only for table regions")
        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "object_name", object_name)
        object.__setattr__(self, "target_name", target_name)

    @property
    def commitment_id(self) -> str:
        return f"goal:{self.predicate}:{self.object_name}:{self.target_name}"

    def to_predicate(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "arguments": [self.object_name, self.target_name],
        }

    def to_dict(self) -> dict[str, str]:
        return {
            "predicate": self.predicate,
            "object": self.object_name,
            "target": self.target_name,
        }


DONE_ATOM = RelationalAtom("on", PORCELAIN_MUG, PLATE)
ORIGINAL_PENDING_ATOM = RelationalAtom("on", PUDDING, RIGHT_REGION)
EVENT1_ATOM = RelationalAtom("on", RED_MUG, RIGHT_REGION)
RETARGET_ATOM = RelationalAtom("on", RED_MUG, LEFT_REGION)


def atom_from_mapping(value: Mapping[str, Any]) -> RelationalAtom:
    if not isinstance(value, Mapping) or set(value) != {"predicate", "object", "target"}:
        raise RelationalSemanticError("atom fields are noncanonical")
    return RelationalAtom(
        str(value["predicate"]), str(value["object"]), str(value["target"])
    )


def _commitment(
    atom: RelationalAtom,
    *,
    status: str,
    valid_from: str,
    valid_until: str = "task_end",
    override_links: Sequence[str] = (),
    supersession_links: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "id": atom.commitment_id,
        "type": "task_goal",
        "predicate": atom.predicate,
        "grounding": [atom.object_name, atom.target_name],
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


def _plan_step(atom: RelationalAtom, done_id: str) -> dict[str, Any]:
    return {
        "step_id": f"place-{atom.commitment_id}",
        "skill": f"place_{atom.predicate}",
        "arguments": [atom.object_name, atom.target_name],
        "status": "pending",
        "preconditions": [],
        "effects": [atom.to_predicate()],
        "dependencies": [done_id],
    }


def build_initial_state(*, sequence_id: str, world_version: int) -> dict[str, Any]:
    genesis = f"relational:{sequence_id}:genesis"
    return {
        "schema_version": SCHEMA,
        "state_version": 1,
        "current_goal": {
            "all": [DONE_ATOM.to_predicate(), ORIGINAL_PENDING_ATOM.to_predicate()]
        },
        "entities": [
            {"id": PORCELAIN_MUG, "kind": "object"},
            {"id": PUDDING, "kind": "object"},
            {"id": RED_MUG, "kind": "object"},
            {"id": PLATE, "kind": "object"},
            {"id": RIGHT_REGION, "kind": "region"},
            {"id": LEFT_REGION, "kind": "region"},
        ],
        "commitments": [
            _commitment(DONE_ATOM, status="satisfied", valid_from=genesis),
            _commitment(ORIGINAL_PENDING_ATOM, status="active", valid_from=genesis),
        ],
        "progress_ledger": [
            {
                "milestone_id": DONE_ATOM.commitment_id,
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [_plan_step(ORIGINAL_PENDING_ATOM, DONE_ATOM.commitment_id)],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": genesis,
            "world_version": int(world_version),
            "input_state_version": 0,
        },
    }


def _commitment_map(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("commitments")
    if not isinstance(rows, list):
        raise RelationalSemanticError("commitments must be a list")
    mapped = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(mapped) != len(rows):
        raise RelationalSemanticError("commitments contain malformed or duplicate IDs")
    return mapped


def active_chain_tip(state: Mapping[str, Any]) -> RelationalAtom:
    rows = [
        row
        for row in _commitment_map(state).values()
        if row.get("lifecycle_status") == "active"
        and row.get("id") != DONE_ATOM.commitment_id
    ]
    if len(rows) != 1:
        raise RelationalSemanticError(
            f"expected one active pending commitment, found {len(rows)}"
        )
    row = rows[0]
    return RelationalAtom(
        str(row.get("predicate")),
        str(row.get("grounding", ["", ""])[0]),
        str(row.get("grounding", ["", ""])[1]),
    )


def build_event(
    state: Mapping[str, Any],
    *,
    sequence_id: str,
    step_index: int,
    event_type: str,
    replacement_atom: RelationalAtom | None,
    world_version: int,
) -> dict[str, Any]:
    source = active_chain_tip(state)
    if event_type not in {"replace_pending_goal", "cancel_pending_goal"}:
        raise RelationalSemanticError(f"unsupported event type {event_type!r}")
    event: dict[str, Any] = {
        "event_id": f"relational:{sequence_id}:step{int(step_index)}",
        "event_type": event_type,
        "issuer": "task_owner",
        "authority": 100,
        "step_index": int(step_index),
        "operation": "override" if event_type == "replace_pending_goal" else "cancel",
        "done_commitment_id": DONE_ATOM.commitment_id,
        "target_commitment_id": source.commitment_id,
        "source_atom": source.to_dict(),
        "valid_from_state_version": int(state["state_version"]),
        "world_version": int(world_version),
    }
    if event_type == "replace_pending_goal":
        if replacement_atom is None:
            raise RelationalSemanticError("replacement event lacks replacement atom")
        if replacement_atom == source:
            raise RelationalSemanticError("replacement equals active source atom")
        event["replacement_atom"] = replacement_atom.to_dict()
        event["replacement_commitment_id"] = replacement_atom.commitment_id
    elif replacement_atom is not None:
        raise RelationalSemanticError("cancellation must not name a replacement atom")
    return event


def validate_event_against_state(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    if set(state) != STATE_FIELDS or state.get("schema_version") != SCHEMA:
        raise RelationalSemanticError("pre-state fields or schema are noncanonical")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise RelationalSemanticError("event is unauthorized")
    if int(event.get("valid_from_state_version", -1)) != int(state["state_version"]):
        raise RelationalSemanticError("event base revision is stale")
    if event.get("done_commitment_id") != DONE_ATOM.commitment_id:
        raise RelationalSemanticError("event completed commitment is mismatched")
    source = active_chain_tip(state)
    if atom_from_mapping(event.get("source_atom", {})) != source:
        raise RelationalSemanticError("event source atom is not the active chain tip")
    if event.get("target_commitment_id") != source.commitment_id:
        raise RelationalSemanticError("event target commitment is mismatched")
    if event.get("event_type") == "replace_pending_goal":
        if event.get("operation") != "override":
            raise RelationalSemanticError("replacement operation is mismatched")
        replacement = atom_from_mapping(event.get("replacement_atom", {}))
        if event.get("replacement_commitment_id") != replacement.commitment_id:
            raise RelationalSemanticError("replacement stable ID is mismatched")
        if replacement.commitment_id in _commitment_map(state):
            raise RelationalSemanticError("replacement reuses historical commitment")
    elif event.get("event_type") == "cancel_pending_goal":
        if event.get("operation") != "cancel":
            raise RelationalSemanticError("cancellation operation is mismatched")
        if "replacement_atom" in event or "replacement_commitment_id" in event:
            raise RelationalSemanticError("cancellation contains replacement fields")
    else:
        raise RelationalSemanticError("unknown event family")


def build_expected_next_state(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    validate_event_against_state(state, event)
    out = copy.deepcopy(dict(state))
    source = atom_from_mapping(event["source_atom"])
    source_row = _commitment_map(out)[source.commitment_id]
    source_row["valid_until"] = str(event["event_id"])
    source_row["lifecycle_status"] = (
        "superseded" if event["event_type"] == "replace_pending_goal" else "cancelled"
    )
    if event["event_type"] == "replace_pending_goal":
        replacement = atom_from_mapping(event["replacement_atom"])
        source_row["supersession_links"] = [replacement.commitment_id]
        out["commitments"].append(
            _commitment(
                replacement,
                status="active",
                valid_from=str(event["event_id"]),
                override_links=(source.commitment_id,),
            )
        )
        out["current_goal"] = {
            "all": [DONE_ATOM.to_predicate(), replacement.to_predicate()]
        }
        out["plan"] = [_plan_step(replacement, DONE_ATOM.commitment_id)]
    else:
        out["current_goal"] = {"all": [DONE_ATOM.to_predicate()]}
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
        raise RelationalSemanticError("state must compile to HALT or one pending action")
    step = plan[0]
    arguments = step.get("arguments")
    predicate = str(step.get("skill", "")).removeprefix("place_")
    if (
        step.get("status") != "pending"
        or predicate not in ALLOWED_PREDICATES
        or not isinstance(arguments, list)
        or len(arguments) != 2
    ):
        raise RelationalSemanticError("remaining action is noncanonical")
    atom = RelationalAtom(predicate, str(arguments[0]), str(arguments[1]))
    return f"place_{atom.predicate}({atom.object_name}, {atom.target_name})"


def validate_transition(
    pre_state: Mapping[str, Any],
    post_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_commitment_ids: Sequence[str],
) -> str:
    expected = build_expected_next_state(pre_state, event)
    if canonical_json(post_state) != canonical_json(expected):
        raise RelationalSemanticError("post-state is not the canonical incremental transition")
    truth = set(str(item) for item in physically_true_commitment_ids)
    if DONE_ATOM.commitment_id not in truth:
        raise RelationalSemanticError("completed commitment is not physically witnessed")
    source = atom_from_mapping(event["source_atom"])
    if source.commitment_id in truth:
        raise RelationalSemanticError("pending commitment was already physically complete")
    done_row = _commitment_map(post_state)[DONE_ATOM.commitment_id]
    if done_row["lifecycle_status"] != "satisfied":
        raise RelationalSemanticError("completed progress was not preserved")
    return compile_directive(post_state)


def oracle_sparse_proposal(event: Mapping[str, Any]) -> dict[str, Any]:
    replacement = event["event_type"] == "replace_pending_goal"
    proposal = {
        "event_id": event["event_id"],
        "operation": "Override" if replacement else "Expire",
        "patch_id": f"relational:{event['event_id']}:oracle",
        "target_id": event["target_commitment_id"],
        "base_version": int(event["valid_from_state_version"]),
    }
    if replacement:
        proposal["replacement_id"] = event["replacement_commitment_id"]
    return proposal


def parse_sparse_proposal(
    proposal: Any, state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    validate_event_against_state(state, event)
    replacement = event["event_type"] == "replace_pending_goal"
    fields = {"event_id", "operation", "patch_id", "target_id", "base_version"}
    if replacement:
        fields.add("replacement_id")
    if not isinstance(proposal, Mapping) or set(proposal) != fields:
        raise RelationalSemanticError("sparse proposal fields are noncanonical")
    expected_operation = "Override" if replacement else "Expire"
    if proposal.get("operation") != expected_operation:
        raise RelationalSemanticError("sparse operation is wrong")
    if proposal.get("event_id") != event["event_id"]:
        raise RelationalSemanticError("sparse event ID is wrong")
    if int(proposal.get("base_version", -1)) != int(state["state_version"]):
        raise RelationalSemanticError("sparse base version is stale")
    if proposal.get("target_id") != event["target_commitment_id"]:
        raise RelationalSemanticError("sparse target is wrong")
    if replacement and proposal.get("replacement_id") != event["replacement_commitment_id"]:
        raise RelationalSemanticError("sparse replacement is wrong")
    return copy.deepcopy(dict(proposal))


def _typed_slot(
    atom: RelationalAtom,
    *,
    event_id: str,
    parent: ConstraintSlot | None = None,
) -> ConstraintSlot:
    identifier = atom.commitment_id
    return ConstraintSlot(
        slot_id=identifier,
        constraint_type="task_goal",
        content=atom.to_predicate(),
        source="task",
        mode="active",
        priority=100,
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=parent.slot_id if parent else None,
        overrides_slot_ids=(parent.slot_id,) if parent else (),
        lineage=parent.lineage + (identifier,) if parent else (identifier,),
        metadata={"semantic_role": "relational_task_goal_commitment"},
    )


def initialize_typed_state(*, sequence_id: str) -> ConstraintState:
    genesis = f"relational:{sequence_id}:genesis"
    state = ConstraintState.empty(f"relational:{sequence_id}")
    patch = Patch(
        patch_id=f"{genesis}:trusted-loader",
        event_id=genesis,
        reason="load witnessed relational task commitments",
        operations=(
            Insert("load-done", _typed_slot(DONE_ATOM, event_id=genesis)),
            Insert("load-pending", _typed_slot(ORIGINAL_PENDING_ATOM, event_id=genesis)),
        ),
        generator="trusted-relational-loader",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    result = apply_patch(state, patch, PatchContext.trusted("trusted-relational-loader"))
    if not result.accepted:
        raise RelationalSemanticError("typed relational genesis was rejected")
    return result.state


def execute_typed_transition(
    typed_state: ConstraintState,
    logical_state: Mapping[str, Any],
    event: Mapping[str, Any],
    proposal: Any,
    *,
    physically_true_commitment_ids: Sequence[str],
) -> tuple[ConstraintState, dict[str, Any], dict[str, Any], str]:
    parsed = parse_sparse_proposal(proposal, logical_state, event)
    if typed_state.revision != int(logical_state["state_version"]):
        raise RelationalSemanticError("typed and logical revisions diverged")
    target = typed_state.get_slot(str(parsed["target_id"]))
    if target.mode.value != "active":
        raise RelationalSemanticError("typed target is not active")
    if parsed["operation"] == "Override":
        replacement_atom = atom_from_mapping(event["replacement_atom"])
        operation = Override(
            f"{parsed['patch_id']}:operation",
            target.slot_id,
            _typed_slot(replacement_atom, event_id=str(event["event_id"]), parent=target),
            "authorized relational commitment replacement",
        )
    else:
        operation = Expire(
            f"{parsed['patch_id']}:operation",
            target.slot_id,
            "authorized relational commitment cancellation",
        )
    patch = Patch(
        patch_id=str(parsed["patch_id"]),
        event_id=str(parsed["event_id"]),
        reason="persistent relational semantic transition",
        operations=(operation,),
        generator="relational-sequence-provider",
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
        task_progress={
            "physically_true_commitment_ids": list(physically_true_commitment_ids)
        },
        metadata={"relational_capability_gate": True},
    )
    transitioned = apply_patch(typed_state, patch, context)
    if not transitioned.accepted:
        raise RelationalSemanticError(
            f"typed transition rejected: {transitioned.rejection_code}:"
            f"{transitioned.rejection_reason}"
        )
    candidate = build_expected_next_state(logical_state, event)
    directive = validate_transition(
        logical_state, candidate, event, physically_true_commitment_ids
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


def state_hash(state: Mapping[str, Any]) -> str:
    return stable_hash(state)

