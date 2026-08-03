#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from cope.providers.openai_compatible import (
    OpenAICompatibleRecoveryProvider,
    normalized_raw_request_hash,
)
from cope.types import ProviderInvocation, canonical_json, stable_hash


MODEL = "qwen/qwen3.5-flash-02-23"
SEED = 20260803
ARMS = ("cope", "compact_tx", "fsr_pc")
MODES = {"cope": "patch", "compact_tx": "compact", "fsr_pc": "regenerate"}
FIELDS = (
    "case_id", "family", "disposition", "arm", "call_order_position",
    "provider_status", "provider_error", "parser_valid", "semantic_correct",
    "unsafe_mutation_attempt", "input_hash", "common_input_bytes_sha256",
    "normalized_request_sha256", "fairness_pass", "response_sha256",
    "prompt_tokens", "completion_tokens", "proposal_bytes", "latency_seconds",
    "retry_count", "parse_or_validation_error", "model", "reasoning_effort",
    "temperature", "seed", "max_completion_tokens", "timeout_seconds",
    "retry_budget", "repair_budget", "fallback_used", "oracle_substitution",
)


class X16Input:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = copy.deepcopy(dict(payload))

    def as_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)


class X16Provider(OpenAICompatibleRecoveryProvider):
    def __init__(self, config: Mapping[str, Any], *, system_prompt: str) -> None:
        super().__init__(config)
        self.system_prompt = system_prompt

    def _common_message(self, recovery_input: X16Input) -> str:
        return "X16_RECOVERY_INPUT_CANONICAL_JSON\n" + canonical_json(
            recovery_input.as_payload()
        )

    def build_audited_request(
        self, mode: str, recovery_input: X16Input, output_contract: str
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self._common_message(recovery_input)},
            {"role": "user", "content": output_contract},
        ]
        wire_payload: dict[str, Any] = {
            "model": self.metadata.model,
            "messages": messages,
            "temperature": self.metadata.temperature,
            "seed": self.seed,
            "max_tokens": self.metadata.max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort is not None:
            wire_payload["reasoning"] = {"effort": self.reasoning_effort}
        return {
            "mode": mode,
            "recovery_input": recovery_input.as_payload(),
            "common_input_message_sha256": stable_hash(messages[1]["content"]),
            "output_contract_sha256": stable_hash(output_contract),
            "wire_payload": wire_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Frozen X16 provider runner")
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_freeze(root: Path) -> dict[str, str]:
    ledger = root / "14_X16_FREEZE_SHA256.txt"
    expected: dict[str, str] = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64:
            expected[parts[1]] = parts[0]
    if len(expected) != 14:
        raise RuntimeError(f"freeze ledger contains {len(expected)} files, expected 14")
    for name, digest in expected.items():
        actual = sha256_file(root / name)
        if actual != digest:
            raise RuntimeError(f"freeze hash mismatch: {name}")
    return expected


def load_qualification(root: Path) -> Any:
    path = root / "04_X16_QUALIFICATION_PROGRAM.txt"
    loader = importlib.machinery.SourceFileLoader("x16_frozen_qualification", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("cannot load frozen X16 qualification program")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def contracts_from_frozen(module: Any) -> dict[str, str]:
    return {arm: str(module.ARM_CONTRACTS[arm]["representation"]) for arm in ARMS}


def preflight(root: Path, module: Any, provider: X16Provider) -> tuple[list[Any], dict[str, tuple[str, ...]]]:
    manifest = {row["case_id"]: row for row in read_csv(root / "01_X16_INDEPENDENT_TASK_MANIFEST.csv")}
    oracle = {row["case_id"]: row for row in read_csv(root / "02_X16_FROZEN_ORACLE.csv")}
    order_rows = read_csv(root / "03_X16_ARM_ORDER.csv")
    orders: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in order_rows:
        orders[row["case_id"]].append((int(row["position"]), row["arm"]))
    frozen_orders = {case_id: tuple(arm for _, arm in sorted(rows)) for case_id, rows in orders.items()}
    if len(module.CASES) != 36 or len(manifest) != 36 or len(oracle) != 36 or len(frozen_orders) != 36:
        raise RuntimeError("X16 independent-template count is not 36")
    contracts = contracts_from_frozen(module)
    normalized_hashes: list[str] = []
    first_positions = defaultdict(int)
    for case in module.CASES:
        case_id = case["case_id"]
        common = module.common_input(case)
        common_text = canonical_json(common)
        if manifest[case_id]["common_input_json"] != common_text:
            raise RuntimeError(f"manifest/common-input mismatch: {case_id}")
        reps = module.representations(case)
        frozen_rep_fields = {
            "cope": "cope_oracle_json",
            "compact_tx": "compact_tx_oracle_json",
            "fsr_pc": "fsr_pc_oracle_json",
        }
        for arm in ARMS:
            if oracle[case_id][frozen_rep_fields[arm]] != canonical_json(reps[arm]):
                raise RuntimeError(f"frozen oracle mismatch: {case_id}/{arm}")
            module.validate_representation(case, arm, reps[arm])
        if set(frozen_orders[case_id]) != set(ARMS) or len(frozen_orders[case_id]) != 3:
            raise RuntimeError(f"invalid arm order: {case_id}")
        first_positions[frozen_orders[case_id][0]] += 1
        audited = [
            provider.build_audited_request(MODES[arm], X16Input(common), contracts[arm])
            for arm in ARMS
        ]
        if len({item["common_input_message_sha256"] for item in audited}) != 1:
            raise RuntimeError(f"common input fairness failed: {case_id}")
        hashes = [normalized_raw_request_hash(item) for item in audited]
        if len(set(hashes)) != 1:
            raise RuntimeError(f"normalized request fairness failed: {case_id}")
        normalized_hashes.extend(hashes)
    if dict(first_positions) != {"cope": 12, "compact_tx": 12, "fsr_pc": 12}:
        raise RuntimeError(f"first-position balance failed: {dict(first_positions)}")
    if len(normalized_hashes) != 108:
        raise RuntimeError("preflight did not qualify 108 arm cells")
    return list(module.CASES), frozen_orders


def provider_status(invocation: ProviderInvocation, provider: X16Provider) -> tuple[str, str]:
    if invocation.timeout:
        return "timeout", "provider_timeout"
    if invocation.validation_failure:
        return "outage", str(invocation.validation_failure)
    if invocation.parse_failure:
        return "response_parse_failure", str(invocation.parse_failure)
    if invocation.usage.prompt_tokens > provider.metadata.max_prompt_tokens:
        return "budget_violation", "reported prompt tokens exceed frozen ceiling"
    if invocation.usage.completion_tokens > provider.metadata.max_completion_tokens:
        return "budget_violation", "reported completion tokens exceed frozen ceiling"
    return "ok", ""


def schema_valid(module: Any, arm: str, proposal: Any) -> bool:
    if not isinstance(proposal, dict):
        return False
    expected = {
        "cope": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "operations"},
        "compact_tx": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "writes"},
        "fsr_pc": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "state"},
    }[arm]
    return set(proposal) == expected and proposal.get("schema_version") == module.ARM_CONTRACTS[arm]["schema_version"]


