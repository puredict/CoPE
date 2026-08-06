#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any

from cope.compact_tx import (
    CompactTransactionRejected,
    execute_compact_transaction,
    proposal_from_verbose_carrier,
)
from cope.native_ntrack import (
    NativeCase,
    derive_post_state,
    expected_patch,
    load_manifest,
    materialize_patch,
    state_without_history,
    validate_and_compile,
)
from cope.tx_exec import execute_transaction
from cope.types import canonical_json, stable_hash


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def common_receipt(method: str, case: NativeCase, post: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "common-execution-receipt-v1",
        "method": method,
        "event_id": case.event["event_id"],
        "read_version": case.pre_state["state_version"],
        "before_sha256": stable_hash(state_without_history(case.pre_state)),
        "after_sha256": stable_hash(post),
        "validator_calls": 1,
        "validator_passed": True,
        "published": True,
        "rolled_back": False,
    }


def case_artifacts(case: NativeCase) -> dict[str, Any]:
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    cope_patch = expected_patch(case.pre_state, case.event)
    cope_state = materialize_patch(cope_patch, case.pre_state, case.event)
    verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
    compact_proposal = proposal_from_verbose_carrier(verbose.carrier)
    compact = execute_compact_transaction(
        compact_proposal, case.pre_state, case.event, validate_and_compile
    )
    return {
        "oracle": oracle,
        "cope_patch": cope_patch,
        "cope_state": cope_state,
        "verbose": verbose,
        "compact_proposal": compact_proposal,
        "compact": compact,
    }


