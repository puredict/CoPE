"""Persistent sequence semantics with stable IDs over variable-arity atoms."""

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


SCHEMA = "arity-commitment-sequence-v1"
TASK_SUITE = "libero_10"
TASK_ID = 9
YELLOW_MUG = "white_yellow_mug_1"
PORCELAIN_MUG = "porcelain_mug_1"
MICROWAVE = "microwave_1"
HEATING_REGION = "microwave_1_heating_region"
STATE_FIELDS = {
    "schema_version", "state_version", "current_goal", "entities",
    "commitments", "progress_ledger", "plan", "pending_restorations",
    "evidence_versions",
}


class ArityCommitmentError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class CommitmentAtom:
    predicate: str
    arguments: tuple[str, ...]

    def __post_init__(self) -> None:
        predicate = str(self.predicate).strip().lower()
        arguments = tuple(str(value).strip() for value in self.arguments)
        if not predicate or not arguments or any(not value for value in arguments):
            raise ArityCommitmentError("atom predicate and arguments must be nonempty")
        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "arguments", arguments)

    @property
    def commitment_id(self) -> str:
        return ":".join(("goal", self.predicate, *self.arguments))

    def to_dict(self) -> dict[str, Any]:
        return {"predicate": self.predicate, "arguments": list(self.arguments)}


DONE_ATOM = CommitmentAtom("in", (YELLOW_MUG, HEATING_REGION))
PENDING_ATOM = CommitmentAtom("close", (MICROWAVE,))
REPLACEMENT_ATOM = CommitmentAtom("in", (PORCELAIN_MUG, HEATING_REGION))
ALLOWED_ATOMS = frozenset({DONE_ATOM, PENDING_ATOM, REPLACEMENT_ATOM})


def require_allowed(atom: CommitmentAtom) -> CommitmentAtom:
    if atom not in ALLOWED_ATOMS:
        raise ArityCommitmentError(f"atom is not licensed by task contract: {atom!r}")
    return atom


def atom_from_mapping(value: Any) -> CommitmentAtom:
    if not isinstance(value, Mapping) or set(value) != {"predicate", "arguments"}:
        raise ArityCommitmentError("atom fields are noncanonical")
    arguments = value["arguments"]
    if not isinstance(arguments, list):
        raise ArityCommitmentError("atom arguments must be a list")
    return require_allowed(CommitmentAtom(str(value["predicate"]), tuple(arguments)))


