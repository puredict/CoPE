#!/usr/bin/env python3
"""Repeated semantic replacement gate on the qualified LIBERO skill substrate."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from cope.repeated_replacement import (
    apply_oracle_replacement_chain,
    build_chained_replacement_event,
)
from cope.semantic_replacement import RECEPTACLE, goal_commitment_id
from cope_benchmark.oracle_skill_controller import (
    LiberoOracleSkillController,
    OracleSkillConfig,
)
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    sim_from_env,
)


DONE_OBJECT = "cream_cheese_1"
ORIGINAL_PENDING = "butter_1"
FIRST_REPLACEMENT = "alphabet_soup_1"
SECOND_REPLACEMENT = "tomato_sauce_1"
MODES = (
    "original",
    "single_patch",
    "double_event_no_edit",
    "second_event_no_edit",
    "double_patch",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-id", type=int, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--max-move-steps", type=int, default=60)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def simulator_state_sha256(env: Any) -> str:
    sim = sim_from_env(env)
    digest = hashlib.sha256()
    for name, value in (("state", sim.get_state().flatten()), ("ctrl", sim.data.ctrl)):
        array = np.asarray(value, dtype="<f8")
        digest.update(name.encode("ascii"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    if args.state_id not in range(5):
        raise ValueError("qualification state-id must be one of 0..4")
    if args.max_move_steps != 60:
        raise ValueError("qualification freezes max-move-steps at 60")
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    states = list(suite.get_task_init_states(1))
    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_id=1,
        trial_id=args.state_id,
        resolution=args.resolution,
    )
    env, prompt = create_libero_env(task, cfg)
    chain: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    try:
        env.reset()
        observation = env.set_init_state(states[args.state_id])
        controller = LiberoOracleSkillController(
            env,
            observation,
            config=OracleSkillConfig(max_move_steps=args.max_move_steps),
        )
        warmup = controller.warmup()
        first_skill = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)
        physical_truth_verified = controller.in_region(
            DONE_OBJECT, RECEPTACLE
        )
        physically_true_objects = (
            (DONE_OBJECT,) if physical_truth_verified else ()
        )
        comparison_step = controller.total_steps
        comparison_action_prefix_sha256 = controller.action_prefix_sha256()
        comparison_sim_state_sha256 = simulator_state_sha256(env)

        pair_key = f"oracle-skill:task01:state{args.state_id:02d}"
        event_one = build_chained_replacement_event(
            pair_key=pair_key,
            step_index=1,
            source_object=ORIGINAL_PENDING,
            replacement_object=FIRST_REPLACEMENT,
            expected_state_revision=1,
            world_version=controller.total_steps,
        )
        event_two = build_chained_replacement_event(
            pair_key=pair_key,
            step_index=2,
            source_object=FIRST_REPLACEMENT,
            replacement_object=SECOND_REPLACEMENT,
            expected_state_revision=2,
            world_version=controller.total_steps + 1,
        )
        if args.mode == "single_patch":
            events = [event_one]
            chain = apply_oracle_replacement_chain(
                events,
                done_object=DONE_OBJECT,
                initial_pending_object=ORIGINAL_PENDING,
                physically_true_objects=physically_true_objects,
                pair_key=pair_key,
            )
        elif args.mode == "double_patch":
            events = [event_one, event_two]
            chain = apply_oracle_replacement_chain(
                events,
                done_object=DONE_OBJECT,
                initial_pending_object=ORIGINAL_PENDING,
                physically_true_objects=physically_true_objects,
                pair_key=pair_key,
            )
        elif args.mode == "second_event_no_edit":
            events = [event_one, event_two]
            chain = apply_oracle_replacement_chain(
                [event_one],
                done_object=DONE_OBJECT,
                initial_pending_object=ORIGINAL_PENDING,
                physically_true_objects=physically_true_objects,
                pair_key=pair_key,
            )
        elif args.mode == "double_event_no_edit":
            events = [event_one, event_two]

        semantic_sim_state_after_sha256 = simulator_state_sha256(env)
        semantic_emitted_no_action = controller.total_steps == comparison_step
        semantic_preserved_sim_state = (
            semantic_sim_state_after_sha256 == comparison_sim_state_sha256
        )

        selected_object = {
            "original": ORIGINAL_PENDING,
            "single_patch": FIRST_REPLACEMENT,
            "double_event_no_edit": ORIGINAL_PENDING,
            "second_event_no_edit": FIRST_REPLACEMENT,
            "double_patch": SECOND_REPLACEMENT,
        }[args.mode]
        second_skill = (
            controller.pick_and_place(selected_object, RECEPTACLE)
            if first_skill.success
            else None
        )
        predicates = {
            name: controller.in_region(name, RECEPTACLE)
            for name in (
                DONE_OBJECT,
                ORIGINAL_PENDING,
                FIRST_REPLACEMENT,
                SECOND_REPLACEMENT,
            )
        }
        original_success = predicates[DONE_OBJECT] and predicates[ORIGINAL_PENDING]
        single_success = predicates[DONE_OBJECT] and predicates[FIRST_REPLACEMENT]
        double_success = predicates[DONE_OBJECT] and predicates[SECOND_REPLACEMENT]
        receipts = chain["receipts"] if chain else []
        final_lineage = ""
        if chain:
            final_id = goal_commitment_id(str(chain["final_active_object"]))
            final_slot = next(
                slot
                for slot in chain["final_state"]["slots"]
                if slot["slot_id"] == final_id
            )
            final_lineage = ">".join(final_slot["lineage"])

        row = {
            "suite": "libero_10",
            "task_id": 1,
            "state_id": args.state_id,
            "mode": args.mode,
            "pair_group": f"repeated_state{args.state_id:02d}",
            "prompt": prompt,
            "controller_privilege": "simulator_geometry_oracle",
            "oracle_geometry_used": True,
            "learned_policy_used": False,
            "shared_init_container_loaded": True,
            "reset_state_index": args.state_id,
            "reserved_state_indexed": False,
            "checkpoint_access": "deterministic_replay_and_simulator_hash",
            "oracle_max_move_steps": args.max_move_steps,
            "warmup_steps": warmup.steps,
            "first_skill_success": first_skill.success,
            "physical_truth_verified_before_patch": physical_truth_verified,
            "comparison_checkpoint_step": comparison_step,
            "comparison_action_prefix_sha256": comparison_action_prefix_sha256,
            "comparison_sim_state_sha256": comparison_sim_state_sha256,
            "semantic_sim_state_after_sha256": semantic_sim_state_after_sha256,
            "semantic_emitted_no_action": semantic_emitted_no_action,
            "semantic_preserved_sim_state": semantic_preserved_sim_state,
            "first_failure_reason": first_skill.failure_reason or "",
            "event_count": len(events),
            "patch_count": len(receipts),
            "all_patches_accepted": bool(receipts)
            and all(receipt["transition"]["accepted"] for receipt in receipts),
            "revision_path": (
                ">".join(
                    [
                        str(receipts[0]["transition"]["revision_before"]),
                        *[
                            str(receipt["transition"]["revision_after"])
                            for receipt in receipts
                        ],
                    ]
                )
                if receipts
                else ""
            ),
            "hash_chain_valid": all(
                receipts[index]["transition"]["after_hash"]
                == receipts[index + 1]["transition"]["before_hash"]
                for index in range(len(receipts) - 1)
            ),
            "final_lineage": final_lineage,
            "oracle_operation_selection": (
                chain["oracle_operation_selection"] if chain else ""
            ),
            "provider_called": chain["provider_called"] if chain else "",
            "selected_object": selected_object,
            "second_skill_success": second_skill.success if second_skill else False,
            "second_failure_reason": (
                (second_skill.failure_reason or "")
                if second_skill
                else "first_skill_failed"
            ),
            "done_object_in_region": predicates[DONE_OBJECT],
            "butter_in_region": predicates[ORIGINAL_PENDING],
            "alphabet_soup_in_region": predicates[FIRST_REPLACEMENT],
            "tomato_sauce_in_region": predicates[SECOND_REPLACEMENT],
            "valid_progress_retained": predicates[DONE_OBJECT],
            "original_goal_success": original_success,
            "single_replacement_goal_success": single_success,
            "double_replacement_goal_success": double_success,
            "first_stale_commitment_executed": predicates[ORIGINAL_PENDING],
            "second_stale_commitment_executed": predicates[FIRST_REPLACEMENT],
            "environment_steps": controller.total_steps,
        }
    finally:
        env.close()

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(row), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow(row)
    print(row, flush=True)

    second_ok = second_skill is not None and second_skill.success
    expected = {
        "original": original_success,
        "single_patch": single_success and not predicates[ORIGINAL_PENDING],
        "double_event_no_edit": (
            not double_success and predicates[ORIGINAL_PENDING]
        ),
        "second_event_no_edit": (
            not double_success
            and not predicates[ORIGINAL_PENDING]
            and predicates[FIRST_REPLACEMENT]
        ),
        "double_patch": (
            double_success
            and not predicates[ORIGINAL_PENDING]
            and not predicates[FIRST_REPLACEMENT]
            and len(receipts) == 2
        ),
    }[args.mode]
    integrity = semantic_emitted_no_action and semantic_preserved_sim_state
    return 0 if first_skill.success and second_ok and expected and integrity else 1


if __name__ == "__main__":
    raise SystemExit(main())
