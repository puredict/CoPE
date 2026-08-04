#!/usr/bin/env python3
"""One-draw task-independent operational smoke for the formal provider."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.occurrence_prompting import (
    MAX_COMPLETION_TOKENS, MAX_PROMPT_TOKENS, MODEL, REASONING_EFFORT,
    TEMPERATURE, TIMEOUT_SECONDS,
)
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import InformationBudget, RecoveryInput, canonical_json, stable_hash
from experiments.sequential_formal_runner_v2 import invocation_failure


SEED = 20260890
CONTRACT = """OUTPUT CONTRACT: provider adapter readiness acknowledgement.
Return exactly one JSON object with exactly one field: status. Its value must
be ready. Return no prose, markdown, or additional fields."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    return parser.parse_args()


def build_smoke_input() -> RecoveryInput:
    return RecoveryInput(
        schema_version="provider-operational-smoke-v1",
        pair_key="provider-operational-smoke-v1",
        original_task="acknowledge JSON adapter readiness",
        observation={"source": "task_independent_operational_smoke"},
        event={"event_id": "operational-smoke-v1", "event_type": "adapter_readiness"},
        public_action_history=(),
        task_progress={"experimental_case": False, "simulator_used": False},
        information_budget=InformationBudget(
            event_fields=("event_id", "event_type"), history_fields=(),
            observation_fields=("source",), max_high_level_calls=1,
            max_prompt_tokens=MAX_PROMPT_TOKENS,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        ),
    )


def evaluate(invocation: Any) -> dict[str, Any]:
    failure = invocation_failure(invocation)
    parsed = invocation.parsed_output
    exact = isinstance(parsed, Mapping) and dict(parsed) == {"status": "ready"}
    response_hash = (
        str(invocation.raw_response.get("response_sha256", ""))
        if isinstance(invocation.raw_response, Mapping) else ""
    )
    passed = bool(
        not failure and exact and response_hash
        and invocation.retry_count == 0 and not invocation.timeout
    )
    return {
        "gate": "PASS" if passed else "FAIL",
        "provider_calls": 1, "retry_count": invocation.retry_count,
        "timeout": invocation.timeout, "parser_valid": isinstance(parsed, Mapping),
        "exact_acknowledgement": exact, "response_sha256": response_hash,
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "latency_seconds": invocation.latency_seconds,
        "failure_class": failure or ("noncanonical_acknowledgement" if not exact else ""),
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("provider smoke requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if not os.environ.get(args.api_key_env):
        args.output_dir.mkdir(parents=True, exist_ok=False)
        blocked = {
            "gate": "BLOCKED_CREDENTIAL_UNAVAILABLE", "provider_calls": 0,
            "credential_logged": False, "simulator_states_indexed": 0,
            "experimental_cases_materialized": 0,
            "runtime_git_commit": runtime_commit,
        }
        (args.output_dir / "00_STATUS.txt").write_text(canonical_json(blocked) + "\n", encoding="utf-8")
        print(canonical_json(blocked), flush=True)
        return 3
    recovery = build_smoke_input()
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "openrouter", "endpoint": args.endpoint,
        "api_key_env": args.api_key_env, "model": MODEL,
        "reasoning_effort": REASONING_EFFORT, "temperature": TEMPERATURE,
        "seed": SEED, "max_prompt_tokens": MAX_PROMPT_TOKENS,
        "max_completion_tokens": MAX_COMPLETION_TOKENS, "max_retries": 0,
        "timeout_seconds": TIMEOUT_SECONDS,
    })
    invocation = provider.call_contract("compact", recovery, CONTRACT)
    result = evaluate(invocation)
    result.update({
        "schema": "provider-operational-smoke-result-v1",
        "runtime_git_commit": runtime_commit, "credential_logged": False,
        "simulator_states_indexed": 0, "experimental_cases_materialized": 0,
        "input_sha256": recovery.input_hash,
        "contract_sha256": stable_hash(CONTRACT),
    })
    trace = {
        "raw_request": invocation.raw_request,
        "raw_response": invocation.raw_response,
        "parsed_output": invocation.parsed_output,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(result) + "\n", encoding="utf-8")
    (args.output_dir / "01_REDACTED_TRACE.txt").write_text(canonical_json(trace) + "\n", encoding="utf-8")
    return 0 if result["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
