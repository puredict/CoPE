#!/usr/bin/env python3
"""Inject a second semantic replacement after the active object is lifted."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from cope.repeated_replacement import (
    apply_oracle_replacement_event,
    build_chained_replacement_event,
    initialize_oracle_replacement_state,
)
from cope.semantic_replacement import RECEPTACLE
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
)


DONE_OBJECT = "cream_cheese_1"
ORIGINAL_PENDING = "butter_1"
HELD_REPLACEMENT = "alphabet_soup_1"
FINAL_REPLACEMENT = "tomato_sauce_1"
MODES = (
    "single_patch_complete",
    "double_patch_stale_continue",
    "double_patch_safe_return_switch",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-id", type=int, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
    try:
        env.reset()
        observation = env.set_init_state(states[args.state_id])
        controller = LiberoOracleSkillController(env, observation)
        warmup = controller.warmup()
        completed = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)

        pair_key = f"in-motion:task01:state{args.state_id:02d}"
        state, _ = initialize_oracle_replacement_state(
            done_object=DONE_OBJECT,
            initial_pending_object=ORIGINAL_PENDING,
            physically_true_objects=(DONE_OBJECT,),
            pair_key=pair_key,
        )
        event_one = build_chained_replacement_event(
            pair_key=pair_key,
            step_index=1,
            source_object=ORIGINAL_PENDING,
            replacement_object=HELD_REPLACEMENT,
            expected_state_revision=1,
            world_version=controller.total_steps,
        )
        state, receipt_one = apply_oracle_replacement_event(
            state,
            event_one,
            expected_source_object=ORIGINAL_PENDING,
            used_objects=(DONE_OBJECT, ORIGINAL_PENDING),
            physically_true_objects=(DONE_OBJECT,),
            pair_key=pair_key,
            chain_index=1,
        )

        held = (
            controller.pick_object(HELD_REPLACEMENT)
            if completed.success
            else None
        )
        lift_checkpoint_step = controller.total_steps
        event_two = None
        receipt_two = None
        if args.mode != "single_patch_complete" and held and held.success:
            event_two = build_chained_replacement_event(
                pair_key=pair_key,
                step_index=2,
                source_object=HELD_REPLACEMENT,
                replacement_object=FINAL_REPLACEMENT,
                expected_state_revision=2,
                world_version=lift_checkpoint_step,
            )
            state, receipt_two = apply_oracle_replacement_event(
                state,
                event_two,
                expected_source_object=HELD_REPLACEMENT,
                used_objects=(
                    DONE_OBJECT,
                    ORIGINAL_PENDING,
                    HELD_REPLACEMENT,
                ),
                physically_true_objects=(DONE_OBJECT,),
                pair_key=pair_key,
                chain_index=2,
            )

        stale_place = None
        returned = None
        replacement_skill = None
        if held and held.success:
            if args.mode in {
                "single_patch_complete",
                "double_patch_stale_continue",
            }:
                stale_place = controller.place_held(held, RECEPTACLE)
            else:
                returned = controller.return_held_to_start(held)
                if returned.success:
                    replacement_skill = controller.pick_and_place(
                        FINAL_REPLACEMENT, RECEPTACLE
                    )

        predicates = {
            name: controller.in_region(name, RECEPTACLE)
            for name in (
                DONE_OBJECT,
                ORIGINAL_PENDING,
                HELD_REPLACEMENT,
                FINAL_REPLACEMENT,
            )
        }
        single_goal_success = bool(
            predicates[DONE_OBJECT] and predicates[HELD_REPLACEMENT]
        )
        double_goal_success = bool(
            predicates[DONE_OBJECT] and predicates[FINAL_REPLACEMENT]
        )
        hash_chain_valid = bool(
            receipt_two
            and receipt_one["transition"]["after_hash"]
            == receipt_two["transition"]["before_hash"]
        )
        row = {
            "suite": "libero_10",
            "task_id": 1,
            "state_id": args.state_id,
            "mode": args.mode,
            "prompt": prompt,
            "warmup_steps": warmup.steps,
            "completed_progress_success": completed.success,
            "first_patch_accepted": receipt_one["transition"]["accepted"],
            "held_checkpoint_captured": held is not None and held.success,
            "held_object": HELD_REPLACEMENT,
            "held_object_lift_m": f"{held.object_lift_m:.6f}" if held else "",
            "lift_checkpoint_step": lift_checkpoint_step,
            "event_two_after_lift": event_two is not None,
            "second_patch_accepted": (
                receipt_two["transition"]["accepted"] if receipt_two else ""
            ),
            "revision_after_event_two": state.revision,
            "hash_chain_valid": hash_chain_valid if receipt_two else "",
            "stale_continuation_attempted": stale_place is not None
            and receipt_two is not None,
            "stale_continuation_success": (
                stale_place.success if stale_place and receipt_two else ""
            ),
            "safe_return_attempted": returned is not None,
            "safe_return_success": returned.success if returned else "",
            "safe_return_error_m": (
                f"{returned.return_position_error_m:.6f}" if returned else ""
            ),
            "replacement_skill_success": (
                replacement_skill.success if replacement_skill else ""
            ),
            "done_object_in_region": predicates[DONE_OBJECT],
            "butter_in_region": predicates[ORIGINAL_PENDING],
            "alphabet_soup_in_region": predicates[HELD_REPLACEMENT],
            "tomato_sauce_in_region": predicates[FINAL_REPLACEMENT],
            "valid_progress_retained": predicates[DONE_OBJECT],
            "single_goal_success": single_goal_success,
            "double_goal_success": double_goal_success,
            "stale_held_commitment_executed": predicates[HELD_REPLACEMENT],
            "environment_steps": controller.total_steps,
            "within_horizon": controller.total_steps <= 600,
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

    common = (
        completed.success
        and held is not None
        and held.success
        and predicates[DONE_OBJECT]
    )
    expected = {
        "single_patch_complete": single_goal_success,
        "double_patch_stale_continue": (
            not double_goal_success and predicates[HELD_REPLACEMENT]
        ),
        "double_patch_safe_return_switch": (
            double_goal_success
            and not predicates[HELD_REPLACEMENT]
            and returned is not None
            and returned.success
            and replacement_skill is not None
            and replacement_skill.success
        ),
    }[args.mode]
    return 0 if common and expected and controller.total_steps <= 600 else 1


if __name__ == "__main__":
    raise SystemExit(main())
