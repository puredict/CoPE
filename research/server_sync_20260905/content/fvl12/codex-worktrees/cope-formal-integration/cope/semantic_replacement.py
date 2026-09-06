from __future__ import annotations

from dataclasses import dataclass
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
from cope.serialization import serialize_state, thaw_json


FULL_STATE_SCHEMA = "full-state-v2"
TASK_ID = 1
RECEPTACLE = "basket_1_contain_region"
ORIGINAL_OBJECTS = ("cream_cheese_1", "butter_1")
REPLACEMENT_OBJECT = "alphabet_soup_1"
ALLOWED_OBJECTS = frozenset(
    {
        "cream_cheese_1",
        "butter_1",
        "alphabet_soup_1",
        "milk_1",
        "ketchup_1",
        "orange_juice_1",
        "tomato_sauce_1",
    }
)
OBJECT_LABELS = {
    "cream_cheese_1": "cream cheese box",
    "butter_1": "butter",
    "alphabet_soup_1": "alphabet soup",
    "milk_1": "milk",
    "ketchup_1": "ketchup",
    "orange_juice_1": "orange juice",
    "tomato_sauce_1": "tomato sauce",
}


class FullStateValidationError(ValueError):
    pass


def goal_commitment_id(object_name: str) -> str:
    return f"goal:in:{object_name}:{RECEPTACLE}"


@dataclass(frozen=True)
class MilestoneEvent:
    policy_step: int
    done_object: str
    pending_object: str
    stable_steps: int


@dataclass
class StableFirstMilestoneDetector:
    required_stable_steps: int = 5
    deadline: int = 300
    _candidate: str | None = None
    _count: int = 0
    _triggered: bool = False

    def __post_init__(self) -> None:
        if self.required_stable_steps <= 0:
            raise ValueError("required_stable_steps must be positive")
        if self.deadline < 0:
            raise ValueError("deadline must be nonnegative")

    def observe(self, policy_step: int, predicates: Mapping[str, bool]) -> MilestoneEvent | None:
        if self._triggered or int(policy_step) > self.deadline:
            return None
        active = [name for name in ORIGINAL_OBJECTS if bool(predicates.get(name, False))]
        candidate = active[0] if len(active) == 1 else None
        if candidate is None:
            self._candidate = None
            self._count = 0
            return None
        if candidate == self._candidate:
            self._count += 1
        else:
            self._candidate = candidate
            self._count = 1
        if self._count < self.required_stable_steps:
            return None
        pending = next(name for name in ORIGINAL_OBJECTS if name != candidate)
        self._triggered = True
        return MilestoneEvent(
            policy_step=int(policy_step),
            done_object=candidate,
            pending_object=pending,
            stable_steps=self._count,
        )


def build_replacement_event(
    milestone: MilestoneEvent,
    *,
    pair_key: str,
    previous_state_version: int = 0,
    replacement_object: str = REPLACEMENT_OBJECT,
) -> dict[str, Any]:
    if replacement_object not in ALLOWED_OBJECTS:
        raise ValueError(f"unknown replacement object {replacement_object!r}")
    return {
        "event_id": f"semantic-replace-v1:{pair_key}",
        "event_type": "replace_pending_goal",
        "issuer": "task_owner",
        "authority": 100,
        "target_commitment_id": goal_commitment_id(milestone.pending_object),
        "operation": "supersede",
        "done_object": milestone.done_object,
        "pending_object": milestone.pending_object,
        "replacement_object": replacement_object,
        "replacement_target": RECEPTACLE,
        "valid_from_state_version": int(previous_state_version),
        "world_version": int(milestone.policy_step),
    }


def _commitment(
    object_name: str,
    *,
    status: str,
    event_id: str,
    authority: int = 100,
    supersedes: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "id": goal_commitment_id(object_name),
        "type": "task_goal",
        "predicate": "in",
        "grounding": [object_name, RECEPTACLE],
        "lifecycle_status": status,
        "source": "task_owner",
        "owner": "task_owner",
        "authority": int(authority),
        "valid_from": event_id,
        "valid_until": "task_end",
        "dependencies": [],
        "support_links": [],
        "override_links": [],
        "supersession_links": list(supersedes),
    }


