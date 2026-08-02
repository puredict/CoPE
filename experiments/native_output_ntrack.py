#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cope.native_ntrack import (
    NativeCase,
    NativeOutputError,
    failure_flags,
    load_manifest,
    materialize_patch,
    parse_full_state,
    parse_patch,
    state_without_history,
    validate_and_compile,
)
from cope.providers.openai_compatible import (
    OpenAICompatibleRecoveryProvider,
    ProviderConfigurationError,
    normalized_wire_request_hash,
)
from cope.types import ProviderInvocation, canonical_json, stable_hash


FIELDS = [
    "case_id", "phase", "family", "source", "arm", "model", "temperature", "seed",
    "max_completion_tokens", "timeout_seconds", "retry_budget", "repair_budget",
    "input_hash", "common_input_bytes_sha256", "normalized_request_sha256", "fairness_pass",
    "provider_status", "provider_error", "response_sha256", "parser_valid", "semantic_valid",
    "first_pass_valid", "semantic_correct", "unauthorized_or_stale_edit", "progress_corruption",
    "continuity_error", "compiled_directive", "prompt_tokens", "completion_tokens",
    "latency_seconds", "validator_calls", "repair_success", "parse_or_validation_error",
]


def _response_hash(invocation: ProviderInvocation) -> str:
    if isinstance(invocation.raw_response, dict) and invocation.raw_response.get("response_sha256"):
        return str(invocation.raw_response["response_sha256"])
    return stable_hash(invocation.raw_response)


def evaluate(case: NativeCase, arm: str, invocation: ProviderInvocation, provider: OpenAICompatibleRecoveryProvider) -> dict[str, Any]:
    provider_status = "ok"
    provider_error = ""
    if invocation.timeout:
        provider_status, provider_error = "timeout", "provider_timeout"
    elif invocation.validation_failure:
        provider_status, provider_error = "outage", invocation.validation_failure
    elif invocation.parse_failure:
        provider_status, provider_error = "response_parse_failure", invocation.parse_failure
    elif (
        invocation.usage.prompt_tokens > provider.metadata.max_prompt_tokens
        or invocation.usage.completion_tokens > provider.metadata.max_completion_tokens
    ):
        provider_status, provider_error = "budget_violation", "reported token usage exceeded frozen ceiling"
    parser_valid = False
    semantic_valid = False
    candidate: dict[str, Any] | None = None
    directive = ""
    error_message = ""
    validator_calls = 0
    if provider_status == "ok":
        try:
            if arm == "cope":
                patch = parse_patch(invocation.parsed_output)
                parser_valid = True
                candidate = materialize_patch(patch, case.pre_state, case.event)
            else:
                candidate = parse_full_state(invocation.parsed_output)
                parser_valid = True
            validator_calls = 1
            directive = validate_and_compile(candidate, case.pre_state, case.event)
            semantic_valid = True
        except (NativeOutputError, KeyError, TypeError, ValueError) as exc:
            error_message = f"{type(exc).__name__}:{exc}"
    flags = failure_flags(candidate, case.pre_state, case.event)
    return {
        "case_id": case.case_id,
        "phase": case.phase,
        "family": case.family,
        "source": case.source,
        "arm": arm,
        "model": provider.metadata.model,
        "temperature": provider.metadata.temperature,
        "seed": provider.seed,
        "max_completion_tokens": provider.metadata.max_completion_tokens,
        "timeout_seconds": provider.metadata.timeout_seconds,
        "retry_budget": provider.metadata.max_retries,
        "repair_budget": 0,
        "input_hash": case.recovery_input.input_hash,
        "common_input_bytes_sha256": invocation.raw_request.get("common_input_message_sha256", ""),
        "normalized_request_sha256": normalized_wire_request_hash(invocation),
        "fairness_pass": False,
        "provider_status": provider_status,
        "provider_error": provider_error,
        "response_sha256": _response_hash(invocation),
        "parser_valid": parser_valid,
        "semantic_valid": semantic_valid,
        "first_pass_valid": semantic_valid,
        "semantic_correct": semantic_valid,
        **flags,
        "compiled_directive": directive,
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "latency_seconds": f"{invocation.latency_seconds:.6f}",
        "validator_calls": validator_calls,
        "repair_success": "not_enabled",
        "parse_or_validation_error": error_message,
    }


