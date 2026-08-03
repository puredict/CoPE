#!/usr/bin/env python3
"""Credential-free four-arm gate for truly sequential semantic transitions."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
    execute_typed_sparse_transition,
    fsr_oracle_proposal,
    full_replan_oracle_proposal,
    initialize_typed_sequence_state,
    materialize_fsr_proposal,
    materialize_full_replan_proposal,
    sequence_state_hash,
    sparse_oracle_proposal,
    validate_sequence_transition,
)
from cope.types import canonical_json, stable_hash


ARMS = ("cope", "neutral_patch", "fsr_pc", "full_replan")
EXPECTED_CASES = {
    "task0_replace_cancel",
    "task0_replace_replace",
    "task7_replace_cancel",
    "task7_replace_replace",
}
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


def repository_commit_and_clean(repo_root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("sequential gate requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _available_objects(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        item
        for item in (
            row["done_object"],
            row["initial_pending_object"],
            row["replacement_c"],
            row["replacement_d"],
        )
        if item
    )


def build_events(
    row: Mapping[str, str], initial: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    event1 = build_sequence_event(
        initial,
        sequence_id=row["case_id"],
        step_index=1,
        done_object=row["done_object"],
        event_type="replace_pending_goal",
        replacement_object=row["replacement_c"],
        world_version=int(row["world_version"]) + 1,
    )
    after1 = build_expected_next_state(initial, event1)
    second_type = (
        "cancel_pending_goal"
        if row["sequence_type"] == "replace_then_cancel"
        else "replace_pending_goal"
    )
    event2 = build_sequence_event(
        after1,
        sequence_id=row["case_id"],
        step_index=2,
        done_object=row["done_object"],
        event_type=second_type,
        replacement_object=row["replacement_d"] or None,
        world_version=int(row["world_version"]) + 2,
    )
    return event1, event2, after1


def run_arm(
    arm: str, row: Mapping[str, str]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    initial = build_initial_sequence_state(
        sequence_id=row["case_id"],
        done_object=row["done_object"],
        pending_object=row["initial_pending_object"],
        available_objects=_available_objects(row),
        world_version=int(row["world_version"]),
    )
    event1, event2, _ = build_events(row, initial)
    physically_true = (row["done_object"],)
    state = initial
    typed_state = (
        initialize_typed_sequence_state(
            sequence_id=row["case_id"],
            done_object=row["done_object"],
            pending_object=row["initial_pending_object"],
        )
        if arm in {"cope", "neutral_patch"}
        else None
    )
    receipts: list[dict[str, Any]] = []
    directives: list[str] = []
    for event in (event1, event2):
        before_hash = sequence_state_hash(state)
        expected = build_expected_next_state(state, event)
        if arm in {"cope", "neutral_patch"}:
            proposal = sparse_oracle_proposal(event, neutral=arm == "neutral_patch")
            assert typed_state is not None
            typed_state, candidate, receipt, directive = execute_typed_sparse_transition(
                typed_state,
                state,
                event,
                proposal,
                neutral=arm == "neutral_patch",
                physically_true_objects=physically_true,
            )
        elif arm == "fsr_pc":
            proposal = fsr_oracle_proposal(expected)
            candidate, directive = materialize_fsr_proposal(
                proposal, state, event, physically_true
            )
            receipt = {"accepted": True}
        elif arm == "full_replan":
            proposal = full_replan_oracle_proposal(expected, event)
            candidate, directive = materialize_full_replan_proposal(
                proposal, state, event, physically_true
            )
            receipt = {"accepted": True}
        else:
            raise ValueError(arm)
        validate_sequence_transition(state, candidate, event, physically_true)
        after_hash = sequence_state_hash(candidate)
        receipts.append(
            {
                **receipt,
                "event_id": event["event_id"],
                "revision_before": int(state["state_version"]),
                "revision_after": int(candidate["state_version"]),
                "logical_before_hash": before_hash,
                "logical_after_hash": after_hash,
                "proposal_sha256": stable_hash(proposal),
            }
        )
        directives.append(directive)
        state = candidate
    return state, receipts, directives


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("zero-provider gate refuses credentials: " + ",".join(credentials))
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) != 4 or {row["case_id"] for row in cases} != EXPECTED_CASES:
        raise ValueError("case manifest differs from frozen assignment")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for case in cases:
        case_rows: list[dict[str, Any]] = []
        for arm in ARMS:
            try:
                final_state, receipts, directives = run_arm(arm, case)
                continuity = (
                    receipts[0]["logical_after_hash"]
                    == receipts[1]["logical_before_hash"]
                )
                revisions = [
                    receipts[0]["revision_before"],
                    receipts[0]["revision_after"],
                    receipts[1]["revision_after"],
                ]
                passed = continuity and revisions == [1, 2, 3]
                error = "" if passed else "continuity_or_revision_failure"
            except Exception as exc:
                final_state, receipts, directives = {}, [], []
                continuity, revisions = False, []
                passed, error = False, f"{type(exc).__name__}:{exc}"
            row = {
                "case_id": case["case_id"],
                "task_id": int(case["task_id"]),
                "sequence_type": case["sequence_type"],
                "arm": arm,
                "passed": passed,
                "revision_path": ">".join(str(item) for item in revisions),
                "adjacent_logical_hash_continuity": continuity,
                "final_state_sha256": stable_hash(final_state) if final_state else "",
                "final_directive": directives[-1] if directives else "",
                "provider_calls": 0,
                "simulator_states_indexed": 0,
                "error": error,
            }
            rows.append(row)
            case_rows.append(row)
            traces.append(
                {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "receipts": receipts,
                    "final_state": final_state,
                    "directives": directives,
                }
            )
            print(canonical_json(row), flush=True)
        hashes = {row["final_state_sha256"] for row in case_rows}
        directives = {row["final_directive"] for row in case_rows}
        if len(hashes) != 1 or len(directives) != 1:
            for row in case_rows:
                row["passed"] = False
                row["error"] = row["error"] or "cross_arm_final_state_mismatch"
    with (args.output_dir / "01_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / "02_TRACES.txt").write_text(
        "\n".join(canonical_json(item) for item in traces) + "\n", encoding="utf-8"
    )
    passed = sum(bool(row["passed"]) for row in rows)
    status = {
        "schema": "sequential-persistence-gate-result-v1",
        "runtime_git_commit": runtime_commit,
        "assigned_cells": len(rows),
        "passed_cells": passed,
        "provider_calls": 0,
        "simulator_states_indexed": 0,
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "gate": "PASS" if passed == len(rows) else "FAIL",
    }
    (args.output_dir / "00_STATUS.txt").write_text(
        canonical_json(status) + "\n", encoding="utf-8"
    )
    (args.output_dir / "03_RESULT.md").write_text(
        "# Sequential persistent-state capability result\n\n"
        f"- Gate: **{status['gate']}**\n"
        f"- Passed cells: **{passed}/{len(rows)}**\n"
        "- Revision path required: **1 > 2 > 3**\n"
        "- Provider calls: **0**\n"
        "- Simulator states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in artifacts
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
