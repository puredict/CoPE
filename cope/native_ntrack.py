from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from cope.types import InformationBudget, RecoveryInput, canonical_json, stable_hash


PATCH_SCHEMA = "cope-typed-minimum-patch-v1"
FULL_STATE_SCHEMA = "full-state-v2"


class NativeOutputError(ValueError):
    pass


@dataclass(frozen=True)
class NativeCase:
    case_id: str
    phase: str
    family: str
    source: str
    pre_state: dict[str, Any]
    event: dict[str, Any]

    @property
    def recovery_input(self) -> RecoveryInput:
        return RecoveryInput(
            schema_version="recovery-input-v1",
            pair_key=self.case_id,
            original_task="Maintain the authorized package-delivery commitments.",
            observation={
                "world_version": self.event["world_version"],
                "facts": self.event.get("world_facts", {}),
                "synthetic_public_case": True,
            },
            event=copy.deepcopy(self.event),
            public_action_history=tuple(copy.deepcopy(self.pre_state["action_history"])),
            task_progress={
                "pre_state": copy.deepcopy(self.pre_state),
                "transition_rules": transition_rules(),
            },
            information_budget=InformationBudget(
                event_fields=tuple(sorted(self.event)),
                history_fields=("action_id", "status", "effect"),
                observation_fields=("world_version", "facts", "synthetic_public_case"),
                max_high_level_calls=1,
                max_prompt_tokens=12000,
                max_completion_tokens=4096,
            ),
        )


def transition_rules() -> dict[str, Any]:
    return {
        "authorization": "Only task_owner with authority >=100 may edit task commitments.",
        "version": "Accept only events whose input_state_version equals pre_state.state_version.",
        "duplicate": "An event already in processed_event_ids is an idempotent no-op.",
        "progress": "Preserve achieved milestones unless world_facts marks them false.",
        "continuity": (
            "Retain an executing action only when event.conflicts_with_action is false; "
            "otherwise mark it cancelled and record event.cancellation_reason."
        ),
        "event_ops": {
            "no_op": "No state change.",
            "cancel_commitment": "Cancel the target and remove it from current_goal.",
            "replace_commitment": "Supersede target and add replacement as active.",
            "activate_override": "Suspend target and add an active override plus restoration record.",
            "release_override": "Expire override and restore or reground its target from world_facts.",
            "irrelevant_world_change": "Advance evidence/state version without changing commitments.",
        },
    }


def _commitment(cid: str, target: str, status: str = "active") -> dict[str, Any]:
    return {
        "id": cid,
        "predicate": "deliver",
        "grounding": [target, "dock"],
        "lifecycle_status": status,
        "source": "task_owner",
        "owner": "task_owner",
        "authority": 100,
        "valid_from": "genesis",
        "valid_until": "task_end",
        "dependencies": [],
        "support_links": [],
        "override_links": [],
        "supersession_links": [],
    }


def base_state(*, version: int = 4, executing: bool = False) -> dict[str, Any]:
    action_status = "executing" if executing else "pending"
    return {
        "schema_version": FULL_STATE_SCHEMA,
        "state_version": version,
        "current_goal": {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]},
            {"predicate": "deliver", "arguments": ["package_b", "dock"]},
        ]},
        "entities": [
            {"id": "package_a", "kind": "object"},
            {"id": "package_b", "kind": "object"},
            {"id": "dock", "kind": "region"},
        ],
        "commitments": [
            _commitment("deliver:a", "package_a", "satisfied"),
            _commitment("deliver:b", "package_b"),
        ],
        "progress_ledger": [
            {
                "milestone_id": "deliver:a",
                "achieved": True,
                "physically_valid": True,
                "still_goal_relevant": True,
            }
        ],
        "plan": [
            {
                "action_id": "place-b",
                "skill": "place",
                "arguments": ["package_b", "dock"],
                "status": action_status,
                "cancellation_reason": None,
            }
        ],
        "pending_restorations": [],
        "evidence_versions": {"event_id": "genesis", "world_version": 40, "input_state_version": version},
        "action_history": [],
    }


def _event(case_id: str, event_type: str, **updates: Any) -> dict[str, Any]:
    event = {
        "event_id": f"native:{case_id}",
        "event_type": event_type,
        "issuer": "task_owner",
        "authority": 100,
        "input_state_version": 4,
        "world_version": 41,
        "world_facts": {"deliver:a": True},
        "conflicts_with_action": False,
    }
    event.update(updates)
    return event


