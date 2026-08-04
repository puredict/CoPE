#!/usr/bin/env python3
"""Credential-free oracle and request preflight for 200 occurrence calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from cope.occurrence_prompting import (
    ARMS, CONTRACTS, MAX_COMPLETION_TOKENS, MAX_PROMPT_TOKENS, MODEL,
    REASONING_EFFORT, TEMPERATURE, TIMEOUT_SECONDS, build_recovery_input,
)
from cope.occurrence_sequence import (
    build_recurrence_case, cope_oracle, expected_next_state, fsr_oracle,
    full_replan_oracle, governed_oracle, materialize_cope, materialize_fsr,
    materialize_full_replan, materialize_governed, materialize_neutral,
    neutral_oracle,
)
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import canonical_json, stable_hash


EXPECTED_MANIFEST_SHA256 = "21f22b95dd106dc91c58ef288ecf22c7b5dcd093d279320b60be392d652992b8"
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def validate_manifest(rows: list[dict[str, str]]) -> None:
    if len(rows) != 40 or len({row["case_id"] for row in rows}) != 40:
        raise ValueError("occurrence manifest must contain 40 unique cases")
    counts = Counter((int(row["triple_index"]), int(row["recurrence_depth"])) for row in rows)
    expected = {(triple, depth) for triple in range(10) for depth in range(1, 5)}
    if set(counts) != expected or set(counts.values()) != {1}:
        raise ValueError("occurrence triple/depth assignment is noncanonical")
    positions = Counter()
    for row in rows:
        order = row["arm_order"].split(";")
        if len(order) != 5 or set(order) != set(ARMS):
            raise ValueError("occurrence arm order is incomplete")
        for position, arm in enumerate(order):
            positions[(position, arm)] += 1
        if int(row["provider_calls_per_arm"]) != 1 or int(row["retry_budget"]) != 0:
            raise ValueError("occurrence call budget drift")
        if row["model"] != MODEL or float(row["temperature"]) != TEMPERATURE:
            raise ValueError("occurrence provider configuration drift")
    if set(positions.values()) != {8}:
        raise ValueError("occurrence arm positions are not balanced")


def proposal_for(
    arm: str, pre: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "cope": lambda: cope_oracle(event),
        "neutral_patch": lambda: neutral_oracle(pre, expected, event),
        "governed_delta": lambda: governed_oracle(pre, expected, event),
        "fsr_pc": lambda: fsr_oracle(expected),
        "full_replan": lambda: full_replan_oracle(expected, event),
    }[arm]()


def materialize(
    arm: str, proposal: Mapping[str, Any], typed: Any,
    pre: Mapping[str, Any], event: Mapping[str, Any], done: str,
) -> dict[str, Any]:
    if arm == "cope":
        _, candidate, _, _ = materialize_cope(proposal, typed, pre, event, (done,))
    elif arm == "neutral_patch":
        candidate, _, _ = materialize_neutral(proposal, pre, event, (done,))
    elif arm == "governed_delta":
        candidate, _, _ = materialize_governed(proposal, pre, event, (done,))
    elif arm == "fsr_pc":
        candidate, _ = materialize_fsr(proposal, pre, event, (done,))
    else:
        candidate, _ = materialize_full_replan(proposal, pre, event, (done,))
    return candidate


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("occurrence preflight requires a clean committed worktree")
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("cold preflight refuses credentials: " + ",".join(populated))
    if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("occurrence manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validate_manifest(rows)
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    requests = []
    for row in rows:
        pre, event, typed = build_recurrence_case(
            case_id=row["case_id"], done_object=row["done_object"],
            recurring_object=row["recurring_object"],
            intermediate_object=row["intermediate_object"],
            recurrence_depth=int(row["recurrence_depth"]),
        )
        expected = expected_next_state(pre, event)
        recovery = build_recovery_input(case_id=row["case_id"], pre_state=pre, event=event)
        provider = OpenAICompatibleRecoveryProvider({
            "provider": "openrouter", "model": MODEL,
            "reasoning_effort": REASONING_EFFORT, "temperature": TEMPERATURE,
            "seed": int(row["seed"]), "max_prompt_tokens": MAX_PROMPT_TOKENS,
            "max_completion_tokens": MAX_COMPLETION_TOKENS, "max_retries": 0,
            "timeout_seconds": TIMEOUT_SECONDS,
        })
        candidate_hashes = set()
        for arm in row["arm_order"].split(";"):
            proposal = proposal_for(arm, pre, expected, event)
            candidate = materialize(
                arm, proposal, typed, pre, event, row["done_object"]
            )
            if canonical_json(candidate) != canonical_json(expected):
                raise RuntimeError(f"oracle candidate mismatch: {row['case_id']}/{arm}")
            candidate_hashes.add(stable_hash(candidate))
            mode = "patch" if arm == "cope" else "compact" if arm in {"neutral_patch", "governed_delta"} else "regenerate"
            audited = provider.build_audited_request(mode, recovery, CONTRACTS[arm])
            normalized = {
                **audited["wire_payload"],
                "messages": [
                    *audited["wire_payload"]["messages"][:2],
                    {"role": "user", "content": "<ARM_OUTPUT_CONTRACT>"},
                ],
            }
            requests.append({
                "case_id": row["case_id"], "arm": arm,
                "recurrence_depth": int(row["recurrence_depth"]),
                "input_sha256": recovery.input_hash,
                "normalized_request_sha256": stable_hash(normalized),
                "output_contract_sha256": stable_hash(CONTRACTS[arm]),
                "oracle_candidate_sha256": stable_hash(candidate),
                "oracle_proposal_bytes": len(canonical_json(proposal).encode("utf-8")),
                "wire_bytes": len(canonical_json(audited["wire_payload"]).encode("utf-8")),
            })
        if len(candidate_hashes) != 1:
            raise RuntimeError(f"five-arm oracle hash drift: {row['case_id']}")
    if len(requests) != 200:
        raise RuntimeError(f"expected 200 requests, built {len(requests)}")
    grouped = Counter(
        (row["case_id"], row["input_sha256"], row["normalized_request_sha256"])
        for row in requests
    )
    if len(grouped) != 40 or set(grouped.values()) != {5}:
        raise RuntimeError("occurrence normalized common requests are not matched")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_REQUESTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(requests[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(requests)
    status = {
        "schema": "occurrence-learned-formal-cold-preflight-v1",
        "gate": "PASS", "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "cases": 40, "arms": 5, "oracle_cells": 200,
        "planned_provider_calls": 200, "provider_calls_made": 0,
        "simulator_states_indexed": 0,
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