def unsafe_mutation_attempt(module: Any, case: Any, arm: str, proposal: Any) -> bool:
    if not isinstance(proposal, dict):
        return False
    try:
        if arm == "cope":
            candidate = module.apply_cope_ops(case["pre"], proposal.get("operations", []), case["event"])
        elif arm == "compact_tx":
            candidate = module.apply_compact(case["pre"], proposal.get("writes", []))
        else:
            candidate = copy.deepcopy(proposal.get("state"))
        return candidate != case["post"] and candidate != case["pre"]
    except Exception:
        return bool(proposal.get("operations") or proposal.get("writes") or proposal.get("state"))


def response_hash(invocation: ProviderInvocation) -> str:
    if isinstance(invocation.raw_response, dict) and invocation.raw_response.get("response_sha256"):
        return str(invocation.raw_response["response_sha256"])
    return stable_hash(invocation.raw_response)


def evaluate(module: Any, case: Any, arm: str, position: int, invocation: ProviderInvocation, provider: X16Provider) -> dict[str, Any]:
    status, provider_error = provider_status(invocation, provider)
    parsed = invocation.parsed_output
    parser_ok = status == "ok" and schema_valid(module, arm, parsed)
    semantic_ok = False
    error_text = ""
    if status == "ok" and parser_ok:
        try:
            module.validate_representation(case, arm, parsed)
            semantic_ok = True
        except Exception as exc:
            error_text = f"{type(exc).__name__}:{exc}"
    elif status == "ok":
        error_text = "representation schema mismatch"
    return {
        "case_id": case["case_id"], "family": case["primary_family"],
        "disposition": case["disposition"], "arm": arm,
        "call_order_position": position, "provider_status": status,
        "provider_error": provider_error, "parser_valid": parser_ok,
        "semantic_correct": semantic_ok,
        "unsafe_mutation_attempt": unsafe_mutation_attempt(module, case, arm, parsed),
        "input_hash": stable_hash(module.common_input(case)),
        "common_input_bytes_sha256": invocation.raw_request.get("common_input_message_sha256", ""),
        "normalized_request_sha256": normalized_raw_request_hash(invocation.raw_request),
        "fairness_pass": False, "response_sha256": response_hash(invocation),
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "proposal_bytes": len(canonical_json(parsed).encode("utf-8")) if isinstance(parsed, dict) else 0,
        "latency_seconds": f"{invocation.latency_seconds:.6f}",
        "retry_count": invocation.retry_count,
        "parse_or_validation_error": error_text,
        "model": provider.metadata.model, "reasoning_effort": provider.reasoning_effort,
        "temperature": provider.metadata.temperature, "seed": provider.seed,
        "max_completion_tokens": provider.metadata.max_completion_tokens,
        "timeout_seconds": provider.metadata.timeout_seconds,
        "retry_budget": provider.metadata.max_retries, "repair_budget": 0,
        "fallback_used": False, "oracle_substitution": False,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...] | list[str]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def exact_result(module: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rows:
        by_case[row["case_id"]][row["arm"]] = bool(row["semantic_correct"])
    cope_only = sum(v["cope"] and not v["compact_tx"] for v in by_case.values())
    compact_only = sum(v["compact_tx"] and not v["cope"] for v in by_case.values())
    return {
        "independent_templates": len(by_case), "cope_only": cope_only,
        "compact_tx_only": compact_only,
        "discordant": cope_only + compact_only,
        "exact_two_sided_p": module.exact_two_sided_p(cope_only, compact_only),
        "direction_pass": cope_only > compact_only,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    freeze_dir = args.freeze_dir.resolve()
    output_dir = args.output_dir.resolve()
    if repo_root / "research" not in output_dir.parents:
        raise RuntimeError("X16 output directory must be under research/")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("X16 requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    freeze_hashes = verify_freeze(freeze_dir)
    module = load_qualification(freeze_dir)
    provider = X16Provider(
        {
            "provider": "openrouter", "endpoint": args.endpoint,
            "api_key_env": args.api_key_env, "model": MODEL,
            "reasoning_effort": "none", "temperature": 0.0, "seed": SEED,
            "max_prompt_tokens": 16000, "max_completion_tokens": 8192,
            "max_retries": 0, "timeout_seconds": 90.0,
        },
        system_prompt=module.SYSTEM_PROMPT,
    )
    cases, orders = preflight(freeze_dir, module, provider)
    if args.preflight_only:
        output_dir.mkdir(parents=True, exist_ok=False)
        (output_dir / "00_PREFLIGHT_STATUS.txt").write_text(
            canonical_json({
                "decision": "PASS", "provider_calls": 0,
                "qualified_templates": 36, "qualified_cells": 108,
                "freeze_files_verified": len(freeze_hashes),
                "runtime_git_commit": runtime_commit,
            }) + "\n", encoding="utf-8",
        )
        return 0
    if not os.environ.get(args.api_key_env):
        raise RuntimeError(f"credential environment variable {args.api_key_env} is not set")
    output_dir.mkdir(parents=True, exist_ok=False)
    contracts = contracts_from_frozen(module)
    rows: list[dict[str, Any]] = []
    journal = output_dir / "00_CALL_JOURNAL.txt"
    with journal.open("x", encoding="utf-8") as journal_handle:
        for case in cases:
            common = X16Input(module.common_input(case))
            triplet: list[dict[str, Any]] = []
            for position, arm in enumerate(orders[case["case_id"]], start=1):
                invocation = provider.call_contract(MODES[arm], common, contracts[arm])
                row = evaluate(module, case, arm, position, invocation, provider)
                triplet.append(row)
                journal_handle.write(canonical_json({
                    "case_id": case["case_id"], "arm": arm,
                    "position": position, "row": row,
                    "raw_response": invocation.raw_response,
                }) + "\n")
                journal_handle.flush()
            fairness = bool(
                len({row["input_hash"] for row in triplet}) == 1
                and len({row["common_input_bytes_sha256"] for row in triplet}) == 1
                and len({row["normalized_request_sha256"] for row in triplet}) == 1
                and all(row["retry_count"] == 0 for row in triplet)
            )
            for row in triplet:
                row["fairness_pass"] = fairness
            rows.extend(triplet)
    write_csv(output_dir / "01_PER_ARM_RESULTS.csv", rows, FIELDS)
    aggregate: list[dict[str, Any]] = []
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        aggregate.append({
            "arm": arm, "assigned": len(selected),
            "provider_ok": sum(row["provider_status"] == "ok" for row in selected),
            "parser_valid": sum(bool(row["parser_valid"]) for row in selected),
            "semantic_correct": sum(bool(row["semantic_correct"]) for row in selected),
            "unsafe_mutation_attempts": sum(bool(row["unsafe_mutation_attempt"]) for row in selected),
            "completion_tokens": sum(int(row["completion_tokens"]) for row in selected),
            "proposal_bytes": sum(int(row["proposal_bytes"]) for row in selected),
            "latency_seconds": f"{sum(float(row['latency_seconds']) for row in selected):.6f}",
        })
    write_csv(output_dir / "02_AGGREGATE.csv", aggregate, list(aggregate[0]))
    exact = exact_result(module, rows)
    status_payload = {
        "decision": "COMPLETE",
        "runtime_git_commit": runtime_commit,
        "freeze_files_verified": len(freeze_hashes),
        "provider_calls": len(rows), "fair_triplets": sum(
            all(row["fairness_pass"] for row in rows if row["case_id"] == case["case_id"])
            for case in cases
        ),
        "reasoning_effort": "none", "retry_budget": 0, "repair_budget": 0,
        "fallback_used": False, "oracle_substitution": False,
        "gpu_used": False, "simulator_used": False,
        "reserved_states_read": False, **exact,
    }
    (output_dir / "03_RUN_STATUS.txt").write_text(
        canonical_json(status_payload) + "\n", encoding="utf-8"
    )
    print(canonical_json(status_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