def build_case(case_id: str, phase: str, family: str, source: str) -> NativeCase:
    state = base_state(executing=case_id.startswith("continuity_"))
    if case_id == "no_op":
        event = _event(case_id, "no_op")
    elif case_id == "cancel_sibling":
        event = _event(case_id, "cancel_commitment", target_id="deliver:b")
    elif case_id == "replace_pending_target":
        event = _event(
            case_id,
            "replace_commitment",
            target_id="deliver:b",
            replacement_id="deliver:c",
            replacement_grounding=["package_c", "dock"],
        )
    elif case_id == "activate_override":
        event = _event(
            case_id,
            "activate_override",
            target_id="deliver:b",
            override_id="prohibit:b",
        )
    elif case_id in {"release_override", "world_change_release"}:
        state["commitments"][1]["lifecycle_status"] = "suspended"
        state["commitments"].append(
            {
                **_commitment("prohibit:b", "package_b"),
                "predicate": "prohibit_touch",
                "override_links": ["deliver:b"],
                "valid_from": "native:activate_override",
            }
        )
        state["current_goal"] = {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]},
            {"predicate": "prohibit_touch", "arguments": ["package_b", "dock"]},
        ]}
        state["pending_restorations"] = [{"target_id": "deliver:b", "override_id": "prohibit:b"}]
        state["plan"] = []
        updates: dict[str, Any] = {"override_id": "prohibit:b", "target_id": "deliver:b"}
        if case_id == "world_change_release":
            updates["world_facts"] = {"deliver:a": True, "deliver:b:grounding": ["package_b", "dock_2"]}
        event = _event(case_id, "release_override", **updates)
    elif case_id == "wrong_source_revoke":
        event = _event(case_id, "cancel_commitment", target_id="deliver:b", issuer="observer", authority=10)
    elif case_id == "stale_version":
        event = _event(case_id, "cancel_commitment", target_id="deliver:b", input_state_version=3)
    elif case_id == "idempotence":
        event = _event(case_id, "cancel_commitment", target_id="deliver:b")
        event["duplicate_delivery"] = True
    elif case_id == "irrelevant_sibling_change":
        event = _event(case_id, "irrelevant_world_change", sibling_id="unrelated:x")
    elif case_id == "continuity_valid":
        event = _event(case_id, "irrelevant_world_change")
    elif case_id == "continuity_invalid":
        event = _event(
            case_id,
            "activate_override",
            target_id="deliver:b",
            override_id="prohibit:b",
            conflicts_with_action=True,
            cancellation_reason="new prohibition conflicts with place-b",
        )
    else:
        raise NativeOutputError(f"unknown case {case_id!r}")
    return NativeCase(case_id, phase, family, source, state, event)


def load_manifest(path: Path) -> list[NativeCase]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    cases = [build_case(row["case_id"], row["phase"], row["family"], row["source"]) for row in rows]
    if len({case.case_id for case in cases}) != len(cases):
        raise NativeOutputError("case IDs must be unique")
    return cases


def is_event_authorized(state: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return bool(
        event.get("issuer") == "task_owner"
        and int(event.get("authority", -1)) >= 100
        and int(event.get("input_state_version", -1)) == int(state["state_version"])
        and event.get("duplicate_delivery") is not True
    )


def expected_patch(state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    if is_event_authorized(state, event):
        kind = event["event_type"]
        if kind == "cancel_commitment":
            operations = [{"op": "cancel_commitment", "target_id": event["target_id"]}]
        elif kind == "replace_commitment":
            operations = [{
                "op": "replace_commitment",
                "target_id": event["target_id"],
                "replacement_id": event["replacement_id"],
            }]
        elif kind == "activate_override":
            operations = [{
                "op": "activate_override",
                "target_id": event["target_id"],
                "override_id": event["override_id"],
            }]
            if event.get("conflicts_with_action"):
                operations.append({"op": "cancel_executing_action", "action_id": "place-b"})
        elif kind == "release_override":
            operations = [{
                "op": "release_override",
                "target_id": event["target_id"],
                "override_id": event["override_id"],
            }]
        elif kind == "irrelevant_world_change":
            operations = [{"op": "acknowledge_event"}]
        elif kind != "no_op":
            raise NativeOutputError(f"unsupported event type {kind!r}")
    return {
        "schema_version": PATCH_SCHEMA,
        "input_state_version": int(state["state_version"]),
        "event_id": event["event_id"],
        "operations": operations,
    }


def derive_post_state(state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    post = copy.deepcopy(dict(state))
    if not is_event_authorized(state, event) or event["event_type"] == "no_op":
        return post
    kind = event["event_type"]
    by_id = {item["id"]: item for item in post["commitments"]}
    if kind == "cancel_commitment":
        by_id[event["target_id"]]["lifecycle_status"] = "cancelled"
        post["current_goal"] = {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]}
        ]}
        post["plan"] = []
    elif kind == "replace_commitment":
        target = by_id[event["target_id"]]
        target["lifecycle_status"] = "superseded"
        replacement = _commitment(event["replacement_id"], event["replacement_grounding"][0])
        replacement["grounding"] = list(event["replacement_grounding"])
        replacement["valid_from"] = event["event_id"]
        replacement["supersession_links"] = [event["target_id"]]
        post["commitments"].append(replacement)
        post["entities"].append({"id": event["replacement_grounding"][0], "kind": "object"})
        post["current_goal"] = {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]},
            {"predicate": "deliver", "arguments": list(event["replacement_grounding"])},
        ]}
        post["plan"] = [{
            "action_id": "place-c", "skill": "place", "arguments": list(event["replacement_grounding"]),
            "status": "pending", "cancellation_reason": None,
        }]
    elif kind == "activate_override":
        by_id[event["target_id"]]["lifecycle_status"] = "suspended"
        override = {
            **_commitment(event["override_id"], "package_b"),
            "predicate": "prohibit_touch",
            "valid_from": event["event_id"],
            "override_links": [event["target_id"]],
        }
        post["commitments"].append(override)
        post["current_goal"] = {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]},
            {"predicate": "prohibit_touch", "arguments": ["package_b", "dock"]},
        ]}
        post["pending_restorations"] = [{"target_id": event["target_id"], "override_id": event["override_id"]}]
        if event.get("conflicts_with_action"):
            for action in post["plan"]:
                if action["status"] == "executing":
                    action["status"] = "cancelled"
                    action["cancellation_reason"] = event["cancellation_reason"]
        else:
            post["plan"] = []
    elif kind == "release_override":
        by_id[event["override_id"]]["lifecycle_status"] = "expired"
        target = by_id[event["target_id"]]
        target["lifecycle_status"] = "active"
        grounding = event.get("world_facts", {}).get("deliver:b:grounding")
        if grounding:
            target["grounding"] = list(grounding)
            if not any(item["id"] == grounding[1] for item in post["entities"]):
                post["entities"].append({"id": grounding[1], "kind": "region"})
        post["current_goal"] = {"all": [
            {"predicate": "deliver", "arguments": ["package_a", "dock"]},
            {"predicate": "deliver", "arguments": list(target["grounding"])},
        ]}
        post["pending_restorations"] = []
        post["plan"] = [{
            "action_id": "place-b", "skill": "place", "arguments": list(target["grounding"]),
            "status": "pending", "cancellation_reason": None,
        }]
    elif kind == "irrelevant_world_change":
        pass
    else:
        raise NativeOutputError(f"unsupported event type {kind!r}")
    post["state_version"] += 1
    post["evidence_versions"] = {
        "event_id": event["event_id"],
        "world_version": event["world_version"],
        "input_state_version": event["input_state_version"],
    }
    return post


