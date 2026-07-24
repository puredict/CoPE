from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, read_jsonl, stable_id, write_jsonl
from auditability.trace_state import replay_patch, state_hash


SYNTHETIC_SCHEMA_VERSION = "auditability.synthetic.v1"


def _slot(
    slot_id: str,
    *,
    kind: str,
    key: str,
    value: Any,
    source: str,
    priority: int,
    status: str = "active",
    policy_step: int = 0,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": slot_id,
        "kind": kind,
        "key": key,
        "value": value,
        "source": source,
        "priority": priority,
        "status": status,
        "policy_step": policy_step,
        "evidence_refs": list(evidence_refs or []),
    }


def synthetic_episode(index: int) -> dict[str, Any]:
    episode_id = f"episode:synthetic-{index:04d}"
    disturbance_id = f"event:synthetic-{index:04d}-disturbance"
    pause_id = f"event:synthetic-{index:04d}-pause"
    failure_id = f"event:synthetic-{index:04d}-failure"
    validation_id = f"validation:synthetic-{index:04d}-alignment"
    preference_id = f"slot:synthetic-{index:04d}-preference"
    alignment_id = f"slot:synthetic-{index:04d}-alignment"
    safety_id = f"slot:synthetic-{index:04d}-safety"
    failure_layers = (
        "perception",
        "event_detection",
        "patch_generation",
        "validation",
        "planning",
        "low_level_control",
        "termination_accounting",
    )
    failure_layer = failure_layers[index % len(failure_layers)]
    methods = (
        "reactive_disturbed",
        "history_augmented_full_regeneration",
        "persistent_typed_patch",
    )
    method = methods[index % len(methods)]
    task_id = index % 5
    preference = _slot(
        preference_id,
        kind="user_preference",
        key="placement_style",
        value="keep upright",
        source="user",
        priority=90,
    )
    alignment = _slot(
        alignment_id,
        kind="object_alignment",
        key="target_alignment",
        value="old_pose",
        source="perception",
        priority=50,
    )
    safety = _slot(
        safety_id,
        kind="safety_constraint",
        key="motion_permission",
        value="continue",
        source="task",
        priority=100,
    )
    states = []
    current_slots = [preference, alignment, safety]

    def append_state(sequence: int, policy_step: int) -> str:
        state_id = f"state:synthetic-{index:04d}-{sequence}"
        state = {
            "id": state_id,
            "sequence": sequence,
            "policy_step": policy_step,
            "slots": copy.deepcopy(current_slots),
        }
        state["state_hash"] = state_hash(state)
        states.append(state)
        return state_id

    state0 = append_state(0, 9)
    patches = []
    patch0 = {
        "id": f"patch:synthetic-{index:04d}-override",
        "sequence": 0,
        "policy_step": 10,
        "op": "override",
        "target_slot_id": safety_id,
        "by_slot_id": alignment_id,
        "changes": {"status": "overridden", "value": "pause"},
        "source_event_id": disturbance_id,
        "evidence_refs": [disturbance_id],
        "before_state_id": state0,
    }
    current_slots = replay_patch(current_slots, patch0)
    state1 = append_state(1, 10)
    patch0["after_state_id"] = state1
    patches.append(patch0)
    patch1 = {
        "id": f"patch:synthetic-{index:04d}-expire",
        "sequence": 1,
        "policy_step": 11,
        "op": "expire",
        "target_slot_id": alignment_id,
        "changes": {"status": "expired"},
        "source_event_id": disturbance_id,
        "evidence_refs": [disturbance_id],
        "before_state_id": state1,
    }
    current_slots = replay_patch(current_slots, patch1)
    state2 = append_state(2, 11)
    patch1["after_state_id"] = state2
    patches.append(patch1)
    patch2 = {
        "id": f"patch:synthetic-{index:04d}-restore",
        "sequence": 2,
        "policy_step": 13,
        "op": "restore",
        "target_slot_id": alignment_id,
        "changes": {
            "status": "active",
            "value": "new_pose",
            "policy_step": 13,
            "evidence_refs": [disturbance_id],
            "fresh_after_event": True,
        },
        "source_event_id": disturbance_id,
        "evidence_refs": [disturbance_id, validation_id],
        "revalidation_id": validation_id,
        "before_state_id": state2,
    }
    current_slots = replay_patch(current_slots, patch2)
    state3 = append_state(3, 13)
    patch2["after_state_id"] = state3
    patches.append(patch2)
    final_slots = copy.deepcopy(current_slots)
    for slot in final_slots:
        if slot["id"] == alignment_id:
            slot["fresh_after_event"] = True
            slot["evidence_refs"] = [disturbance_id]

    events = [
        {
            "id": disturbance_id,
            "event": "object_moved",
            "policy_step": 10,
            "reason": "object displacement detected",
            "object_id": f"object:synthetic-{task_id}",
        },
        {
            "id": pause_id,
            "event": "behavior_pause",
            "policy_step": 10,
            "reason": "object displacement detected",
            "caused_by": disturbance_id,
        },
        {
            "id": failure_id,
            "event": "layer_failure",
            "policy_step": 15,
            "failed": True,
            "failure_layer": failure_layer,
        },
    ]
    if index % 2:
        events.insert(
            2,
            {
                "id": f"event:synthetic-{index:04d}-repeat",
                "event": "secondary_interruption",
                "policy_step": 12,
                "reason": "second object displacement detected",
            },
        )
    actions = [
        {
            "id": f"action:synthetic-{index:04d}-{step}",
            "policy_step": step,
            "action": [round(0.01 * step, 3), 0.0, 0.0],
            "status": "paused" if step == 10 else "running",
        }
        for step in (9, 10, 13, 15)
    ]
    episode = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "metadata": {
            "episode_id": episode_id,
            "method": method,
            "task": f"synthetic task {task_id}",
            "task_id": task_id,
            "success": index % 3 == 0,
            "status": "success" if index % 3 == 0 else "failure",
            "event_type": "object_displacement",
            "interruption_kind": "repeated" if index % 2 else "single",
            "interruption_count": 2 if index % 2 else 1,
            "failure_layer": failure_layer,
            "input_origin": "generated synthetic fixture",
            "input_commit": "synthetic-not-a-repository-commit",
            "input_config_hash": content_hash({"generator": SYNTHETIC_SCHEMA_VERSION}),
            "input_schema_version": SYNTHETIC_SCHEMA_VERSION,
            "synthetic": True,
        },
        "raw": {
            "events": events,
            "actions": actions,
            "observation_summaries": [
                {
                    "id": f"observation:synthetic-{index:04d}-post",
                    "policy_step": 10,
                    "summary": "target object moved to a new pose",
                }
            ],
        },
        "regeneration": {
            "snapshots": [
                {
                    "id": f"regen:synthetic-{index:04d}-0",
                    "policy_step": 11,
                    "plan": ["locate object", "resume placement"],
                    "source_event_id": disturbance_id,
                }
            ]
        },
        "cope": {
            "slots": final_slots,
            "states": states,
            "patches": patches,
            "validator_outputs": [
                {
                    "id": validation_id,
                    "policy_step": 12,
                    "success": True,
                    "validated_slot_id": alignment_id,
                    "evidence_refs": [disturbance_id],
                }
            ],
        },
        "controller_status": {
            "id": f"controller:synthetic-{index:04d}",
            "policy_step": 15,
            "status": "failed" if index % 3 else "succeeded",
            "failure_layer": failure_layer if index % 3 else None,
        },
        "task_progress": [],
        "extensions": {"fixture_label": "SYNTHETIC_NOT_FORMAL_EVIDENCE"},
    }
    episode["adapter_hash"] = content_hash(
        {key: value for key, value in episode.items() if key != "adapter_hash"}
    )
    return episode


