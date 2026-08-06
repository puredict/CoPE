#!/usr/bin/env python3
"""Embodied development gate for opt-in bounded regrasp on task-1 states 0--4."""

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


AUTHORIZED_STATE_IDS = tuple(range(5))
ALTERNATIVES = ((0.012, 0.0), (-0.012, 0.0), (0.0, 0.012), (0.0, -0.012))
ARM_CONFIGS = {
    "natural_legacy": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.0, 0.0),),
    ),
    "natural_candidate": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.0, 0.0),) + ALTERNATIVES,
    ),
    "stress_single": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.040, 0.0),),
    ),
    "stress_candidate": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.040, 0.0), (0.0, 0.0)) + ALTERNATIVES,
    ),
}
ARM_ORDER = tuple(ARM_CONFIGS)
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
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
        raise RuntimeError("repair development requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def array_hash(array: Any) -> str:
    value = np.asarray(array)
    digest = hashlib.sha256()
    digest.update(str(value.shape).encode("ascii"))
    digest.update(str(value.dtype).encode("ascii"))
    digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def simulator_state_hash(env: Any) -> str:
    sim = sim_from_env(env)
    payload = np.concatenate(
        [
            np.asarray(sim.data.qpos, dtype="<f8").ravel(),
            np.asarray(sim.data.qvel, dtype="<f8").ravel(),
        ]
    )
    return hashlib.sha256(payload.tobytes()).hexdigest()


def phase_summary(phases: list[Any]) -> str:
    return ";".join(
        f"{phase.phase}:{phase.steps}:"
        + ("" if phase.final_error_m is None else f"{phase.final_error_m:.9f}")
        for phase in phases
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_episode(
    *,
    task: Any,
    initial_state: Any,
    state_id: int,
    arm: str,
    config: OracleSkillConfig,
    resolution: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "state_id": state_id,
        "seed": state_id,
        "arm": arm,
        "controller_config_sha256": stable_hash(asdict(config)),
        "prefix_success": False,
        "failure_class": "",
        "initial_state_sha256": array_hash(initial_state),
        "action_prefix_sha256": "",
        "simulator_state_sha256": "",
        "action_count": 0,
        "grasp_acquired": False,
        "object_lift_m": "",
        "target_predicate": False,
        "stable_milestone": False,
        "phase_summary": "",
        "stability_trace": "",
    }
    env = None
    controller = None
    try:
        cfg = ExperimentConfig(
            checkpoint="oracle-skill-controller",
            task_suite="libero_10",
            task_id=1,
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
        env.reset()
        observation = env.set_init_state(initial_state)
        controller = LiberoOracleSkillController(env, observation, config=config)
        controller.warmup()
        placement = controller.pick_and_place("cream_cheese_1", RECEPTACLE)
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
                            "in", ("cream_cheese_1", RECEPTACLE)
                        ),
                        "butter_1": view.libero_predicate(
                            "in", ("butter_1", RECEPTACLE)
                        ),
                    }
                )
        stable = len(stability_trace) == 5 and all(
            item == {"cream_cheese_1": True, "butter_1": False}
            for item in stability_trace
        )
        row["stability_trace"] = canonical_json(stability_trace)
        row["stable_milestone"] = stable
        row["prefix_success"] = bool(placement.success and stable)
        if not placement.success:
            row["failure_class"] = placement.failure_reason or "skill_failure"
        elif not stable:
            row["failure_class"] = "stable_physical_milestone_false"
    except Exception as exc:
        row["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
    finally:
        if controller is not None:
            row["action_prefix_sha256"] = controller.action_prefix_sha256()
            row["action_count"] = controller.total_steps
        if env is not None:
            row["simulator_state_sha256"] = simulator_state_hash(env)
            env.close()
    return row


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("provider credentials forbidden: " + ",".join(populated))
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope_bounded_regrasp_development_v1",
        "runtime_git_commit": runtime_commit,
        "authorized_state_ids": list(AUTHORIZED_STATE_IDS),
        "arm_order": list(ARM_ORDER),
        "arm_configs": {name: asdict(config) for name, config in ARM_CONFIGS.items()},
        "arm_config_sha256": {
            name: stable_hash(asdict(config)) for name, config in ARM_CONFIGS.items()
        },
        "states_5_49_not_indexed": True,
        "provider_calls": 0,
        "provider_credentials_present": False,
    }
    (args.output_dir / "00_RUN_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    journal = args.output_dir / "01_ATTEMPT_JOURNAL.txt"
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    rows: list[dict[str, Any]] = []
    for state_id in AUTHORIZED_STATE_IDS:
        for arm in ARM_ORDER:
            row = run_episode(
                task=task,
                initial_state=initial_states[state_id],
                state_id=state_id,
                arm=arm,
                config=ARM_CONFIGS[arm],
                resolution=args.resolution,
            )
            rows.append(row)
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(row) + "\n")
            print(canonical_json(row), flush=True)

    csv_path = args.output_dir / "02_RESULTS.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    by_arm = {
        arm: sum(row["prefix_success"] for row in rows if row["arm"] == arm)
        for arm in ARM_ORDER
    }
    natural_hash_equal = all(
        next(
            row["action_prefix_sha256"]
            for row in rows
            if row["state_id"] == state_id and row["arm"] == "natural_legacy"
        )
        == next(
            row["action_prefix_sha256"]
            for row in rows
            if row["state_id"] == state_id and row["arm"] == "natural_candidate"
        )
        for state_id in AUTHORIZED_STATE_IDS
    )
    failures = Counter(
        f"{row['arm']}:{row['failure_class']}"
        for row in rows
        if not row["prefix_success"]
    )
    gates = {
        "natural_legacy_all_success": by_arm["natural_legacy"] == 5,
        "natural_candidate_all_success": by_arm["natural_candidate"] == 5,
        "natural_action_hashes_equal": natural_hash_equal,
        "stress_candidate_strictly_better": (
            by_arm["stress_candidate"] > by_arm["stress_single"]
        ),
    }
    result = [
        "# Bounded regrasp development result",
        "",
        f"- Runtime commit: `{runtime_commit}`",
        f"- Successes by arm: `{canonical_json(by_arm)}`",
        f"- Gate results: `{canonical_json(gates)}`",
        f"- Failure classes: `{canonical_json(dict(sorted(failures.items())))}`",
        "- Provider calls: **0**",
        "- States 5--49 indexed by this runner: **no**",
    ]
    (args.output_dir / "03_RESULT.md").write_text(
        "\n".join(result) + "\n", encoding="utf-8"
    )
    artifacts = sorted(
        path for path in args.output_dir.iterdir() if path.name != "04_SHA256SUMS.txt"
    )
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in artifacts) + "\n",
        encoding="utf-8",
    )
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
