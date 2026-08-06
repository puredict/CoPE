#!/usr/bin/env python3
"""Resume only missing physical executions from a frozen semantic journal."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from cope.semantic_live_runner import (
    LIVE_ARMS,
    build_expected_live_post_state,
    load_semantic_config,
    select_validated_live_execution,
    sha256_file,
    validate_live_persistent_state,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    RECEPTACLE,
    build_replacement_event,
)
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


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--semantic-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def simulator_state_hash(env: Any) -> str:
    sim = sim_from_env(env)
    payload = np.concatenate(
        [
            np.asarray(sim.data.qpos, dtype="<f8").ravel(),
            np.asarray(sim.data.qvel, dtype="<f8").ravel(),
        ]
    )
    return hashlib.sha256(payload.tobytes()).hexdigest()


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("refusing to write empty resume evidence")
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = arguments()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("execution resume is CPU-only")
    if os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("execution-only resume forbids a provider credential")
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir.resolve()
    if (repo_root / "research").resolve() not in output_dir.parents:
        raise RuntimeError("resume output must be under research/")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("resume requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    records = [
        json.loads(line)
        for line in args.journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    semantic_records = [
        record for record in records if record.get("record_type") == "semantic"
    ]
    embodied_records = [
        record for record in records if record.get("record_type") == "embodied"
    ]
    if (
        len(records) != 6
        or len(semantic_records) != 2
        or len(embodied_records) != 4
    ):
        raise RuntimeError("interrupted journal shape differs from frozen recovery case")
    semantic_rows = [
        dict(row)
        for record in semantic_records
        for row in record.get("rows", [])
    ]
    cancellation_rows = [
        dict(record["row"]) for record in embodied_records
    ]
    if (
        len(semantic_rows) != 2 * len(LIVE_ARMS)
        or {row["arm"] for row in semantic_rows if row["event_type"] == "replace_pending_goal"}
        != set(LIVE_ARMS)
        or any(row["event_type"] != "cancel_pending_goal" for row in cancellation_rows)
    ):
        raise RuntimeError("retained semantic or cancellation assignment is incomplete")

    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    replacement_manifest = [
        row
        for row in manifest
        if int(row["state_id"]) == 0
        and row["event_type"] == "replace_pending_goal"
    ]
    if len(replacement_manifest) != 1:
        raise RuntimeError("resume requires exactly one development state-0 replacement")
    case = replacement_manifest[0]
    config = load_semantic_config(args.semantic_config, repo_root=repo_root)
    retained_replacement = [
        row for row in semantic_rows if row["event_type"] == "replace_pending_goal"
    ]
    reference = retained_replacement[0]
    if (
        reference["case_manifest_sha256"] != sha256_file(args.case_manifest)
        or reference["semantic_config_sha256"] != config.sha256
        or any(row["input_hash"] != reference["input_hash"] for row in retained_replacement)
        or any(row["settings_sha256"] != reference["settings_sha256"] for row in retained_replacement)
    ):
        raise RuntimeError("retained semantic rows fail manifest/config/fairness binding")

    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    state_id = 0
    controller_config = OracleSkillConfig(max_move_steps=60)
    cfg = ExperimentConfig(
        checkpoint=config.row["checkpoint_path"],
        task_suite="libero_10",
        task_id=1,
        trial_id=state_id,
        mode="clean",
        max_steps=400,
        num_steps_wait=0,
        seed=state_id,
        resolution=64,
        enable_auto_disturbance=False,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    resume_journal = output_dir / "00_RESUME_JOURNAL.txt"
    resumed_rows: list[dict[str, Any]] = []
    for arm_row in retained_replacement:
        arm = str(arm_row["arm"])
        semantic_correct = str(arm_row["semantic_correct"]).lower() == "true"
        if not semantic_correct:
            resumed_rows.append(
                {
                    "case_id": case["case_id"],
                    "state_id": state_id,
                    "event_type": case["event_type"],
                    "arm": arm,
                    "semantic_correct": False,
                    "execution_attempted": False,
                    "matched_prefix_pass": True,
                    "selection_source": "",
                    "execution_kind": "fail_closed",
                    "selected_object": "",
                    "compiled_directive": "",
                    "low_level_controller": "not_invoked",
                    "learned_policy_used": False,
                    "provider_called_during_resume": False,
                    "original_response_sha256": arm_row["response_sha256"],
                    "skill_success": False,
                    "skill_failure_reason": arm_row["parse_or_validation_error"],
                    "terminal_goal_success": False,
                    "valid_progress_retained": True,
                    "stale_pending_executed": False,
                    "replacement_object_in_region": False,
                    "post_event_action_count": 0,
                    "post_event_action_sha256": stable_hash([]),
                    "simulator_state_before_execution": arm_row["simulator_state_before"],
                    "simulator_state_after_execution": arm_row["simulator_state_before"],
                    "original_runtime_git_commit": arm_row["runtime_git_commit"],
                    "resume_runtime_git_commit": runtime_commit,
                    "reserved_states_27_49_consumed": False,
                }
            )
            with resume_journal.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(resumed_rows[-1]) + "\n")
            continue

        env = None
        try:
            set_seed(state_id)
            env, prompt = create_libero_env(task, cfg)
            env.reset()
            observation = env.set_init_state(initial_states[state_id])
            controller = LiberoOracleSkillController(
                env, observation, config=controller_config
            )
            warmup = controller.warmup()
            placement = controller.pick_and_place("cream_cheese_1", RECEPTACLE)
            if not placement.success:
                raise RuntimeError(
                    f"resume prefix failed: {placement.failure_reason}"
                )
            view = LiberoStateView(env)
            stability_trace = []
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
            initial_sha256 = hashlib.sha256(
                np.asarray(initial_states[state_id]).tobytes()
            ).hexdigest()
            if prompt != (
                "put both the cream cheese box and the butter in the basket"
            ):
                raise RuntimeError("resume task prompt differs from frozen task")
            if (
                controller.action_prefix_sha256()
                != arm_row["prefix_action_sha256"]
                or simulator_state_hash(env) != arm_row["simulator_state_before"]
                or stable_hash(stability_trace)
                != arm_row["stability_trace_sha256"]
                or initial_sha256 != arm_row["initial_state_sha256"]
                or warmup.steps != int(arm_row["warmup_steps"])
            ):
                raise RuntimeError("resume prefix provenance differs from retained row")
            milestone = MilestoneEvent(
                controller.total_steps,
                case["done_object"],
                case["pending_object"],
                int(case["stable_steps"]),
            )
            event = build_replacement_event(
                milestone,
                pair_key=case["case_id"],
                replacement_object=case["replacement_object"],
            )
            if event["event_id"] != arm_row["transaction_processed_event_id"]:
                raise RuntimeError("resume event ID differs from retained transaction")
            expected_state = build_expected_live_post_state(event)
            if stable_hash(expected_state) != arm_row["after_state_sha256"]:
                raise RuntimeError("retained provider post-state hash is not canonical")
            directive = validate_live_persistent_state(
                expected_state, event, ("cream_cheese_1",)
            )
            if directive != arm_row["compiled_directive"]:
                raise RuntimeError("retained compiled directive differs from canonical state")
            decision = select_validated_live_execution(
                {
                    "arm": arm,
                    "semantic_correct": True,
                    "trusted_after_state": expected_state,
                    "compiled_directive": directive,
                },
                case["event_type"],
            )
            actions_before = len(controller.action_history)
            sim_before = simulator_state_hash(env)
            skill = controller.pick_and_place(
                decision["selected_object"], RECEPTACLE
            )
            actions_after = len(controller.action_history)
            sim_after = simulator_state_hash(env)
            predicates = {
                name: view.libero_predicate("in", (name, RECEPTACLE))
                for name in (
                    case["done_object"],
                    case["pending_object"],
                    case["replacement_object"],
                )
            }
            suffix = controller.action_history[actions_before:]
            resumed_rows.append(
                {
                    "case_id": case["case_id"],
                    "state_id": state_id,
                    "event_type": case["event_type"],
                    "arm": arm,
                    "semantic_correct": True,
                    "execution_attempted": True,
                    "matched_prefix_pass": True,
                    "selection_source": decision["selection_source"],
                    "execution_kind": decision["execution_kind"],
                    "selected_object": decision["selected_object"],
                    "compiled_directive": decision["compiled_directive"],
                    "low_level_controller": "privileged_simulator_geometry_oracle",
                    "learned_policy_used": False,
                    "provider_called_during_resume": False,
                    "original_response_sha256": arm_row["response_sha256"],
                    "skill_success": skill.success,
                    "skill_failure_reason": skill.failure_reason or "",
                    "terminal_goal_success": bool(
                        predicates[case["done_object"]]
                        and predicates[case["replacement_object"]]
                    ),
                    "valid_progress_retained": predicates[case["done_object"]],
                    "stale_pending_executed": predicates[case["pending_object"]],
                    "replacement_object_in_region": predicates[
                        case["replacement_object"]
                    ],
                    "post_event_action_count": actions_after - actions_before,
                    "post_event_action_sha256": stable_hash(
                        [list(action) for action in suffix]
                    ),
                    "simulator_state_before_execution": sim_before,
                    "simulator_state_after_execution": sim_after,
                    "original_runtime_git_commit": arm_row["runtime_git_commit"],
                    "resume_runtime_git_commit": runtime_commit,
                    "reserved_states_27_49_consumed": False,
                }
            )
        finally:
            if env is not None:
                env.close()
        with resume_journal.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(resumed_rows[-1]) + "\n")

    valid_resumed = [
        row for row in resumed_rows if row["semantic_correct"]
    ]
    invalid_resumed = [
        row for row in resumed_rows if not row["semantic_correct"]
    ]
    cancellation_valid = [
        row
        for row in cancellation_rows
        if bool(row["semantic_correct"])
    ]
    cancellation_invalid = [
        row
        for row in cancellation_rows
        if not bool(row["semantic_correct"])
    ]
    pass_gate = bool(
        len(valid_resumed) == 2
        and all(
            row["execution_attempted"]
            and row["terminal_goal_success"]
            and row["valid_progress_retained"]
            and not row["stale_pending_executed"]
            for row in valid_resumed
        )
        and len({row["post_event_action_count"] for row in valid_resumed}) == 1
        and len({row["post_event_action_sha256"] for row in valid_resumed}) == 1
        and len(invalid_resumed) == 2
        and all(not row["execution_attempted"] for row in invalid_resumed)
        and len(cancellation_valid) == 2
        and all(
            row["execution_attempted"]
            and row["terminal_goal_success"]
            and int(row["post_event_action_count"]) == 0
            for row in cancellation_valid
        )
        and len(cancellation_invalid) == 2
        and all(not row["execution_attempted"] for row in cancellation_invalid)
    )
    write_csv(output_dir / "01_RETAINED_SEMANTIC_RESULTS.csv", semantic_rows)
    write_csv(
        output_dir / "02_RETAINED_CANCELLATION_RESULTS.csv",
        cancellation_rows,
    )
    write_csv(output_dir / "03_RESUMED_REPLACEMENT_RESULTS.csv", resumed_rows)
    status_payload = {
        "status": "PASS" if pass_gate else "FAIL",
        "provider_calls_during_resume": 0,
        "source_journal_sha256": sha256_file(args.journal),
        "source_journal_lines": len(records),
        "retained_provider_rows": len(semantic_rows),
        "retained_cancellation_rows": len(cancellation_rows),
        "resumed_replacement_rows": len(resumed_rows),
        "valid_replacement_terminal_successes": sum(
            bool(row["terminal_goal_success"]) for row in valid_resumed
        ),
        "invalid_replacement_fail_closed": sum(
            not bool(row["execution_attempted"]) for row in invalid_resumed
        ),
        "runtime_git_commit": runtime_commit,
        "reserved_states_27_49_consumed": False,
    }
    (output_dir / "04_RESUME_STATUS.txt").write_text(
        canonical_json(status_payload) + "\n", encoding="utf-8"
    )
    print(canonical_json(status_payload))
    return 0 if pass_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
