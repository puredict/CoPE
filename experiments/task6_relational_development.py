#!/usr/bin/env python3
"""Preregistered CPU-only task-6 relational prefix and terminal canary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from cope.relational_sequential_semantics import (
    DONE_ATOM,
    EVENT1_ATOM,
    LEFT_REGION,
    ORIGINAL_PENDING_ATOM,
    PLATE,
    PORCELAIN_MUG,
    RED_MUG,
    RETARGET_ATOM,
    RIGHT_REGION,
    build_event,
    build_initial_state,
    execute_typed_transition,
    initialize_typed_state,
    oracle_sparse_proposal,
    state_hash,
)
from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController
from cope_benchmark.task_progress import LiberoStateView
from experiments.multitask_prefix_audit import (
    CONTROLLER_CONFIG,
    EXPECTED_CONFIG_HASH,
)
from experiments.sequential_formal_runner import observation_hash, simulator_hash
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
)


AUTHORIZED_STATE_IDS = tuple(range(10))
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)
EXPECTED_FINAL_DIRECTIVE = (
    "place_on(red_coffee_mug_1, living_room_table_plate_left_region)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--state-id", type=int, choices=AUTHORIZED_STATE_IDS, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def array_hash(value: Any) -> str:
    array = np.asarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def snapshot(view: LiberoStateView) -> dict[str, bool]:
    return {
        "done_on_plate": view.libero_predicate(
            "on", (PORCELAIN_MUG, PLATE)
        ),
        "original_pudding_on_right": view.libero_predicate(
            "on", (ORIGINAL_PENDING_ATOM.object_name, RIGHT_REGION)
        ),
        "red_mug_on_right": view.libero_predicate("on", (RED_MUG, RIGHT_REGION)),
        "red_mug_on_left": view.libero_predicate("on", (RED_MUG, LEFT_REGION)),
    }


def stable_trace(
    controller: LiberoOracleSkillController,
    view: LiberoStateView,
    *,
    phase_prefix: str,
) -> list[dict[str, bool]]:
    trace = []
    for index in range(5):
        controller.hold(f"{phase_prefix}_{index + 1}", 1, gripper=-1.0)
        trace.append(snapshot(view))
    return trace


def create_env(task: Any, initial_state: Any, state_id: int, resolution: int):
    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_suite="libero_10",
        task_id=6,
        trial_id=state_id,
        mode="clean",
        max_steps=700,
        num_steps_wait=0,
        seed=state_id,
        resolution=resolution,
        enable_auto_disturbance=False,
    )
    set_seed(state_id)
    env, _ = create_libero_env(task, cfg)
    try:
        env.reset()
        observation = env.set_init_state(initial_state)
        controller = LiberoOracleSkillController(
            env, observation, config=CONTROLLER_CONFIG
        )
        controller.warmup()
        return env, controller, LiberoStateView(env)
    except Exception:
        env.close()
        raise


def run_prefix_only(
    task: Any, initial_state: Any, state_id: int, resolution: int
) -> dict[str, Any]:
    env = None
    try:
        env, controller, view = create_env(task, initial_state, state_id, resolution)
        placement = controller.pick_and_place(PORCELAIN_MUG, PLATE, predicate="on")
        trace = stable_trace(controller, view, phase_prefix="prefix_stability")
        expected = {
            "done_on_plate": True,
            "original_pudding_on_right": False,
            "red_mug_on_right": False,
            "red_mug_on_left": False,
        }
        stable = len(trace) == 5 and all(item == expected for item in trace)
        return {
            "placement_success": placement.success,
            "placement_failure": placement.failure_reason or "",
            "grasp_acquired": placement.grasp_acquired,
            "object_lift_m": placement.object_lift_m,
            "target_predicate": placement.target_predicate,
            "stable": stable,
            "trace": trace,
            "action_count": controller.total_steps,
            "action_sha256": controller.action_prefix_sha256(),
            "simulator_sha256": simulator_hash(env),
            "observation_sha256": observation_hash(controller.observation),
            "phase_records": [asdict(phase) for phase in placement.phases],
            "success": bool(placement.success and stable),
        }
    finally:
        if env is not None:
            env.close()


def oracle_semantic_sequence(sequence_id: str, world_version: int):
    logical0 = build_initial_state(
        sequence_id=sequence_id, world_version=world_version
    )
    typed0 = initialize_typed_state(sequence_id=sequence_id)
    event1 = build_event(
        logical0,
        sequence_id=sequence_id,
        step_index=1,
        event_type="replace_pending_goal",
        replacement_atom=EVENT1_ATOM,
        world_version=world_version + 1,
    )
    typed1, logical1, receipt1, directive1 = execute_typed_transition(
        typed0,
        logical0,
        event1,
        oracle_sparse_proposal(event1),
        physically_true_commitment_ids=(DONE_ATOM.commitment_id,),
    )
    event2 = build_event(
        logical1,
        sequence_id=sequence_id,
        step_index=2,
        event_type="replace_pending_goal",
        replacement_atom=RETARGET_ATOM,
        world_version=world_version + 2,
    )
    typed2, logical2, receipt2, directive2 = execute_typed_transition(
        typed1,
        logical1,
        event2,
        oracle_sparse_proposal(event2),
        physically_true_commitment_ids=(DONE_ATOM.commitment_id,),
    )
    return {
        "logical0": logical0,
        "logical1": logical1,
        "logical2": logical2,
        "typed_revision": typed2.revision,
        "event1": event1,
        "event2": event2,
        "receipt1": receipt1,
        "receipt2": receipt2,
        "directive1": directive1,
        "directive2": directive2,
    }


def oracle_cancellation_sibling(sequence_id: str, world_version: int):
    logical0 = build_initial_state(
        sequence_id=sequence_id, world_version=world_version
    )
    typed0 = initialize_typed_state(sequence_id=sequence_id)
    event1 = build_event(
        logical0,
        sequence_id=sequence_id,
        step_index=1,
        event_type="replace_pending_goal",
        replacement_atom=EVENT1_ATOM,
        world_version=world_version + 1,
    )
    typed1, logical1, _, _ = execute_typed_transition(
        typed0,
        logical0,
        event1,
        oracle_sparse_proposal(event1),
        physically_true_commitment_ids=(DONE_ATOM.commitment_id,),
    )
    event2 = build_event(
        logical1,
        sequence_id=sequence_id,
        step_index=2,
        event_type="cancel_pending_goal",
        replacement_atom=None,
        world_version=world_version + 2,
    )
    _, logical2, receipt2, directive2 = execute_typed_transition(
        typed1,
        logical1,
        event2,
        oracle_sparse_proposal(event2),
        physically_true_commitment_ids=(DONE_ATOM.commitment_id,),
    )
    return logical2, receipt2, directive2


def run_sequence(
    task: Any, initial_state: Any, state_id: int, resolution: int
) -> dict[str, Any]:
    env = None
    try:
        env, controller, view = create_env(task, initial_state, state_id, resolution)
        prefix = controller.pick_and_place(PORCELAIN_MUG, PLATE, predicate="on")
        prefix_trace = stable_trace(
            controller, view, phase_prefix="sequence_prefix_stability"
        )
        prefix_expected = {
            "done_on_plate": True,
            "original_pudding_on_right": False,
            "red_mug_on_right": False,
            "red_mug_on_left": False,
        }
        prefix_stable = len(prefix_trace) == 5 and all(
            item == prefix_expected for item in prefix_trace
        )
        if not prefix.success or not prefix_stable:
            return {
                "prefix_success": False,
                "failure": prefix.failure_reason or "prefix_predicate_stability_failure",
                "prefix_trace": prefix_trace,
                "action_count": controller.total_steps,
                "action_sha256": controller.action_prefix_sha256(),
                "simulator_sha256": simulator_hash(env),
                "success": False,
            }

        action_count_before_semantics = controller.total_steps
        sequence_id = f"task6-state{state_id}-retarget-canary"
        semantic = oracle_semantic_sequence(sequence_id, controller.total_steps)
        if semantic["directive2"] != EXPECTED_FINAL_DIRECTIVE:
            raise RuntimeError("semantic compiler produced unexpected terminal directive")
        semantic_action_count = controller.total_steps - action_count_before_semantics
        if semantic_action_count != 0:
            raise RuntimeError("semantic transitions issued controller actions")

        final_placement = controller.pick_and_place(
            RED_MUG, LEFT_REGION, predicate="on"
        )
        terminal_trace = stable_trace(
            controller, view, phase_prefix="terminal_stability"
        )
        terminal_expected = {
            "done_on_plate": True,
            "original_pudding_on_right": False,
            "red_mug_on_right": False,
            "red_mug_on_left": True,
        }
        terminal_stable = len(terminal_trace) == 5 and all(
            item == terminal_expected for item in terminal_trace
        )

        cancellation_action_count = controller.total_steps
        cancellation_state, cancellation_receipt, cancellation_directive = (
            oracle_cancellation_sibling(
                f"task6-state{state_id}-cancel-canary", controller.total_steps
            )
        )
        cancellation_no_action = controller.total_steps == cancellation_action_count
        cancellation_valid = (
            cancellation_directive == "HALT"
            and cancellation_state["plan"] == []
            and cancellation_no_action
        )
        return {
            "prefix_success": True,
            "prefix_trace": prefix_trace,
            "semantic_state_hashes": [
                state_hash(semantic["logical0"]),
                state_hash(semantic["logical1"]),
                state_hash(semantic["logical2"]),
            ],
            "event_ids": [
                semantic["event1"]["event_id"], semantic["event2"]["event_id"]
            ],
            "receipt_hashes": [
                stable_hash(semantic["receipt1"]), stable_hash(semantic["receipt2"])
            ],
            "revision_after": semantic["typed_revision"],
            "directive1": semantic["directive1"],
            "directive2": semantic["directive2"],
            "semantic_action_count": semantic_action_count,
            "final_placement_success": final_placement.success,
            "final_placement_failure": final_placement.failure_reason or "",
            "final_target_predicate": final_placement.target_predicate,
            "terminal_trace": terminal_trace,
            "terminal_stable": terminal_stable,
            "cancellation_directive": cancellation_directive,
            "cancellation_receipt_sha256": stable_hash(cancellation_receipt),
            "cancellation_no_action": cancellation_no_action,
            "cancellation_valid": cancellation_valid,
            "action_count": controller.total_steps,
            "action_sha256": controller.action_prefix_sha256(),
            "simulator_sha256": simulator_hash(env),
            "observation_sha256": observation_hash(controller.observation),
            "final_phase_records": [asdict(phase) for phase in final_placement.phases],
            "success": bool(
                final_placement.success and terminal_stable and cancellation_valid
            ),
        }
    finally:
        if env is not None:
            env.close()


def write_json_line(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("task6 canary requires a clean committed worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if args.state_id != 0:
        raise RuntimeError("the one-cell canary authorizes state 0 only")
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH:
        raise RuntimeError("validated controller configuration hash mismatch")
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("development canary refuses provider credentials: " + ",".join(credentials))
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("task6 canary requires explicit CUDA_VISIBLE_DEVICES='' ")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope-task6-relational-development-v1",
        "runtime_git_commit": commit,
        "task_suite": "libero_10",
        "task_id": 6,
        "authorized_state_ids": [0],
        "provisional_formal_reserve": list(range(10, 30)),
        "untouched_holdout": list(range(30, 50)),
        "controller_config": asdict(CONTROLLER_CONFIG),
        "controller_config_sha256": EXPECTED_CONFIG_HASH,
        "provider_calls": 0,
        "cuda_visible_devices": "",
    }
    (args.output_dir / "00_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(6)
    initial_states = suite.get_task_init_states(6)
    initial_state = initial_states[args.state_id]
    journal = args.output_dir / "01_JOURNAL.txt"
    result: dict[str, Any] = {
        "task_suite": "libero_10",
        "task_id": 6,
        "state_id": args.state_id,
        "initial_state_sha256": array_hash(initial_state),
        "prefix_only_success": False,
        "sequence_success": False,
        "cell_success": False,
        "failure_class": "",
        "provider_calls": 0,
        "formal_states_indexed": 0,
        "task1_forbidden_states_indexed": 0,
    }
    try:
        prefix = run_prefix_only(
            task, initial_state, args.state_id, args.resolution
        )
        write_json_line(journal, {"phase": "prefix_only", "result": prefix})
        result["prefix_only_success"] = bool(prefix["success"])
        result["prefix_action_sha256"] = prefix["action_sha256"]
        result["prefix_simulator_sha256"] = prefix["simulator_sha256"]
        if not prefix["success"]:
            result["failure_class"] = (
                "prefix_only:" + (prefix["placement_failure"] or "stability_failure")
            )
        else:
            sequence = run_sequence(
                task, initial_state, args.state_id, args.resolution
            )
            write_json_line(journal, {"phase": "retarget_sequence", "result": sequence})
            result["sequence_success"] = bool(sequence["success"])
            result["sequence_action_sha256"] = sequence["action_sha256"]
            result["sequence_simulator_sha256"] = sequence["simulator_sha256"]
            result["semantic_state_hashes"] = canonical_json(
                sequence.get("semantic_state_hashes", [])
            )
            result["receipt_hashes"] = canonical_json(
                sequence.get("receipt_hashes", [])
            )
            result["final_directive"] = sequence.get("directive2", "")
            result["cancellation_directive"] = sequence.get(
                "cancellation_directive", ""
            )
            if not sequence["success"]:
                result["failure_class"] = (
                    "sequence:" + (sequence.get("final_placement_failure") or "gate_failure")
                )
        result["cell_success"] = bool(
            result["prefix_only_success"] and result["sequence_success"]
        )
    except Exception as exc:
        result["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
    write_json_line(journal, {"phase": "final", "result": result})
    with (args.output_dir / "02_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result), lineterminator="\n")
        writer.writeheader()
        writer.writerow(result)
    passed = bool(result["cell_success"])
    (args.output_dir / "03_RESULT.md").write_text(
        "# Task-6 relational state-0 canary result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Prefix-only reset: **{'PASS' if result['prefix_only_success'] else 'FAIL'}**\n"
        f"- Two-event retarget reset: **{'PASS' if result['sequence_success'] else 'FAIL'}**\n"
        f"- Failure: `{result['failure_class']}`\n"
        "- Provider calls: **0**\n"
        "- Formal task-6 states indexed: **0**\n"
        "- Task-1 forbidden states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in artifacts
        )
        + "\n",
        encoding="utf-8",
    )
    print(canonical_json(result), flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
