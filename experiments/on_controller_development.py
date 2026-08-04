#!/usr/bin/env python3
"""One-cell non-task6 development gate for bounded `on` placement."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import (
    LiberoOracleSkillController,
    OnPlacementConfig,
)
from cope_benchmark.task_progress import LiberoStateView
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG, EXPECTED_CONFIG_HASH
from experiments.sequential_formal_runner import observation_hash, simulator_hash
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
)


TASK_ID = 4
STATE_ID = 0
OBJECT = "porcelain_mug_1"
TARGET = "plate_1"
SIBLING_OBJECT = "white_yellow_mug_1"
SIBLING_TARGET = "plate_2"
ON_CONFIG = OnPlacementConfig()
EXPECTED_ON_CONFIG_HASH = "1cb870a686ea52179eb4c72fe75e234fb1f860f1050b510ea25ca3261861438d"
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def array_hash(value: Any) -> str:
    array = np.asarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("on-controller development requires a clean committed worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("on-controller development requires CUDA_VISIBLE_DEVICES='' ")
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("on-controller development refuses provider credentials")
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH:
        raise RuntimeError("historical controller config hash mismatch")
    if stable_hash(asdict(ON_CONFIG)) != EXPECTED_ON_CONFIG_HASH:
        raise RuntimeError("on-placement config hash mismatch")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope-on-controller-development-v1",
        "runtime_git_commit": commit,
        "task_suite": "libero_10",
        "task_id": TASK_ID,
        "state_id": STATE_ID,
        "object": OBJECT,
        "target": TARGET,
        "controller_config_sha256": EXPECTED_CONFIG_HASH,
        "on_config": asdict(ON_CONFIG),
        "on_config_sha256": EXPECTED_ON_CONFIG_HASH,
        "provider_calls": 0,
        "task6_states_indexed": 0,
        "cuda_visible_devices": "",
    }
    (args.output_dir / "00_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(TASK_ID)
    initial_state = suite.get_task_init_states(TASK_ID)[STATE_ID]
    result: dict[str, Any] = {
        "task_suite": "libero_10",
        "task_id": TASK_ID,
        "state_id": STATE_ID,
        "initial_state_sha256": array_hash(initial_state),
        "placement_success": False,
        "stable_success": False,
        "cell_success": False,
        "failure_class": "",
        "provider_calls": 0,
        "task6_states_indexed": 0,
    }
    env = None
    journal = args.output_dir / "01_JOURNAL.txt"
    try:
        cfg = ExperimentConfig(
            checkpoint="oracle-skill-controller",
            task_suite="libero_10",
            task_id=TASK_ID,
            trial_id=STATE_ID,
            mode="clean",
            max_steps=700,
            num_steps_wait=0,
            seed=STATE_ID,
            resolution=args.resolution,
            enable_auto_disturbance=False,
        )
        set_seed(STATE_ID)
        env, _ = create_libero_env(task, cfg)
        env.reset()
        observation = env.set_init_state(initial_state)
        controller = LiberoOracleSkillController(
            env, observation, config=CONTROLLER_CONFIG, on_config=ON_CONFIG
        )
        view = LiberoStateView(env)
        initial_snapshot = {
            "target": view.libero_predicate("on", (OBJECT, TARGET)),
            "sibling": view.libero_predicate("on", (SIBLING_OBJECT, SIBLING_TARGET)),
        }
        start_object_position = controller.position(OBJECT).tolist()
        target_position = controller.position(TARGET).tolist()
        controller.warmup()
        placement = controller.pick_and_place(OBJECT, TARGET, predicate="on")
        trace = []
        for index in range(5):
            controller.hold(f"on_development_stability_{index + 1}", 1, gripper=-1.0)
            trace.append(
                {
                    "target": view.libero_predicate("on", (OBJECT, TARGET)),
                    "sibling": view.libero_predicate(
                        "on", (SIBLING_OBJECT, SIBLING_TARGET)
                    ),
                }
            )
        stable = len(trace) == 5 and all(
            item == {"target": True, "sibling": False} for item in trace
        )
        result.update(
            {
                "placement_success": placement.success,
                "stable_success": stable,
                "cell_success": bool(placement.success and stable),
                "failure_class": (
                    "" if placement.success and stable
                    else placement.failure_reason or "predicate_stability_failure"
                ),
                "action_count": controller.total_steps,
                "action_sha256": controller.action_prefix_sha256(),
                "simulator_sha256": simulator_hash(env),
                "observation_sha256": observation_hash(controller.observation),
                "initial_snapshot": canonical_json(initial_snapshot),
                "stability_trace": canonical_json(trace),
                "start_object_position": canonical_json(start_object_position),
                "target_position": canonical_json(target_position),
                "final_object_position": canonical_json(
                    controller.position(OBJECT).tolist()
                ),
                "phase_records": canonical_json(
                    [asdict(phase) for phase in placement.phases]
                ),
                "released": not controller.is_grasping(OBJECT),
            }
        )
    except Exception as exc:
        result["failure_class"] = f"exception:{type(exc).__name__}:{exc}"
    finally:
        if env is not None:
            env.close()
    journal.write_text(canonical_json(result) + "\n", encoding="utf-8")
    with (args.output_dir / "02_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result), lineterminator="\n")
        writer.writeheader()
        writer.writerow(result)
    passed = bool(result["cell_success"])
    (args.output_dir / "03_RESULT.md").write_text(
        "# Generic on-controller task-4 state-0 result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Placement: **{'PASS' if result['placement_success'] else 'FAIL'}**\n"
        f"- Five-check stability: **{'PASS' if result['stable_success'] else 'FAIL'}**\n"
        f"- Failure: `{result['failure_class']}`\n"
        "- Provider calls: **0**\n"
        "- Task-6 states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in artifacts
        ) + "\n",
        encoding="utf-8",
    )
    print(canonical_json(result), flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

