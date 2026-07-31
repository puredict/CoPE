from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


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
    if done_object not in set(physically_true_objects):
        raise FullStateValidationError("claimed completed milestone is not physically true")

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
    if not isinstance(atoms, list):
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
