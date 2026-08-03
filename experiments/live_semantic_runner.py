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
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

from cope.libero_predicate_validator import attach_libero_predicate_snapshot
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.semantic_live_runner import (
    X15_COMPLETION_BUDGET,
    X15_MODEL,
    X15_PROMPT_BUDGET,
    X15_REASONING_EFFORT,
    X15_SEED,
    X15_TEMPERATURE,
    X15_TIMEOUT_SECONDS,
    LIVE_ARMS,
    load_semantic_config,
    recorded_state0_expansion_allowed,
    run_learned_semantic_triplet,
    select_validated_cope_execution,
    sha256_file,
    state0_expansion_allowed,
    validate_case_rows,
)
from cope.semantic_replacement import RECEPTACLE
from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController, OracleSkillConfig
from cope_benchmark.task_progress import LiberoStateView
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
    sim_from_env,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="X15 provider-driven live semantic Phase A")
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--semantic-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--expand-states-1-4", action="store_true")
    parser.add_argument("--state0-results", type=Path)
    parser.add_argument(
        "--execute-cope",
        action="store_true",
        help="Phase B: execute only the accepted CoPE command with the qualified oracle substrate",
    )
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument(
        "--endpoint", default="https://openrouter.ai/api/v1/chat/completions"
    )
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--model", default=X15_MODEL)
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
        raise RuntimeError("X15 smoke requires a clean committed worktree")
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


def observation_packet(obs: dict[str, Any], *, resolution: int) -> dict[str, Any]:
    frame = np.flipud(np.asarray(obs["agentview_image"], dtype=np.uint8))
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


