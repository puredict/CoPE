#!/usr/bin/env python3
"""Frozen zero-provider shared-prefix diagnostic for LIBERO task 1 states 5--14."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from cope.semantic_replacement import RECEPTACLE
from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import (
    LiberoOracleSkillController,
    OracleSkillConfig,
)
from cope_benchmark.task_progress import LiberoStateView
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
    sim_from_env,
)


AUTHORIZED_STATE_IDS = tuple(range(5, 15))
LOCKED_STATE_IDS = tuple(range(15, 25))
CONTROLLER_CONFIG = OracleSkillConfig(max_move_steps=60)
OBJECT_NAME = "cream_cheese_1"
EXPECTED_STABILITY = {"cream_cheese_1": True, "butter_1": False}
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen task-1 states 5--14 prefix diagnostic"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def repository_commit_and_clean(repo_root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("prefix audit requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def simulator_state_hash(env: Any) -> str:
    sim = sim_from_env(env)
    payload = np.concatenate(
        [
            np.asarray(sim.data.qpos, dtype="<f8").ravel(),
            np.asarray(sim.data.qvel, dtype="<f8").ravel(),
        ]
    )
    return hashlib.sha256(payload.tobytes()).hexdigest()


def array_hash(array: Any) -> str:
    value = np.asarray(array)
    digest = hashlib.sha256()
    digest.update(str(value.shape).encode("ascii"))
    digest.update(str(value.dtype).encode("ascii"))
    digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def phase_summary(phases: list[Any]) -> str:
    return ";".join(
        ":".join(
            (
                phase.phase,
                str(phase.steps),
                "" if phase.final_error_m is None else f"{phase.final_error_m:.9f}",
            )
        )
        for phase in phases
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    populated_credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated_credentials:
        raise RuntimeError(
            "zero-provider audit refuses to start with provider credentials in environment: "
            + ",".join(populated_credentials)
        )
    if args.output_dir.exists():
        raise FileExistsError(f"output directory already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "schema": "cope_prefix_feasibility_diagnostic_v1",
        "runtime_git_commit": runtime_commit,
        "authorized_state_ids": list(AUTHORIZED_STATE_IDS),
        "locked_state_ids_not_indexed": list(LOCKED_STATE_IDS),
        "states_25_49_not_indexed": True,
        "controller_config": asdict(CONTROLLER_CONFIG),
        "controller_config_sha256": stable_hash(asdict(CONTROLLER_CONFIG)),
        "provider_calls": 0,
        "provider_credentials_present": False,
        "retry_budget": 0,
        "resolution": args.resolution,
    }
    (args.output_dir / "00_RUN_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    journal_path = args.output_dir / "01_ATTEMPT_JOURNAL.txt"

    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    rows: list[dict[str, Any]] = []

    for state_id in AUTHORIZED_STATE_IDS:
        env = None
        row: dict[str, Any] = {
            "state_id": state_id,
            "seed": state_id,
            "attempted_once": True,
            "prefix_success": False,
            "failure_class": "",
            "initial_state_sha256": array_hash(initial_states[state_id]),
            "action_prefix_sha256": "",
            "simulator_state_sha256": "",
            "action_count": 0,
            "warmup_steps": 0,
            "skill_steps": 0,
            "grasp_acquired": False,
            "object_lift_m": "",
            "target_predicate": False,
            "stable_milestone": False,
            "initial_object_xyz": "",
            "initial_eef_xyz": "",
            "final_object_xyz": "",
            "final_eef_xyz": "",
            "phase_summary": "",
            "stability_trace": "",
            "prompt_sha256": "",
        }
        controller = None
        try:
            cfg = ExperimentConfig(
                checkpoint="oracle-skill-controller",
                task_suite="libero_10",
                task_id=1,
                trial_id=state_id,
                mode="clean",
                max_steps=400,
                num_steps_wait=0,
                seed=state_id,
                resolution=args.resolution,
                enable_auto_disturbance=False,
            )
            set_seed(state_id)
            env, prompt = create_libero_env(task, cfg)
            env.reset()
            observation = env.set_init_state(initial_states[state_id])
            controller = LiberoOracleSkillController(
                env, observation, config=CONTROLLER_CONFIG
            )
            row["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            row["initial_object_xyz"] = canonical_json(
                controller.position(OBJECT_NAME).tolist()
            )
            row["initial_eef_xyz"] = canonical_json(
                np.asarray(observation["robot0_eef_pos"], dtype=float).tolist()
            )
            warmup = controller.warmup()
            row["warmup_steps"] = warmup.steps
            placement = controller.pick_and_place(OBJECT_NAME, RECEPTACLE)
            row["skill_steps"] = placement.total_steps
            row["grasp_acquired"] = placement.grasp_acquired
            row["object_lift_m"] = f"{placement.object_lift_m:.9f}"
            row["target_predicate"] = placement.target_predicate
            row["phase_summary"] = phase_summary(placement.phases)

            stability_trace: list[dict[str, bool]] = []
            if placement.success:
                view = LiberoStateView(env)
                for index in range(5):
                    controller.hold(
                        f"predicate_stability_{index + 1}", 1, gripper=-1.0
                    )
                    stability_trace.append(
                        {
                            "cream_cheese_1": view.libero_predicate(
                                "in", (OBJECT_NAME, RECEPTACLE)
                            ),
                            "butter_1": view.libero_predicate(
                                "in", ("butter_1", RECEPTACLE)
                            ),
                        }
                    )
            row["stability_trace"] = canonical_json(stability_trace)
            stable = len(stability_trace) == 5 and all(
                item == EXPECTED_STABILITY for item in stability_trace
            )
            row["stable_milestone"] = stable
            row["prefix_success"] = bool(placement.success and stable)
            if not placement.success:
                row["failure_class"] = placement.failure_reason or "skill_failure"
            elif not stable:
                row["failure_class"] = "stable_physical_milestone_false"
        except Exception as exc:  # retain every failed attempt; never retry
            row["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
        finally:
            if controller is not None:
                row["action_prefix_sha256"] = controller.action_prefix_sha256()
                row["action_count"] = controller.total_steps
                row["final_object_xyz"] = canonical_json(
                    controller.position(OBJECT_NAME).tolist()
                )
                row["final_eef_xyz"] = canonical_json(
                    np.asarray(
                        controller.observation["robot0_eef_pos"], dtype=float
                    ).tolist()
                )
            if env is not None:
                row["simulator_state_sha256"] = simulator_state_hash(env)
                env.close()

        rows.append(row)
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(row) + "\n")
        print(canonical_json(row), flush=True)

    results_path = args.output_dir / "02_PREFIX_RESULTS.csv"
    write_csv(results_path, rows)
    failures = Counter(
        str(row["failure_class"]) for row in rows if not bool(row["prefix_success"])
    )
    success_count = sum(bool(row["prefix_success"]) for row in rows)
    result_lines = [
        "# Shared-prefix diagnostic result",
        "",
        f"- Runtime commit: `{runtime_commit}`",
        f"- Authorized states attempted: `{','.join(map(str, AUTHORIZED_STATE_IDS))}`",
        f"- Prefix success: **{success_count}/{len(rows)}**",
        f"- Prefix failures: **{len(rows) - success_count}/{len(rows)}**",
        f"- Failure classes: `{canonical_json(dict(sorted(failures.items())))}`",
        "- Provider calls: **0**",
        "- States 15--24 indexed: **no**",
        "- States 25--49 indexed: **no**",
        "",
        "Any failure blocks use of this controller as a guaranteed formal event constructor.",
    ]
    (args.output_dir / "03_RESULT.md").write_text(
        "\n".join(result_lines) + "\n", encoding="utf-8"
    )
    artifact_paths = sorted(
        path for path in args.output_dir.iterdir() if path.name != "04_SHA256SUMS.txt"
    )
    checksum_lines = [f"{sha256_file(path)}  {path.name}" for path in artifact_paths]
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return 0 if success_count == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
