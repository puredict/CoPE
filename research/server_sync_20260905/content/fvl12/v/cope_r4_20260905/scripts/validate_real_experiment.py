#!/usr/bin/env python3
"""Validate real episode schemas, artifacts, and paired-run invariants."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ARTIFACTS = {
    "result.json",
    "events.jsonl",
    "adaptation_trace.jsonl",
    "repair_trace.jsonl",
    "state_snapshots.json",
    "simulator.log",
    "video.mp4",
}


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def event_signature(row: dict) -> list[tuple]:
    return [
        (
            event.get("event_id"),
            event.get("ordinal"),
            event.get("simulator_step"),
            json.dumps(
                event.get("world_application", {}).get("requested_world", {}),
                sort_keys=True,
            ),
            json.dumps(
                event.get("world_application", {}).get("simulator_changes", []),
                sort_keys=True,
            ),
        )
        for event in row.get("events", [])
    ]


def repair_signature(row: dict) -> list[tuple]:
    return [
        (
            repair.get("event_id"),
            repair.get("requirements_fingerprint"),
            tuple(repair.get("candidate_names", [])),
            repair.get("selected"),
            bool(repair.get("restore_validated")),
            bool(repair.get("stage_resumed")),
        )
        for repair in row.get("repair_outcomes", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--require-pairs", action="store_true")
    parser.add_argument(
        "--require-pair-success",
        action="store_true",
        help="debug-gate only: additionally require both arms in every pair "
        "to succeed; scientific pilot task failures remain valid records",
    )
    args = parser.parse_args()
    if args.require_pair_success and not args.require_pairs:
        parser.error("--require-pair-success requires --require-pairs")

    schema = json.loads(
        (ROOT / "results_schema" / "real_episode_record.schema.json").read_text()
    )
    paths = sorted(args.root.rglob("result.json"))
    problems: list[str] = []
    rows: list[dict] = []
    if args.expected_records is not None and len(paths) != args.expected_records:
        fail(problems, f"record count {len(paths)} != {args.expected_records}")

    for path in paths:
        row = json.loads(path.read_text())
        try:
            jsonschema.validate(row, schema)
        except jsonschema.ValidationError as exc:
            fail(problems, f"{path}: schema: {exc.message}")
        missing = REQUIRED_ARTIFACTS - {item.name for item in path.parent.iterdir()}
        if missing:
            fail(problems, f"{path.parent}: missing artifacts {sorted(missing)}")
        if row["denominators"].get("valid_episodes") != 1:
            fail(problems, f"{path}: invalid episode denominator")
        if row.get("infrastructure_errors"):
            fail(problems, f"{path}: infrastructure errors present")
        if not row.get("video", {}).get("written"):
            fail(problems, f"{path}: video not written")
        if not row.get("task_metrics", {}).get("no_task_object_attached"):
            fail(problems, f"{path}: a task object remains attached")
        if not row.get("task_metrics", {}).get("stability_gate_passed"):
            fail(problems, f"{path}: final stability gate failed")
        rows.append(row)

    grouped: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        grouped[(row["condition"], row["seed"])][row["method"]] = row

    pairs_checked = 0
    if args.require_pairs:
        for key, methods in sorted(grouped.items()):
            if not {"CoPE", "FSR-PC"}.issubset(methods):
                fail(problems, f"{key}: missing CoPE/FSR-PC pair")
                continue
            cope, fsrpc = methods["CoPE"], methods["FSR-PC"]
            pairs_checked += 1
            if args.require_pair_success:
                if not cope["metrics"].get("revised_task_success"):
                    fail(problems, f"{key}: CoPE debug task failed")
                if not fsrpc["metrics"].get("revised_task_success"):
                    fail(problems, f"{key}: FSR-PC debug task failed")
            if cope["reset_meta"]["state_hash"] != fsrpc["reset_meta"]["state_hash"]:
                fail(problems, f"{key}: initial simulator hashes differ")
            if event_signature(cope) != event_signature(fsrpc):
                fail(problems, f"{key}: interruption signatures differ")
            if repair_signature(cope) != repair_signature(fsrpc):
                fail(problems, f"{key}: downstream repair signatures differ")
            cope_markers = [m for e in cope["events"] for m in e["pipeline_markers"]]
            fsrpc_markers = [m for e in fsrpc["events"] for m in e["pipeline_markers"]]
            if "PATCH" not in cope_markers or "REGENERATION" in cope_markers:
                fail(problems, f"{key}: CoPE state-semantics markers wrong")
            if "REGENERATION" not in fsrpc_markers or "PATCH" in fsrpc_markers:
                fail(problems, f"{key}: FSR-PC state-semantics markers wrong")
            if not cope["metrics"].get("identity_preserved"):
                fail(problems, f"{key}: CoPE identity not preserved")
            if fsrpc["metrics"].get("identity_preserved"):
                fail(problems, f"{key}: FSR-PC unexpectedly preserved identity")

    print(f"records={len(rows)} pairs_checked={pairs_checked} problems={len(problems)}")
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print("REAL EXPERIMENT VALIDATION: PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
