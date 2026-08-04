#!/usr/bin/env python3
"""Two-episode physical canary for task-7 occurrence restoration."""

from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from cope.occurrence_sequence import (
    build_event,
    build_initial_state,
    compile_directive,
    expected_next_state,
    occurrence_id,
)
from cope.semantic_replacement import RECEPTACLE
from cope.types import canonical_json, stable_hash
from cope_benchmark.task_progress import LiberoStateView
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
    sim_from_env,
)


TASK_ID = 7
STATE_ID = 0
DONE = "alphabet_soup_1"
ORIGINAL = "cream_cheese_1"
INTERMEDIATE = "tomato_sauce_1"
MODES = ("cancel", "restore")
EXPECTED_CONTROLLER_SHA256 = "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def simulator_hash(env: Any) -> str:
    sim = sim_from_env(env)
    values = np.concatenate([
        np.asarray(sim.data.qpos, dtype="<f8").ravel(),
        np.asarray(sim.data.qvel, dtype="<f8").ravel(),
        np.asarray(sim.data.ctrl, dtype="<f8").ravel(),
    ])
    return hashlib.sha256(values.tobytes()).hexdigest()


def predicates(view: LiberoStateView) -> dict[str, bool]:
    return {
        "done": view.libero_predicate("in", (DONE, RECEPTACLE)),
        "original": view.libero_predicate("in", (ORIGINAL, RECEPTACLE)),
        "intermediate": view.libero_predicate("in", (INTERMEDIATE, RECEPTACLE)),
    }


def terminal_expected(mode: str) -> dict[str, bool]:
    if mode == "cancel":
        return {"done": True, "original": False, "intermediate": False}
    if mode == "restore":
        return {"done": True, "original": True, "intermediate": False}
    raise ValueError(mode)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("task-7 canary requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONTROLLER_SHA256:
        raise RuntimeError("controller configuration hash drift")
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(TASK_ID)
    initial_states = suite.get_task_init_states(TASK_ID)
    rows: list[dict[str, Any]] = []
    for mode in MODES:
        cfg = ExperimentConfig(
            checkpoint="oracle-skill-controller", task_suite="libero_10",
            task_id=TASK_ID, trial_id=STATE_ID, mode="clean", max_steps=700,
            num_steps_wait=0, seed=STATE_ID, resolution=args.resolution,
            enable_auto_disturbance=False,
        )
        set_seed(STATE_ID)
        env, prompt = create_libero_env(task, cfg)
        try:
            env.reset()
            observation = env.set_init_state(initial_states[STATE_ID])
            from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController

            controller = LiberoOracleSkillController(
                env, observation, config=CONTROLLER_CONFIG
            )
            controller.warmup()
            prefix = controller.pick_and_place(DONE, RECEPTACLE)
            view = LiberoStateView(env)
            prefix_trace = []
            for index in range(5):
                controller.hold(f"task7_occurrence_prefix_{index + 1}", 1, gripper=-1.0)
                prefix_trace.append(predicates(view))
            prefix_expected = {"done": True, "original": False, "intermediate": False}
            prefix_valid = bool(
                prefix.success and len(prefix_trace) == 5
                and all(item == prefix_expected for item in prefix_trace)
            )
            prefix_action_sha256 = controller.action_prefix_sha256()
            actions_before_semantic = controller.total_steps
            sim_before_semantic = simulator_hash(env)
            sequence_id = f"task7-state0-{mode}"
            logical = build_initial_state(
                sequence_id=sequence_id, done_object=DONE,
                pending_object=ORIGINAL,
                available_objects=(DONE, ORIGINAL, INTERMEDIATE),
                world_version=controller.total_steps,
            )
            event1 = build_event(
                logical, sequence_id=sequence_id, step_index=1,
                done_object=DONE, event_type="replace_pending_goal",
                replacement_object=INTERMEDIATE, replacement_occurrence=1,
                world_version=controller.total_steps + 1,
            )
            logical = expected_next_state(logical, event1)
            event2 = build_event(
                logical, sequence_id=sequence_id, step_index=2,
                done_object=DONE,
                event_type="cancel_pending_goal" if mode == "cancel" else "replace_pending_goal",
                replacement_object=None if mode == "cancel" else ORIGINAL,
                replacement_occurrence=None if mode == "cancel" else 2,
                world_version=controller.total_steps + 2,
            )
            logical = expected_next_state(logical, event2)
            directive = compile_directive(logical)
            actions_after_semantic = controller.total_steps
            sim_after_semantic = simulator_hash(env)
            semantic_no_action = actions_after_semantic == actions_before_semantic
            semantic_preserved_sim = sim_after_semantic == sim_before_semantic
            terminal_skill_success = True
            terminal_failure = ""
            if directive != "HALT":
                placement = controller.pick_and_place(ORIGINAL, RECEPTACLE)
                terminal_skill_success = bool(placement.success)
                terminal_failure = placement.failure_reason or ""
            final_trace = []
            for index in range(5):
                controller.hold(f"task7_occurrence_final_{index + 1}", 1, gripper=-1.0)
                final_trace.append(predicates(view))
            terminal_valid = bool(
                terminal_skill_success and len(final_trace) == 5
                and all(item == terminal_expected(mode) for item in final_trace)
            )
            records = {row["id"]: row for row in logical["commitments"]}
            history_valid = bool(
                records[occurrence_id(ORIGINAL, 1)]["lifecycle_status"] == "superseded"
                and records[occurrence_id(INTERMEDIATE, 1)]["lifecycle_status"]
                == ("cancelled" if mode == "cancel" else "superseded")
                and (
                    occurrence_id(ORIGINAL, 2) not in records
                    if mode == "cancel" else
                    records[occurrence_id(ORIGINAL, 2)]["lifecycle_status"] == "active"
                )
            )
            row = {
                "suite": "libero_10", "task_id": TASK_ID,
                "state_id": STATE_ID, "mode": mode, "prompt": prompt,
                "runtime_git_commit": runtime_commit,
                "controller_sha256": EXPECTED_CONTROLLER_SHA256,
                "provider_calls": 0, "learned_policy_used": False,
                "prefix_skill_success": prefix.success,
                "prefix_failure": prefix.failure_reason or "",
                "prefix_valid": prefix_valid,
                "prefix_action_sha256": prefix_action_sha256,
                "semantic_no_action": semantic_no_action,
                "semantic_preserved_simulator": semantic_preserved_sim,
                "semantic_state_sha256": stable_hash(logical),
                "history_valid": history_valid, "directive": directive,
                "terminal_skill_success": terminal_skill_success,
                "terminal_failure": terminal_failure,
                "terminal_valid": terminal_valid,
                "action_budget_respected": controller.total_steps <= 700,
                "environment_steps": controller.total_steps,
                "done_predicate": final_trace[-1]["done"],
                "original_predicate": final_trace[-1]["original"],
                "intermediate_predicate": final_trace[-1]["intermediate"],
                "episode_success": bool(
                    prefix_valid and semantic_no_action and semantic_preserved_sim
                    and history_valid and terminal_valid and controller.total_steps <= 700
                ),
            }
            rows.append(row)
        finally:
            env.close()
    gate = len(rows) == 2 and all(row["episode_success"] for row in rows)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    status = {
        "schema": "task7-occurrence-physical-canary-v1",
        "gate": "PASS" if gate else "FAIL", "episodes": 2,
        "successes": sum(bool(row["episode_success"]) for row in rows),
        "provider_calls": 0, "task7_states_indexed": [0],
        "task7_states1_49_indexed": False, "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "runtime_git_commit": runtime_commit,
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
