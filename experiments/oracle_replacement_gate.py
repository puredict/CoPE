#!/usr/bin/env python3
"""Paired replacement gate using explicit LIBERO skills and a typed CoPE patch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from cope.semantic_replacement import (
    ORIGINAL_OBJECTS,
    RECEPTACLE,
    REPLACEMENT_OBJECT,
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    validate_oracle_full_state,
)
from cope.repeated_replacement import initialize_oracle_replacement_state
from cope.semantic_materialization import materialize_replacement_receipt
from cope.types import stable_hash
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


MODES = (
    "original_reset",
    "updated_reset",
    "checkpoint_no_edit",
    "checkpoint_oracle_full",
    "checkpoint_oracle_patch",
    "no_event_plain",
    "no_event_semantic_scaffold",
)
DONE_OBJECT = ORIGINAL_OBJECTS[0]
PENDING_OBJECT = ORIGINAL_OBJECTS[1]


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


def active_object_from_state(state: Any, done_object: str) -> str:
    active = [
        str(slot.content["arguments"][0])
        for slot in state.slots
        if slot.mode.value == "active"
        and str(slot.content["arguments"][0]) != done_object
    ]
    if len(active) != 1:
        raise ValueError(f"expected one pending active object, found {active}")
    return active[0]


def main() -> int:
    args = parse_args()
    if args.state_id not in range(5):
        raise ValueError("qualification state-id must be one of 0..4")
    if args.max_move_steps != 60:
        raise ValueError("qualification freezes max-move-steps at 60")
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
        controller = LiberoOracleSkillController(
            env,
            observation,
            config=OracleSkillConfig(max_move_steps=args.max_move_steps),
        )
        warmup = controller.warmup()
        initial_step = controller.total_steps
        initial_action_prefix_sha256 = controller.action_prefix_sha256()
        initial_sim_state_sha256 = simulator_state_sha256(env)
        first = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)
        physical_truth_verified = controller.in_region(
            DONE_OBJECT, RECEPTACLE
        )
        physically_true_objects = (
            (DONE_OBJECT,) if physical_truth_verified else ()
        )

        checkpoint_action_prefix_sha256 = controller.action_prefix_sha256()
        checkpoint_sim_state_sha256 = simulator_state_sha256(env)
        checkpoint_step = controller.total_steps
        semantic_sim_before = checkpoint_sim_state_sha256
        semantic_actions_before = controller.total_steps
        compiled_directive = ""
        canonical_state_sha256 = ""
        patch_materialized = False
        semantic_scaffold_initialized = False
        oracle_full_state_selection = False

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
            if args.mode == "checkpoint_oracle_full":
                full_state = build_oracle_full_state(event, previous_state_version=0)
                validate_oracle_full_state(
                    full_state,
                    event,
                    previous_state_version=0,
                    physically_true_objects=physically_true_objects,
                )
                compiled_directive = compile_controller_prompt(full_state)
                canonical_state_sha256 = stable_hash(full_state)
                second_object = str(full_state["plan"][0]["arguments"][0])
                oracle_full_state_selection = True
            elif args.mode == "checkpoint_oracle_patch":
                patch_receipt = apply_oracle_replacement_patch(
                    event,
                    physically_true_objects=physically_true_objects,
                )
                materialized = materialize_replacement_receipt(
                    patch_receipt,
                    event,
                    physically_true_objects=physically_true_objects,
                )
                validate_oracle_full_state(
                    materialized,
                    event,
                    previous_state_version=0,
                    physically_true_objects=physically_true_objects,
                )
                compiled_directive = compile_controller_prompt(materialized)
                canonical_state_sha256 = stable_hash(materialized)
                second_object = str(materialized["plan"][0]["arguments"][0])
                patch_materialized = True
            else:
                second_object = PENDING_OBJECT
        elif args.mode == "no_event_semantic_scaffold" and first.success:
            persistent_state, _ = initialize_oracle_replacement_state(
                done_object=DONE_OBJECT,
                initial_pending_object=PENDING_OBJECT,
                physically_true_objects=physically_true_objects,
                pair_key=f"no-event:task01:state{args.state_id:02d}",
            )
            canonical_state_sha256 = persistent_state.state_hash
            second_object = active_object_from_state(persistent_state, DONE_OBJECT)
            semantic_scaffold_initialized = True
        else:
            second_object = (
                REPLACEMENT_OBJECT if args.mode == "updated_reset" else PENDING_OBJECT
            )

        semantic_sim_after = simulator_state_sha256(env)
        semantic_actions_after = controller.total_steps
        semantic_preserved_sim_state = semantic_sim_before == semantic_sim_after
        semantic_emitted_no_action = semantic_actions_before == semantic_actions_after
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
            "pair_group": (
                f"reset_state{args.state_id:02d}"
                if args.mode in {"original_reset", "updated_reset"}
                else f"no_event_state{args.state_id:02d}"
                if args.mode.startswith("no_event_")
                else f"milestone_state{args.state_id:02d}"
            ),
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
            "initial_checkpoint_step": initial_step,
            "initial_action_prefix_sha256": initial_action_prefix_sha256,
            "initial_sim_state_sha256": initial_sim_state_sha256,
            "milestone_checkpoint_step": checkpoint_step,
            "milestone_action_prefix_sha256": checkpoint_action_prefix_sha256,
            "milestone_sim_state_sha256": checkpoint_sim_state_sha256,
            "first_object": DONE_OBJECT,
            "first_skill_success": first.success,
            "first_failure_reason": first.failure_reason or "",
            "first_lift_m": f"{first.object_lift_m:.6f}",
            "physical_truth_verified_before_patch": physical_truth_verified,
            "event_reached": event is not None,
            "oracle_full_state_selection": oracle_full_state_selection,
            "patch_applied": patch_receipt is not None,
            "patch_materialized": patch_materialized,
            "semantic_scaffold_initialized": semantic_scaffold_initialized,
            "canonical_state_sha256": canonical_state_sha256,
            "compiled_directive": compiled_directive,
            "semantic_preserved_sim_state": semantic_preserved_sim_state,
            "semantic_emitted_no_action": semantic_emitted_no_action,
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
                patch_receipt["oracle_operation_selection"]
                if patch_receipt
                else oracle_full_state_selection
            ),
            "provider_called": (
                patch_receipt["provider_called"] if patch_receipt else False
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
        "original_reset": original_goal_success,
        "updated_reset": updated_goal_success,
        "checkpoint_no_edit": not updated_goal_success,
        "checkpoint_oracle_full": updated_goal_success,
        "checkpoint_oracle_patch": updated_goal_success,
        "no_event_plain": original_goal_success,
        "no_event_semantic_scaffold": original_goal_success,
    }[args.mode]
    integrity = semantic_preserved_sim_state and semantic_emitted_no_action
    return 0 if first.success and second is not None and second.success and expected and integrity else 1


if __name__ == "__main__":
    raise SystemExit(main())
