#!/usr/bin/env python3
"""Preregistered task-9 state0 cross-predicate commitment canary."""

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

from cope.arity_commitment_sequence import (
    DONE_ATOM,
    HEATING_REGION,
    MICROWAVE,
    PORCELAIN_MUG,
    REPLACEMENT_ATOM,
    YELLOW_MUG,
    build_event,
    build_initial_state,
    execute_transition,
    initialize_typed_state,
    oracle_proposal,
    state_hash,
)
from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController
from cope_benchmark.task_progress import LiberoStateView
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG, EXPECTED_CONFIG_HASH
from experiments.sequential_formal_runner import observation_hash, simulator_hash
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
)


TASK_ID = 9
STATE_ID = 0
EXPECTED_EVENT1_DIRECTIVE = (
    "place_in(porcelain_mug_1, microwave_1_heating_region)"
)
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


def snapshot(view: LiberoStateView) -> dict[str, bool]:
    return {
        "yellow_in_microwave": view.libero_predicate(
            "in", (YELLOW_MUG, HEATING_REGION)
        ),
        "porcelain_in_microwave": view.libero_predicate(
            "in", (PORCELAIN_MUG, HEATING_REGION)
        ),
        "microwave_open": view.libero_predicate("open", (MICROWAVE,)),
        "microwave_closed": view.libero_predicate("close", (MICROWAVE,)),
    }


def semantic_sequence(sequence_id: str, world_version: int):
    logical0 = build_initial_state(sequence_id=sequence_id, world_version=world_version)
    typed0 = initialize_typed_state(sequence_id=sequence_id)
    event1 = build_event(
        logical0, sequence_id=sequence_id, step_index=1,
        event_type="replace_pending_goal", replacement_atom=REPLACEMENT_ATOM,
        world_version=world_version + 1,
    )
    typed1, logical1, receipt1, directive1 = execute_transition(
        typed0, logical0, event1, oracle_proposal(event1),
        physically_true_ids=(DONE_ATOM.commitment_id,),
    )
    event2 = build_event(
        logical1, sequence_id=sequence_id, step_index=2,
        event_type="cancel_pending_goal", replacement_atom=None,
        world_version=world_version + 2,
    )
    typed2, logical2, receipt2, directive2 = execute_transition(
        typed1, logical1, event2, oracle_proposal(event2),
        physically_true_ids=(DONE_ATOM.commitment_id,),
    )
    return {
        "logical_states": (logical0, logical1, logical2),
        "events": (event1, event2),
        "receipts": (receipt1, receipt2),
        "directives": (directive1, directive2),
        "typed_revision": typed2.revision,
    }


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("task9 canary requires a clean committed worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("task9 canary requires CUDA_VISIBLE_DEVICES='' ")
    if [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]:
        raise RuntimeError("task9 canary refuses provider credentials")
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH:
        raise RuntimeError("historical controller config hash mismatch")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope-task9-cross-predicate-canary-v1",
        "runtime_git_commit": commit,
        "task_suite": "libero_10",
        "task_id": TASK_ID,
        "state_id": STATE_ID,
        "controller_config": asdict(CONTROLLER_CONFIG),
        "controller_config_sha256": EXPECTED_CONFIG_HASH,
        "bddl_sha256": "456d145f92be049f445fc77673dc583d9d17ea7afe92f6ffcb2fd1fa5565d420",
        "development_reserve": list(range(1, 10)),
        "formal_reserve": list(range(10, 30)),
        "untouched_holdout": list(range(30, 50)),
        "provider_calls": 0,
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
        "initial_contract_valid": False,
        "prefix_placement_success": False,
        "prefix_stable_success": False,
        "semantic_success": False,
        "cell_success": False,
        "failure_class": "",
        "provider_calls": 0,
        "task9_states_1_49_indexed": 0,
        "task6_states_opened_after_stop": 0,
        "task1_forbidden_states_indexed": 0,
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
            env, observation, config=CONTROLLER_CONFIG
        )
        view = LiberoStateView(env)
        initial_snapshot = snapshot(view)
        initial_expected = {
            "yellow_in_microwave": False,
            "porcelain_in_microwave": False,
            "microwave_open": True,
            "microwave_closed": False,
        }
        result["initial_contract_valid"] = initial_snapshot == initial_expected
        if not result["initial_contract_valid"]:
            raise RuntimeError("initial predicate contract mismatch")
        controller.warmup()
        placement = controller.pick_and_place(YELLOW_MUG, HEATING_REGION)
        trace = []
        for index in range(5):
            controller.hold(f"task9_prefix_stability_{index + 1}", 1, gripper=-1.0)
            trace.append(snapshot(view))
        prefix_expected = {
            "yellow_in_microwave": True,
            "porcelain_in_microwave": False,
            "microwave_open": True,
            "microwave_closed": False,
        }
        stable = len(trace) == 5 and all(item == prefix_expected for item in trace)
        result["prefix_placement_success"] = placement.success
        result["prefix_stable_success"] = stable
        if not placement.success or not stable:
            result["failure_class"] = (
                placement.failure_reason or "prefix_predicate_stability_failure"
            )
        else:
            before_semantic_actions = controller.total_steps
            sequence = semantic_sequence(
                f"task9-state{STATE_ID}-canary", controller.total_steps
            )
            after_semantic_actions = controller.total_steps
            directives = sequence["directives"]
            post_semantic_snapshot = snapshot(view)
            semantic_valid = (
                directives == (EXPECTED_EVENT1_DIRECTIVE, "HALT")
                and sequence["typed_revision"] == 3
                and before_semantic_actions == after_semantic_actions
                and post_semantic_snapshot == prefix_expected
            )
            result.update(
                {
                    "semantic_success": semantic_valid,
                    "event1_directive": directives[0],
                    "event2_directive": directives[1],
                    "event_ids": canonical_json(
                        [event["event_id"] for event in sequence["events"]]
                    ),
                    "state_hashes": canonical_json(
                        [state_hash(state) for state in sequence["logical_states"]]
                    ),
                    "receipt_hashes": canonical_json(
                        [stable_hash(receipt) for receipt in sequence["receipts"]]
                    ),
                    "semantic_action_delta": after_semantic_actions - before_semantic_actions,
                }
            )
            if not semantic_valid:
                result["failure_class"] = "semantic_contract_failure"
        result.update(
            {
                "cell_success": bool(
                    result["initial_contract_valid"]
                    and result["prefix_placement_success"]
                    and result["prefix_stable_success"]
                    and result["semantic_success"]
                ),
                "initial_snapshot": canonical_json(initial_snapshot),
                "prefix_trace": canonical_json(trace),
                "action_count": controller.total_steps,
                "action_sha256": controller.action_prefix_sha256(),
                "simulator_sha256": simulator_hash(env),
                "observation_sha256": observation_hash(controller.observation),
                "placement_phases": canonical_json(
                    [asdict(phase) for phase in placement.phases]
                ),
                "released_after_stability": not controller.is_grasping(YELLOW_MUG),
            }
        )
    except Exception as exc:
        if not result["failure_class"]:
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
        "# Task-9 cross-predicate state-0 canary result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Initial contract: **{'PASS' if result['initial_contract_valid'] else 'FAIL'}**\n"
        f"- Physical prefix: **{'PASS' if result['prefix_stable_success'] else 'FAIL'}**\n"
        f"- Two-event zero-action semantics: **{'PASS' if result['semantic_success'] else 'FAIL'}**\n"
        f"- Failure: `{result['failure_class']}`\n"
        "- Provider calls: **0**\n"
        "- Task-9 states 1--49 indexed: **0**\n",
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

