#!/usr/bin/env python3
"""Zero-provider oracle-correct capability gate for all live semantic arms."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.compact_tx import execute_compact_transaction, parse_proposal
from cope.semantic_cancellation import build_cancellation_event
from cope.semantic_live_runner import (
    SEMANTIC_STATE_FIELDS,
    build_expected_live_post_state,
    build_live_pre_state,
    execute_live_cope_patch,
    parse_live_fsr_semantic_state,
    translate_live_neutral_patch,
    trusted_live_transaction_finalize,
    validate_live_persistent_state,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    build_replacement_event,
    goal_commitment_id,
)
from cope.types import canonical_json, stable_hash


EXPECTED_CASE_IDS = {
    "task0_replace",
    "task0_cancel",
    "task7_replace",
    "task7_cancel",
}
ARMS = ("cope", "neutral_patch", "compact_tx", "fsr_pc")
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
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("interface gate requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def build_event(row: Mapping[str, str]) -> dict[str, Any]:
    milestone = MilestoneEvent(
        policy_step=int(row["policy_step"]),
        done_object=row["done_object"],
        pending_object=row["pending_object"],
        stable_steps=5,
    )
    common = {
        "pair_key": row["case_id"],
        "previous_state_version": int(row["previous_state_version"]),
    }
    if row["event_type"] == "replace_pending_goal":
        return build_replacement_event(
            milestone, replacement_object=row["replacement_object"], **common
        )
    if row["event_type"] == "cancel_pending_goal":
        return build_cancellation_event(milestone, **common)
    raise ValueError(f"unsupported event type {row['event_type']!r}")


def oracle_patch(event: Mapping[str, Any], *, neutral: bool) -> dict[str, Any]:
    replacement = event["event_type"] == "replace_pending_goal"
    value = {
        "event_id": event["event_id"],
        "operation": "N01" if neutral and replacement else
            "N02" if neutral else "Override" if replacement else "Expire",
        "patch_id": f"capability:{event['event_id']}:{'neutral' if neutral else 'cope'}",
        "target_id": event["target_commitment_id"],
    }
    if replacement:
        value["replacement_id"] = goal_commitment_id(event["replacement_object"])
    return value


def compact_oracle_proposal(
    pre_state: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    writes: list[dict[str, Any]] = []
    for root in ("current_goal", "plan", "pending_restorations"):
        if canonical_json(pre_state[root]) != canonical_json(expected[root]):
            writes.append({"op": "replace", "path": f"/{root}", "value": copy.deepcopy(expected[root])})
    pre_commitments = {row["id"]: row for row in pre_state["commitments"]}
    for record in expected["commitments"]:
        record_id = record["id"]
        if record_id not in pre_commitments:
            writes.append({"op": "add", "path": f"/commitments/+/{record_id}", "value": copy.deepcopy(record)})
            continue
        before = pre_commitments[record_id]
        for field, value in record.items():
            if canonical_json(before[field]) != canonical_json(value):
                writes.append({"op": "replace", "path": f"/commitments/{record_id}/{field}", "value": copy.deepcopy(value)})
    pre_entities = {row["id"] for row in pre_state["entities"]}
    for record in expected["entities"]:
        if record["id"] not in pre_entities:
            writes.append({"op": "add", "path": f"/entities/+/{record['id']}", "value": copy.deepcopy(record)})
    return {
        "schema_version": "generic-compact-transaction-v1",
        "base_version": int(pre_state["state_version"]),
        "event_id": event["event_id"],
        "writes": writes,
    }


def run_arm(arm: str, event: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    physically_true = (str(event["done_object"]),)
    pre_state = build_live_pre_state(event)
    expected = build_expected_live_post_state(event)
    proposal: Any
    if arm == "cope":
        proposal = oracle_patch(event, neutral=False)
        candidate, _ = execute_live_cope_patch(
            proposal, event, physically_true_objects=physically_true
        )
    elif arm == "neutral_patch":
        proposal = oracle_patch(event, neutral=True)
        translated = translate_live_neutral_patch(proposal, event)
        candidate, _ = execute_live_cope_patch(
            translated, event, physically_true_objects=physically_true
        )
    elif arm == "compact_tx":
        proposal = compact_oracle_proposal(pre_state, expected, event)
        parsed = parse_proposal(proposal, pre_state, event)
        result = execute_compact_transaction(
            parsed,
            pre_state,
            event,
            lambda staged, _state, current_event: validate_live_persistent_state(
                staged, current_event, physically_true
            ),
            trusted_finalize=trusted_live_transaction_finalize,
        )
        candidate = result.post_state
    elif arm == "fsr_pc":
        proposal = {key: copy.deepcopy(expected[key]) for key in SEMANTIC_STATE_FIELDS}
        candidate = parse_live_fsr_semantic_state(proposal, event)
    else:
        raise ValueError(arm)
    directive = validate_live_persistent_state(candidate, event, physically_true)
    return candidate, directive, stable_hash(proposal)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("zero-provider gate refuses credentials: " + ",".join(populated))
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) != 4 or {row["case_id"] for row in cases} != EXPECTED_CASE_IDS:
        raise ValueError("case manifest differs from frozen four-case assignment")
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for case in cases:
        event = build_event(case)
        expected_hash = stable_hash(build_expected_live_post_state(event))
        case_rows = []
        for arm in ARMS:
            try:
                candidate, directive, proposal_hash = run_arm(arm, event)
                passed = stable_hash(candidate) == expected_hash
                error = "" if passed else "post_state_hash_mismatch"
            except Exception as exc:
                candidate, directive, proposal_hash = {}, "", ""
                passed, error = False, f"{type(exc).__name__}:{exc}"
            row = {
                "case_id": case["case_id"], "task_id": int(case["task_id"]),
                "event_type": case["event_type"], "arm": arm,
                "parser_materializer_validator_pass": passed,
                "proposal_sha256": proposal_hash,
                "post_state_sha256": stable_hash(candidate) if candidate else "",
                "expected_post_state_sha256": expected_hash,
                "compiled_directive": directive,
                "error": error, "provider_calls": 0,
                "simulator_states_indexed": 0,
            }
            rows.append(row); case_rows.append(row)
            print(canonical_json(row), flush=True)
        hashes = {row["post_state_sha256"] for row in case_rows}
        directives = {row["compiled_directive"] for row in case_rows}
        if len(hashes) != 1 or len(directives) != 1:
            for row in case_rows:
                row["parser_materializer_validator_pass"] = False
                row["error"] = row["error"] or "cross_arm_equality_failure"
    result_path = args.output_dir / "01_RESULTS.csv"
    with result_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    passed = sum(bool(row["parser_materializer_validator_pass"]) for row in rows)
    summary = {
        "schema": "cope-multitask-interface-gate-result-v1",
        "runtime_git_commit": runtime_commit,
        "assigned_cells": len(rows), "passed_cells": passed,
        "provider_calls": 0, "simulator_states_indexed": 0,
        "task1_states_25_49_indexed": False,
        "gate": "PASS" if passed == len(rows) else "FAIL",
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    (args.output_dir / "02_RESULT.md").write_text(
        "# Multi-task interface capability result\n\n"
        f"- Gate: **{summary['gate']}**\n- Passed cells: **{passed}/{len(rows)}**\n"
        "- Provider calls: **0**\n- Simulator states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "03_SHA256SUMS.txt").write_text(
        "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts) + "\n",
        encoding="utf-8",
    )
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
