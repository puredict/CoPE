#!/usr/bin/env python3
"""Crash-safe 200-call runner for occurrence-sensitive learned outputs."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.formal_recovery import AMBIGUOUS_FAILURE, FormalRecoveryLedger, cell_key
from cope.occurrence_prompting import (
    ARMS, CONTRACTS, MAX_COMPLETION_TOKENS, MAX_PROMPT_TOKENS, MODEL,
    REASONING_EFFORT, TEMPERATURE, TIMEOUT_SECONDS, build_recovery_input,
)
from cope.occurrence_sequence import build_recurrence_case, expected_next_state
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import canonical_json, stable_hash
from experiments.occurrence_formal_preflight import (
    EXPECTED_MANIFEST_SHA256, materialize, validate_manifest,
)
from experiments.sequential_formal_runner_v2 import (
    FormalTransitionError, invocation_failure, worktree_clean_for_run,
)


EXPECTED_CONTRACT_HASHES = {
    "cope": "673f4a2728cc9a77fc8f19cc098ee2b8866306530f1e889827759a7eaf5c949b",
    "neutral_patch": "611fcc351095c2a2cdd487519fb4595d38c7276ebf7d9cf5b69bfc8e247dee64",
    "governed_delta": "af9597298e0b4df308ff2c320d0385f19ed1154ae2cf2426c1decc0276abaf6b",
    "fsr_pc": "d187dc50c24becc7126aea356421a76c4e806488d3b58b290838eb1c428da387",
    "full_replan": "059327311d8696f1b4a74a87457b9eb6343d487d40fa14fa1d452955721428c8",
}
EXPECTED_PROTOCOL_SHA256 = "976d4705d2abef8371a7b954b6764cbef3cd66b2a89ed9961ed5d67400d1e8e3"
RESULT_FIELDS = (
    "sequence_id", "arm", "event_index", "case_id", "triple_index",
    "recurrence_depth", "provider_called", "retry_count", "parser_valid",
    "semantic_valid", "canonical_valid", "history_valid", "directive_valid",
    "proposal_bytes", "prompt_tokens", "completion_tokens", "latency_seconds",
    "failure_class", "input_sha256", "proposal_sha256", "response_sha256",
    "candidate_sha256",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def protocol_config() -> dict[str, Any]:
    return {
        "provider": "openrouter", "model": MODEL,
        "reasoning_effort": REASONING_EFFORT, "temperature": TEMPERATURE,
        "max_prompt_tokens": MAX_PROMPT_TOKENS,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "max_retries": 0, "timeout_seconds": TIMEOUT_SECONDS,
        "arms": list(ARMS), "calls_per_cell": 1,
        "recovery_protocol": "intent-response-result-v1",
    }


def base_result(row: Mapping[str, str], arm: str) -> dict[str, Any]:
    return {
        "sequence_id": row["case_id"], "arm": arm, "event_index": 1,
        "case_id": row["case_id"], "triple_index": int(row["triple_index"]),
        "recurrence_depth": int(row["recurrence_depth"]),
        "provider_called": False, "retry_count": 0, "parser_valid": False,
        "semantic_valid": False, "canonical_valid": False,
        "history_valid": False, "directive_valid": False,
        "proposal_bytes": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "latency_seconds": 0.0, "failure_class": "", "input_sha256": "",
        "proposal_sha256": "", "response_sha256": "", "candidate_sha256": "",
    }


def response_diagnostics(invocation: Any) -> dict[str, Any]:
    failure = invocation_failure(invocation)
    return {
        "provider_called": True, "retry_count": invocation.retry_count,
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "latency_seconds": invocation.latency_seconds,
        "response_sha256": (
            str(invocation.raw_response.get("response_sha256", ""))
            if isinstance(invocation.raw_response, Mapping) else ""
        ),
        "parsed_output": invocation.parsed_output,
        "raw_response": invocation.raw_response,
        "failure": failure,
    }


def obtain_proposal(
    *, ledger: FormalRecoveryLedger, row: Mapping[str, str], arm: str,
    provider: OpenAICompatibleRecoveryProvider, recovery: Any,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    key_payload = {"sequence_id": row["case_id"], "arm": arm, "event_index": 1}
    key = cell_key(key_payload)
    if key in ledger.responses:
        diagnostics = dict(ledger.responses[key]["diagnostics"])
        if diagnostics.get("failure"):
            raise FormalTransitionError(str(diagnostics["failure"]), diagnostics)
        proposal = diagnostics.get("parsed_output")
        if not isinstance(proposal, Mapping):
            raise FormalTransitionError("missing_provider_output", diagnostics)
        return proposal, diagnostics
    if key in ledger.intents:
        diagnostics = {
            "provider_called": True, "retry_count": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "latency_seconds": 0.0,
            "response_sha256": "", "parsed_output": None, "raw_response": {},
            "failure": AMBIGUOUS_FAILURE,
        }
        raise FormalTransitionError(AMBIGUOUS_FAILURE, diagnostics)
    ledger.record_intent({
        **key_payload, "input_sha256": recovery.input_hash,
    })
    mode = "patch" if arm == "cope" else "compact" if arm in {"neutral_patch", "governed_delta"} else "regenerate"
    invocation = provider.call_contract(mode, recovery, CONTRACTS[arm])
    diagnostics = response_diagnostics(invocation)
    ledger.record_response({**key_payload, "diagnostics": diagnostics})
    if diagnostics["failure"]:
        raise FormalTransitionError(str(diagnostics["failure"]), diagnostics)
    proposal = diagnostics["parsed_output"]
    if not isinstance(proposal, Mapping):
        raise FormalTransitionError("missing_provider_output", diagnostics)
    return proposal, diagnostics


def history_is_valid(candidate: Mapping[str, Any], row: Mapping[str, str]) -> bool:
    records = candidate.get("commitments")
    if not isinstance(records, list):
        return False
    active = [item for item in records if item.get("lifecycle_status") == "active"]
    historical = [item for item in records if item.get("lifecycle_status") == "superseded"]
    depth = int(row["recurrence_depth"])
    return bool(
        len(active) == 1
        and active[0].get("grounding", [None])[0] == row["recurring_object"]
        and int(active[0].get("occurrence", -1)) == depth + 1
        and len(historical) == 2 * depth
    )


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if not worktree_clean_for_run(repo_root, args.output_dir, args.resume):
        raise RuntimeError("occurrence runner requires a clean worktree outside its resume directory")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)
    if __import__("hashlib").sha256(args.manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("occurrence manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_manifest(rows)
    if {arm: stable_hash(CONTRACTS[arm]) for arm in ARMS} != EXPECTED_CONTRACT_HASHES:
        raise RuntimeError("occurrence contract hash drift")
    if stable_hash(protocol_config()) != EXPECTED_PROTOCOL_SHA256:
        raise RuntimeError("occurrence provider protocol hash drift")
    if not os.environ.get(args.api_key_env):
        blocked = {
            "gate": "BLOCKED_CREDENTIAL_UNAVAILABLE",
            "provider_calls": 0, "symbolic_cases_materialized": 0,
            "simulator_states_indexed": 0, "credential_logged": False,
            "runtime_git_commit": runtime_commit,
        }
        if not args.resume:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            (args.output_dir / "00_CREDENTIAL_PREFLIGHT.txt").write_text(
                canonical_json(blocked) + "\n", encoding="utf-8"
            )
        print(canonical_json(blocked), flush=True)
        return 3
    metadata = {
        "schema": "occurrence-learned-formal-run-metadata-v1",
        "runtime_git_commit": runtime_commit,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "contract_hashes": EXPECTED_CONTRACT_HASHES,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "endpoint": args.endpoint, "api_key_env": args.api_key_env,
        "credential_logged": False,
    }
    ledger = FormalRecoveryLedger(args.output_dir, metadata, resume=args.resume)

    def publish(result: Mapping[str, Any]) -> None:
        key = cell_key(result)
        existing = ledger.results.get(key)
        if existing is not None:
            if canonical_json(existing) != canonical_json(result):
                raise RuntimeError(f"occurrence rematerialized result drift: {key}")
            return
        ledger.record_result(result)
        print(canonical_json(result), flush=True)

    for row in rows:
        pre, event, typed = build_recurrence_case(
            case_id=row["case_id"], done_object=row["done_object"],
            recurring_object=row["recurring_object"],
            intermediate_object=row["intermediate_object"],
            recurrence_depth=int(row["recurrence_depth"]),
        )
        expected = expected_next_state(pre, event)
        recovery = build_recovery_input(case_id=row["case_id"], pre_state=pre, event=event)
        for arm in row["arm_order"].split(";"):
            key = (row["case_id"], arm, 1)
            if key in ledger.results:
                continue
            result = base_result(row, arm)
            result["input_sha256"] = recovery.input_hash
            provider = OpenAICompatibleRecoveryProvider({
                "provider": "openrouter", "endpoint": args.endpoint,
                "api_key_env": args.api_key_env, "model": MODEL,
                "reasoning_effort": REASONING_EFFORT,
                "temperature": TEMPERATURE, "seed": int(row["seed"]),
                "max_prompt_tokens": MAX_PROMPT_TOKENS,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "max_retries": 0, "timeout_seconds": TIMEOUT_SECONDS,
            })
            diagnostics: dict[str, Any] = {}
            try:
                proposal, diagnostics = obtain_proposal(
                    ledger=ledger, row=row, arm=arm, provider=provider,
                    recovery=recovery,
                )
                candidate = materialize(
                    arm, proposal, typed, pre, event, row["done_object"]
                )
                canonical = canonical_json(candidate) == canonical_json(expected)
                history = history_is_valid(candidate, row)
                directive = candidate["plan"][0]["arguments"][0] == row["recurring_object"]
                result.update({
                    "provider_called": True,
                    "retry_count": diagnostics["retry_count"],
                    "parser_valid": True, "semantic_valid": True,
                    "canonical_valid": canonical, "history_valid": history,
                    "directive_valid": directive,
                    "proposal_bytes": len(canonical_json(proposal).encode("utf-8")),
                    "prompt_tokens": diagnostics["prompt_tokens"],
                    "completion_tokens": diagnostics["completion_tokens"],
                    "latency_seconds": diagnostics["latency_seconds"],
                    "proposal_sha256": stable_hash(proposal),
                    "response_sha256": diagnostics["response_sha256"],
                    "candidate_sha256": stable_hash(candidate),
                })
            except Exception as exc:
                if isinstance(exc, FormalTransitionError):
                    diagnostics = exc.diagnostics
                parsed = diagnostics.get("parsed_output")
                result.update({
                    "provider_called": bool(diagnostics.get("provider_called", False)),
                    "retry_count": int(diagnostics.get("retry_count", 0)),
                    "parser_valid": isinstance(parsed, Mapping),
                    "proposal_bytes": len(canonical_json(parsed).encode("utf-8")) if isinstance(parsed, Mapping) else 0,
                    "prompt_tokens": int(diagnostics.get("prompt_tokens", 0)),
                    "completion_tokens": int(diagnostics.get("completion_tokens", 0)),
                    "latency_seconds": float(diagnostics.get("latency_seconds", 0.0)),
                    "proposal_sha256": stable_hash(parsed) if isinstance(parsed, Mapping) else "",
                    "response_sha256": str(diagnostics.get("response_sha256", "")),
                    "failure_class": f"{type(exc).__name__}:{exc}",
                })
            publish(result)
    results = list(ledger.results.values())
    if len(results) != 200:
        raise RuntimeError(f"occurrence run has {len(results)} results, expected 200")
    final = args.output_dir / "03_EVENT_RESULTS.csv"
    temporary = args.output_dir / "03_EVENT_RESULTS.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(results)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, final)
    status = {
        "schema": "occurrence-learned-formal-run-v1",
        "result_cells": 200,
        "provider_calls": sum(bool(row["provider_called"]) for row in results),
        "retry_count": sum(int(row["retry_count"]) for row in results),
        "ambiguous_interrupted_calls": sum(AMBIGUOUS_FAILURE in str(row["failure_class"]) for row in results),
        "simulator_states_indexed": 0, "runtime_git_commit": runtime_commit,
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