def _flatten(triplet: Mapping[str, Any], runtime: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for arm in triplet["arms"]:
        rows.append(
            {
                "case_id": triplet["case_id"],
                "state_id": triplet["state_id"],
                "event_type": triplet["event_type"],
                "shared_envelope_pass": triplet["shared_envelope"]["pass"],
                "shared_envelope_error": triplet["shared_envelope"]["error"],
                "shared_transaction_meta_sha256": triplet["shared_envelope"].get("transaction_meta_sha256", ""),
                "shared_semantic_state_sha256": triplet["shared_envelope"].get("semantic_state_sha256", ""),
                "shared_event_sha256": triplet["shared_envelope"].get("event_sha256", ""),
                "transaction_base_version": triplet["shared_envelope"].get("transaction_base_version", ""),
                "transaction_pre_state_version": triplet["shared_envelope"].get("transaction_pre_state_version", ""),
                "transaction_post_state_version": triplet["shared_envelope"].get("transaction_post_state_version", ""),
                "transaction_evidence_version": triplet["shared_envelope"].get("transaction_evidence_version", ""),
                "transaction_processed_event_id": triplet["shared_envelope"].get("transaction_processed_event_id", ""),
                "transaction_processed_payload_sha256": triplet["shared_envelope"].get(
                    "transaction_processed_payload_sha256", ""
                ),
                "transaction_metadata_model_generated": triplet["shared_envelope"].get(
                    "transaction_metadata_model_generated", False
                ),
                "arm": arm["arm"],
                "provider_called": arm["provider_called"],
                "provider_status": arm["provider_status"],
                "provider_error": arm["provider_error"],
                "parser_valid": arm["parser_valid"],
                "semantic_valid": arm["semantic_valid"],
                "semantic_correct": arm["semantic_correct"],
                "oracle_substitution": arm["oracle_substitution"],
                "fallback_used": arm["fallback_used"],
                "fairness_pass": arm["fairness_pass"],
                "input_hash": arm["input_hash"],
                "settings_sha256": arm["settings_sha256"],
                "common_input_bytes_sha256": arm["common_input_bytes_sha256"],
                "normalized_request_sha256": arm["normalized_request_sha256"],
                "response_sha256": arm["response_sha256"],
                "before_state_sha256": arm["before_state_sha256"],
                "after_state_sha256": arm["after_state_sha256"],
                "receipt_sha256": arm["receipt_sha256"],
                "compiled_directive": arm["compiled_directive"],
                "prompt_tokens": arm["prompt_tokens"],
                "completion_tokens": arm["completion_tokens"],
                "proposal_bytes": arm["proposal_bytes"],
                "latency_seconds": f"{float(arm['latency_seconds']):.6f}",
                "retry_count": arm["retry_count"],
                "parse_or_validation_error": arm["parse_or_validation_error"],
                "predicate_done": arm["predicate_outcome"]["done"],
                "predicate_pending": arm["predicate_outcome"]["pending"],
                "controller_action_count_before": arm["controller_action_count_before"],
                "controller_action_count_after": arm["controller_action_count_after"],
                "post_interruption_action_delta": arm["post_interruption_action_delta"],
                "simulator_state_before": arm["simulator_state_before"],
                "simulator_state_after": arm["simulator_state_after"],
                **runtime,
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("refusing to write an empty X15 result")
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_family_aggregate(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "event_type",
        "arm",
        "assigned",
        "provider_ok",
        "semantic_correct",
        "parser_valid",
        "fallback_count",
        "oracle_substitution_count",
        "action_delta_sum",
    ]
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for event_type in ("replace_pending_goal", "cancel_pending_goal"):
            for arm in LIVE_ARMS:
                selected = [
                    row
                    for row in rows
                    if row["event_type"] == event_type and row["arm"] == arm
                ]
                writer.writerow(
                    {
                        "event_type": event_type,
                        "arm": arm,
                        "assigned": len(selected),
                        "provider_ok": sum(row["provider_status"] == "ok" for row in selected),
                        "semantic_correct": sum(bool(row["semantic_correct"]) for row in selected),
                        "parser_valid": sum(bool(row["parser_valid"]) for row in selected),
                        "fallback_count": sum(bool(row["fallback_used"]) for row in selected),
                        "oracle_substitution_count": sum(
                            bool(row["oracle_substitution"]) for row in selected
                        ),
                        "action_delta_sum": sum(
                            int(row["post_interruption_action_delta"]) for row in selected
                        ),
                    }
                )


def main() -> int:
    args = parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("X15 Phase A is CPU-only; set CUDA_VISIBLE_DEVICES to empty")
    repo_root = Path(__file__).resolve().parents[1]
    research_root = (repo_root / "research").resolve()
    output_dir = args.output_dir.resolve()
    if research_root not in output_dir.parents:
        raise RuntimeError("X15 outputs must be placed under research/")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")
    runtime_commit = repository_commit_and_clean(repo_root)
    config = load_semantic_config(args.semantic_config, repo_root=repo_root)
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_case_rows(rows)
    provider = OpenAICompatibleRecoveryProvider(
        {
            "provider": args.provider,
            "endpoint": args.endpoint,
            "api_key_env": args.api_key_env,
            "model": args.model,
            "reasoning_effort": X15_REASONING_EFFORT,
            "temperature": X15_TEMPERATURE,
            "seed": X15_SEED,
            "max_prompt_tokens": X15_PROMPT_BUDGET,
            "max_completion_tokens": X15_COMPLETION_BUDGET,
            "max_retries": 0,
            "timeout_seconds": X15_TIMEOUT_SECONDS,
        }
    )
    # Credential check precedes LIBERO suite loading, init-state indexing, and all actions.
    if not os.environ.get(provider.api_key_env):
        output_dir.mkdir(parents=True, exist_ok=False)
        status = {
            "x15_gate": "BLOCKED_CREDENTIAL_UNAVAILABLE",
            "provider_calls": 0,
            "state_ids_indexed": [],
            "controller_actions": 0,
            "credential_env_name": provider.api_key_env,
            "credential_logged": False,
            "oracle_substitution": False,
            "fallback_used": False,
            "reserved_states_27_49_consumed": False,
            "runtime_git_commit": runtime_commit,
        }
        (output_dir / "00_CREDENTIAL_PREFLIGHT.txt").write_text(
            canonical_json(status) + "\n", encoding="utf-8"
        )
        print(canonical_json(status))
        return 3

    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    controller_config = OracleSkillConfig(max_move_steps=60)
    common_runtime = {
        "runtime_git_commit": runtime_commit,
        "case_manifest_sha256": sha256_file(args.case_manifest),
        "semantic_config_sha256": config.sha256,
        "controller_config_sha256": stable_hash(asdict(controller_config)),
        "model": provider.metadata.model,
        "reasoning_effort": provider.reasoning_effort,
        "temperature": provider.metadata.temperature,
        "seed": provider.seed,
        "max_completion_tokens": provider.metadata.max_completion_tokens,
        "retry_budget": provider.metadata.max_retries,
        "repair_budget": 0,
        "reserved_states_27_49_consumed": False,
    }
    triplets: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []
    embodied_rows: list[dict[str, Any]] = []
    journal_path: Path | None = None
    if args.execute_cope:
        output_dir.mkdir(parents=True, exist_ok=False)
        journal_path = output_dir / "00_CASE_JOURNAL.txt"

    def run_states(state_ids: Sequence[int]) -> None:
        for state_id in state_ids:
            if state_id not in range(5):
                raise RuntimeError("X15 attempted to leave development states 0--4")
            state_rows = [row for row in rows if int(row["state_id"]) == state_id]
            if args.execute_cope:
                # HALT is evaluated first and emits no action, so both event
                # families see the exact same physical milestone.
                state_rows.sort(key=lambda row: row["event_type"] != "cancel_pending_goal")
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
                controller = LiberoOracleSkillController(env, obs, config=controller_config)
                warmup = controller.warmup()
                placement = controller.pick_and_place("cream_cheese_1", RECEPTACLE)
                if not placement.success:
                    raise RuntimeError(
                        f"state {state_id} failed physical prefix: {placement.failure_reason}"
                    )
                view = LiberoStateView(env)
                stability_trace: list[dict[str, bool]] = []
                for index in range(5):
                    controller.hold(f"predicate_stability_{index + 1}", 1, gripper=-1.0)
                    stability_trace.append(
                        {
                            "cream_cheese_1": view.libero_predicate(
                                "in", ("cream_cheese_1", RECEPTACLE)
                            ),
                            "butter_1": view.libero_predicate("in", ("butter_1", RECEPTACLE)),
                        }
                    )
                independent = stability_trace[-1]
                if any(
                    item != {"cream_cheese_1": True, "butter_1": False}
                    for item in stability_trace
                ):
                    raise RuntimeError(f"state {state_id} failed stable physical milestone")
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
                    triplet = run_learned_semantic_triplet(
                        row=row,
                        config=config,
                        original_task=prompt,
                        observation=packet,
                        public_action_history=prefix_history,
                        independently_logged_predicates=independent,
                        simulator_state_probe=lambda: simulator_state_hash(env),
                        action_counter=lambda: len(controller.action_history),
                        provider=provider,
                    )
                    triplets.append(triplet)
                    runtime = {
                        **common_runtime,
                        "initial_state_sha256": hashlib.sha256(
                            np.asarray(initial_states[state_id]).tobytes()
                        ).hexdigest(),
                        "prefix_action_sha256": controller.action_prefix_sha256(),
                        "stability_trace_sha256": stable_hash(stability_trace),
                        "warmup_steps": warmup.steps,
                        "initial_state_indexed": state_id,
                    }
                    case_flat_rows = _flatten(triplet, runtime)
                    flat_rows.extend(case_flat_rows)
                    embodied_row: dict[str, Any] | None = None
                    if args.execute_cope:
                        if journal_path is None:
                            raise RuntimeError("Phase-B journal path was not initialized")
                        with journal_path.open("a", encoding="utf-8") as handle:
                            handle.write(
                                canonical_json(
                                    {
                                        "record_type": "semantic",
                                        "case_id": row["case_id"],
                                        "rows": case_flat_rows,
                                    }
                                )
                                + "\n"
                            )
                        cope_arm = next(
                            item for item in triplet["arms"] if item["arm"] == "cope"
                        )
                        decision = select_validated_cope_execution(
                            cope_arm, row["event_type"]
                        )
                        execution_actions_before = len(controller.action_history)
                        execution_sim_before = simulator_state_hash(env)
                        skill = (
                            controller.pick_and_place(
                                decision["selected_object"], RECEPTACLE
                            )
                            if decision["execution_kind"] == "pick_and_place"
                            else None
                        )
                        execution_actions_after = len(controller.action_history)
                        execution_sim_after = simulator_state_hash(env)
                        predicates = {
                            name: view.libero_predicate("in", (name, RECEPTACLE))
                            for name in (
                                row["done_object"],
                                row["pending_object"],
                                row["replacement_object"] or "alphabet_soup_1",
                            )
                        }
                        terminal_goal_success = bool(
                            predicates[row["done_object"]]
                            and (
                                predicates[row["replacement_object"]]
                                if row["event_type"] == "replace_pending_goal"
                                else not predicates[row["pending_object"]]
                            )
                        )
                        suffix = controller.action_history[execution_actions_before:]
                        embodied_row = {
                            "case_id": row["case_id"],
                            "state_id": state_id,
                            "event_type": row["event_type"],
                            "cope_semantic_correct": cope_arm["semantic_correct"],
                            "shared_envelope_pass": triplet["shared_envelope"]["pass"],
                            "selection_source": decision["selection_source"],
                            "execution_kind": decision["execution_kind"],
                            "selected_object": decision["selected_object"],
                            "compiled_directive": decision["compiled_directive"],
                            "low_level_controller": "privileged_simulator_geometry_oracle",
                            "learned_policy_used": False,
                            "provider_called": True,
                            "skill_success": skill.success if skill is not None else True,
                            "skill_failure_reason": (
                                skill.failure_reason or "" if skill is not None else ""
                            ),
                            "terminal_goal_success": terminal_goal_success,
                            "valid_progress_retained": predicates[row["done_object"]],
                            "stale_pending_executed": predicates[row["pending_object"]],
                            "replacement_object_in_region": predicates[
                                row["replacement_object"] or "alphabet_soup_1"
                            ],
                            "post_event_action_count": (
                                execution_actions_after - execution_actions_before
                            ),
                            "post_event_action_sha256": stable_hash(
                                [list(action) for action in suffix]
                            ),
                            "simulator_state_before_execution": execution_sim_before,
                            "simulator_state_after_execution": execution_sim_after,
                            "runtime_git_commit": runtime_commit,
                            "reserved_states_27_49_consumed": False,
                        }
                        embodied_rows.append(embodied_row)
                        with journal_path.open("a", encoding="utf-8") as handle:
                            handle.write(
                                canonical_json(
                                    {
                                        "record_type": "embodied",
                                        "case_id": row["case_id"],
                                        "row": embodied_row,
                                    }
                                )
                                + "\n"
                            )
            finally:
                if env is not None:
                    env.close()

    state0_triplets: list[dict[str, Any]] = []
    if args.expand_states_1_4:
        if args.state0_results is None:
            raise RuntimeError("expansion requires --state0-results from the retained smoke")
        with args.state0_results.open(newline="", encoding="utf-8") as handle:
            retained_state0 = list(csv.DictReader(handle))
        expansion_allowed = recorded_state0_expansion_allowed(retained_state0)
        if not expansion_allowed:
            raise RuntimeError("retained state-0 result does not pass the frozen expansion gate")
        run_states((1, 2, 3, 4))
    else:
        if args.state0_results is not None:
            raise RuntimeError("--state0-results is valid only for expansion")
        # Mandatory first smoke: state 0 only, both event families, no retries.
        run_states((0,))
        state0_triplets = [item for item in triplets if item["state_id"] == 0]
        expansion_allowed = state0_expansion_allowed(state0_triplets)

    if not args.execute_cope:
        output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(output_dir / "01_PER_ARM_RESULTS.csv", flat_rows)
    _write_family_aggregate(output_dir / "02_FAMILY_ARM_AGGREGATE.csv", flat_rows)
    if args.execute_cope:
        _write_csv(output_dir / "03_EMBODIED_RESULTS.csv", embodied_rows)
    status = {
        "state0_triplets": len(state0_triplets),
        "state0_expansion_allowed": expansion_allowed,
        "states_1_4_requested": bool(args.expand_states_1_4),
        "states_1_4_executed": any(item["state_id"] > 0 for item in triplets),
        "provider_calls": len(LIVE_ARMS) * len(triplets),
        "fallback_used": any(item["fallback_used"] for item in triplets),
        "oracle_substitution": any(item["oracle_substitution"] for item in triplets),
        "post_interruption_action_delta": sum(
            int(item["post_interruption_action_delta"]) for item in triplets
        ),
        "embodied_phase_b": bool(args.execute_cope),
        "embodied_cases": len(embodied_rows),
        "embodied_terminal_successes": sum(
            bool(item["terminal_goal_success"]) for item in embodied_rows
        ),
        "embodied_post_event_actions": sum(
            int(item["post_event_action_count"]) for item in embodied_rows
        ),
        "shared_envelope_pass": all(
            item.get("shared_envelope", {}).get("pass") is True for item in triplets
        ),
        "transaction_metadata_model_generated": any(
            item.get("shared_envelope", {}).get("transaction_metadata_model_generated") is True
            for item in triplets
        ),
        "replacement": {
            "triplets": sum(item["event_type"] == "replace_pending_goal" for item in triplets)
        },
        "cancellation": {
            "triplets": sum(item["event_type"] == "cancel_pending_goal" for item in triplets)
        },
        "credential_env_name": provider.api_key_env,
        "credential_logged": False,
        "reserved_states_27_49_consumed": False,
        "runtime_git_commit": runtime_commit,
    }
    status_path = output_dir / (
        "04_RUN_STATUS.txt" if args.execute_cope else "03_RUN_STATUS.txt"
    )
    status_path.write_text(
        canonical_json(status) + "\n", encoding="utf-8"
    )
    print(canonical_json(status))
    embodied_gate = (
        not args.execute_cope
        or (
            len(embodied_rows) == len(triplets)
            and all(item["terminal_goal_success"] for item in embodied_rows)
        )
    )
    return 0 if expansion_allowed and embodied_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
