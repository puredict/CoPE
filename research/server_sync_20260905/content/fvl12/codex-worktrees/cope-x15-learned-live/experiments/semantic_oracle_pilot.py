#!/usr/bin/env python3
"""Two-state CPU Oracle pilot for semantic replacement and cancellation."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from cope.libero_predicate_validator import attach_libero_predicate_snapshot
from cope.semantic_live_runner import (
    LoadedSemanticConfig,
    finalize_mutation_accounting,
    load_semantic_config,
    run_oracle_semantic_fixture,
    sha256_file,
)
from cope.semantic_replacement import RECEPTACLE
from cope.types import stable_hash
from cope_benchmark.oracle_skill_controller import (
    LiberoOracleSkillController,
    OracleSkillConfig,
)
from cope_benchmark.task_progress import LiberoStateView
from experiments.live_semantic_runner import (
    observation_packet,
    repository_commit_and_clean,
    simulator_state_hash,
)
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
)


TASK_SUITE = "libero_10"
TASK_ID = 1
DONE_OBJECT = "cream_cheese_1"
PENDING_OBJECT = "butter_1"
REPLACEMENT_OBJECT = "alphabet_soup_1"
AUTHORIZED_STATES = frozenset({25, 26})
EVENT_TYPES = frozenset({"replace_pending_goal", "cancel_pending_goal"})
ARMS = ("native_fsr_pc", "oracle_cope")
CONTROLLER_CONFIG = OracleSkillConfig(max_move_steps=60)


RESULT_FIELDS = (
    "pair_id",
    "arm",
    "task_suite",
    "task_id",
    "state_id",
    "event_type",
    "runtime_git_commit",
    "authorization_sha256",
    "source_manifest_sha256",
    "semantic_config_sha256",
    "controller_config_sha256",
    "resolution",
    "seed",
    "initial_state_sha256",
    "prefix_action_sha256",
    "prefix_action_count",
    "event_policy_step",
    "event_simulator_sha256",
    "event_rgb_sha256",
    "event_packet_sha256",
    "event_recovery_input_sha256",
    "checkpoint_pose_sha256",
    "checkpoint_eef_position",
    "checkpoint_done_position",
    "checkpoint_pending_position",
    "checkpoint_replacement_position",
    "stable_steps_required",
    "stable_steps_observed",
    "semantic_pass",
    "canonical_states_equal",
    "directives_equal",
    "compiled_directive",
    "provider_called",
    "validator_is_fake",
    "semantic_simulator_unchanged",
    "semantic_actions_unchanged",
    "selected_semantic_arm",
    "post_event_target_object",
    "post_event_policy_action_budget",
    "post_event_policy_actions",
    "verification_hold_steps_required",
    "verification_hold_steps_observed",
    "verification_environment_actions",
    "post_event_skill_success",
    "done_object_final",
    "pending_object_final",
    "replacement_object_final",
    "valid_progress_retained",
    "stale_pending_executed",
    "updated_goal_success",
    "final_action_prefix_sha256",
    "final_simulator_sha256",
    "reserved_states_27_49_indexed",
    "passed",
    "failure_stage",
    "error_type",
    "error_message",
)


PAIR_FIELDS = (
    "pair_id",
    "state_id",
    "event_type",
    "arm_count",
    "both_arms_passed",
    "initial_state_equal",
    "prefix_action_equal",
    "prefix_count_equal",
    "event_step_equal",
    "event_simulator_equal",
    "event_rgb_equal",
    "event_packet_equal",
    "recovery_input_equal",
    "checkpoint_pose_equal",
    "compiled_directive_equal",
    "final_action_prefix_equal",
    "final_simulator_equal",
    "budgets_respected",
    "pair_passed",
)


@dataclass(frozen=True)
class PilotAuthorization:
    row: dict[str, str]
    path: Path
    sha256: str
    manifest_path: Path
    manifest_sha256: str
    cases: tuple[dict[str, str], ...]
    semantic_config: LoadedSemanticConfig


def validate_pilot_manifest(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != 2:
        raise ValueError("Oracle pilot manifest must contain exactly two rows")
    expected = {(25, "replace_pending_goal"), (26, "cancel_pending_goal")}
    observed = {(int(row["state_id"]), str(row["event_type"])) for row in rows}
    if observed != expected:
        raise ValueError("Oracle pilot manifest is not the frozen state25/state26 assignment")
    for row in rows:
        state_id = int(row["state_id"])
        event_type = str(row["event_type"])
        if state_id not in AUTHORIZED_STATES:
            raise ValueError("Oracle pilot attempted to index a non-authorized state")
        if int(row["stable_steps"]) != 5 or int(row["deadline"]) != 300:
            raise ValueError("Oracle pilot milestone threshold was retuned")
        if row.get("status") != "reserved_uninspected":
            raise ValueError("Oracle pilot source reserve was already consumed or modified")
        if event_type == "replace_pending_goal":
            if row.get("replacement_object") != REPLACEMENT_OBJECT:
                raise ValueError("replacement object differs from preregistration")
            if int(row["post_event_action_budget"]) != 280 or int(row["hold_steps"]) != 0:
                raise ValueError("replacement budget differs from preregistration")
        else:
            if row.get("replacement_object", "") or int(row["post_event_action_budget"]) != 0:
                raise ValueError("cancellation policy-action budget differs from preregistration")
            if int(row["hold_steps"]) != 30:
                raise ValueError("cancellation verification window differs from preregistration")


def load_authorization(path: Path, *, repo_root: Path) -> PilotAuthorization:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError("pilot authorization must contain exactly one row")
    row = {str(key): str(value) for key, value in rows[0].items()}
    required = {
        "schema_version": "cope-x09-oracle-pilot-authorization-v1",
        "authorized_state_ids": "25;26",
        "authorized_event_types": "replace_pending_goal;cancel_pending_goal",
        "resolution": "64",
        "state27_49_locked": "true",
        "run_authorized": "true",
    }
    for key, expected in required.items():
        if row.get(key) != expected:
            raise ValueError(f"pilot authorization {key} is not the frozen value")
    controller_hash = stable_hash(asdict(CONTROLLER_CONFIG))
    if row.get("controller_config_sha256") != controller_hash:
        raise ValueError("pilot authorization controller config differs from X04")

    manifest_path = repo_root / row["source_manifest_path"]
    semantic_config_path = repo_root / row["semantic_config_path"]
    x04_result_path = repo_root / row["x04_result_path"]
    for target, expected, label in (
        (manifest_path, row["source_manifest_sha256"], "source manifest"),
        (semantic_config_path, row["semantic_config_sha256"], "semantic config"),
        (x04_result_path, row["x04_result_sha256"], "X04 result"),
    ):
        if not target.is_file() or sha256_file(target) != expected:
            raise ValueError(f"pilot authorization {label} digest mismatch")
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        cases = tuple(dict(item) for item in csv.DictReader(handle))
    validate_pilot_manifest(cases)
    semantic_config = load_semantic_config(semantic_config_path, repo_root=repo_root)

    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            row["x04_evidence_commit"],
            "HEAD",
        ],
        cwd=repo_root,
    )
    if ancestor.returncode != 0:
        raise ValueError("committed X04 evidence is not an ancestor of the pilot runtime")
    with x04_result_path.open(newline="", encoding="utf-8") as handle:
        x04_rows = list(csv.DictReader(handle))
    if len(x04_rows) != 10 or any(item.get("passed") != "True" for item in x04_rows):
        raise ValueError("X04 assigned evidence is not a clean 10/10 pass")
    return PilotAuthorization(
        row=row,
        path=path,
        sha256=sha256_file(path),
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        cases=cases,
        semantic_config=semantic_config,
    )


def _predicates(view: LiberoStateView) -> dict[str, bool]:
    return {
        DONE_OBJECT: view.libero_predicate("in", (DONE_OBJECT, RECEPTACLE)),
        PENDING_OBJECT: view.libero_predicate("in", (PENDING_OBJECT, RECEPTACLE)),
        REPLACEMENT_OBJECT: view.libero_predicate(
            "in", (REPLACEMENT_OBJECT, RECEPTACLE)
        ),
    }


def _position(controller: LiberoOracleSkillController, name: str) -> list[float]:
    return [float(value) for value in controller.position(name)]


def _base_row(case: Mapping[str, str], arm: str) -> dict[str, Any]:
    row = {field: "" for field in RESULT_FIELDS}
    row.update(
        {
            "pair_id": case["pair_id"],
            "arm": arm,
            "task_suite": TASK_SUITE,
            "task_id": TASK_ID,
            "state_id": int(case["state_id"]),
            "event_type": case["event_type"],
            "stable_steps_required": int(case["stable_steps"]),
            "post_event_policy_action_budget": int(case["post_event_action_budget"]),
            "verification_hold_steps_required": int(case["hold_steps"]),
            "provider_called": False,
            "reserved_states_27_49_indexed": False,
            "passed": False,
        }
    )
    return row


def run_arm(
    *,
    case: Mapping[str, str],
    arm: str,
    authorization: PilotAuthorization,
    runtime_commit: str,
    suite: Any,
    task: Any,
    initial_states: Any,
) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError(f"unknown semantic arm {arm!r}")
    state_id = int(case["state_id"])
    if state_id not in AUTHORIZED_STATES:
        raise ValueError("pilot state is outside the explicit authorization")
    row = _base_row(case, arm)
    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_suite=TASK_SUITE,
        task_id=TASK_ID,
        trial_id=state_id,
        mode="clean",
        max_steps=600,
        num_steps_wait=0,
        seed=state_id,
        resolution=int(authorization.row["resolution"]),
        enable_auto_disturbance=False,
    )
    env = None
    row.update(
        {
            "runtime_git_commit": runtime_commit,
            "authorization_sha256": authorization.sha256,
            "source_manifest_sha256": authorization.manifest_sha256,
            "semantic_config_sha256": authorization.semantic_config.sha256,
            "controller_config_sha256": stable_hash(asdict(CONTROLLER_CONFIG)),
            "resolution": int(authorization.row["resolution"]),
            "seed": state_id,
        }
    )
    try:
        set_seed(state_id)
        initial_state = initial_states[state_id]
        initial_hash = __import__("hashlib").sha256(
            np.asarray(initial_state).tobytes()
        ).hexdigest()
        row["initial_state_sha256"] = initial_hash
        env, prompt = create_libero_env(task, cfg)
        env.reset()
        observation = env.set_init_state(initial_state)
        controller = LiberoOracleSkillController(
            env, observation, config=CONTROLLER_CONFIG
        )
        controller.warmup()
        first = controller.pick_and_place(DONE_OBJECT, RECEPTACLE)
        if not first.success:
            raise RuntimeError(f"common prefix failed: {first.failure_reason}")
        view = LiberoStateView(env)
        stability_trace: list[dict[str, bool]] = []
        for index in range(int(case["stable_steps"])):
            controller.hold(f"pilot_stability_{index + 1}", 1, gripper=-1.0)
            truth = _predicates(view)
            stability_trace.append(truth)
            if not truth[DONE_OBJECT] or truth[PENDING_OBJECT]:
                raise RuntimeError(
                    f"five-step milestone failed at step {index + 1}: {truth}"
                )

        independent = {
            DONE_OBJECT: stability_trace[-1][DONE_OBJECT],
            PENDING_OBJECT: stability_trace[-1][PENDING_OBJECT],
        }
        prefix_history = tuple(
            {
                "policy_step": index,
                "environment_action": list(action),
            }
            for index, action in enumerate(controller.action_history)
        )
        semantic_row = {
            "case_id": case["pair_id"],
            "state_id": case["state_id"],
            "event_type": case["event_type"],
            "done_object": DONE_OBJECT,
            "pending_object": PENDING_OBJECT,
            "replacement_object": case["replacement_object"],
            "stable_steps": case["stable_steps"],
        }

        # Build the event once to bind the live packet. The explicitly named
        # oracle fixture below is isolated from the X15 production runner.
        # deterministically rebuilds the same event from semantic_row.
        from cope.semantic_cancellation import build_cancellation_event
        from cope.semantic_replacement import MilestoneEvent, build_replacement_event

        milestone = MilestoneEvent(
            controller.total_steps,
            DONE_OBJECT,
            PENDING_OBJECT,
            int(case["stable_steps"]),
        )
        event = (
            build_replacement_event(
                milestone,
                pair_key=case["pair_id"],
                replacement_object=case["replacement_object"],
            )
            if case["event_type"] == "replace_pending_goal"
            else build_cancellation_event(milestone, pair_key=case["pair_id"])
        )
        prefix_hash = controller.action_prefix_sha256()
        prefix_count = controller.total_steps
        sim_before = simulator_state_hash(env)
        checkpoint_pose = {
            "eef": [float(value) for value in controller.observation["robot0_eef_pos"]],
            "done": _position(controller, DONE_OBJECT),
            "pending": _position(controller, PENDING_OBJECT),
            "replacement": _position(controller, REPLACEMENT_OBJECT),
        }
        row.update(
            {
                "prefix_action_sha256": prefix_hash,
                "prefix_action_count": prefix_count,
                "event_policy_step": controller.total_steps,
                "event_simulator_sha256": sim_before,
                "checkpoint_pose_sha256": stable_hash(checkpoint_pose),
                "checkpoint_eef_position": json.dumps(checkpoint_pose["eef"]),
                "checkpoint_done_position": json.dumps(checkpoint_pose["done"]),
                "checkpoint_pending_position": json.dumps(checkpoint_pose["pending"]),
                "checkpoint_replacement_position": json.dumps(
                    checkpoint_pose["replacement"]
                ),
                "stable_steps_observed": len(stability_trace),
            }
        )
        outer_observation = observation_packet(
            controller.observation,
            resolution=int(authorization.row["resolution"]),
        )
        live_observation = attach_libero_predicate_snapshot(
            outer_observation,
            env,
            engine_config=authorization.semantic_config.predicate_engine_config,
            observation_fields=authorization.semantic_config.observation_fields,
            task_suite=TASK_SUITE,
            task_id=TASK_ID,
            event_id=event["event_id"],
            policy_step=controller.total_steps,
            simulator_state_sha256=sim_before,
        )
        row.update(
            {
                "event_rgb_sha256": live_observation["sha256"],
                "event_packet_sha256": live_observation["predicate_snapshot"][
                    "snapshot_sha256"
                ],
            }
        )
        semantic = run_oracle_semantic_fixture(
            row=semantic_row,
            config=authorization.semantic_config,
            original_task=prompt,
            observation=live_observation,
            public_action_history=prefix_history,
            independently_logged_predicates=independent,
            simulator_state_before=sim_before,
            controller_action_count_before=prefix_count,
            authorized_state_ids=AUTHORIZED_STATES,
        )
        semantic = finalize_mutation_accounting(
            semantic,
            simulator_state_before=sim_before,
            simulator_state_after=simulator_state_hash(env),
            controller_action_count_before=prefix_count,
            controller_action_count_after=controller.total_steps,
        )
        if semantic["passed"] is not True:
            raise RuntimeError("X04 semantic wiring failed inside the pilot episode")

        row.update(
            {
                "event_recovery_input_sha256": semantic[
                    "native_recovery_input_sha256"
                ],
                "semantic_pass": semantic["semantic_pass"],
                "canonical_states_equal": semantic["canonical_states_equal"],
                "directives_equal": semantic["directives_equal"],
                "provider_called": semantic["provider_called"],
                "validator_is_fake": semantic["validator_is_fake"],
                "semantic_simulator_unchanged": semantic[
                    "simulator_unchanged_by_semantics"
                ],
                "semantic_actions_unchanged": semantic[
                    "controller_actions_unchanged_by_semantics"
                ],
            }
        )

        directive = json.loads(semantic["compiled_directive"])
        policy_actions = 0
        verification_actions = 0
        skill_success = True
        post_event_target = ""
        if case["event_type"] == "replace_pending_goal":
            if directive != (
                "put both the alphabet soup and the cream cheese box in the basket"
            ):
                raise RuntimeError("replacement directive differs from shared compiler")
            post_event_target = REPLACEMENT_OBJECT
            action_start = controller.total_steps
            skill = controller.pick_and_place(REPLACEMENT_OBJECT, RECEPTACLE)
            policy_actions = controller.total_steps - action_start
            skill_success = bool(skill.success)
        else:
            if directive != "HALT":
                raise RuntimeError("cancellation directive is not HALT")
            action_start = controller.total_steps
            # These neutral environment steps are an observation window, not
            # execution of a task policy or the cancelled butter commitment.
            for index in range(int(case["hold_steps"])):
                controller.hold(
                    f"cancellation_verification_{index + 1}", 1, gripper=-1.0
                )
            verification_actions = controller.total_steps - action_start
            policy_actions = 0

        final_truth = _predicates(view)
        replacement_success = bool(
            final_truth[DONE_OBJECT]
            and final_truth[REPLACEMENT_OBJECT]
            and not final_truth[PENDING_OBJECT]
        )
        cancellation_success = bool(
            final_truth[DONE_OBJECT] and not final_truth[PENDING_OBJECT]
        )
        event_pass = bool(
            semantic["passed"] is True
            and not final_truth[PENDING_OBJECT]
            and final_truth[DONE_OBJECT]
            and (
                (
                    case["event_type"] == "replace_pending_goal"
                    and skill_success
                    and policy_actions <= int(case["post_event_action_budget"])
                    and replacement_success
                    and verification_actions == 0
                )
                or (
                    case["event_type"] == "cancel_pending_goal"
                    and policy_actions == 0
                    and verification_actions == int(case["hold_steps"])
                    and cancellation_success
                )
            )
        )
        row.update(
            {
                "initial_state_sha256": initial_hash,
                "prefix_action_sha256": prefix_hash,
                "prefix_action_count": prefix_count,
                "event_policy_step": live_observation["predicate_snapshot"]["policy_step"],
                "event_simulator_sha256": sim_before,
                "event_rgb_sha256": live_observation["sha256"],
                "event_packet_sha256": live_observation["predicate_snapshot"][
                    "snapshot_sha256"
                ],
                "event_recovery_input_sha256": semantic[
                    "native_recovery_input_sha256"
                ],
                "checkpoint_pose_sha256": stable_hash(checkpoint_pose),
                "checkpoint_eef_position": json.dumps(checkpoint_pose["eef"]),
                "checkpoint_done_position": json.dumps(checkpoint_pose["done"]),
                "checkpoint_pending_position": json.dumps(checkpoint_pose["pending"]),
                "checkpoint_replacement_position": json.dumps(
                    checkpoint_pose["replacement"]
                ),
                "stable_steps_observed": len(stability_trace),
                "semantic_pass": semantic["semantic_pass"],
                "canonical_states_equal": semantic["canonical_states_equal"],
                "directives_equal": semantic["directives_equal"],
                "compiled_directive": directive,
                "provider_called": semantic["provider_called"],
                "validator_is_fake": semantic["validator_is_fake"],
                "semantic_simulator_unchanged": semantic[
                    "simulator_unchanged_by_semantics"
                ],
                "semantic_actions_unchanged": semantic[
                    "controller_actions_unchanged_by_semantics"
                ],
                "selected_semantic_arm": arm,
                "post_event_target_object": post_event_target,
                "post_event_policy_actions": policy_actions,
                "verification_hold_steps_observed": verification_actions,
                "verification_environment_actions": verification_actions,
                "post_event_skill_success": skill_success,
                "done_object_final": final_truth[DONE_OBJECT],
                "pending_object_final": final_truth[PENDING_OBJECT],
                "replacement_object_final": final_truth[REPLACEMENT_OBJECT],
                "valid_progress_retained": final_truth[DONE_OBJECT],
                "stale_pending_executed": final_truth[PENDING_OBJECT],
                "updated_goal_success": (
                    replacement_success
                    if case["event_type"] == "replace_pending_goal"
                    else cancellation_success
                ),
                "final_action_prefix_sha256": controller.action_prefix_sha256(),
                "final_simulator_sha256": simulator_state_hash(env),
                "passed": event_pass,
            }
        )
        return row
    except Exception as exc:
        row.update(
            {
                "failure_stage": "pilot_episode",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "passed": False,
            }
        )
        return row
    finally:
        if env is not None:
            env.close()


def audit_pairs(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    equality_fields = {
        "initial_state_equal": "initial_state_sha256",
        "prefix_action_equal": "prefix_action_sha256",
        "prefix_count_equal": "prefix_action_count",
        "event_step_equal": "event_policy_step",
        "event_simulator_equal": "event_simulator_sha256",
        "event_rgb_equal": "event_rgb_sha256",
        "event_packet_equal": "event_packet_sha256",
        "recovery_input_equal": "event_recovery_input_sha256",
        "checkpoint_pose_equal": "checkpoint_pose_sha256",
        "compiled_directive_equal": "compiled_directive",
        "final_action_prefix_equal": "final_action_prefix_sha256",
        "final_simulator_equal": "final_simulator_sha256",
    }
    for pair_id in sorted({str(row["pair_id"]) for row in rows}):
        pair = [row for row in rows if str(row["pair_id"]) == pair_id]
        audit: dict[str, Any] = {
            "pair_id": pair_id,
            "state_id": pair[0].get("state_id", "") if pair else "",
            "event_type": pair[0].get("event_type", "") if pair else "",
            "arm_count": len(pair),
            "both_arms_passed": len(pair) == 2
            and {str(item.get("arm")) for item in pair} == set(ARMS)
            and all(item.get("passed") in (True, "True", "true") for item in pair),
        }
        for output_name, field in equality_fields.items():
            values = [item.get(field) for item in pair]
            audit[output_name] = (
                len(pair) == 2
                and all(value not in (None, "") for value in values)
                and len({str(value) for value in values}) == 1
            )
        required_budget_fields = (
            "post_event_policy_actions",
            "post_event_policy_action_budget",
            "verification_hold_steps_observed",
            "verification_hold_steps_required",
        )
        audit["budgets_respected"] = (
            len(pair) == 2
            and all(
                item.get(field) not in (None, "")
                for item in pair
                for field in required_budget_fields
            )
            and all(
                int(item["post_event_policy_actions"])
                <= int(item["post_event_policy_action_budget"])
                and int(item["verification_hold_steps_observed"])
                == int(item["verification_hold_steps_required"])
                for item in pair
            )
        )
        audit["pair_passed"] = all(
            audit.get(field) in (True, "True", "true")
            for field in PAIR_FIELDS
            if field not in {"pair_id", "state_id", "event_type", "arm_count", "pair_passed"}
        ) and audit["arm_count"] == 2
        audits.append(audit)
    return audits


def _write_row(
    writer: csv.DictWriter, handle: Any, row: Mapping[str, Any]
) -> None:
    writer.writerow({field: row.get(field, "") for field in RESULT_FIELDS})
    handle.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--result-csv", type=Path, required=True)
    parser.add_argument("--pair-audit-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("X09 is CPU-only; CUDA_VISIBLE_DEVICES must be empty")
    if args.result_csv.exists() or args.pair_audit_csv.exists():
        raise FileExistsError("X09 refuses to overwrite either assigned output")
    repo_root = Path(__file__).resolve().parents[1]
    authorization = load_authorization(args.authorization, repo_root=repo_root)
    runtime_commit = repository_commit_and_clean(repo_root)
    suite = get_benchmark_suite(TASK_SUITE)
    task = suite.get_task(TASK_ID)
    initial_states = suite.get_task_init_states(TASK_ID)
    if len(initial_states) <= max(AUTHORIZED_STATES):
        raise RuntimeError("LIBERO init-state container lacks an authorized pilot state")

    args.result_csv.parent.mkdir(parents=True, exist_ok=True)
    result_rows: list[dict[str, Any]] = []
    with args.result_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        handle.flush()
        for case in authorization.cases:
            for arm in ARMS:
                row = _base_row(case, arm)
                try:
                    row = run_arm(
                        case=case,
                        arm=arm,
                        authorization=authorization,
                        runtime_commit=runtime_commit,
                        suite=suite,
                        task=task,
                        initial_states=initial_states,
                    )
                except Exception as exc:
                    row.update(
                        {
                            "runtime_git_commit": runtime_commit,
                            "authorization_sha256": authorization.sha256,
                            "source_manifest_sha256": authorization.manifest_sha256,
                            "semantic_config_sha256": authorization.semantic_config.sha256,
                            "controller_config_sha256": stable_hash(
                                asdict(CONTROLLER_CONFIG)
                            ),
                            "failure_stage": "pilot_episode",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "passed": False,
                        }
                    )
                result_rows.append(row)
                _write_row(writer, handle, row)

    pair_rows = audit_pairs(result_rows)
    with args.pair_audit_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(pair_rows)
    passed = len(result_rows) == 4 and all(row["passed"] is True for row in result_rows)
    paired = len(pair_rows) == 2 and all(row["pair_passed"] is True for row in pair_rows)
    print(
        f"arms={len(result_rows)} arm_passed={sum(row['passed'] is True for row in result_rows)} "
        f"pairs={len(pair_rows)} pair_passed={sum(row['pair_passed'] is True for row in pair_rows)} "
        "states27_49_indexed=0",
        flush=True,
    )
    return 0 if passed and paired else 1


if __name__ == "__main__":
    raise SystemExit(main())