def _commitment(
    atom: CommitmentAtom,
    *,
    status: str,
    valid_from: str,
    valid_until: str = "task_end",
    override_links: Sequence[str] = (),
    supersession_links: Sequence[str] = (),
) -> dict[str, Any]:
    atom = require_allowed(atom)
    return {
        "id": atom.commitment_id,
        "type": "task_goal",
        "predicate": atom.predicate,
        "grounding": list(atom.arguments),
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


def _plan_step(atom: CommitmentAtom) -> dict[str, Any]:
    atom = require_allowed(atom)
    skill = "place_in" if atom.predicate == "in" else atom.predicate
    return {
        "step_id": f"execute-{atom.commitment_id}",
        "skill": skill,
        "arguments": list(atom.arguments),
        "status": "pending",
        "preconditions": [],
        "effects": [atom.to_dict()],
        "dependencies": [DONE_ATOM.commitment_id],
    }


def build_initial_state(*, sequence_id: str, world_version: int) -> dict[str, Any]:
    genesis = f"arity:{sequence_id}:genesis"
    return {
        "schema_version": SCHEMA,
        "state_version": 1,
        "current_goal": {"all": [DONE_ATOM.to_dict(), PENDING_ATOM.to_dict()]},
        "entities": [
            {"id": YELLOW_MUG, "kind": "object"},
            {"id": PORCELAIN_MUG, "kind": "object"},
            {"id": MICROWAVE, "kind": "fixture"},
            {"id": HEATING_REGION, "kind": "region"},
        ],
        "commitments": [
            _commitment(DONE_ATOM, status="satisfied", valid_from=genesis),
            _commitment(PENDING_ATOM, status="active", valid_from=genesis),
        ],
        "progress_ledger": [{
            "milestone_id": DONE_ATOM.commitment_id,
            "achieved": True,
            "physically_valid": True,
            "still_goal_relevant": True,
        }],
        "plan": [_plan_step(PENDING_ATOM)],
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
        raise ArityCommitmentError("commitments must be a list")
    mapped = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(mapped) != len(rows):
        raise ArityCommitmentError("malformed or duplicate commitment IDs")
    return mapped


def active_tip(state: Mapping[str, Any]) -> CommitmentAtom:
    active = [
        row for row in _commitment_map(state).values()
        if row.get("lifecycle_status") == "active"
    ]
    if len(active) != 1:
        raise ArityCommitmentError(f"expected one active chain tip, found {len(active)}")
    row = active[0]
    return require_allowed(
        CommitmentAtom(str(row.get("predicate")), tuple(row.get("grounding", ())))
    )


def build_event(
    state: Mapping[str, Any],
    *,
    sequence_id: str,
    step_index: int,
    event_type: str,
    replacement_atom: CommitmentAtom | None,
    world_version: int,
) -> dict[str, Any]:
    source = active_tip(state)
    if event_type not in {"replace_pending_goal", "cancel_pending_goal"}:
        raise ArityCommitmentError(f"unsupported event type {event_type!r}")
    event: dict[str, Any] = {
        "event_id": f"arity:{sequence_id}:step{int(step_index)}",
        "event_type": event_type,
        "issuer": "task_owner",
        "authority": 100,
        "target_commitment_id": source.commitment_id,
        "source_atom": source.to_dict(),
        "operation": "override" if replacement_atom is not None else "cancel",
        "valid_from_state_version": int(state["state_version"]),
        "world_version": int(world_version),
    }
    if event_type == "replace_pending_goal":
        if replacement_atom is None:
            raise ArityCommitmentError("replacement event lacks atom")
        replacement = require_allowed(replacement_atom)
        if replacement == source:
            raise ArityCommitmentError("replacement equals source")
        if replacement.commitment_id in _commitment_map(state):
            raise ArityCommitmentError("replacement reuses historical commitment")
        event["replacement_atom"] = replacement.to_dict()
        event["replacement_commitment_id"] = replacement.commitment_id
    elif replacement_atom is not None:
        raise ArityCommitmentError("cancellation names a replacement")
    return event


def validate_event(state: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    if set(state) != STATE_FIELDS or state.get("schema_version") != SCHEMA:
        raise ArityCommitmentError("pre-state schema or fields are noncanonical")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise ArityCommitmentError("event is unauthorized")
    if int(event.get("valid_from_state_version", -1)) != int(state["state_version"]):
        raise ArityCommitmentError("event base revision is stale")
    source = active_tip(state)
    if atom_from_mapping(event.get("source_atom")) != source:
        raise ArityCommitmentError("event source atom is not active chain tip")
    if event.get("target_commitment_id") != source.commitment_id:
        raise ArityCommitmentError("event target stable ID is wrong")
    if event.get("event_type") == "replace_pending_goal":
        if event.get("operation") != "override":
            raise ArityCommitmentError("replacement operation is wrong")
        replacement = atom_from_mapping(event.get("replacement_atom"))
        if event.get("replacement_commitment_id") != replacement.commitment_id:
            raise ArityCommitmentError("replacement stable ID is wrong")
        if replacement.commitment_id in _commitment_map(state):
            raise ArityCommitmentError("replacement reuses historical commitment")
    elif event.get("event_type") == "cancel_pending_goal":
        if event.get("operation") != "cancel":
            raise ArityCommitmentError("cancellation operation is wrong")
        if "replacement_atom" in event or "replacement_commitment_id" in event:
            raise ArityCommitmentError("cancellation has replacement fields")
    else:
        raise ArityCommitmentError("unknown event family")


def expected_next_state(state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    validate_event(state, event)
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
        out["commitments"].append(_commitment(
            replacement,
            status="active",
            valid_from=str(event["event_id"]),
            override_links=(source.commitment_id,),
        ))
        out["current_goal"] = {"all": [DONE_ATOM.to_dict(), replacement.to_dict()]}
        out["plan"] = [_plan_step(replacement)]
    else:
        out["current_goal"] = {"all": [DONE_ATOM.to_dict()]}
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
        raise ArityCommitmentError("state must compile to one action or HALT")
    step = plan[0]
    args = step.get("arguments")
    if step.get("status") != "pending" or not isinstance(args, list):
        raise ArityCommitmentError("plan step is malformed")
    if step.get("skill") == "place_in" and len(args) == 2:
        return f"place_in({args[0]}, {args[1]})"
    if step.get("skill") == "close" and len(args) == 1:
        return f"close({args[0]})"
    raise ArityCommitmentError("plan skill/arity is unsupported")


def validate_transition(
    pre_state: Mapping[str, Any], post_state: Mapping[str, Any],
    event: Mapping[str, Any], physically_true_ids: Sequence[str],
) -> str:
    expected = expected_next_state(pre_state, event)
    if canonical_json(post_state) != canonical_json(expected):
        raise ArityCommitmentError("post-state is not canonical incremental transition")
    truth = set(str(value) for value in physically_true_ids)
    if DONE_ATOM.commitment_id not in truth:
        raise ArityCommitmentError("completed commitment lacks physical witness")
    if atom_from_mapping(event["source_atom"]).commitment_id in truth:
        raise ArityCommitmentError("pending source was already physically satisfied")
    if _commitment_map(post_state)[DONE_ATOM.commitment_id]["lifecycle_status"] != "satisfied":
        raise ArityCommitmentError("completed progress was not preserved")
    return compile_directive(post_state)


def oracle_proposal(event: Mapping[str, Any]) -> dict[str, Any]:
    replacement = event["event_type"] == "replace_pending_goal"
    value = {
        "event_id": event["event_id"],
        "operation": "Override" if replacement else "Expire",
        "patch_id": f"arity:{event['event_id']}:oracle",
        "target_id": event["target_commitment_id"],
        "base_version": int(event["valid_from_state_version"]),
    }
    if replacement:
        value["replacement_id"] = event["replacement_commitment_id"]
    return value


def parse_proposal(value: Any, state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    validate_event(state, event)
    replacement = event["event_type"] == "replace_pending_goal"
    fields = {"event_id", "operation", "patch_id", "target_id", "base_version"}
    if replacement:
        fields.add("replacement_id")
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ArityCommitmentError("proposal fields are noncanonical")
    expected_operation = "Override" if replacement else "Expire"
    expected_replacement = event.get("replacement_commitment_id")
    if (
        value.get("event_id") != event["event_id"]
        or value.get("operation") != expected_operation
        or value.get("target_id") != event["target_commitment_id"]
        or int(value.get("base_version", -1)) != int(state["state_version"])
        or (replacement and value.get("replacement_id") != expected_replacement)
    ):
        raise ArityCommitmentError("proposal is not event-bound")
    return copy.deepcopy(dict(value))


def _slot(atom: CommitmentAtom, *, event_id: str, parent: ConstraintSlot | None = None) -> ConstraintSlot:
    atom = require_allowed(atom)
    return ConstraintSlot(
        slot_id=atom.commitment_id,
        constraint_type="task_goal",
        content=atom.to_dict(),
        source="task",
        mode="active",
        priority=100,
        created_event_id=event_id,
        last_updated_event_id=event_id,
        parent_slot_id=parent.slot_id if parent else None,
        overrides_slot_ids=(parent.slot_id,) if parent else (),
        lineage=parent.lineage + (atom.commitment_id,) if parent else (atom.commitment_id,),
        metadata={"semantic_role": "variable_arity_task_goal"},
    )


def initialize_typed_state(*, sequence_id: str) -> ConstraintState:
    genesis = f"arity:{sequence_id}:genesis"
    state = ConstraintState.empty(f"arity:{sequence_id}")
    patch = Patch(
        patch_id=f"{genesis}:trusted-loader",
        event_id=genesis,
        reason="load witnessed variable-arity commitments",
        operations=(
            Insert("load-done", _slot(DONE_ATOM, event_id=genesis)),
            Insert("load-pending", _slot(PENDING_ATOM, event_id=genesis)),
        ),
        generator="trusted-arity-loader",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    result = apply_patch(state, patch, PatchContext.trusted("trusted-arity-loader"))
    if not result.accepted:
        raise ArityCommitmentError("typed genesis rejected")
    return result.state


def execute_transition(
    typed_state: ConstraintState, logical_state: Mapping[str, Any],
    event: Mapping[str, Any], proposal: Any, *, physically_true_ids: Sequence[str],
) -> tuple[ConstraintState, dict[str, Any], dict[str, Any], str]:
    parsed = parse_proposal(proposal, logical_state, event)
    if typed_state.revision != int(logical_state["state_version"]):
        raise ArityCommitmentError("typed/logical revisions diverged")
    target = typed_state.get_slot(str(parsed["target_id"]))
    if target.mode.value != "active":
        raise ArityCommitmentError("typed target is inactive")
    if parsed["operation"] == "Override":
        replacement = atom_from_mapping(event["replacement_atom"])
        operation = Override(
            f"{parsed['patch_id']}:operation", target.slot_id,
            _slot(replacement, event_id=str(event["event_id"]), parent=target),
            "authorized cross-predicate replacement",
        )
    else:
        operation = Expire(
            f"{parsed['patch_id']}:operation", target.slot_id,
            "authorized dependent cancellation",
        )
    patch = Patch(
        patch_id=str(parsed["patch_id"]),
        event_id=str(parsed["event_id"]),
        reason="variable-arity persistent transition",
        operations=(operation,),
        generator="arity-sequence-provider",
        input_state_hash=typed_state.state_hash,
        created_at=int(logical_state["state_version"]),
        metadata={"provider_called": False, "oracle_fixture": True},
    )
    transitioned = apply_patch(
        typed_state, patch,
        PatchContext(
            actor="task_owner", authority_priority=100,
            authorized_sources=("task",), event_source="oracle",
            information_budget=0, policy_step_budget=0, high_level_call_count=0,
            pair_key={"event_id": str(event["event_id"])},
            task_progress={"physically_true_ids": list(physically_true_ids)},
            metadata={"variable_arity_gate": True},
        ),
    )
    if not transitioned.accepted:
        raise ArityCommitmentError(
            f"typed transition rejected: {transitioned.rejection_code}:"
            f"{transitioned.rejection_reason}"
        )
    candidate = expected_next_state(logical_state, event)
    directive = validate_transition(logical_state, candidate, event, physically_true_ids)
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