def parse_patch(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeOutputError("patch output must be an object")
    required = {"schema_version", "input_state_version", "event_id", "operations"}
    if set(value) != required or value.get("schema_version") != PATCH_SCHEMA:
        raise NativeOutputError("patch output has noncanonical fields or schema")
    if not isinstance(value.get("operations"), list):
        raise NativeOutputError("patch operations must be a list")
    return copy.deepcopy(dict(value))


def parse_full_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema_version") != FULL_STATE_SCHEMA:
        raise NativeOutputError("full-state output must be a full-state-v2 object")
    required = set(base_state()) - {"action_history"}
    if set(value) != required:
        raise NativeOutputError("full-state output fields are not canonical full-state-v2")
    return copy.deepcopy(dict(value))


def materialize_patch(
    patch: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    canonical = expected_patch(state, event)
    if canonical_json(patch) != canonical_json(canonical):
        raise NativeOutputError("typed patch is not the authorized minimum transition")
    return state_without_history(derive_post_state(state, event))


def validate_and_compile(
    candidate: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]
) -> str:
    expected = derive_post_state(state, event)
    if canonical_json(candidate) != canonical_json({k: v for k, v in expected.items() if k != "action_history"}):
        raise NativeOutputError("candidate post-state is not event-bound canonical state")
    executing = [action for action in candidate["plan"] if action["status"] == "executing"]
    cancelled = [action for action in candidate["plan"] if action["status"] == "cancelled"]
    if cancelled:
        return f"CANCEL:{cancelled[0]['action_id']}"
    if executing:
        return f"CONTINUE:{executing[0]['action_id']}"
    pending = [action for action in candidate["plan"] if action["status"] == "pending"]
    if pending:
        return f"PLAN:{pending[0]['action_id']}"
    return "HALT"


def failure_flags(candidate: Mapping[str, Any] | None, state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, bool]:
    if candidate is None:
        return {"unauthorized_or_stale_edit": False, "progress_corruption": False, "continuity_error": False}
    expected = derive_post_state(state, event)
    unauthorized = not is_event_authorized(state, event) and canonical_json(candidate) != canonical_json(
        {k: v for k, v in state.items() if k != "action_history"}
    )
    return {
        "unauthorized_or_stale_edit": unauthorized,
        "progress_corruption": candidate.get("progress_ledger") != expected.get("progress_ledger"),
        "continuity_error": candidate.get("plan") != expected.get("plan"),
    }


def state_without_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in state.items() if k != "action_history"}


def case_hash(case: NativeCase) -> str:
    return stable_hash({"case_id": case.case_id, "pre_state": case.pre_state, "event": case.event})
