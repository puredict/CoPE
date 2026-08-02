#!/usr/bin/env python3
"""Audit-grade oracle canary for second-replacement timing sensitivity.

The two arms for each (state, timing) are reset independently, but record the
exact low-level action prefix and MuJoCo state at the second event.  Matching
hashes demonstrate that the arms diverge only after the semantic event.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from cope.repeated_replacement import (
    apply_oracle_replacement_event,
    build_chained_replacement_event,
    initialize_oracle_replacement_state,
)
from cope.semantic_replacement import RECEPTACLE
from cope_benchmark.oracle_safety_telemetry import OracleSafetyTelemetry
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
HELD_REPLACEMENT = "alphabet_soup_1"
FINAL_REPLACEMENT = "tomato_sauce_1"
TIMINGS = ("post_lift", "mid_transfer", "pre_release")
MODES = ("stale_continue", "safe_return_switch", "local_stage_switch")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-id", type=int, required=True)
    parser.add_argument("--timing", choices=TIMINGS, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--safety-telemetry", action="store_true")
    parser.add_argument("--max-move-steps", type=int, default=40)
    parser.add_argument("--stage-descent-action-limit", type=float, default=1.0)
    parser.add_argument("--stage-offset-x-m", type=float, default=0.0)
    parser.add_argument("--stage-offset-y-m", type=float, default=0.0)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def _sha256_array(digest: Any, name: str, value: Any) -> None:
    array = np.asarray(value, dtype="<f8")
    digest.update(name.encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes(order="C"))


def simulator_state_sha256(env: Any) -> str:
    """Hash dynamic MuJoCo state and current controls without mutating them."""

    sim = sim_from_env(env)
    digest = hashlib.sha256()
    _sha256_array(digest, "state", sim.get_state().flatten())
    _sha256_array(digest, "ctrl", sim.data.ctrl)
    return digest.hexdigest()


def position_json(controller: LiberoOracleSkillController, name: str) -> str:
    return json.dumps(
        [round(float(value), 9) for value in controller.position(name)],
        separators=(",", ":"),
    )


def advance_to_timing(
    controller: LiberoOracleSkillController,
    timing: str,
) -> int:
    """Move the still-held object to the requested pre-event phase."""

    start = controller.total_steps
    if timing == "post_lift":
        return 0
    current = np.asarray(controller.observation["robot0_eef_pos"], dtype=float)
    region = controller.position(RECEPTACLE)
    transfer_z = max(
        controller.config.transfer_height_m,
        float(current[2]),
        float(
            region[2]
            + controller.config.release_offset_m
            + controller.config.retreat_height_m
        ),
    )
    above_target = np.array([region[0], region[1], transfer_z], dtype=float)
    if timing == "mid_transfer":
        target = 0.5 * (current + above_target)
        phase = "advance_to_mid_transfer"
    elif timing == "pre_release":
        target = above_target
        phase = "advance_to_pre_release"
    else:
        raise ValueError(f"unsupported timing: {timing}")
    controller.move_to(phase, target, gripper=1.0)
    return controller.total_steps - start


def stage_held_near_region(
    controller: LiberoOracleSkillController,
    checkpoint: Any,
    region_name: str,
    descent_action_limit: float = 1.0,
    xy_offset_m: Sequence[float] = (0.0, 0.0),
) -> dict[str, Any]:
    """Release an obsolete held object at a short, verified table staging pose."""

    start_step = controller.total_steps
    object_name = checkpoint.object_name
    origin = np.asarray(checkpoint.object_start_position, dtype=float)
    region = controller.position(region_name)
    direction = origin[:2] - region[:2]
    distance = float(np.linalg.norm(direction))
    if not checkpoint.success or not controller.is_grasping(object_name):
        return {
            "success": False,
            "failure_reason": "invalid_or_stale_held_checkpoint",
            "released": False,
            "outside_region": False,
            "position_error_m": float("inf"),
            "position_error_xy_m": float("inf"),
            "position_error_z_m": float("inf"),
            "target": (),
            "final_position": (),
            "steps": 0,
        }
    if distance <= 1e-9:
        return {
            "success": False,
            "failure_reason": "undefined_staging_direction",
            "released": False,
            "outside_region": False,
            "position_error_m": float("inf"),
            "position_error_xy_m": float("inf"),
            "position_error_z_m": float("inf"),
            "target": (),
            "final_position": (),
            "steps": 0,
        }

    # Stop 25% short of the object's known stable original table pose. This
    # remains a local shortcut, but avoids the unsupported area near the
    # basket edge exposed by the more aggressive 20 cm pilot.
    offset = 0.75 * distance
    stage_xy = region[:2] + direction / distance * offset
    stage_xy += np.asarray(xy_offset_m, dtype=float)
    target = np.array([stage_xy[0], stage_xy[1], origin[2]], dtype=float)
    safe_z = max(
        controller.config.transfer_height_m,
        float(controller.observation["robot0_eef_pos"][2]),
        float(target[2] + controller.config.approach_height_m),
    )
    controller.move_to(
        "stage_above_local_pose",
        [target[0], target[1], safe_z],
        gripper=1.0,
    )
    controller.move_to(
        "stage_descend",
        target + np.array([0.0, 0.0, controller.config.grasp_offset_m]),
        gripper=1.0,
        translation_action_limit=descent_action_limit,
    )
    controller.hold(
        "stage_release", controller.config.open_steps, gripper=-1.0
    )
    retreat = np.asarray(
        controller.observation["robot0_eef_pos"], dtype=float
    ).copy()
    retreat[2] += 0.10
    controller.move_to("stage_retreat", retreat, gripper=-1.0)
    controller.hold("stage_short_settle", 5, gripper=-1.0)

    final_position = controller.position(object_name)
    error = float(np.linalg.norm(final_position - target))
    error_xy = float(np.linalg.norm(final_position[:2] - target[:2]))
    error_z = float(abs(final_position[2] - target[2]))
    released = not controller.is_grasping(object_name)
    outside_region = not controller.in_region(object_name, region_name)
    success = released and outside_region and error <= 0.06
    return {
        "success": success,
        "failure_reason": "" if success else "local_staging_verification_failed",
        "released": released,
        "outside_region": outside_region,
        "position_error_m": error,
        "position_error_xy_m": error_xy,
        "position_error_z_m": error_z,
        "target": tuple(float(value) for value in target),
        "final_position": tuple(float(value) for value in final_position),
        "steps": controller.total_steps - start_step,
    }


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
    try:
        env.reset()
        observation = env.set_init_state(states[args.state_id])
        telemetry = OracleSafetyTelemetry(env) if args.safety_telemetry else None
        controller = LiberoOracleSkillController(
            env,
            observation,
            config=OracleSkillConfig(max_move_steps=args.max_move_steps),
            step_observer=telemetry.record if telemetry else None,
        )
        warmup = controller.warmup()
        completed = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)

        physical_truth_before_first_patch = controller.in_region(
            DONE_OBJECT, RECEPTACLE
        )
        physically_true_objects = (
            (DONE_OBJECT,) if physical_truth_before_first_patch else ()
        )
        pair_key = (
            f"timing:task01:state{args.state_id:02d}:{args.timing}"
        )
        state, _ = initialize_oracle_replacement_state(
            done_object=DONE_OBJECT,
            initial_pending_object=ORIGINAL_PENDING,
            physically_true_objects=physically_true_objects,
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
            physically_true_objects=physically_true_objects,
            pair_key=pair_key,
            chain_index=1,
        )

        held = controller.pick_object(HELD_REPLACEMENT)
        timing_advance_steps = (
            advance_to_timing(controller, args.timing) if held.success else 0
        )
        event_step = controller.total_steps
        action_prefix_sha256 = controller.action_prefix_sha256()
        sim_before_patch = simulator_state_sha256(env)
        physical_truth_before_second_patch = controller.in_region(
            DONE_OBJECT, RECEPTACLE
        )
        physically_true_objects = (
            (DONE_OBJECT,) if physical_truth_before_second_patch else ()
        )
        held_at_event = controller.is_grasping(HELD_REPLACEMENT)
        held_in_region_at_event = controller.in_region(
            HELD_REPLACEMENT, RECEPTACLE
        )
        eef_at_event = json.dumps(
            [
                round(float(value), 9)
                for value in controller.observation["robot0_eef_pos"]
            ],
            separators=(",", ":"),
        )
        held_position_at_event = position_json(controller, HELD_REPLACEMENT)
        if telemetry:
            telemetry.begin(
                event_step=event_step,
                object_positions={
                    name: controller.position(name)
                    for name in (
                        DONE_OBJECT,
                        ORIGINAL_PENDING,
                        HELD_REPLACEMENT,
                        FINAL_REPLACEMENT,
                    )
                },
            )

        event_two = build_chained_replacement_event(
            pair_key=pair_key,
            step_index=2,
            source_object=HELD_REPLACEMENT,
            replacement_object=FINAL_REPLACEMENT,
            expected_state_revision=2,
            world_version=event_step,
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
            physically_true_objects=physically_true_objects,
            pair_key=pair_key,
            chain_index=2,
        )
        sim_after_patch = simulator_state_sha256(env)
        patch_preserved_sim_state = sim_before_patch == sim_after_patch
        patch_emitted_no_action = controller.total_steps == event_step

        stale_place = None
        returned = None
        staged = None
        replacement_skill = None
        if held.success and args.mode == "stale_continue":
            stale_place = controller.place_held(held, RECEPTACLE)
        elif held.success and args.mode == "safe_return_switch":
            returned = controller.return_held_to_start(held)
            if returned.success:
                replacement_skill = controller.pick_and_place(
                    FINAL_REPLACEMENT, RECEPTACLE
                )
        elif held.success:
            staged = stage_held_near_region(
                controller,
                held,
                RECEPTACLE,
                descent_action_limit=args.stage_descent_action_limit,
                xy_offset_m=(args.stage_offset_x_m, args.stage_offset_y_m),
            )
            if staged["success"]:
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
        final_goal_success = bool(
            predicates[DONE_OBJECT] and predicates[FINAL_REPLACEMENT]
        )
        stale_commitment_executed = predicates[HELD_REPLACEMENT]
        telemetry_summary = (
            telemetry.summarize(
                final_object_positions={
                    name: controller.position(name)
                    for name in (
                        DONE_OBJECT,
                        ORIGINAL_PENDING,
                        HELD_REPLACEMENT,
                        FINAL_REPLACEMENT,
                    )
                },
                final_step=controller.total_steps,
            )
            if telemetry
            else None
        )
        if args.mode == "stale_continue":
            expected = not final_goal_success and stale_commitment_executed
        elif args.mode == "safe_return_switch":
            expected = (
                final_goal_success
                and not stale_commitment_executed
                and returned is not None
                and returned.success
                and replacement_skill is not None
                and replacement_skill.success
            )
        else:
            expected = (
                final_goal_success
                and not stale_commitment_executed
                and staged is not None
                and staged["success"]
                and replacement_skill is not None
                and replacement_skill.success
            )
        row = {
            "suite": "libero_10",
            "task_id": 1,
            "state_id": args.state_id,
            "timing": args.timing,
            "mode": args.mode,
            "pair_key": pair_key,
            "prompt": prompt,
            "controller_privilege": "simulator_geometry_oracle",
            "oracle_geometry_used": True,
            "oracle_execution": True,
            "oracle_operation_selection": True,
            "provider_called": False,
            "learned_policy_used": False,
            "shared_init_container_loaded": True,
            "reset_state_index": args.state_id,
            "reserved_state_indexed": False,
            "checkpoint_access": "deterministic_replay_and_simulator_hash",
            "oracle_max_move_steps": args.max_move_steps,
            "warmup_steps": warmup.steps,
            "completed_progress_success": completed.success,
            "physical_truth_before_first_patch": physical_truth_before_first_patch,
            "first_patch_accepted": receipt_one["transition"]["accepted"],
            "held_checkpoint_success": held.success,
            "held_object_lift_m": f"{held.object_lift_m:.9f}",
            "timing_advance_steps": timing_advance_steps,
            "event_step": event_step,
            "action_prefix_sha256": action_prefix_sha256,
            "sim_state_before_patch_sha256": sim_before_patch,
            "sim_state_after_patch_sha256": sim_after_patch,
            "patch_preserved_sim_state": patch_preserved_sim_state,
            "patch_emitted_no_action": patch_emitted_no_action,
            "physical_truth_before_second_patch": physical_truth_before_second_patch,
            "held_at_event": held_at_event,
            "held_in_region_at_event": held_in_region_at_event,
            "eef_at_event": eef_at_event,
            "held_position_at_event": held_position_at_event,
            "second_patch_accepted": receipt_two["transition"]["accepted"],
            "revision_after_event_two": state.revision,
            "hash_chain_valid": (
                receipt_one["transition"]["after_hash"]
                == receipt_two["transition"]["before_hash"]
            ),
            "safe_return_success": returned.success if returned else "",
            "safe_return_error_m": (
                f"{returned.return_position_error_m:.9f}" if returned else ""
            ),
            **(
                {
                    "local_stage_success": staged["success"],
                    "local_stage_error_m": f"{staged['position_error_m']:.9f}",
                    "local_stage_error_xy_m": (
                        f"{staged['position_error_xy_m']:.9f}"
                    ),
                    "local_stage_error_z_m": (
                        f"{staged['position_error_z_m']:.9f}"
                    ),
                    "local_stage_outside_region": staged["outside_region"],
                    "local_stage_steps": staged["steps"],
                    "local_stage_descent_action_limit": (
                        args.stage_descent_action_limit
                    ),
                    "local_stage_offset_x_m": args.stage_offset_x_m,
                    "local_stage_offset_y_m": args.stage_offset_y_m,
                    "local_stage_target": json.dumps(
                        staged["target"], separators=(",", ":")
                    ),
                    "local_stage_final_position": json.dumps(
                        staged["final_position"], separators=(",", ":")
                    ),
                }
                if staged
                else {}
            ),
            "replacement_skill_success": (
                replacement_skill.success if replacement_skill else ""
            ),
            "stale_place_success": stale_place.success if stale_place else "",
            "done_object_in_region": predicates[DONE_OBJECT],
            "butter_in_region": predicates[ORIGINAL_PENDING],
            "alphabet_soup_in_region": predicates[HELD_REPLACEMENT],
            "tomato_sauce_in_region": predicates[FINAL_REPLACEMENT],
            "final_goal_success": final_goal_success,
            "stale_commitment_executed": stale_commitment_executed,
            "environment_steps": controller.total_steps,
            "within_horizon": controller.total_steps <= 600,
            **(telemetry_summary or {}),
            "contact_force_proxy_measured": telemetry is not None,
            # We measure positional return and predicates, not force, contact,
            # or collision safety.  Keep this explicit in every raw row.
            "force_contact_collision_safety_measured": False,
            "expected_outcome_observed": expected,
        }
    finally:
        env.close()

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    print(row, flush=True)

    integrity = bool(
        completed.success
        and physical_truth_before_first_patch
        and held.success
        and physical_truth_before_second_patch
        and held_at_event
        and receipt_one["transition"]["accepted"]
        and receipt_two["transition"]["accepted"]
        and patch_preserved_sim_state
        and patch_emitted_no_action
    )
    return 0 if integrity and expected and controller.total_steps <= 600 else 1


if __name__ == "__main__":
    raise SystemExit(main())