def oracle_predictions(
    questions: list[dict[str, Any]], packages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    truth_by_item = {row["item_id"]: row["ground_truth"] for row in questions}
    outputs = []
    for package in packages:
        truth = truth_by_item[package["item_id"]]
        outputs.append(
            {
                "package_id": package["package_id"],
                "item_id": package["item_id"],
                "episode_id": package["episode_id"],
                "answer": truth["normalized_answer"],
                "supporting_ids": truth["supporting_ids"],
                "failure_layer": truth["failure_layer"],
                "answerability": truth["answerability"],
                "confidence": 5,
                "completion_time_seconds": 30.0,
                "synthetic_oracle": True,
            }
        )
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate clearly labeled synthetic evaluator fixtures.")
    sub = parser.add_subparsers(dest="command", required=True)
    episodes = sub.add_parser("episodes")
    episodes.add_argument("--output", type=Path, required=True)
    episodes.add_argument("--count", type=int, default=12)
    episodes.add_argument("--seed", type=int, required=True)
    episodes.add_argument("--schema-version", default=SCHEMA_VERSION)
    episodes.add_argument("--dry-run", action="store_true")
    oracle = sub.add_parser("oracle-predictions")
    oracle.add_argument("--questions", type=Path, required=True)
    oracle.add_argument("--packages", type=Path, required=True)
    oracle.add_argument("--output", type=Path, required=True)
    oracle.add_argument("--seed", type=int, required=True)
    oracle.add_argument("--schema-version", default=SCHEMA_VERSION)
    oracle.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    if args.command == "episodes":
        rows = [synthetic_episode(index) for index in range(args.count)]
    else:
        rows = oracle_predictions(read_jsonl(args.questions), read_jsonl(args.packages))
    if args.dry_run:
        print(json.dumps({"command": args.command, "row_count": len(rows)}, sort_keys=True))
        return
    write_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output), "row_count": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
