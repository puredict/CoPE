#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from cope.libero_predicate_validator import (
    LiberoPredicateRevalidationValidator,
    build_predicate_snapshot,
)
from cope.schema import ConstraintSlot


PRODUCER_COMMIT = "2fcfb32ec9c3a4b80642ddea494d9e32c85eb11b"
EXPECTED_CASE_COUNT = 10


def parse_bool(value: str) -> bool:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"non-boolean value {value!r}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_slot(object_name: str, region: str) -> ConstraintSlot:
    return ConstraintSlot(
        slot_id=f"goal:in:{object_name}:{region}",
        constraint_type="task_goal",
        content={"predicate": "in", "arguments": [object_name, region]},
        source="task",
        mode="suspended",
        priority=100,
        created_event_id="genesis",
        last_updated_event_id="replay-suspend",
        lineage=(f"goal:in:{object_name}:{region}",),
    )


def run_case(repo_root: Path, case: dict[str, str]) -> dict[str, object]:
    source = repo_root / case["source_path"]
    actual_source_hash = file_sha256(source)
    if actual_source_hash != case["source_sha256"]:
        raise ValueError(f"source hash mismatch for {case['case_id']}")
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"source must contain exactly one row: {source}")
    raw = rows[0]
    source_value = parse_bool(raw[case["source_field"]])
    expected = parse_bool(case["expected"])
    if source_value is not expected:
        raise ValueError(f"frozen expectation disagrees with source: {case['case_id']}")
    event_id = f"recorded-summary-replay:task1:state{case['state_id']}"
    packet = build_predicate_snapshot(
        task_suite="libero_10",
        task_id=1,
        event_id=event_id,
        policy_step=int(raw["event_step"]),
        observation_sha256=actual_source_hash,
        simulator_state_sha256=raw["sim_state_before_patch_sha256"],
        producer_commit=PRODUCER_COMMIT,
        predicates=(
            ("in", (case["slot_object"], case["slot_region"]), source_value),
        ),
        test_only=True,
        source_kind="recorded_summary_replay",
    )
    checked = LiberoPredicateRevalidationValidator(
        {
            "predicate_snapshot": {
                "allow_test_packets": True,
                "task_suite": "libero_10",
                "task_id": 1,
                "producer_commit": PRODUCER_COMMIT,
            }
        }
    )
    actual = checked(
        make_slot(case["slot_object"], case["slot_region"]),
        {
            "provider_evidence": {"claimed_value": not source_value},
            "observation": {
                "sha256": actual_source_hash,
                "predicate_snapshot": packet,
            },
            "event": {"event_id": event_id},
        },
    )
    return {
        "case_id": case["case_id"],
        "state_id": int(case["state_id"]),
        "source_sha256_verified": True,
        "source_field": case["source_field"],
        "source_value": source_value,
        "validator_value": actual,
        "expected": expected,
        "provider_contradiction_ignored": actual is not (not source_value),
        "test_only": packet["test_only"],
        "live_packet": False,
        "reserved_state_consumed": False,
        "passed": actual is expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) != EXPECTED_CASE_COUNT or len({row["case_id"] for row in cases}) != len(cases):
        raise ValueError("replay manifest is not the frozen 10-case assignment")
    results = [run_case(repo_root, case) for case in cases]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    passed = sum(bool(row["passed"]) for row in results)
    print(f"assigned={len(results)} passed={passed} live_packets=0 reserve_consumed=0")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
