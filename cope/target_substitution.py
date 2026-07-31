from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TASK_ID = 5
BOOK = "black_book_1"
BACK_REGION = "desk_caddy_1_back_contain_region"
FRONT_REGION = "desk_caddy_1_front_contain_region"
FULL_STATE_SCHEMA = "full-state-v2"
FRONT_PROMPT = "pick up the book and place it in the front compartment of the caddy"


class TargetStateValidationError(ValueError):
    pass


def commitment_id(region: str) -> str:
    return f"goal:in:{BOOK}:{region}"


@dataclass(frozen=True)
class LiftMilestone:
    policy_step: int
    initial_z: float
    current_z: float
    stable_steps: int


@dataclass
class StableLiftDetector:
    initial_z: float
    minimum_lift: float = 0.03
    required_stable_steps: int = 5
    deadline: int = 300
    _count: int = 0
    _triggered: bool = False

    def __post_init__(self) -> None:
        if self.minimum_lift <= 0:
            raise ValueError("minimum_lift must be positive")
        if self.required_stable_steps <= 0:
            raise ValueError("required_stable_steps must be positive")

    def observe(
        self,
        policy_step: int,
        *,
        book_z: float,
        in_back: bool,
        in_front: bool,
    ) -> LiftMilestone | None:
        if self._triggered or int(policy_step) > self.deadline:
            return None
        lifted = (
            float(book_z) - float(self.initial_z) >= self.minimum_lift
            and not bool(in_back)
            and not bool(in_front)
        )
        self._count = self._count + 1 if lifted else 0
        if self._count < self.required_stable_steps:
            return None
        self._triggered = True
        return LiftMilestone(
            policy_step=int(policy_step),
            initial_z=float(self.initial_z),
            current_z=float(book_z),
            stable_steps=self._count,
        )


def build_target_event(
    milestone: LiftMilestone,
    *,
    pair_key: str,
    previous_state_version: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": f"target-substitute-v1:{pair_key}",
        "event_type": "replace_goal_target",
        "issuer": "task_owner",
        "authority": 100,
        "target_commitment_id": commitment_id(BACK_REGION),
        "operation": "supersede",
        "object": BOOK,
        "old_target": BACK_REGION,
        "replacement_target": FRONT_REGION,
        "valid_from_state_version": int(previous_state_version),
        "world_version": int(milestone.policy_step),
        "evidence": {
            "predicate": "lifted",
            "initial_z": milestone.initial_z,
            "current_z": milestone.current_z,
            "stable_steps": milestone.stable_steps,
        },
    }


def _commitment(region: str, *, status: str, event_id: str, links=()) -> dict[str, Any]:
    return {
        "id": commitment_id(region),
        "type": "task_goal",
        "predicate": "in",
        "grounding": [BOOK, region],
        "lifecycle_status": status,
        "source": "task_owner",
        "owner": "task_owner",
        "authority": 100,
        "valid_from": event_id,
        "valid_until": "task_end",
        "dependencies": ["milestone:book_lifted"],
        "support_links": [],
        "override_links": [],
        "supersession_links": list(links),
    }


def build_oracle_target_state(
    event: Mapping[str, Any],
    *,
    previous_state_version: int = 0,
) -> dict[str, Any]:
    event_id = str(event["event_id"])
    return {
        "schema_version": FULL_STATE_SCHEMA,
        "state_version": int(previous_state_version) + 1,
        "current_goal": {
            "all": [{"predicate": "in", "arguments": [BOOK, FRONT_REGION]}]
        },
        "entities": [
            {"id": BOOK, "kind": "object"},
            {"id": BACK_REGION, "kind": "region"},
            {"id": FRONT_REGION, "kind": "region"},
        ],
        "commitments": [
            _commitment(BACK_REGION, status="superseded", event_id=event_id),
            _commitment(
                FRONT_REGION,
                status="active",
                event_id=event_id,
                links=(commitment_id(BACK_REGION),),
            ),
        ],
        "progress_ledger": [
            {
                "milestone_id": "milestone:book_lifted",
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [
            {
                "step_id": "place-book-front",
                "skill": "place_in",
                "arguments": [BOOK, FRONT_REGION],
                "status": "pending",
                "preconditions": ["milestone:book_lifted"],
                "effects": [{"predicate": "in", "arguments": [BOOK, FRONT_REGION]}],
                "dependencies": ["milestone:book_lifted"],
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


def validate_oracle_target_state(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    previous_state_version: int,
    physically_lifted: bool,
) -> None:
    if state.get("schema_version") != FULL_STATE_SCHEMA:
        raise TargetStateValidationError("wrong full-state schema")
    if int(state.get("state_version", -1)) != int(previous_state_version) + 1:
        raise TargetStateValidationError("state version is stale or skips a revision")
    if event.get("issuer") != "task_owner" or int(event.get("authority", -1)) < 100:
        raise TargetStateValidationError("event is not authorized")
    if event.get("target_commitment_id") != commitment_id(BACK_REGION):
        raise TargetStateValidationError("event targets the wrong commitment")
    if event.get("replacement_target") != FRONT_REGION:
        raise TargetStateValidationError("replacement target is invalid")
    if not physically_lifted:
        raise TargetStateValidationError("claimed lift milestone is not physically true")

    commitments = state.get("commitments")
    if not isinstance(commitments, list) or len(commitments) != 2:
        raise TargetStateValidationError("full state must contain exactly two commitments")
    by_id = {item.get("id"): item for item in commitments if isinstance(item, Mapping)}
    if len(by_id) != 2:
        raise TargetStateValidationError("commitment IDs must be unique")
    if by_id.get(commitment_id(BACK_REGION), {}).get("lifecycle_status") != "superseded":
        raise TargetStateValidationError("old target is not superseded")
    replacement = by_id.get(commitment_id(FRONT_REGION), {})
    if replacement.get("lifecycle_status") != "active":
        raise TargetStateValidationError("replacement target is not active")
    if replacement.get("supersession_links") != [commitment_id(BACK_REGION)]:
        raise TargetStateValidationError("replacement lineage is invalid")
    if state.get("current_goal") != {
        "all": [{"predicate": "in", "arguments": [BOOK, FRONT_REGION]}]
    }:
        raise TargetStateValidationError("current goal does not match the authorized event")


def compile_target_prompt(state: Mapping[str, Any]) -> str:
    expected = {"all": [{"predicate": "in", "arguments": [BOOK, FRONT_REGION]}]}
    if state.get("current_goal") != expected:
        raise TargetStateValidationError("unsupported current goal")
    return FRONT_PROMPT


def current_goal_success(predicates: Mapping[str, bool]) -> bool:
    return bool(predicates.get("front", False))
