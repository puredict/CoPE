#!/usr/bin/env python3
"""Deterministic carrier/contract accounting for the governance collision arm."""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.governance_collision_prompting import GOVERNED_DELTA_CONTRACT
from cope.governed_delta import governed_oracle_proposal, materialize_governed_delta
from cope.sequential_prompting import CONTRACTS
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    fsr_oracle_proposal,
    full_replan_oracle_proposal,
    materialize_fsr_proposal,
    materialize_full_replan_proposal,
    materialize_neutral_json_patch,
    neutral_json_oracle_proposal,
    parse_sparse_proposal,
    sparse_oracle_proposal,
    validate_sequence_transition,
)
from cope.types import canonical_json
from experiments.sequential_persistence_gate import build_events


ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan")
EXPECTED_MANIFEST_SHA256 = "3c97c85cb66d048e39e575e4cce56a8d76a699471ecd462df60c37175d0bfa49"
CONTRACT_BY_ARM = {
    **CONTRACTS,
    "governed_delta": GOVERNED_DELTA_CONTRACT,
}
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def json_leaf_count(value: Any) -> int:
    if isinstance(value, Mapping):
        return sum(json_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(json_leaf_count(item) for item in value)
    return 1


def available_objects(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        item for item in (
            row["done_object"], row["initial_pending_object"],
            row["replacement_c"], row["replacement_d"],
        ) if item
    )


def proposal_and_materialize(
    arm: str, state: Mapping[str, Any], expected: Mapping[str, Any],
    event: Mapping[str, Any], done_object: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    physical = (done_object,)
    if arm == "cope":
        proposal = sparse_oracle_proposal(event, neutral=False)
        parse_sparse_proposal(proposal, state, event, neutral=False)
        candidate = dict(expected)
        directive = validate_sequence_transition(state, candidate, event, physical)
        return proposal, candidate, directive
    if arm == "neutral_patch":
        proposal = neutral_json_oracle_proposal(state, expected, event)
        candidate, _, directive = materialize_neutral_json_patch(
            proposal, state, event, physical
        )
    elif arm == "governed_delta":
        proposal = governed_oracle_proposal(state, expected, event)
        candidate, _, directive = materialize_governed_delta(
            proposal, state, event, physical
        )
    elif arm == "fsr_pc":
        proposal = fsr_oracle_proposal(expected)
        candidate, directive = materialize_fsr_proposal(
            proposal, state, event, physical
        )
    elif arm == "full_replan":
        proposal = full_replan_oracle_proposal(expected, event)
        candidate, directive = materialize_full_replan_proposal(
            proposal, state, event, physical
        )
    else:
        raise ValueError(arm)
    return proposal, candidate, directive


def build_rows(cases: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        initial = build_initial_sequence_state(
            sequence_id=case["case_id"],
            done_object=case["done_object"],
            pending_object=case["initial_pending_object"],
            available_objects=available_objects(case),
            world_version=int(case["world_version"]),
        )
        event1, event2, middle = build_events(case, initial)
        state = initial
        for event_index, event in enumerate((event1, event2), start=1):
            expected = build_expected_next_state(state, event)
            transition_rows = []
            for arm in ARMS:
                proposal, candidate, directive = proposal_and_materialize(
                    arm, state, expected, event, case["done_object"]
                )
                if canonical_json(candidate) != canonical_json(expected):
                    raise RuntimeError(f"oracle materialization mismatch: {case['case_id']}/{event_index}/{arm}")
                transition_rows.append(
                    {
                        "case_id": case["case_id"],
                        "event_index": event_index,
                        "sequence_type": case["sequence_type"],
                        "arm": arm,
                        "proposal_bytes": len(canonical_json(proposal).encode("utf-8")),
                        "contract_bytes": len(CONTRACT_BY_ARM[arm].encode("utf-8")),
                        "json_leaf_count": json_leaf_count(proposal),
                        "directive": directive,
                        "canonical_equivalent": True,
                    }
                )
            fsr_bytes = next(
                row["proposal_bytes"] for row in transition_rows if row["arm"] == "fsr_pc"
            )
            for row in transition_rows:
                row["proposal_to_fsr_ratio"] = row["proposal_bytes"] / fsr_bytes
            rows.extend(transition_rows)
            state = expected
    return rows


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if __import__("hashlib").sha256(args.case_manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("carrier byte manifest hash mismatch")
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("carrier byte audit refuses credentials: " + ",".join(credentials))
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout
    if dirty.strip():
        raise RuntimeError("carrier byte audit requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    rows = build_rows(cases)
    aggregate = []
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        values = [int(row["proposal_bytes"]) for row in selected]
        leaves = [int(row["json_leaf_count"]) for row in selected]
        aggregate.append(
            {
                "arm": arm,
                "transitions": len(selected),
                "proposal_bytes_median": statistics.median(values),
                "proposal_bytes_min": min(values),
                "proposal_bytes_max": max(values),
                "contract_bytes": len(CONTRACT_BY_ARM[arm].encode("utf-8")),
                "json_leaf_count_median": statistics.median(leaves),
                "cope_smaller_pairs": (
                    "" if arm == "cope" else sum(
                        next(r["proposal_bytes"] for r in rows if r["case_id"] == row["case_id"] and r["event_index"] == row["event_index"] and r["arm"] == "cope") < row["proposal_bytes"]
                        for row in selected
                    )
                ),
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_PER_TRANSITION.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with (args.output_dir / "02_AGGREGATE.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregate[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(aggregate)
    status = {
        "schema": "governed-carrier-byte-audit-v1",
        "runtime_git_commit": runtime_commit,
        "transitions": 8,
        "rows": len(rows),
        "canonical_equivalent_rows": sum(bool(row["canonical_equivalent"]) for row in rows),
        "provider_calls": 0,
        "simulator_states_indexed": 0,
        "credential_names_present": [],
        "gate": "PASS" if len(rows) == 40 else "FAIL",
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0 if status["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
