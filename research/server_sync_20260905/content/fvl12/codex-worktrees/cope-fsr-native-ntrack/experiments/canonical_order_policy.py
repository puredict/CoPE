#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import statistics
import time
from pathlib import Path
from typing import Any

from cope.decomposed_validator import decomposed_violations
from cope.native_ntrack import derive_post_state, load_manifest, state_without_history
from cope.record_normalization import (
    NORMALIZATION_VERSION,
    RecordNormalizationError,
    is_normalized_record_order,
    normalize_record_order,
    normalized_state_hash,
)
from cope.types import canonical_json, stable_hash


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_order_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [row for row in csv.DictReader(stream) if row["order_only_divergence"] == "True"]
    if len(rows) != 14:
        raise ValueError("expected the 14 frozen X18 v2 order-only rows")
    return rows


def clean_controls(cases):
    rows = []
    cache = {}
    for case in cases:
        caller_before = canonical_json(case.pre_state)
        post = state_without_history(derive_post_state(case.pre_state, case.event))
        normalized_pre = normalize_record_order(case.pre_state)
        normalized_post = normalize_record_order(post)
        second = normalize_record_order(normalized_post)
        violations = decomposed_violations(normalized_post, normalized_pre, case.event)
        cache[case.case_id] = {"post": post, "normalized_pre": normalized_pre, "normalized_post": normalized_post}
        passed = bool(
            canonical_json(normalized_post) == canonical_json(second)
            and not any(violations.values())
            and is_normalized_record_order(normalized_post)
            and canonical_json(case.pre_state) == caller_before
        )
        rows.append({
            "case_id": case.case_id,
            "normalization_version": NORMALIZATION_VERSION,
            "legacy_already_strict": is_normalized_record_order(post),
            "normalized_strict": is_normalized_record_order(normalized_post),
            "idempotent": canonical_json(normalized_post) == canonical_json(second),
            "decomposed_semantic_accepted": not any(violations.values()),
            "legacy_sha256": stable_hash(post),
            "normalized_sha256": normalized_state_hash(post),
            "caller_state_unchanged": canonical_json(case.pre_state) == caller_before,
            "pass": passed,
        })
    return rows, cache


def reorder_controls(order_rows, cases_by_id, cache):
    rows = []
    for source in order_rows:
        case = cases_by_id[source["case_id"]]
        canonical = cache[case.case_id]["post"]
        candidate = copy.deepcopy(canonical)
        collection = source["path"].removeprefix("/")
        candidate[collection].reverse()
        normalized_candidate = normalize_record_order(candidate)
        normalized_reference = cache[case.case_id]["normalized_post"]
        violations = decomposed_violations(
            normalized_candidate, cache[case.case_id]["normalized_pre"], case.event
        )
        strict_accepts_provider = is_normalized_record_order(candidate)
        bytes_equal = canonical_json(normalized_candidate) == canonical_json(normalized_reference)
        hash_equal = normalized_state_hash(candidate) == normalized_state_hash(canonical)
        passed = bool(
            not strict_accepts_provider and bytes_equal and hash_equal
            and not any(violations.values()) and is_normalized_record_order(normalized_candidate)
        )
        rows.append({
            "case_id": case.case_id,
            "x18_mutation_id": source["mutation_id"],
            "collection_path": source["path"],
            "strict_policy_accepts_provider_candidate": strict_accepts_provider,
            "normalize_policy_accepts": not any(violations.values()),
            "normalized_bytes_equal": bytes_equal,
            "normalized_hash_equal": hash_equal,
            "normalized_idempotent": canonical_json(normalized_candidate) == canonical_json(normalize_record_order(normalized_candidate)),
            "normalization_version": NORMALIZATION_VERSION,
            "pass": passed,
        })
    return rows


