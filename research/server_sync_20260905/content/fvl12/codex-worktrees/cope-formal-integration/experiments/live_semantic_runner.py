#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cope.libero_predicate_validator import attach_libero_predicate_snapshot
from cope.semantic_live_runner import (
    finalize_mutation_accounting,
    load_semantic_config,
    run_semantic_wiring,
    sha256_file,
    validate_case_rows,
)
from cope.semantic_replacement import RECEPTACLE
from cope.types import stable_hash
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController, OracleSkillConfig
from cope_benchmark.task_progress import LiberoStateView
from libero_experiment_core import ExperimentConfig, create_libero_env, get_benchmark_suite, set_seed, sim_from_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--semantic-config", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
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
        raise RuntimeError("assigned X04 run requires a clean committed worktree")
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
        [np.asarray(sim.data.qpos, dtype="<f8").ravel(), np.asarray(sim.data.qvel, dtype="<f8").ravel()]
    )
    return hashlib.sha256(payload.tobytes()).hexdigest()


def observation_packet(obs: dict[str, Any], *, resolution: int = 256) -> dict[str, Any]:
    frame = np.asarray(obs["agentview_image"], dtype=np.uint8)
    frame = np.flipud(frame)
    image = Image.fromarray(frame).resize((resolution, resolution))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()
    return {
        "encoding": "image/png;base64",
        "rgb": base64.b64encode(png).decode("ascii"),
        "sha256": hashlib.sha256(png).hexdigest(),
        "width": resolution,
        "height": resolution,
        "fresh": True,
    }


def main() -> int:
    args = parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("X04 is preregistered CPU-only; set CUDA_VISIBLE_DEVICES to empty")
    repo_root = Path(__file__).resolve().parents[1]
    if args.output_csv.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_csv}")
    config = load_semantic_config(args.semantic_config, repo_root=repo_root)
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_case_rows(rows)
    manifest_sha256 = sha256_file(args.case_manifest)
    runtime_git_commit = repository_commit_and_clean(repo_root)
    controller_config = OracleSkillConfig(max_move_steps=60)
    controller_config_sha256 = stable_hash(asdict(controller_config))

    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    if len(initial_states) <= max(range(5)):
        raise RuntimeError("LIBERO initial-state container lacks an assigned development state")
    results: list[dict[str, Any]] = []
    by_state = {state_id: [row for row in rows if int(row["state_id"]) == state_id] for state_id in range(5)}
    for state_id, state_rows in by_state.items():
        cfg = ExperimentConfig(
            checkpoint=config.row["checkpoint_path"],
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
        env = None
        try:
            set_seed(state_id)
            env, prompt = create_libero_env(task, cfg)
            env.reset()
            obs = env.set_init_state(initial_states[state_id])
            controller = LiberoOracleSkillController(
                env,
                obs,
                config=controller_config,
            )
            warmup = controller.warmup()
            placement = controller.pick_and_place("cream_cheese_1", RECEPTACLE)
            if not placement.success:
                raise RuntimeError(f"state {state_id} failed physical prefix: {placement.failure_reason}")
            view = LiberoStateView(env)
            stability_trace: list[dict[str, bool]] = []
            for stable_index in range(5):
                controller.hold(
                    f"predicate_stability_{stable_index + 1}", 1, gripper=-1.0
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
            independent = stability_trace[-1]
            if any(
                item != {"cream_cheese_1": True, "butter_1": False}
                for item in stability_trace
            ):
                raise RuntimeError(
                    f"state {state_id} failed the five-step predicate trace: {stability_trace}"
                )
            if independent != {"cream_cheese_1": True, "butter_1": False}:
                raise RuntimeError(f"state {state_id} physical milestone is not canonical: {independent}")
            prefix_history = tuple(
                {"policy_step": index, "environment_action": list(action)}
                for index, action in enumerate(controller.action_history)
            )
            for row in state_rows:
                from cope.semantic_cancellation import build_cancellation_event
                from cope.semantic_replacement import MilestoneEvent, build_replacement_event

                milestone = MilestoneEvent(
                    controller.total_steps,
                    row["done_object"],
                    row["pending_object"],
                    int(row["stable_steps"]),
                )
                event = (
                    build_replacement_event(
                        milestone,
                        pair_key=row["case_id"],
                        replacement_object=row["replacement_object"],
                    )
                    if row["event_type"] == "replace_pending_goal"
                    else build_cancellation_event(milestone, pair_key=row["case_id"])
                )
                sim_before = simulator_state_hash(env)
                action_count_before = len(controller.action_history)
                packet = attach_libero_predicate_snapshot(
                    observation_packet(controller.observation, resolution=args.resolution),
                    env,
                    engine_config=config.predicate_engine_config,
                    observation_fields=config.observation_fields,
                    task_suite="libero_10",
                    task_id=1,
                    event_id=event["event_id"],
                    policy_step=controller.total_steps,
                    simulator_state_sha256=sim_before,
                )
                semantic_result = run_semantic_wiring(
                    row=row,
                    config=config,
                    original_task=prompt,
                    observation=packet,
                    public_action_history=prefix_history,
                    independently_logged_predicates=independent,
                    simulator_state_before=sim_before,
                    controller_action_count_before=action_count_before,
                )
                sim_after_semantics = simulator_state_hash(env)
                result = finalize_mutation_accounting(
                    semantic_result,
                    simulator_state_before=sim_before,
                    simulator_state_after=sim_after_semantics,
                    controller_action_count_before=action_count_before,
                    controller_action_count_after=len(controller.action_history),
                )
                result["initial_state_sha256"] = hashlib.sha256(
                    np.asarray(initial_states[state_id]).tobytes()
                ).hexdigest()
                result["prefix_action_sha256"] = controller.action_prefix_sha256()
                result["independent_predicates_sha256"] = stable_hash(independent)
                result["stability_trace_sha256"] = stable_hash(stability_trace)
                result["stable_steps_observed"] = len(stability_trace)
                result["warmup_steps"] = warmup.steps
                result["controller_config_sha256"] = controller_config_sha256
                result["case_manifest_sha256"] = manifest_sha256
                result["runtime_git_commit"] = runtime_git_commit
                result["gpu_visible"] = os.environ.get("CUDA_VISIBLE_DEVICES", "")
                result["live_packet_builder"] = "attach_libero_predicate_snapshot"
                result["init_container_deserialized"] = True
                result["initial_state_indexed"] = state_id
                result["reserved_states_indexed"] = False
                results.append(result)
        finally:
            if env is not None:
                env.close()

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    passed = sum(row["passed"] is True for row in results)
    print(f"assigned={len(results)} passed={passed} live_packets={len(results)} reserved_state_consumed=0")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
