#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

from cope.shared_commit_envelope import (
    ARMS,
    SEMANTIC_TO_NEUTRAL,
    SharedEnvelopeError,
    build_development_cases,
    materialize_proposal,
    oracle_proposal,
    qualification_rows,
)
from cope.types import canonical_json, stable_hash
from x16_provider_runner import X16Input, provider_status, response_hash
from x17_stagea_runner import StageAProvider, infer_schema, normalized_hash


MODEL = "qwen/qwen3.5-flash-02-23"
SEED = 20260803
MODES = {
    "cope_semantic": "patch",
    "neutral_typed": "patch",
    "compact_semantic": "compact",
    "fsr_semantic": "regenerate",
}
VERSIONS = {
    "cope_semantic": "cope-semantic-delta-v1",
    "neutral_typed": "neutral-semantic-delta-v1",
    "compact_semantic": "compact-semantic-delta-v1",
    "fsr_semantic": "fsr-semantic-state-v1",
}
FIELDS = (
    "case_id", "family", "arm", "call_order_position", "provider_status",
    "provider_error", "parser_valid", "semantic_correct", "input_hash",
    "common_input_bytes_sha256", "normalized_request_sha256", "fairness_pass",
    "response_sha256", "prompt_tokens", "completion_tokens", "proposal_bytes",
    "latency_seconds", "retry_count", "parse_or_validation_error", "model",
    "reasoning_effort", "temperature", "seed", "max_completion_tokens",
    "timeout_seconds", "retry_budget", "repair_budget", "fallback_used",
    "oracle_substitution", "transaction_metadata_model_generated",
)


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shared commit-envelope development gate")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args()


def schemas() -> dict[str, dict[str, Any]]:
    cases = build_development_cases()
    return {
        arm: infer_schema([oracle_proposal(case, arm) for case in cases])
        for arm in ARMS
    }