def fault_controls(case, fault_manifest: Path):
    with fault_manifest.open(newline="", encoding="utf-8") as stream:
        assignments = list(csv.DictReader(stream))
    canonical = state_without_history(derive_post_state(case.pre_state, case.event))
    rows = []
    for assignment in assignments:
        candidate = copy.deepcopy(canonical)
        fault_id = assignment["fault_id"]
        if fault_id == "K01": candidate["commitments"].append(copy.deepcopy(candidate["commitments"][0]))
        elif fault_id == "K02": candidate["entities"].append(copy.deepcopy(candidate["entities"][0]))
        elif fault_id == "K03": candidate["progress_ledger"].append(copy.deepcopy(candidate["progress_ledger"][0]))
        elif fault_id == "K04": del candidate["commitments"][0]["id"]
        elif fault_id == "K05": candidate["entities"][0]["id"] = 5
        elif fault_id == "K06": candidate["progress_ledger"] = {}
        elif fault_id == "K07": candidate["commitments"][0] = "not-a-record"
        else: raise ValueError(fault_id)
        before = canonical_json(candidate)
        rejected = False
        error = ""
        try:
            normalize_record_order(candidate)
        except RecordNormalizationError as exc:
            rejected = True
            error = f"{type(exc).__name__}:{exc}"
        rows.append({
            "fault_id": fault_id,
            "collection": assignment["collection"],
            "fault": assignment["fault"],
            "rejected": rejected,
            "error": error,
            "caller_candidate_unchanged": canonical_json(candidate) == before,
            "pass": rejected and canonical_json(candidate) == before,
        })
    return rows


def timing_controls(cases, cache):
    data = {case.case_id: [] for case in cases}
    for warmup in range(20):
        order = cases[warmup % len(cases):] + cases[:warmup % len(cases)]
        for case in order: normalize_record_order(cache[case.case_id]["post"])
    for repetition in range(1000):
        order = cases[repetition % len(cases):] + cases[:repetition % len(cases)]
        for case in order:
            started = time.perf_counter_ns()
            normalize_record_order(cache[case.case_id]["post"])
            data[case.case_id].append(time.perf_counter_ns() - started)
    return [{
        "case_id": case.case_id,
        "warmups": 20,
        "recorded_repetitions": 1000,
        "median_normalization_ns": int(statistics.median(data[case.case_id])),
    } for case in cases]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--x18-results", type=Path, required=True)
    parser.add_argument("--fault-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    cases = load_manifest(args.case_manifest)
    clean, cache = clean_controls(cases)
    reorder = reorder_controls(load_order_rows(args.x18_results), {case.case_id: case for case in cases}, cache)
    faults = fault_controls(next(case for case in cases if case.case_id == "replace_pending_target"), args.fault_manifest)
    timing = timing_controls(cases, cache)
    write_csv(args.output_dir / "02_CLEAN_NORMALIZATION.csv", clean)
    write_csv(args.output_dir / "03_REORDER_POLICY_RESULTS.csv", reorder)
    write_csv(args.output_dir / "04_KEY_FAULT_RESULTS.csv", faults)
    write_csv(args.output_dir / "05_TIMING.csv", timing)
    aggregate_median = int(statistics.median(row["median_normalization_ns"] for row in timing))
    decision = bool(
        all(row["pass"] for row in clean) and all(row["pass"] for row in reorder)
        and all(row["pass"] for row in faults) and aggregate_median < 1_000_000
    )
    lines = [
        "schema_version=canonical-order-policy-status-v1",
        f"normalization_version={NORMALIZATION_VERSION}",
        f"clean_pass={sum(bool(row['pass']) for row in clean)}/12",
        f"legacy_clean_already_strict={sum(bool(row['legacy_already_strict']) for row in clean)}/12",
        f"normalized_clean_strict={sum(bool(row['normalized_strict']) for row in clean)}/12",
        f"strict_rejects_reorder={sum(not bool(row['strict_policy_accepts_provider_candidate']) for row in reorder)}/14",
        f"normalize_accepts_reorder={sum(bool(row['normalize_policy_accepts']) for row in reorder)}/14",
        f"normalized_bytes_hash_equal={sum(bool(row['normalized_bytes_equal']) and bool(row['normalized_hash_equal']) for row in reorder)}/14",
        f"key_faults_rejected={sum(bool(row['rejected']) for row in faults)}/7",
        f"aggregate_median_normalization_ns={aggregate_median}",
        f"timing_gate_under_1ms={aggregate_median < 1_000_000}",
        f"selected_policy={'normalize_before_validate_publish_hash' if decision else 'strict_reject'}",
        f"decision={'PASS' if decision else 'FAIL'}",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "06_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