def run_pair(case: NativeCase, provider: OpenAICompatibleRecoveryProvider) -> list[dict[str, Any]]:
    common = case.recovery_input
    patch_call = provider.patch(common, case.pre_state)
    full_call = provider.regenerate(common)
    rows = [evaluate(case, "cope", patch_call, provider), evaluate(case, "fsr_pc", full_call, provider)]
    expected_payload = common.as_payload()
    fairness = bool(
        rows[0]["input_hash"] == rows[1]["input_hash"]
        and patch_call.raw_request.get("recovery_input") == expected_payload
        and full_call.raw_request.get("recovery_input") == expected_payload
        and rows[0]["common_input_bytes_sha256"] == rows[1]["common_input_bytes_sha256"]
        and rows[0]["normalized_request_sha256"] == rows[1]["normalized_request_sha256"]
        and patch_call.retry_count == full_call.retry_count == 0
    )
    for row in rows:
        row["fairness_pass"] = fairness
    return rows


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_fairness(path: Path, rows: list[dict[str, Any]]) -> None:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[row["case_id"]].append(row)
    fields = ["case_id", "paired_rows", "input_hash_equal", "common_bytes_equal", "normalized_request_equal", "fairness_pass"]
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for case_id, pair in by_case.items():
            writer.writerow({
                "case_id": case_id,
                "paired_rows": len(pair),
                "input_hash_equal": len({row["input_hash"] for row in pair}) == 1,
                "common_bytes_equal": len({row["common_input_bytes_sha256"] for row in pair}) == 1,
                "normalized_request_equal": len({row["normalized_request_sha256"] for row in pair}) == 1,
                "fairness_pass": len(pair) == 2 and all(row["fairness_pass"] for row in pair),
            })


def write_aggregate(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["arm", "assigned", "provider_ok", "provider_outage_or_timeout", "first_pass_valid", "semantic_correct", "unauthorized_or_stale_edit", "progress_corruption", "continuity_error", "prompt_tokens", "completion_tokens", "latency_seconds", "validator_calls"]
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for arm in ("cope", "fsr_pc"):
            selected = [row for row in rows if row["arm"] == arm]
            writer.writerow({
                "arm": arm,
                "assigned": len(selected),
                "provider_ok": sum(row["provider_status"] == "ok" for row in selected),
                "provider_outage_or_timeout": sum(row["provider_status"] in {"outage", "timeout"} for row in selected),
                "first_pass_valid": sum(bool(row["first_pass_valid"]) for row in selected),
                "semantic_correct": sum(bool(row["semantic_correct"]) for row in selected),
                "unauthorized_or_stale_edit": sum(bool(row["unauthorized_or_stale_edit"]) for row in selected),
                "progress_corruption": sum(bool(row["progress_corruption"]) for row in selected),
                "continuity_error": sum(bool(row["continuity_error"]) for row in selected),
                "prompt_tokens": sum(int(row["prompt_tokens"]) for row in selected),
                "completion_tokens": sum(int(row["completion_tokens"]) for row in selected),
                "latency_seconds": f"{sum(float(row['latency_seconds']) for row in selected):.6f}",
                "validator_calls": sum(int(row["validator_calls"]) for row in selected),
            })


def write_failures(path: Path, rows: list[dict[str, Any]]) -> None:
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        if row["provider_status"] != "ok":
            category = "provider_" + row["provider_status"]
        elif not row["parser_valid"]:
            category = "parser_invalid"
        elif not row["semantic_valid"]:
            category = "semantic_invalid"
        else:
            category = "valid"
        counts[(row["arm"], row["family"], category)] += 1
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["arm", "family", "category", "count"])
        for key, count in sorted(counts.items()):
            writer.writerow([*key, count])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--model", required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=90.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    provider = OpenAICompatibleRecoveryProvider({
        "provider": args.provider, "endpoint": args.endpoint, "api_key_env": args.api_key_env,
        "model": args.model, "temperature": args.temperature, "seed": args.seed,
        "max_completion_tokens": args.max_tokens, "max_prompt_tokens": 12000,
        "max_retries": 0, "timeout_seconds": args.timeout,
    })
    cases = load_manifest(args.manifest)
    smoke = [case for case in cases if case.phase == "smoke"]
    expansion = [case for case in cases if case.phase == "expansion"]
    rows: list[dict[str, Any]] = []
    for case in smoke:
        rows.extend(run_pair(case, provider))
    smoke_gate = bool(
        len(rows) == 2 * len(smoke)
        and all(row["fairness_pass"] for row in rows)
        and all(row["provider_status"] == "ok" for row in rows)
    )
    if smoke_gate:
        for case in expansion:
            rows.extend(run_pair(case, provider))
    write_rows(args.output_dir / "04_PER_SAMPLE_RESULTS.csv", rows)
    write_fairness(args.output_dir / "03_FAIRNESS_INPUT_HASH_AUDIT.csv", rows)
    write_aggregate(args.output_dir / "05_AGGREGATE.csv", rows)
    write_failures(args.output_dir / "06_FAILURE_TAXONOMY.csv", rows)
    status = {
        "smoke_gate_pass": smoke_gate,
        "expanded": smoke_gate,
        "assigned_pairs": len(rows) // 2,
        "provider": provider.metadata.provider,
        "model": provider.metadata.model,
        "temperature": provider.metadata.temperature,
        "seed": provider.seed,
        "max_tokens": provider.metadata.max_completion_tokens,
        "timeout_seconds": provider.metadata.timeout_seconds,
        "retries": 0,
        "repairs": 0,
        "credential_env_name": provider.api_key_env,
        "credential_logged": False,
    }
    (args.output_dir / "07_RUN_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    print(canonical_json(status))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
