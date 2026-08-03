#!/usr/bin/env python3
"""Embodied two-event formal runner for the frozen task-0 manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.semantic_replacement import RECEPTACLE
from cope.sequential_prompting import (
    ARMS,
    CONTRACTS,
    MAX_COMPLETION_TOKENS,
    MAX_PROMPT_TOKENS,
    MODEL,
    REASONING_EFFORT,
    TEMPERATURE,
    TIMEOUT_SECONDS,
    build_sequential_recovery_input,
)
from cope.sequential_semantics import (
    build_initial_sequence_state,
    build_sequence_event,
    execute_typed_sparse_transition,
    initialize_typed_sequence_state,
    materialize_fsr_proposal,
    materialize_full_replan_proposal,
    materialize_neutral_json_patch,
    sequence_state_hash,
)
from cope.types import canonical_json, stable_hash
from cope_benchmark.task_progress import LiberoStateView
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG
from experiments.sequential_formal_preflight import validate_manifest
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
    set_seed,
    sim_from_env,
)


EXPECTED_MANIFEST_SHA256 = "1fe0b231bb17e9ed0711c76ee440928faccf84696043ac0a84ddd9645bf6b7ec"
EXPECTED_CONTROLLER_SHA256 = "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a"
RESULT_FIELDS = (
    "sequence_id", "arm", "event_index", "task_id", "state_id",
    "prefix_orientation", "sequence_type", "substrate_eligible",
    "provider_called", "retry_count", "parser_valid", "semantic_valid",
    "revision_hash_continuity", "intermediate_invariant_valid",
    "progress_preserved", "stale_commitment_executed",
    "final_intent_satisfied", "action_budget_respected",
    "call_budget_respected", "proposal_bytes", "prompt_tokens",
    "completion_tokens", "latency_seconds", "failure_class",
    "input_sha256", "proposal_sha256", "response_sha256",
    "logical_before_sha256", "logical_after_sha256",
    "prefix_action_sha256", "prefix_simulator_sha256",
    "post_event_action_count", "done_predicate", "b_predicate",
    "c_predicate", "d_predicate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def simulator_hash(env: Any) -> str:
    sim = sim_from_env(env)
    values = np.concatenate(
        [np.asarray(sim.data.qpos, dtype="<f8").ravel(), np.asarray(sim.data.qvel, dtype="<f8").ravel()]
    )
    return sha256_bytes(values.tobytes())


def observation_hash(observation: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    for key in sorted(observation):
        value = observation[key]
        if isinstance(value, np.ndarray):
            digest.update(key.encode("utf-8"))
            digest.update(str(value.shape).encode("ascii"))
            digest.update(str(value.dtype).encode("ascii"))
            digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def predicate_snapshot(view: LiberoStateView, row: Mapping[str, str]) -> dict[str, bool]:
    return {
        "done": view.libero_predicate("in", (row["done_object"], RECEPTACLE)),
        "b": view.libero_predicate("in", (row["initial_pending_object"], RECEPTACLE)),
        "c": view.libero_predicate("in", (row["replacement_c"], RECEPTACLE)),
        "d": view.libero_predicate("in", ("butter_1", RECEPTACLE)),
    }


def create_prefixed_env(
    task: Any,
    initial_state: Any,
    row: Mapping[str, str],
    resolution: int,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    state_id = int(row["state_id"])
    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_suite="libero_10",
        task_id=0,
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
    try:
        env.reset()
        observation = env.set_init_state(initial_state)
        from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController

        controller = LiberoOracleSkillController(env, observation, config=CONTROLLER_CONFIG)
        controller.warmup()
        placement = controller.pick_and_place(row["done_object"], RECEPTACLE)
        view = LiberoStateView(env)
        trace = []
        for index in range(5):
            controller.hold(f"formal_prefix_stability_{index + 1}", 1, gripper=-1.0)
            trace.append(predicate_snapshot(view, row))
        expected = {"done": True, "b": False, "c": False, "d": False}
        eligible = bool(placement.success and len(trace) == 5 and all(item == expected for item in trace))
        evidence = {
            "eligible": eligible,
            "placement_success": placement.success,
            "placement_failure": placement.failure_reason,
            "trace": trace,
            "action_sha256": controller.action_prefix_sha256(),
            "simulator_sha256": simulator_hash(env),
            "action_count": controller.total_steps,
            "observation_sha256": observation_hash(controller.observation),
        }
        return env, controller, view, evidence
    except Exception:
        env.close()
        raise


def base_result(row: Mapping[str, str], arm: str, event_index: int) -> dict[str, Any]:
    return {
        "sequence_id": row["sequence_id"], "arm": arm,
        "event_index": event_index, "task_id": 0,
        "state_id": int(row["state_id"]),
        "prefix_orientation": row["prefix_orientation"],
        "sequence_type": row["sequence_type"],
        "substrate_eligible": False, "provider_called": False,
        "retry_count": 0, "parser_valid": False, "semantic_valid": False,
        "revision_hash_continuity": False,
        "intermediate_invariant_valid": False, "progress_preserved": False,
        "stale_commitment_executed": False,
        "final_intent_satisfied": False, "action_budget_respected": False,
        "call_budget_respected": True, "proposal_bytes": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "latency_seconds": 0.0,
        "failure_class": "", "input_sha256": "", "proposal_sha256": "",
        "response_sha256": "", "logical_before_sha256": "",
        "logical_after_sha256": "", "prefix_action_sha256": "",
        "prefix_simulator_sha256": "", "post_event_action_count": 0,
        "done_predicate": False, "b_predicate": False,
        "c_predicate": False, "d_predicate": False,
    }


def invocation_failure(invocation: Any) -> str:
    if invocation.timeout:
        return "provider_timeout"
    if invocation.validation_failure:
        return str(invocation.validation_failure)
    if invocation.parse_failure:
        return "response_parse_failure"
    if invocation.parsed_output is None:
        return "missing_provider_output"
    return ""


class FormalTransitionError(RuntimeError):
    def __init__(self, message: str, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


def call_and_transition(
    *,
    provider: OpenAICompatibleRecoveryProvider,
    arm: str,
    recovery_input: Any,
    event: Mapping[str, Any],
    logical_state: Mapping[str, Any],
    typed_state: Any,
    physically_true: tuple[str, ...],
) -> tuple[dict[str, Any], Any, dict[str, Any], str, dict[str, Any]]:
    mode = "patch" if arm == "cope" else "compact" if arm == "neutral_patch" else "regenerate"
    invocation = provider.call_contract(mode, recovery_input, CONTRACTS[arm])
    diagnostics = {
        "provider_called": True,
        "retry_count": invocation.retry_count,
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "latency_seconds": invocation.latency_seconds,
        "response_sha256": (
            str(invocation.raw_response.get("response_sha256", ""))
            if isinstance(invocation.raw_response, Mapping) else ""
        ),
        "parsed_output": invocation.parsed_output,
        "raw_response": invocation.raw_response,
    }
    failure = invocation_failure(invocation)
    if failure:
        raise FormalTransitionError(failure, diagnostics)
    proposal = invocation.parsed_output
    assert proposal is not None
    try:
        if arm == "cope":
            typed_state, candidate, receipt, directive = execute_typed_sparse_transition(
                typed_state, logical_state, event, proposal,
                neutral=arm == "neutral_patch",
                physically_true_objects=physically_true,
            )
        elif arm == "neutral_patch":
            candidate, receipt, directive = materialize_neutral_json_patch(
                proposal, logical_state, event, physically_true
            )
        elif arm == "fsr_pc":
            candidate, directive = materialize_fsr_proposal(
                proposal, logical_state, event, physically_true
            )
            receipt = {"accepted": True}
        else:
            candidate, directive = materialize_full_replan_proposal(
                proposal, logical_state, event, physically_true
            )
            receipt = {"accepted": True}
    except Exception as exc:
        raise FormalTransitionError(
            f"{type(exc).__name__}:{exc}", diagnostics
        ) from exc
    return candidate, typed_state, receipt, directive, diagnostics


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("formal runner requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if sha256_bytes(args.manifest.read_bytes()) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("formal manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_manifest(rows)
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONTROLLER_SHA256:
        raise RuntimeError("controller configuration hash drift")
    if not os.environ.get(args.api_key_env):
        args.output_dir.mkdir(parents=True, exist_ok=False)
        blocked = {
            "gate": "BLOCKED_CREDENTIAL_UNAVAILABLE",
            "credential_env_name": args.api_key_env,
            "credential_logged": False,
            "provider_calls": 0,
            "simulator_states_indexed": 0,
            "runtime_git_commit": runtime_commit,
        }
        (args.output_dir / "00_CREDENTIAL_PREFLIGHT.txt").write_text(
            canonical_json(blocked) + "\n", encoding="utf-8"
        )
        print(canonical_json(blocked), flush=True)
        return 3

    args.output_dir.mkdir(parents=True, exist_ok=False)
    journal = args.output_dir / "01_EVENT_JOURNAL.txt"
    trace_journal = args.output_dir / "02_PROVIDER_TRACES.txt"
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(0)
    initial_states = suite.get_task_init_states(0)
    results: list[dict[str, Any]] = []

    def publish(result: dict[str, Any], trace: Mapping[str, Any] | None = None) -> None:
        results.append(result)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(result) + "\n")
        if trace is not None:
            with trace_journal.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(trace) + "\n")
        print(canonical_json(result), flush=True)

    for row in rows:
        state_id = int(row["state_id"])
        if state_id not in range(10, 30):
            raise RuntimeError("runner attempted unauthorized state")
        pre_env = None
        try:
            pre_env, _, _, shared = create_prefixed_env(
                task, initial_states[state_id], row, args.resolution
            )
        finally:
            if pre_env is not None:
                pre_env.close()
        if not shared["eligible"]:
            for arm in row["arm_order"].split(";"):
                for event_index in (1, 2):
                    result = base_result(row, arm, event_index)
                    result.update(
                        {
                            "failure_class": "shared_prefix_ineligible",
                            "prefix_action_sha256": shared["action_sha256"],
                            "prefix_simulator_sha256": shared["simulator_sha256"],
                        }
                    )
                    publish(result)
            continue

        for arm in row["arm_order"].split(";"):
            env = None
            try:
                env, controller, view, prefix = create_prefixed_env(
                    task, initial_states[state_id], row, args.resolution
                )
                if not prefix["eligible"] or prefix["action_sha256"] != shared["action_sha256"] or prefix["simulator_sha256"] != shared["simulator_sha256"]:
                    raise RuntimeError("arm prefix diverged from shared precheck")
                provider = OpenAICompatibleRecoveryProvider(
                    {
                        "provider": "openrouter", "endpoint": args.endpoint,
                        "api_key_env": args.api_key_env, "model": MODEL,
                        "reasoning_effort": REASONING_EFFORT,
                        "temperature": TEMPERATURE, "seed": int(row["seed"]),
                        "max_prompt_tokens": MAX_PROMPT_TOKENS,
                        "max_completion_tokens": MAX_COMPLETION_TOKENS,
                        "max_retries": 0, "timeout_seconds": TIMEOUT_SECONDS,
                    }
                )
                logical = build_initial_sequence_state(
                    sequence_id=row["sequence_id"],
                    done_object=row["done_object"],
                    pending_object=row["initial_pending_object"],
                    available_objects=(
                        row["done_object"], row["initial_pending_object"],
                        row["replacement_c"], "butter_1",
                    ),
                    world_version=controller.total_steps,
                )
                typed = (
                    initialize_typed_sequence_state(
                        sequence_id=row["sequence_id"],
                        done_object=row["done_object"],
                        pending_object=row["initial_pending_object"],
                    ) if arm == "cope" else None
                )
                event1 = build_sequence_event(
                    logical, sequence_id=row["sequence_id"], step_index=1,
                    done_object=row["done_object"],
                    event_type="replace_pending_goal",
                    replacement_object=row["replacement_c"],
                    world_version=controller.total_steps + 1,
                )
                event1_result = base_result(row, arm, 1)
                event1_result.update(
                    {
                        "substrate_eligible": True,
                        "prefix_action_sha256": prefix["action_sha256"],
                        "prefix_simulator_sha256": prefix["simulator_sha256"],
                        "input_sha256": "",
                        "logical_before_sha256": sequence_state_hash(logical),
                    }
                )
                recovery1 = build_sequential_recovery_input(
                    sequence_id=row["sequence_id"], task_id=0, state_id=state_id,
                    event=event1, pre_state=logical,
                    physically_true_objects=(row["done_object"],),
                    processed_event_ids=(), event_index=1,
                    rgb_observation_sha256=observation_hash(controller.observation),
                )
                event1_result["input_sha256"] = recovery1.input_hash
                diagnostics1: dict[str, Any] = {}
                try:
                    candidate1, typed, receipt1, _, diagnostics1 = call_and_transition(
                        provider=provider, arm=arm, recovery_input=recovery1,
                        event=event1, logical_state=logical, typed_state=typed,
                        physically_true=(row["done_object"],),
                    )
                    snapshot1 = predicate_snapshot(view, row)
                    event1_result.update(
                        {
                            "provider_called": True, "retry_count": diagnostics1["retry_count"],
                            "parser_valid": True, "semantic_valid": True,
                            "revision_hash_continuity": int(candidate1["state_version"]) == 2,
                            "intermediate_invariant_valid": True,
                            "progress_preserved": snapshot1["done"],
                            "final_intent_satisfied": True,
                            "action_budget_respected": controller.total_steps <= 700,
                            "call_budget_respected": diagnostics1["retry_count"] == 0,
                            "proposal_bytes": len(canonical_json(diagnostics1["parsed_output"]).encode("utf-8")),
                            "prompt_tokens": diagnostics1["prompt_tokens"],
                            "completion_tokens": diagnostics1["completion_tokens"],
                            "latency_seconds": diagnostics1["latency_seconds"],
                            "proposal_sha256": stable_hash(diagnostics1["parsed_output"]),
                            "response_sha256": diagnostics1["response_sha256"],
                            "logical_after_sha256": sequence_state_hash(candidate1),
                            "done_predicate": snapshot1["done"], "b_predicate": snapshot1["b"],
                            "c_predicate": snapshot1["c"], "d_predicate": snapshot1["d"],
                        }
                    )
                    publish(event1_result, {"sequence_id": row["sequence_id"], "arm": arm, "event_index": 1, **diagnostics1})
                except Exception as exc:
                    if isinstance(exc, FormalTransitionError):
                        diagnostics1 = exc.diagnostics
                    parsed1 = diagnostics1.get("parsed_output")
                    event1_result.update(
                        {
                            "provider_called": bool(diagnostics1.get("provider_called", False)),
                            "retry_count": int(diagnostics1.get("retry_count", 0)),
                            "parser_valid": isinstance(parsed1, Mapping),
                            "proposal_bytes": (
                                len(canonical_json(parsed1).encode("utf-8"))
                                if isinstance(parsed1, Mapping) else 0
                            ),
                            "prompt_tokens": int(diagnostics1.get("prompt_tokens", 0)),
                            "completion_tokens": int(diagnostics1.get("completion_tokens", 0)),
                            "latency_seconds": float(diagnostics1.get("latency_seconds", 0.0)),
                            "proposal_sha256": stable_hash(parsed1) if isinstance(parsed1, Mapping) else "",
                            "response_sha256": str(diagnostics1.get("response_sha256", "")),
                            "failure_class": f"event1:{type(exc).__name__}:{exc}",
                            "call_budget_respected": int(diagnostics1.get("retry_count", 0)) == 0,
                        }
                    )
                    publish(event1_result, {"sequence_id": row["sequence_id"], "arm": arm, "event_index": 1, **diagnostics1})
                    skipped = base_result(row, arm, 2)
                    skipped.update(
                        {
                            "substrate_eligible": True,
                            "failure_class": "dependency_skip_after_event1_failure",
                            "prefix_action_sha256": prefix["action_sha256"],
                            "prefix_simulator_sha256": prefix["simulator_sha256"],
                        }
                    )
                    publish(skipped)
                    continue

                logical = candidate1
                event2_type = "cancel_pending_goal" if row["sequence_type"] == "replace_then_cancel" else "replace_pending_goal"
                event2 = build_sequence_event(
                    logical, sequence_id=row["sequence_id"], step_index=2,
                    done_object=row["done_object"], event_type=event2_type,
                    replacement_object=row["replacement_d"] or None,
                    world_version=controller.total_steps + 2,
                )
                recovery2 = build_sequential_recovery_input(
                    sequence_id=row["sequence_id"], task_id=0, state_id=state_id,
                    event=event2, pre_state=logical,
                    physically_true_objects=(row["done_object"],),
                    processed_event_ids=(event1["event_id"],), event_index=2,
                    rgb_observation_sha256=observation_hash(controller.observation),
                )
                event2_result = base_result(row, arm, 2)
                event2_result.update(
                    {
                        "substrate_eligible": True,
                        "prefix_action_sha256": prefix["action_sha256"],
                        "prefix_simulator_sha256": prefix["simulator_sha256"],
                        "input_sha256": recovery2.input_hash,
                        "logical_before_sha256": sequence_state_hash(logical),
                    }
                )
                diagnostics2: dict[str, Any] = {}
                actions_before = controller.total_steps
                try:
                    candidate2, typed, receipt2, directive, diagnostics2 = call_and_transition(
                        provider=provider, arm=arm, recovery_input=recovery2,
                        event=event2, logical_state=logical, typed_state=typed,
                        physically_true=(row["done_object"],),
                    )
                    continuity = event1_result["logical_after_sha256"] == sequence_state_hash(logical)
                    if arm == "cope":
                        continuity = continuity and receipt1["after_hash"] == receipt2["before_hash"]
                    if directive != "HALT":
                        placement = controller.pick_and_place(row["replacement_d"], RECEPTACLE)
                        if not placement.success:
                            raise RuntimeError(f"final_execution:{placement.failure_reason}")
                    for index in range(5):
                        controller.hold(f"formal_final_stability_{index + 1}", 1, gripper=-1.0)
                    final = predicate_snapshot(view, row)
                    cancel = row["sequence_type"] == "replace_then_cancel"
                    intended = (
                        final == {"done": True, "b": False, "c": False, "d": False}
                        if cancel else
                        final == {"done": True, "b": False, "c": False, "d": True}
                    )
                    stale = final["b"] or final["c"]
                    event2_result.update(
                        {
                            "provider_called": True, "retry_count": diagnostics2["retry_count"],
                            "parser_valid": True, "semantic_valid": True,
                            "revision_hash_continuity": continuity and int(candidate2["state_version"]) == 3,
                            "intermediate_invariant_valid": True,
                            "progress_preserved": final["done"],
                            "stale_commitment_executed": stale,
                            "final_intent_satisfied": intended,
                            "action_budget_respected": controller.total_steps <= 700,
                            "call_budget_respected": diagnostics2["retry_count"] == 0,
                            "proposal_bytes": len(canonical_json(diagnostics2["parsed_output"]).encode("utf-8")),
                            "prompt_tokens": diagnostics2["prompt_tokens"],
                            "completion_tokens": diagnostics2["completion_tokens"],
                            "latency_seconds": diagnostics2["latency_seconds"],
                            "proposal_sha256": stable_hash(diagnostics2["parsed_output"]),
                            "response_sha256": diagnostics2["response_sha256"],
                            "logical_after_sha256": sequence_state_hash(candidate2),
                            "post_event_action_count": controller.total_steps - actions_before,
                            "done_predicate": final["done"], "b_predicate": final["b"],
                            "c_predicate": final["c"], "d_predicate": final["d"],
                        }
                    )
                    publish(event2_result, {"sequence_id": row["sequence_id"], "arm": arm, "event_index": 2, **diagnostics2})
                except Exception as exc:
                    if isinstance(exc, FormalTransitionError):
                        diagnostics2 = exc.diagnostics
                    parsed2 = diagnostics2.get("parsed_output")
                    event2_result.update(
                        {
                            "provider_called": bool(diagnostics2.get("provider_called", False)),
                            "retry_count": int(diagnostics2.get("retry_count", 0)),
                            "parser_valid": isinstance(parsed2, Mapping),
                            "proposal_bytes": (
                                len(canonical_json(parsed2).encode("utf-8"))
                                if isinstance(parsed2, Mapping) else 0
                            ),
                            "prompt_tokens": int(diagnostics2.get("prompt_tokens", 0)),
                            "completion_tokens": int(diagnostics2.get("completion_tokens", 0)),
                            "latency_seconds": float(diagnostics2.get("latency_seconds", 0.0)),
                            "proposal_sha256": stable_hash(parsed2) if isinstance(parsed2, Mapping) else "",
                            "response_sha256": str(diagnostics2.get("response_sha256", "")),
                            "failure_class": f"event2:{type(exc).__name__}:{exc}",
                            "call_budget_respected": int(diagnostics2.get("retry_count", 0)) == 0,
                        }
                    )
                    publish(event2_result, {"sequence_id": row["sequence_id"], "arm": arm, "event_index": 2, **diagnostics2})
            finally:
                if env is not None:
                    env.close()

    with (args.output_dir / "03_EVENT_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(results)
    summary = {
        "schema": "cope-sequential-formal-run-v1",
        "runtime_git_commit": runtime_commit,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "result_cells": len(results),
        "provider_calls": sum(bool(row["provider_called"]) for row in results),
        "retry_count": sum(int(row["retry_count"]) for row in results),
        "formal_states_indexed": list(range(10, 30)),
        "reserve_states_30_49_indexed": False,
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
    }
    (args.output_dir / "00_STATUS.txt").write_text(
        canonical_json(summary) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
