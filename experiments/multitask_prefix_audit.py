#!/usr/bin/env python3
"""Frozen task-0/task-7 prefix audit on development states 0--9 only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from cope.semantic_replacement import RECEPTACLE
from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController, OracleSkillConfig
from cope_benchmark.task_progress import LiberoStateView
from libero_experiment_core import ExperimentConfig, create_libero_env, get_benchmark_suite, set_seed, sim_from_env


STATE_IDS = tuple(range(10))
TASK_SPECS = (
    {"task_id": 0, "done_object": "alphabet_soup_1", "pending_object": "tomato_sauce_1"},
    {"task_id": 7, "done_object": "alphabet_soup_1", "pending_object": "cream_cheese_1"},
)
ALTERNATIVES = ((0.012, 0.0), (-0.012, 0.0), (0.0, 0.012), (0.0, -0.012))
CONTROLLER_CONFIG = OracleSkillConfig(
    max_move_steps=60,
    grasp_attempt_xy_offsets_m=((0.0, 0.0),) + ALTERNATIVES,
)
EXPECTED_CONFIG_HASH = "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a"
PROVIDER_ENV_NAMES = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def repo_commit(repo_root: Path) -> str:
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, check=True, capture_output=True, text=True).stdout
    if status.strip():
        raise RuntimeError("multitask prefix audit requires a clean committed worktree")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()


def array_hash(value: Any) -> str:
    array = np.asarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii")); digest.update(str(array.dtype).encode("ascii")); digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def simulator_hash(env: Any) -> str:
    sim = sim_from_env(env)
    values = np.concatenate([np.asarray(sim.data.qpos, dtype="<f8").ravel(), np.asarray(sim.data.qvel, dtype="<f8").ravel()])
    return hashlib.sha256(values.tobytes()).hexdigest()


def phase_summary(phases: list[Any]) -> str:
    return ";".join(f"{phase.phase}:{phase.steps}:" + ("" if phase.final_error_m is None else f"{phase.final_error_m:.9f}") for phase in phases)


def run_episode(task: Any, initial_state: Any, spec: dict[str, Any], state_id: int, resolution: int) -> dict[str, Any]:
    task_id = int(spec["task_id"]); done_object = str(spec["done_object"]); pending_object = str(spec["pending_object"])
    row: dict[str, Any] = {
        "task_id": task_id, "state_id": state_id, "seed": state_id,
        "done_object": done_object, "pending_object": pending_object,
        "prefix_success": False, "failure_class": "",
        "initial_state_sha256": array_hash(initial_state), "action_prefix_sha256": "",
        "simulator_state_sha256": "", "action_count": 0,
        "grasp_acquired": False, "object_lift_m": "", "target_predicate": False,
        "stable_milestone": False, "regrasp_activated": False,
        "phase_summary": "", "stability_trace": "",
    }
    env = None; controller = None
    try:
        cfg = ExperimentConfig(checkpoint="oracle-skill-controller", task_suite="libero_10", task_id=task_id, trial_id=state_id, mode="clean", max_steps=700, num_steps_wait=0, seed=state_id, resolution=resolution, enable_auto_disturbance=False)
        set_seed(state_id); env, _ = create_libero_env(task, cfg); env.reset(); observation = env.set_init_state(initial_state)
        controller = LiberoOracleSkillController(env, observation, config=CONTROLLER_CONFIG)
        controller.warmup(); placement = controller.pick_and_place(done_object, RECEPTACLE)
        row["grasp_acquired"] = placement.grasp_acquired; row["object_lift_m"] = f"{placement.object_lift_m:.9f}"
        row["target_predicate"] = placement.target_predicate; row["phase_summary"] = phase_summary(placement.phases)
        row["regrasp_activated"] = "regrasp_1_open_gripper" in row["phase_summary"]
        trace: list[dict[str, bool]] = []
        if placement.success:
            view = LiberoStateView(env)
            for index in range(5):
                controller.hold(f"predicate_stability_{index + 1}", 1, gripper=-1.0)
                trace.append({"done": view.libero_predicate("in", (done_object, RECEPTACLE)), "pending": view.libero_predicate("in", (pending_object, RECEPTACLE))})
        stable = len(trace) == 5 and all(item == {"done": True, "pending": False} for item in trace)
        row["stability_trace"] = canonical_json(trace); row["stable_milestone"] = stable; row["prefix_success"] = bool(placement.success and stable)
        if not placement.success: row["failure_class"] = placement.failure_reason or "skill_failure"
        elif not stable: row["failure_class"] = "stable_physical_milestone_false"
    except Exception as exc:
        row["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
    finally:
        if controller is not None:
            row["action_prefix_sha256"] = controller.action_prefix_sha256(); row["action_count"] = controller.total_steps
        if env is not None:
            row["simulator_state_sha256"] = simulator_hash(env); env.close()
    return row


def main() -> int:
    args = parse_args(); repo_root = Path(__file__).resolve().parents[1]; runtime_commit = repo_commit(repo_root)
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH: raise RuntimeError("validated controller config hash mismatch")
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated: raise RuntimeError("provider credentials forbidden: " + ",".join(populated))
    if args.output_dir.exists(): raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {"schema":"cope-multitask-prefix-audit-v1","runtime_git_commit":runtime_commit,"task_specs":TASK_SPECS,"authorized_state_ids":STATE_IDS,"controller_config":asdict(CONTROLLER_CONFIG),"controller_config_sha256":EXPECTED_CONFIG_HASH,"provider_calls":0,"task0_task7_states_10_49_indexed":False,"task1_states_25_49_indexed":False}
    (args.output_dir / "00_METADATA.txt").write_text(canonical_json(metadata) + "\n", encoding="utf-8")
    suite = get_benchmark_suite("libero_10"); rows: list[dict[str, Any]] = []; journal = args.output_dir / "01_JOURNAL.txt"
    for spec in TASK_SPECS:
        task_id = int(spec["task_id"]); task = suite.get_task(task_id); states = suite.get_task_init_states(task_id)
        for state_id in STATE_IDS:
            row = run_episode(task, states[state_id], spec, state_id, args.resolution); rows.append(row)
            with journal.open("a", encoding="utf-8") as handle: handle.write(canonical_json(row) + "\n")
            print(canonical_json(row), flush=True)
    with (args.output_dir / "02_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    successes = {str(spec["task_id"]): sum(row["prefix_success"] for row in rows if row["task_id"] == spec["task_id"]) for spec in TASK_SPECS}
    failures = Counter(row["failure_class"] for row in rows if not row["prefix_success"]); passed = all(value == 10 for value in successes.values())
    (args.output_dir / "03_RESULT.md").write_text("# Multi-task prefix audit result\n\n" + f"- Gate: **{'PASS' if passed else 'FAIL'}**\n- Successes: `{canonical_json(successes)}`\n- Failures: `{canonical_json(dict(sorted(failures.items())))}`\n- Provider calls: **0**\n- Formal states indexed: **0**\n", encoding="utf-8")
    artifacts = sorted(args.output_dir.iterdir()); (args.output_dir / "04_SHA256SUMS.txt").write_text("\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts) + "\n", encoding="utf-8")
    return 0 if passed else 2


if __name__ == "__main__": raise SystemExit(main())
