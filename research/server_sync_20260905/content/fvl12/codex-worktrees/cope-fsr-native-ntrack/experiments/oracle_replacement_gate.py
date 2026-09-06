#!/usr/bin/env python3
"""Paired replacement gate using explicit LIBERO skills and a typed CoPE patch."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from cope.semantic_replacement import (
    ORIGINAL_OBJECTS,
    RECEPTACLE,
    REPLACEMENT_OBJECT,
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_replacement_event,
)
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
)


MODES = (
    "original",
    "reset_counterfactual",
    "checkpoint_no_edit",
    "checkpoint_oracle_cope_patch",
)
DONE_OBJECT = ORIGINAL_OBJECTS[0]
PENDING_OBJECT = ORIGINAL_OBJECTS[1]


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
    initial_states = list(suite.get_task_init_states(1))
    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_id=1,
        trial_id=args.state_id,
        resolution=args.resolution,
    )
    env, prompt = create_libero_env(task, cfg)
    patch_receipt: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    try:
        env.reset()
        observation = env.set_init_state(initial_states[args.state_id])
        controller = LiberoOracleSkillController(env, observation)
        warmup = controller.warmup()
        first = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)
        physical_truth_verified = controller.in_region(
            DONE_OBJECT, RECEPTACLE
        )
        physically_true_objects = (
            (DONE_OBJECT,) if physical_truth_verified else ()
        )

        checkpoint_mode = args.mode.startswith("checkpoint_")
        if checkpoint_mode and first.success:
            milestone = MilestoneEvent(
                policy_step=controller.total_steps,
                done_object=DONE_OBJECT,
                pending_object=PENDING_OBJECT,
                stable_steps=controller.config.settle_steps,
            )
            event = build_replacement_event(
                milestone,
                pair_key=f"oracle-skill:task01:state{args.state_id:02d}",
            )
            if args.mode == "checkpoint_oracle_cope_patch":
                patch_receipt = apply_oracle_replacement_patch(
                    event,
                    physically_true_objects=physically_true_objects,
                )

        second_object = (
            PENDING_OBJECT
            if args.mode in {"original", "checkpoint_no_edit"}
            else REPLACEMENT_OBJECT
        )
        second = (
            controller.pick_and_place(second_object, RECEPTACLE)
            if first.success
            else None
        )
        predicates = {
            name: controller.in_region(name, RECEPTACLE)
            for name in (DONE_OBJECT, PENDING_OBJECT, REPLACEMENT_OBJECT)
        }
        updated_goal_success = bool(
            predicates[DONE_OBJECT] and predicates[REPLACEMENT_OBJECT]
        )
        original_goal_success = bool(
            predicates[DONE_OBJECT] and predicates[PENDING_OBJECT]
        )
        row = {
            "suite": "libero_10",
            "task_id": 1,
            "state_id": args.state_id,
            "mode": args.mode,
            "prompt": prompt,
            "warmup_steps": warmup.steps,
            "first_object": DONE_OBJECT,
            "first_skill_success": first.success,
            "first_failure_reason": first.failure_reason or "",
            "first_lift_m": f"{first.object_lift_m:.6f}",
            "physical_truth_verified_before_patch": physical_truth_verified,
            "event_reached": event is not None,
            "patch_applied": patch_receipt is not None,
            "patch_operation": (
                patch_receipt["patch"]["operation"] if patch_receipt else ""
            ),
            "patch_accepted": (
                patch_receipt["transition"]["accepted"] if patch_receipt else ""
            ),
            "patch_before_hash": (
                patch_receipt["transition"]["before_hash"] if patch_receipt else ""
            ),
            "patch_after_hash": (
                patch_receipt["transition"]["after_hash"] if patch_receipt else ""
            ),
            "oracle_operation_selection": (
                patch_receipt["oracle_operation_selection"] if patch_receipt else ""
            ),
            "provider_called": (
                patch_receipt["provider_called"] if patch_receipt else ""
            ),
            "second_object": second_object,
            "second_skill_success": second.success if second else False,
            "second_failure_reason": (
                (second.failure_reason or "") if second else "first_skill_failed"
            ),
            "second_lift_m": f"{second.object_lift_m:.6f}" if second else "",
            "done_object_in_region": predicates[DONE_OBJECT],
            "pending_object_in_region": predicates[PENDING_OBJECT],
            "replacement_object_in_region": predicates[REPLACEMENT_OBJECT],
            "valid_progress_retained": predicates[DONE_OBJECT],
            "stale_pending_executed": predicates[PENDING_OBJECT],
            "updated_goal_success": updated_goal_success,
            "original_goal_success": original_goal_success,
            "libero_task_success": bool(env.env._check_success()),
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

    expected = {
        "original": original_goal_success,
        "reset_counterfactual": updated_goal_success,
        "checkpoint_no_edit": not updated_goal_success,
        "checkpoint_oracle_cope_patch": updated_goal_success,
    }[args.mode]
    return 0 if first.success and second is not None and second.success and expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