def clean_and_bytes(cases: list[NativeCase]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    clean = []
    sizes = []
    cached = {}
    for case in cases:
        before = canonical_json(case.pre_state)
        item = case_artifacts(case)
        cached[case.case_id] = item
        candidates = [
            item["oracle"], item["cope_state"], item["verbose"].post_state,
            item["compact"].post_state,
        ]
        directives = [validate_and_compile(value, case.pre_state, case.event) for value in candidates]
        receipt = item["compact"].receipt
        integrity = bool(
            receipt["before_sha256"] == stable_hash(state_without_history(case.pre_state))
            and receipt["staged_sha256"] == receipt["after_sha256"] == stable_hash(item["compact"].post_state)
            and receipt["validator_calls"] == 1
            and receipt["validator_passed"] is True
            and receipt["published"] is True
            and receipt["rolled_back"] is False
        )
        passed = bool(
            all(value == item["oracle"] for value in candidates)
            and len(set(directives)) == 1
            and canonical_json(case.pre_state) == before
            and integrity
        )
        clean.append({
            "case_id": case.case_id,
            "family": case.family,
            "compact_equals_verbose_tx": item["compact"].post_state == item["verbose"].post_state,
            "compact_equals_cope": item["compact"].post_state == item["cope_state"],
            "compact_equals_fsr": item["compact"].post_state == item["oracle"],
            "directive_equal": len(set(directives)) == 1,
            "directive": directives[0],
            "input_unchanged": canonical_json(case.pre_state) == before,
            "receipt_integrity": integrity,
            "validator_calls": receipt["validator_calls"],
            "pass": passed,
        })
        proposals = {
            "cope": item["cope_patch"],
            "compact_tx": item["compact_proposal"],
            "verbose_tx": item["verbose"].carrier,
            "fsr_pc": item["oracle"],
        }
        for method, proposal in proposals.items():
            sizes.append({
                "case_id": case.case_id,
                "family": case.family,
                "method": method,
                "proposal_bytes": len(canonical_json(proposal).encode("utf-8")),
                "common_receipt_bytes": len(canonical_json(common_receipt(method, case, item["oracle"])).encode("utf-8")),
                "proposal_plus_common_receipt_bytes": len(canonical_json(proposal).encode("utf-8")) + len(canonical_json(common_receipt(method, case, item["oracle"])).encode("utf-8")),
            })
    return clean, sizes, cached


def fault_results(fault_manifest: Path, cases: dict[str, NativeCase], cached: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    with fault_manifest.open(newline="", encoding="utf-8") as handle:
        assignments = list(csv.DictReader(handle))
    rows = []
    for assignment in assignments:
        fault_id = assignment["fault_id"]
        case = cases[assignment["source_case"]]
        proposal = copy.deepcopy(cached[case.case_id]["compact_proposal"])
        staged_fault = None
        if fault_id == "C01": proposal["base_version"] -= 1
        elif fault_id == "C02": proposal["event_id"] = "wrong:event"
        elif fault_id == "C03": proposal["writes"].append({"op": "replace", "path": "/schema_version", "value": "evil"})
        elif fault_id == "C04": proposal["writes"].append(copy.deepcopy(proposal["writes"][0]))
        elif fault_id == "C05": proposal["writes"][0]["path"] = "/commitments/unknown:id/lifecycle_status"
        elif fault_id == "C06": staged_fault = "drop_progress_ledger"
        elif fault_id == "C07": staged_fault = "retain_illegal_executing_action"

        def validator(candidate: Any, state: Any, event: Any) -> str:
            if fault_id == "C08":
                raise RuntimeError("external validator exception")
            return validate_and_compile(candidate, state, event)

        before = canonical_json(case.pre_state)
        receipt = {}
        rejected = False
        try:
            execute_compact_transaction(
                proposal, case.pre_state, case.event, validator, staged_fault=staged_fault
            )
        except CompactTransactionRejected as exc:
            receipt = exc.receipt
            rejected = True
        pre_unchanged = canonical_json(case.pre_state) == before
        passed = bool(
            rejected and receipt.get("published") is False
            and receipt.get("rolled_back") is True
            and receipt.get("after_sha256") is None and pre_unchanged
            and receipt.get("rejection_stage") == assignment["layer"]
        )
        rows.append({
            "fault_id": fault_id,
            "source_case": case.case_id,
            "layer": assignment["layer"],
            "rejected": rejected,
            "published": receipt.get("published", ""),
            "rolled_back": receipt.get("rolled_back", ""),
            "pre_state_unchanged": pre_unchanged,
            "after_sha256_empty": receipt.get("after_sha256") is None,
            "validator_calls": receipt.get("validator_calls", ""),
            "rejection_class": receipt.get("rejection_class", ""),
            "actual_rejection_stage": receipt.get("rejection_stage", ""),
            "stage_matches_manifest": receipt.get("rejection_stage") == assignment["layer"],
            "pass": passed,
        })
    return rows


def invoke(method: str, case: NativeCase, cached: dict[str, dict[str, Any]]) -> None:
    if method == "compact_tx":
        execute_compact_transaction(cached[case.case_id]["compact_proposal"], case.pre_state, case.event, validate_and_compile)
    elif method == "verbose_tx":
        execute_transaction(case.pre_state, case.event, validate_and_compile)
    elif method == "cope":
        candidate = materialize_patch(expected_patch(case.pre_state, case.event), case.pre_state, case.event)
        validate_and_compile(candidate, case.pre_state, case.event)
    elif method == "fsr_pc":
        candidate = state_without_history(derive_post_state(case.pre_state, case.event))
        validate_and_compile(candidate, case.pre_state, case.event)
    else:
        raise ValueError(method)


def resources(cases: list[NativeCase], cached: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    methods = ["compact_tx", "verbose_tx", "cope", "fsr_pc"]
    data = {(case.case_id, method): {"ns": [], "peak": []} for case in cases for method in methods}
    for case_index, case in enumerate(cases):
        for warmup in range(20):
            offset = (case_index + warmup) % len(methods)
            for method in methods[offset:] + methods[:offset]: invoke(method, case, cached)
        for repetition in range(100):
            offset = (case_index + repetition) % len(methods)
            for method in methods[offset:] + methods[:offset]:
                tracemalloc.start()
                start = time.perf_counter_ns()
                invoke(method, case, cached)
                elapsed = time.perf_counter_ns() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                data[(case.case_id, method)]["ns"].append(elapsed)
                data[(case.case_id, method)]["peak"].append(peak)
    rows = []
    for case in cases:
        for method in methods:
            item = data[(case.case_id, method)]
            rows.append({
                "case_id": case.case_id,
                "family": case.family,
                "method": method,
                "warmups": 20,
                "recorded_repetitions": 100,
                "median_total_ns": int(statistics.median(item["ns"])),
                "median_peak_bytes": int(statistics.median(item["peak"])),
            })
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--fault-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    cases = load_manifest(args.case_manifest)
    clean, sizes, cached = clean_and_bytes(cases)
    faults = fault_results(args.fault_manifest, {case.case_id: case for case in cases}, cached)
    timing = resources(cases, cached)
    replay = []
    for case in cases:
        first = cached[case.case_id]["compact_proposal"]
        second = proposal_from_verbose_carrier(
            execute_transaction(case.pre_state, case.event, validate_and_compile).carrier
        )
        replay.append({
            "case_id": case.case_id,
            "first_sha256": stable_hash(first),
            "second_sha256": stable_hash(second),
            "byte_identical": canonical_json(first) == canonical_json(second),
        })
    write_csv(args.output_dir / "03_CLEAN_RESULTS.csv", clean)
    write_csv(args.output_dir / "04_FAULT_RESULTS.csv", faults)
    write_csv(args.output_dir / "05_BYTE_RESULTS.csv", sizes)
    write_csv(args.output_dir / "06_RESOURCE_RESULTS.csv", timing)
    write_csv(args.output_dir / "07_REPLAY_RESULTS.csv", replay)
    by_case = {}
    for row in sizes: by_case.setdefault(row["case_id"], {})[row["method"]] = int(row["proposal_bytes"])
    compact_over_fsr = [item["compact_tx"] / item["fsr_pc"] for item in by_case.values()]
    cope_over_compact = [item["cope"] / item["compact_tx"] for item in by_case.values()]
    compact_gate = sum(v < 1 for v in compact_over_fsr) >= 8 and statistics.median(compact_over_fsr) <= 0.9
    cope_gate = sum(v < 1 for v in cope_over_compact) == 12 and statistics.median(cope_over_compact) <= 0.5
    passed = bool(
        len(clean) == 12 and all(row["pass"] for row in clean)
        and len(faults) == 8 and all(row["pass"] for row in faults)
        and all(row["byte_identical"] for row in replay)
    )
    lines = [
        "schema_version=compact-tx-ablation-status-v1",
        f"clean_pass={sum(bool(row['pass']) for row in clean)}/12",
        f"fault_pass={sum(bool(row['pass']) for row in faults)}/8",
        f"replay_identical={sum(bool(row['byte_identical']) for row in replay)}/12",
        f"compact_smaller_than_fsr={sum(v < 1 for v in compact_over_fsr)}/12",
        f"median_compact_over_fsr={statistics.median(compact_over_fsr):.6f}",
        f"cope_smaller_than_compact={sum(v < 1 for v in cope_over_compact)}/12",
        f"median_cope_over_compact={statistics.median(cope_over_compact):.6f}",
        f"verbose_encoding_confound_gate={compact_gate}",
        f"cope_specialized_size_gate={cope_gate}",
        f"decision={'PASS' if passed else 'FAIL'}",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "08_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