def build_oracle_full_state(
    event: Mapping[str, Any],
    *,
    previous_state_version: int = 0,
) -> dict[str, Any]:
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    replacement_object = str(event["replacement_object"])
    event_id = str(event["event_id"])
    pending_id = goal_commitment_id(pending_object)
    return {
        "schema_version": FULL_STATE_SCHEMA,
        "state_version": int(previous_state_version) + 1,
        "current_goal": {
            "all": [
                {"predicate": "in", "arguments": [done_object, RECEPTACLE]},
                {"predicate": "in", "arguments": [replacement_object, RECEPTACLE]},
            ]
        },
        "entities": [
            {"id": done_object, "kind": "object"},
            {"id": pending_object, "kind": "object"},
            {"id": replacement_object, "kind": "object"},
            {"id": RECEPTACLE, "kind": "region"},
        ],
        "commitments": [
            _commitment(done_object, status="satisfied", event_id=event_id),
            _commitment(pending_object, status="superseded", event_id=event_id),
            _commitment(
                replacement_object,
                status="active",
                event_id=event_id,
                supersedes=(pending_id,),
            ),
        ],
        "progress_ledger": [
            {
                "milestone_id": goal_commitment_id(done_object),
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [
            {
                "step_id": "place-replacement",
                "skill": "place_in",
                "arguments": [replacement_object, RECEPTACLE],
                "status": "pending",
                "preconditions": [],
                "effects": [
                    {"predicate": "in", "arguments": [replacement_object, RECEPTACLE]}
                ],
                "dependencies": [goal_commitment_id(done_object)],
            }
        ],
        "pending_restorations": [],
        "evidence_versions": {
            "event_id": event_id,
            "world_version": int(event["world_version"]),
            "input_state_version": int(event["valid_from_state_version"]),
        },
        "controller_prompt": "diagnostic-only; execution must use the shared compiler",
    }


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FullStateValidationError(f"{label} must be an object")
    return value


def _mapping_list_by_id(value: Any, *, label: str, id_field: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise FullStateValidationError(f"{label} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(value):
        item = _require_mapping(raw, f"{label}[{index}]")
        identifier = item.get(id_field)
        if not isinstance(identifier, str) or not identifier:
            raise FullStateValidationError(f"{label}[{index}].{id_field} must be nonempty")
        if identifier in result:
            raise FullStateValidationError(f"duplicate {label} {id_field} {identifier!r}")
        result[identifier] = item
    return result


def validate_canonical_task_sections(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> None:
    """Validate persistent sections shared by native rewrites and materialized patches.

    The canonical builders are event-bound and deterministic. Comparing their
    semantic sections closes omissions without trusting provider prose. Current
    goal and event authorization remain event-specific checks in the callers.
    """

    actual_commitments = _mapping_list_by_id(
        state.get("commitments"), label="commitments", id_field="id"
    )
    expected_commitments = _mapping_list_by_id(
        canonical.get("commitments"), label="canonical commitments", id_field="id"
    )
    if actual_commitments != expected_commitments:
        raise FullStateValidationError(
            "commitment semantics, authority, provenance, or lineage are non-canonical"
        )

    actual_entities = _mapping_list_by_id(
        state.get("entities"), label="entities", id_field="id"
    )
    expected_entities = _mapping_list_by_id(
        canonical.get("entities"), label="canonical entities", id_field="id"
    )
    if actual_entities != expected_entities:
        raise FullStateValidationError("task-relevant entity closure is non-canonical")

    actual_progress = _mapping_list_by_id(
        state.get("progress_ledger"),
        label="progress_ledger",
        id_field="milestone_id",
    )
    expected_progress = _mapping_list_by_id(
        canonical.get("progress_ledger"),
        label="canonical progress_ledger",
        id_field="milestone_id",
    )
    if actual_progress != expected_progress:
        raise FullStateValidationError("progress ledger does not match witnessed progress")

    if state.get("plan") != canonical.get("plan"):
        raise FullStateValidationError("plan does not implement the authorized current goal")
    if state.get("pending_restorations") != canonical.get("pending_restorations"):
        raise FullStateValidationError("pending restorations were not authorized by the event")
    if state.get("evidence_versions") != canonical.get("evidence_versions"):
        raise FullStateValidationError("evidence versions do not bind to the current event and state")


def validate_oracle_full_state(
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
        raise FullStateValidationError("event is not authorized to replace the task goal")
    done_object = str(event.get("done_object"))
    pending_object = str(event.get("pending_object"))
    replacement_object = str(event.get("replacement_object"))
    if {done_object, pending_object} != set(ORIGINAL_OBJECTS):
        raise FullStateValidationError("event does not identify exactly one done and one pending sibling")
    if replacement_object not in ALLOWED_OBJECTS or replacement_object in ORIGINAL_OBJECTS:
        raise FullStateValidationError("replacement object is invalid")
    if event.get("target_commitment_id") != goal_commitment_id(pending_object):
        raise FullStateValidationError("event targets the wrong commitment")
    physically_true = set(physically_true_objects)
    if done_object not in physically_true:
        raise FullStateValidationError("claimed completed milestone is not physically true")
    if pending_object in physically_true:
        raise FullStateValidationError("pending commitment is already physically satisfied")

    commitments = state.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 3:
        raise FullStateValidationError("full state must contain exactly three task commitments")
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(commitments):
        item = _require_mapping(raw, f"commitments[{index}]")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise FullStateValidationError("commitment id must be nonempty")
        if identifier in by_id:
            raise FullStateValidationError(f"duplicate commitment id {identifier!r}")
        grounding = item.get("grounding")
        if not isinstance(grounding, list) or len(grounding) != 2:
            raise FullStateValidationError(f"commitment {identifier!r} has invalid grounding")
        if grounding[0] not in ALLOWED_OBJECTS or grounding[1] != RECEPTACLE:
            raise FullStateValidationError(f"commitment {identifier!r} has unknown grounding")
        by_id[identifier] = item
    expected = {
        goal_commitment_id(done_object): "satisfied",
        goal_commitment_id(pending_object): "superseded",
        goal_commitment_id(replacement_object): "active",
    }
    if {key: by_id.get(key, {}).get("lifecycle_status") for key in expected} != expected:
        raise FullStateValidationError("commitment lifecycle statuses do not match the event")
    replacement = by_id[goal_commitment_id(replacement_object)]
    if replacement.get("supersession_links") != [goal_commitment_id(pending_object)]:
        raise FullStateValidationError("replacement does not preserve supersession lineage")

    goal = _require_mapping(state.get("current_goal"), "current_goal")
    atoms = goal.get("all")
    if not isinstance(atoms, list) or len(atoms) != 2:
        raise FullStateValidationError("current_goal.all must be a list")
    normalized = {
        (atom.get("predicate"), tuple(atom.get("arguments", ())))
        for atom in atoms
        if isinstance(atom, Mapping)
    }
    expected_atoms = {
        ("in", (done_object, RECEPTACLE)),
        ("in", (replacement_object, RECEPTACLE)),
    }
    if normalized != expected_atoms:
        raise FullStateValidationError("current goal is not the authorized post-event conjunction")

    canonical = build_oracle_full_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_canonical_task_sections(state, canonical)


def compile_controller_prompt(state: Mapping[str, Any]) -> str:
    goal = _require_mapping(state.get("current_goal"), "current_goal")
    atoms = goal.get("all")
    if not isinstance(atoms, list) or len(atoms) != 2:
        raise FullStateValidationError("compiler requires exactly two goal atoms")
    objects: list[str] = []
    for atom in atoms:
        item = _require_mapping(atom, "current_goal atom")
        arguments = item.get("arguments")
        if item.get("predicate") != "in" or not isinstance(arguments, list) or len(arguments) != 2:
            raise FullStateValidationError("unsupported goal atom")
        if arguments[1] != RECEPTACLE or arguments[0] not in OBJECT_LABELS:
            raise FullStateValidationError("unsupported goal grounding")
        objects.append(str(arguments[0]))
    object_set = set(objects)
    if object_set == {"cream_cheese_1", "alphabet_soup_1"}:
        # Reuse the exact instruction represented in LIBERO-10 task 7.  The
        # scene differs, so this still needs a checkpoint-continuation gate,
        # but we do not introduce avoidable wording novelty.
        return "put both the alphabet soup and the cream cheese box in the basket"
    labels = [OBJECT_LABELS[name] for name in objects]
    return f"put both the {labels[0]} and the {labels[1]} in the basket"


def current_goal_success(state: Mapping[str, Any], predicates: Mapping[str, bool]) -> bool:
    goal = _require_mapping(state.get("current_goal"), "current_goal")
    atoms = goal.get("all")
    if not isinstance(atoms, list):
        return False
    for atom in atoms:
        if not isinstance(atom, Mapping):
            return False
        arguments = atom.get("arguments")
        if atom.get("predicate") != "in" or not isinstance(arguments, list) or len(arguments) != 2:
            return False
        if arguments[1] != RECEPTACLE or not bool(predicates.get(str(arguments[0]), False)):
            return False
    return True


def apply_oracle_replacement_patch(
    event: Mapping[str, Any],
    *,
    physically_true_objects: Sequence[str],
) -> dict[str, Any]:
    """Exercise CoPE's typed patch engine with an oracle Override choice.

    The semantic operation is selected by an oracle and no provider is called.
    This is a mechanism canary, not a claim about event interpretation.
    """

    previous_state_version = int(event.get("valid_from_state_version", 0))
    oracle_state = build_oracle_full_state(
        event,
        previous_state_version=previous_state_version,
    )
    validate_oracle_full_state(
        oracle_state,
        event,
        previous_state_version=previous_state_version,
        physically_true_objects=physically_true_objects,
    )
    done_object = str(event["done_object"])
    pending_object = str(event["pending_object"])
    replacement_object = str(event["replacement_object"])
    event_id = str(event["event_id"])
    genesis_event = f"{event_id}:genesis"
    state = ConstraintState.empty(f"replacement:{event_id}")

    def goal_slot(
        object_name: str,
        *,
        created_event_id: str,
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
            created_event_id=created_event_id,
            last_updated_event_id=created_event_id,
            parent_slot_id=parent_slot_id,
            overrides_slot_ids=overrides_slot_ids,
            lineage=lineage or (identifier,),
            metadata={"semantic_role": "task_goal_commitment"},
        )

    genesis = Patch(
        patch_id=f"{event_id}:genesis-patch",
        event_id=genesis_event,
        reason="initialize two atomic task commitments",
        operations=(
            Insert(
                "genesis-insert-done",
                goal_slot(done_object, created_event_id=genesis_event),
            ),
            Insert(
                "genesis-insert-pending",
                goal_slot(pending_object, created_event_id=genesis_event),
            ),
        ),
        generator="oracle-replacement-canary",
        input_state_hash=state.state_hash,
        created_at=0,
    )
    initialized = apply_patch(
        state,
        genesis,
        PatchContext.trusted("replacement-genesis"),
    )
    if not initialized.accepted:
        raise FullStateValidationError(
            f"replacement genesis patch rejected: {initialized.rejection_reason}"
        )
    state = initialized.state
    state_before = serialize_state(state)
    pending_id = goal_commitment_id(pending_object)
    replacement_id = goal_commitment_id(replacement_object)
    replacement = goal_slot(
        replacement_object,
        created_event_id=event_id,
        parent_slot_id=pending_id,
        overrides_slot_ids=(pending_id,),
        lineage=(pending_id, replacement_id),
    )
    replacement_patch = Patch(
        patch_id=f"{event_id}:oracle-cope-patch",
        event_id=event_id,
        reason="authorized replacement of pending task commitment",
        operations=(
            Override(
                "override-pending-goal-with-replacement",
                pending_id,
                replacement,
                "task owner replaced the pending goal",
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
        pair_key={"event_id": event_id},
        task_progress={"physically_true_objects": list(physically_true_objects)},
        manual_intervention=False,
        metadata={"oracle_patch_canary": True},
    )
    transitioned = apply_patch(state, replacement_patch, context)
    if not transitioned.accepted:
        raise FullStateValidationError(
            "oracle CoPE replacement patch rejected: "
            f"{transitioned.rejection_code}: {transitioned.rejection_reason}"
        )
    state_after = transitioned.state
    if state_after.get_slot(pending_id).mode.value != "overridden":
        raise FullStateValidationError("pending commitment did not become overridden")
    if state_after.get_slot(replacement_id).mode.value != "active":
        raise FullStateValidationError("replacement commitment is not active")
    if state_after.get_slot(goal_commitment_id(done_object)).mode.value != "active":
        raise FullStateValidationError("unaffected completed commitment did not remain active")
    return {
        "method_label": "oracle_cope_patch_override",
        "oracle_operation_selection": True,
        "provider_called": False,
        "state_before": state_before,
        "state_after": serialize_state(state_after),
        "patch": {
            "patch_id": replacement_patch.patch_id,
            "event_id": replacement_patch.event_id,
            "operation": "Override",
            "target_id": pending_id,
            "replacement_id": replacement_id,
        },
        "transition": {
            "accepted": True,
            "before_hash": transitioned.before_hash,
            "after_hash": transitioned.after_hash,
            "applied_operation_ids": list(transitioned.applied_operation_ids),
            "audit_record": thaw_json(transitioned.audit_record),
        },
        "execution_directive": {
            "skill": "place_in",
            "arguments": [replacement_object, RECEPTACLE],
        },
        "oracle_full_state": oracle_state,
    }
