#!/usr/bin/env python3
"""Zero-provider capability gate for the Tang-inspired governed-delta control."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.governed_delta import governed_oracle_proposal, materialize_governed_delta
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    sequence_state_hash,
)
from cope.types import canonical_json, stable_hash
from experiments.sequential_persistence_gate import build_events, run_arm


ARMS = ("cope", "neutral_patch", "fsr_pc", "full_replan", "governed_delta")
EXPECTED_MANIFEST_SHA256 = "3c97c85cb66d048e39e575e4cce56a8d76a699471ecd462df60c37175d0bfa49"
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def available_objects(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        item
        for item in (
            row["done_object"], row["initial_pending_object"],
            row["replacement_c"], row["replacement_d"],
        )
        if item
    )


def run_governed(
    row: Mapping[str, str]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    state = build_initial_sequence_state(
        sequence_id=row["case_id"],
        done_object=row["done_object"],
        pending_object=row["initial_pending_object"],
        available_objects=available_objects(row),
        world_version=int(row["world_version"]),
    )
    event1, event2, _ = build_events(row, state)
    receipts: list[dict[str, Any]] = []
    directives: list[str] = []
    for event in (event1, event2):
        expected = build_expected_next_state(state, event)
        proposal = governed_oracle_proposal(state, expected, event)
        candidate, receipt, directive = materialize_governed_delta(
            proposal, state, event, (row["done_object"],)
        )
        receipts.append(
            {
                **receipt,
                "event_id": event["event_id"],
                "logical_before_hash": sequence_state_hash(state),
                "logical_after_hash": sequence_state_hash(candidate),
                "proposal_sha256": stable_hash(proposal),
            }
        )
        directives.append(directive)
        state = candidate
    return state, receipts, directives


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if hashlib.sha256(args.case_manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("governance collision manifest hash mismatch")
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("zero-provider gate refuses credentials: " + ",".join(credentials))
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("governance collision gate requires a clean commit")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) != 4:
        raise RuntimeError("governance collision gate requires four cases")

    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for case in cases:
        case_rows: list[dict[str, Any]] = []
        for arm in ARMS:
            final, receipts, directives = (
                run_governed(case) if arm == "governed_delta" else run_arm(arm, case)
            )
            continuity = (
                receipts[0]["logical_after_hash"]
                == receipts[1]["logical_before_hash"]
            )
            revisions = [
                receipts[0]["revision_before"] if arm != "governed_delta" else receipts[0]["read_revision"],
                receipts[0]["revision_after"] if arm != "governed_delta" else receipts[0]["published_revision"],
                receipts[1]["revision_after"] if arm != "governed_delta" else receipts[1]["published_revision"],
            ]
            row = {
                "case_id": case["case_id"],
                "arm": arm,
                "revision_path": ">".join(str(value) for value in revisions),
                "hash_continuity": continuity,
                "final_state_sha256": stable_hash(final),
                "final_directive": directives[-1],
                "provider_calls": 0,
                "simulator_states_indexed": 0,
                "passed": continuity and revisions == [1, 2, 3],
            }
            rows.append(row)
            case_rows.append(row)
            traces.append(
                {"case_id": case["case_id"], "arm": arm,
                 "receipts": receipts, "directives": directives,
                 "final_state": final}
            )
        hashes = {row["final_state_sha256"] for row in case_rows}
        directives = {row["final_directive"] for row in case_rows}
        if len(hashes) != 1 or len(directives) != 1:
            for row in case_rows:
                row["passed"] = False

    passed = sum(bool(row["passed"]) for row in rows)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (args.output_dir / "02_TRACES.txt").write_text(
        "\n".join(canonical_json(item) for item in traces) + "\n",
        encoding="utf-8",
    )
    result = {
        "schema": "governance-collision-capability-v1",
        "runtime_git_commit": runtime_commit,
        "assigned_cells": len(rows),
        "assigned_transitions": len(rows) * 2,
        "passed_cells": passed,
        "provider_calls": 0,
        "simulator_states_indexed": 0,
        "credential_names_present": [],
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "gate": "PASS" if passed == len(rows) else "FAIL",
    }
    (args.output_dir / "00_STATUS.txt").write_text(
        canonical_json(result) + "\n", encoding="utf-8"
    )
    (args.output_dir / "03_RESULT.md").write_text(
        "# Governance-collision capability result\n\n"
        f"- Gate: **{result['gate']}**\n"
        f"- Passed sequence-arm cells: **{passed}/{len(rows)}**\n"
        f"- Transitions: **{len(rows) * 2}**\n"
        "- Provider calls: **0**\n"
        "- Simulator states indexed: **0**\n\n"
        "This establishes oracle capability parity only. The governed-delta "
        "arm is a Tang-inspired operationalization, not the authors' code.\n",
        encoding="utf-8",
    )
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())