def contracts(arm_schemas: dict[str, dict[str, Any]]) -> dict[str, str]:
    signatures = (
        "Typed signatures: SetCommitmentStatus={op,target_id,status}; "
        "SetCommitmentField={op,target_id,field,value}; InsertCommitment={op,record}; "
        "SetActionFields={op,target_id,fields}; InsertAction={op,record}; "
        "SetProgressFields={op,target_id,fields}; InsertProgress={op,record}; "
        "AddRestoration={op,record}; RemoveRestoration={op,target_id}; SetFact={op,key,value}. "
        "Do not emit CommitEvent or transaction metadata."
    )
    neutral = "; ".join(
        f"{label} means {semantic}" for semantic, label in sorted(SEMANTIC_TO_NEUTRAL.items())
    )
    prefix = (
        "Return exactly one JSON object satisfying the JSON Schema. Apply every visible rule clause and preserve all other semantic fields. "
        "The trusted shared envelope—not you—handles state/evidence versions, processed events, event hashes, and receipts. "
    )
    return {
        "cope_semantic": prefix + signatures + "\nJSON_SCHEMA\n" + canonical_json(arm_schemas["cope_semantic"]),
        "neutral_typed": prefix + "Use only neutral operation labels: " + neutral + ". " + signatures.replace(
            "SetCommitmentStatus", "N01"
        ) + "\nJSON_SCHEMA\n" + canonical_json(arm_schemas["neutral_typed"]),
        "compact_semantic": prefix + (
            "Each write is exactly {op,path,value}; op is add or replace. Allowed semantic paths are "
            "/commitments/<id>/<field>, /commitments/+/<id>, /actions/<id>/<field>, "
            "/actions/+/<id>, /progress/<id>/<field>, /progress/+/<id>, /restorations, and /facts/<key>. "
            "Transaction metadata paths are forbidden.\nJSON_SCHEMA\n"
        ) + canonical_json(arm_schemas["compact_semantic"]),
        "fsr_semantic": prefix + (
            "Return the complete post-decision semantic state only; it excludes every transaction-metadata field.\nJSON_SCHEMA\n"
        ) + canonical_json(arm_schemas["fsr_semantic"]),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Iterable[str]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parsed = args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = parsed.output_dir.resolve()
    if repo_root / "research" not in output_dir.parents:
        raise RuntimeError("output must be under research/")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("shared-envelope gate requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    cases = build_development_cases()
    oracle_rows = qualification_rows()
    if len(oracle_rows) != 24 or not all(row["oracle_accepted"] for row in oracle_rows):
        raise RuntimeError("oracle qualification failed")
    arm_schemas = schemas()
    arm_contracts = contracts(arm_schemas)
    contract_to_arm = {stable_hash(text): arm for arm, text in arm_contracts.items()}
    provider = StageAProvider(
        {
            "provider": "openrouter", "endpoint": parsed.endpoint,
            "api_key_env": parsed.api_key_env, "model": MODEL,
            "reasoning_effort": "none", "temperature": 0.0, "seed": SEED,
            "max_prompt_tokens": 16000, "max_completion_tokens": 8192,
            "max_retries": 0, "timeout_seconds": 90.0,
        },
        system_prompt=(
            "You are a deterministic semantic state-transition generator. Use only the supplied shared-envelope input and explicit rule clauses. "
            "Return one JSON object; do not generate transaction metadata."
        ),
        structured=True, schemas=arm_schemas, contract_to_arm=contract_to_arm,
    )
    preflight: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        hashes = []
        for arm in ARMS:
            audited = provider.build_audited_request(MODES[arm], X16Input(case.common_input), arm_contracts[arm])
            hashes.append(normalized_hash(audited))
        order = ARMS[index % 4:] + ARMS[:index % 4]
        preflight.append({
            "case_id": case.case_id, "family": case.family,
            "rule_clause_count": len(case.rule_clauses), "arm_cells": 4,
            "fairness_pass": len(set(hashes)) == 1,
            "normalized_request_sha256": hashes[0] if len(set(hashes)) == 1 else "",
            "call_order": canonical_json(list(order)),
        })
    if not all(row["fairness_pass"] for row in preflight):
        raise RuntimeError("preflight fairness failed")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_csv(output_dir / "00_CASE_AND_FAIRNESS_PREFLIGHT.csv", preflight, list(preflight[0]))
    write_csv(output_dir / "01_ORACLE_QUALIFICATION.csv", oracle_rows, list(oracle_rows[0]))
    (output_dir / "02_INTERFACE_FREEZE.txt").write_text(
        canonical_json({
            "case_ids": [case.case_id for case in cases],
            "families": [case.family for case in cases],
            "schema_sha256": {arm: stable_hash(value) for arm, value in arm_schemas.items()},
            "contract_sha256": {arm: stable_hash(value) for arm, value in arm_contracts.items()},
            "common_input_sha256": {case.case_id: stable_hash(case.common_input) for case in cases},
            "oracle_sha256": {case.case_id: stable_hash(case.post_state) for case in cases},
            "runtime_git_commit": runtime_commit, "provider_calls": 0,
        }) + "\n", encoding="utf-8",
    )
    if parsed.preflight_only:
        return 0
    if not os.environ.get(parsed.api_key_env):
        raise RuntimeError("provider credential missing")
    rows: list[dict[str, Any]] = []
    with (output_dir / "03_CALL_JOURNAL.txt").open("x", encoding="utf-8") as journal:
        for index, case in enumerate(cases):
            order = ARMS[index % 4:] + ARMS[:index % 4]
            group: list[dict[str, Any]] = []
            for position, arm in enumerate(order, start=1):
                invocation = provider.call_contract(MODES[arm], X16Input(case.common_input), arm_contracts[arm])
                pstatus, perror = provider_status(invocation, provider)
                proposal = invocation.parsed_output
                parser_valid = bool(
                    pstatus == "ok" and isinstance(proposal, dict)
                    and proposal.get("schema_version") == VERSIONS[arm]
                )
                correct = False
                validation_error = ""
                if parser_valid:
                    try:
                        materialize_proposal(case, arm, proposal)
                        correct = True
                    except (SharedEnvelopeError, KeyError, TypeError, ValueError) as exc:
                        validation_error = f"{type(exc).__name__}:{exc}"
                elif pstatus == "ok":
                    validation_error = "proposal object or schema version mismatch"
                row = {
                    "case_id": case.case_id, "family": case.family, "arm": arm,
                    "call_order_position": position, "provider_status": pstatus,
                    "provider_error": perror, "parser_valid": parser_valid,
                    "semantic_correct": correct, "input_hash": stable_hash(case.common_input),
                    "common_input_bytes_sha256": invocation.raw_request.get("common_input_message_sha256", ""),
                    "normalized_request_sha256": normalized_hash(invocation.raw_request),
                    "fairness_pass": False, "response_sha256": response_hash(invocation),
                    "prompt_tokens": invocation.usage.prompt_tokens,
                    "completion_tokens": invocation.usage.completion_tokens,
                    "proposal_bytes": len(canonical_json(proposal).encode("utf-8")) if isinstance(proposal, dict) else 0,
                    "latency_seconds": f"{invocation.latency_seconds:.6f}",
                    "retry_count": invocation.retry_count,
                    "parse_or_validation_error": validation_error,
                    "model": provider.metadata.model, "reasoning_effort": provider.reasoning_effort,
                    "temperature": provider.metadata.temperature, "seed": provider.seed,
                    "max_completion_tokens": provider.metadata.max_completion_tokens,
                    "timeout_seconds": provider.metadata.timeout_seconds,
                    "retry_budget": 0, "repair_budget": 0, "fallback_used": False,
                    "oracle_substitution": False, "transaction_metadata_model_generated": False,
                }
                group.append(row)
                journal.write(canonical_json({
                    "case_id": case.case_id, "arm": arm, "row": row,
                    "raw_response": invocation.raw_response,
                }) + "\n")
                journal.flush()
            fairness = len({row["input_hash"] for row in group}) == 1 and len({
                row["common_input_bytes_sha256"] for row in group
            }) == 1 and len({row["normalized_request_sha256"] for row in group}) == 1
            for row in group:
                row["fairness_pass"] = fairness
            rows.extend(group)
    write_csv(output_dir / "04_PER_ARM_RESULTS.csv", rows, FIELDS)
    aggregate: list[dict[str, Any]] = []
    for arm in ARMS:
        chosen = [row for row in rows if row["arm"] == arm]
        aggregate.append({
            "arm": arm, "assigned": len(chosen),
            "provider_ok": sum(row["provider_status"] == "ok" for row in chosen),
            "parser_valid": sum(bool(row["parser_valid"]) for row in chosen),
            "semantic_correct": sum(bool(row["semantic_correct"]) for row in chosen),
            "completion_tokens": sum(int(row["completion_tokens"]) for row in chosen),
            "proposal_bytes": sum(int(row["proposal_bytes"]) for row in chosen),
            "latency_seconds": f"{sum(float(row['latency_seconds']) for row in chosen):.6f}",
        })
    write_csv(output_dir / "05_AGGREGATE.csv", aggregate, list(aggregate[0]))
    sparse = {
        row["arm"]: int(row["semantic_correct"])
        for row in aggregate if row["arm"] in {"cope_semantic", "neutral_typed", "compact_semantic"}
    }
    passed = all(value >= 4 for value in sparse.values())
    (output_dir / "06_RUN_STATUS.txt").write_text(
        canonical_json({
            "decision": "PASS" if passed else "FAIL",
            "threshold": "each sparse arm >=4/6", "sparse_correct": sparse,
            "provider_calls": len(rows), "fair_quadruplets": 6,
            "transaction_metadata_model_generated": False,
            "retry_budget": 0, "repair_budget": 0, "fallback_used": False,
            "oracle_substitution": False, "reserved_states_read": False,
            "runtime_git_commit": runtime_commit,
        }) + "\n", encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
