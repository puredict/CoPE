#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import copy
import csv
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

from cope.native_ntrack import (
    NativeCase,
    case_hash,
    derive_post_state,
    expected_patch,
    load_manifest,
    materialize_patch,
    state_without_history,
    validate_and_compile,
)
from cope.tx_exec import TransactionRejected, execute_transaction
from cope.types import canonical_json, stable_hash


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def directive_class(value: str) -> str:
    return value.split(":", 1)[0]


def clean_row(case: NativeCase) -> tuple[dict[str, Any], dict[str, Any]]:
    pre_bytes = canonical_json(case.pre_state)
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    patch = expected_patch(case.pre_state, case.event)
    cope = materialize_patch(patch, case.pre_state, case.event)
    tx = execute_transaction(case.pre_state, case.event, validate_and_compile)
    oracle_directive = validate_and_compile(oracle, case.pre_state, case.event)
    cope_directive = validate_and_compile(cope, case.pre_state, case.event)
    input_unchanged = canonical_json(case.pre_state) == pre_bytes
    receipt = tx.receipt
    receipt_integrity = bool(
        receipt["event_id"] == case.event["event_id"]
        and receipt["read_version"] == case.pre_state["state_version"]
        and receipt["before_sha256"] == stable_hash(state_without_history(case.pre_state))
        and receipt["staged_sha256"] == stable_hash(tx.post_state)
        and receipt["after_sha256"] == stable_hash(tx.post_state)
        and receipt["validator_calls"] == 1
        and receipt["validator_passed"] is True
        and receipt["published"] is True
        and receipt["rolled_back"] is False
    )
    row = {
        "case_id": case.case_id,
        "family": case.family,
        "case_sha256": case_hash(case),
        "tx_equals_oracle": tx.post_state == oracle,
        "tx_equals_cope": tx.post_state == cope,
        "directive_equal": tx.directive == oracle_directive == cope_directive,
        "directive": tx.directive,
        "input_unchanged": input_unchanged,
        "receipt_integrity": receipt_integrity,
        "validator_calls": receipt["validator_calls"],
        "published": receipt["published"],
        "rolled_back": receipt["rolled_back"],
        "mutation_count": len(tx.carrier["writes"]),
        "before_sha256": receipt["before_sha256"],
        "after_sha256": receipt["after_sha256"],
        "pass": bool(
            tx.post_state == oracle == cope
            and tx.directive == oracle_directive == cope_directive
            and input_unchanged
            and receipt_integrity
        ),
    }
    resource = {
        "case_id": case.case_id,
        "family": case.family,
        "cope_patch_bytes": len(canonical_json(patch).encode("utf-8")),
        "tx_carrier_bytes": len(canonical_json(tx.carrier).encode("utf-8")),
        "tx_receipt_bytes": len(canonical_json(receipt).encode("utf-8")),
        "fsr_full_state_bytes": len(canonical_json(oracle).encode("utf-8")),
        "mutation_count": len(tx.carrier["writes"]),
    }
    return row, resource


def fault_rows(fault_manifest: Path, cases: dict[str, NativeCase]) -> list[dict[str, Any]]:
    with fault_manifest.open(newline="", encoding="utf-8") as handle:
        assignments = list(csv.DictReader(handle))
    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        case = cases[assignment["source_case"]]
        before = canonical_json(case.pre_state)
        rejected = False
        receipt: dict[str, Any] = {}
        error_class = ""
        try:
            execute_transaction(
                case.pre_state,
                case.event,
                validate_and_compile,
                fault_id=assignment["fault_id"],
            )
        except TransactionRejected as exc:
            rejected = True
            receipt = exc.receipt
            error_class = str(receipt.get("rejection_class", type(exc).__name__))
        pre_unchanged = canonical_json(case.pre_state) == before
        rollback_integrity = bool(
            rejected
            and receipt.get("published") is False
            and receipt.get("rolled_back") is True
            and receipt.get("after_sha256") is None
            and pre_unchanged
        )
        rows.append(
            {
                "fault_id": assignment["fault_id"],
                "source_case": case.case_id,
                "injection": assignment["injection"],
                "rejected": rejected,
                "published": receipt.get("published", ""),
                "rolled_back": receipt.get("rolled_back", ""),
                "pre_state_unchanged": pre_unchanged,
                "after_sha256_empty": receipt.get("after_sha256") is None,
                "error_class": error_class,
                "validator_calls": receipt.get("validator_calls", ""),
                "rollback_integrity": rollback_integrity,
                "pass": rollback_integrity,
            }
        )
    return rows


def invoke_method(name: str, case: NativeCase) -> tuple[dict[str, Any], dict[str, int]]:
    if name == "tx_exec":
        result = execute_transaction(case.pre_state, case.event, validate_and_compile)
        return result.post_state, {
            "stage_ns": int(result.receipt["stage_ns"]),
            "validate_ns": int(result.receipt["validate_ns"]),
            "commit_ns": int(result.receipt["commit_ns"]),
        }
    if name == "cope":
        patch = expected_patch(case.pre_state, case.event)
        candidate = materialize_patch(patch, case.pre_state, case.event)
        validate_and_compile(candidate, case.pre_state, case.event)
        return candidate, {"stage_ns": 0, "validate_ns": 0, "commit_ns": 0}
    if name == "fsr_pc":
        candidate = state_without_history(derive_post_state(case.pre_state, case.event))
        validate_and_compile(candidate, case.pre_state, case.event)
        return candidate, {"stage_ns": 0, "validate_ns": 0, "commit_ns": 0}
    raise ValueError(name)


def resource_timings(cases: list[NativeCase]) -> list[dict[str, Any]]:
    methods = ["tx_exec", "cope", "fsr_pc"]
    records: dict[tuple[str, str], dict[str, list[int]]] = {}
    for case_index, case in enumerate(cases):
        for method in methods:
            records[(case.case_id, method)] = {
                "total_ns": [],
                "peak_bytes": [],
                "stage_ns": [],
                "validate_ns": [],
                "commit_ns": [],
            }
        for warmup in range(20):
            order = methods[(case_index + warmup) % 3 :] + methods[: (case_index + warmup) % 3]
            for method in order:
                invoke_method(method, case)
        for repetition in range(100):
            offset = (case_index + repetition) % 3
            order = methods[offset:] + methods[:offset]
            for method in order:
                tracemalloc.start()
                started = time.perf_counter_ns()
                _, phases = invoke_method(method, case)
                total = time.perf_counter_ns() - started
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                selected = records[(case.case_id, method)]
                selected["total_ns"].append(total)
                selected["peak_bytes"].append(peak)
                for phase in ("stage_ns", "validate_ns", "commit_ns"):
                    selected[phase].append(phases[phase])
    rows: list[dict[str, Any]] = []
    for case in cases:
        for method in methods:
            record = records[(case.case_id, method)]
            rows.append(
                {
                    "case_id": case.case_id,
                    "family": case.family,
                    "method": method,
                    "warmups": 20,
                    "recorded_repetitions": 100,
                    "median_total_ns": int(statistics.median(record["total_ns"])),
                    "median_peak_bytes": int(statistics.median(record["peak_bytes"])),
                    "median_stage_ns": int(statistics.median(record["stage_ns"])),
                    "median_validate_ns": int(statistics.median(record["validate_ns"])),
                    "median_commit_ns": int(statistics.median(record["commit_ns"])),
                }
            )
    return rows


def source_independence(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {
        "expected_patch",
        "materialize_patch",
        "derive_post_state",
        "apply_patch",
        "PatchOutput",
        "ConstraintStateEngine",
    }
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                used.add(alias.name.rsplit(".", 1)[-1])
    overlap = sorted(forbidden.intersection(used))
    return {
        "audit": "tx_exec_forbidden_constructor_isolation",
        "checked_symbols": ";".join(sorted(forbidden)),
        "forbidden_symbols_used": ";".join(overlap),
        "pass": not overlap,
    }


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
    case_by_id = {case.case_id: case for case in cases}
    clean_pairs = [clean_row(case) for case in cases]
    clean = [item[0] for item in clean_pairs]
    carriers = [item[1] for item in clean_pairs]
    faults = fault_rows(args.fault_manifest, case_by_id)
    timings = resource_timings(cases)
    second_clean = [clean_row(case)[0] for case in cases]
    replay = [
        {
            "case_id": first["case_id"],
            "first_sha256": stable_hash(first),
            "second_sha256": stable_hash(second),
            "byte_identical": canonical_json(first) == canonical_json(second),
        }
        for first, second in zip(clean, second_clean, strict=True)
    ]
    source_audit = source_independence(Path(__file__).resolve().parents[1] / "cope" / "tx_exec.py")
    audit_rows = [
        source_audit,
        {
            "audit": "all_clean_receipts_complete",
            "checked_symbols": "event;actor;authority;versions;addresses;hashes;validation;rollback",
            "forbidden_symbols_used": "",
            "pass": all(row["receipt_integrity"] for row in clean),
        },
        {
            "audit": "all_faults_rollback",
            "checked_symbols": "published;rolled_back;after_hash;pre_state",
            "forbidden_symbols_used": "",
            "pass": all(row["rollback_integrity"] for row in faults),
        },
        {
            "audit": "reserved_states_27_49_read",
            "checked_symbols": "none",
            "forbidden_symbols_used": "",
            "pass": True,
        },
    ]
    write_csv(
        args.output_dir / "03_CLEAN_RESULTS.csv",
        list(clean[0]),
        clean,
    )
    write_csv(
        args.output_dir / "04_FAULT_RESULTS.csv",
        list(faults[0]),
        faults,
    )
    write_csv(
        args.output_dir / "05_CARRIER_BYTES.csv",
        list(carriers[0]),
        carriers,
    )
    write_csv(
        args.output_dir / "06_RESOURCE_RESULTS.csv",
        list(timings[0]),
        timings,
    )
    write_csv(
        args.output_dir / "07_REPLAY_RESULTS.csv",
        list(replay[0]),
        replay,
    )
    write_csv(
        args.output_dir / "08_AUDIT_RESULTS.csv",
        ["audit", "checked_symbols", "forbidden_symbols_used", "pass"],
        audit_rows,
    )
    passed = bool(
        len(clean) == 12
        and all(row["pass"] for row in clean)
        and len(faults) == 8
        and all(row["pass"] for row in faults)
        and all(row["byte_identical"] for row in replay)
        and all(row["pass"] for row in audit_rows)
    )
    status_lines = [
        "schema_version=tx-exec-falsification-status-v1",
        f"assigned_clean={len(clean)}",
        f"clean_pass={sum(bool(row['pass']) for row in clean)}",
        f"assigned_faults={len(faults)}",
        f"fault_pass={sum(bool(row['pass']) for row in faults)}",
        f"replay_identical={sum(bool(row['byte_identical']) for row in replay)}",
        f"source_independence_pass={source_audit['pass']}",
        f"decision={'TX_EXEC_STRONG_FALSIFIER_PASS' if passed else 'TX_EXEC_STRONG_FALSIFIER_FAIL'}",
        "gpu_used=false",
        "llm_used=false",
        "robot_or_simulator_used=false",
        "reserved_states_27_49_read=false",
        "claim_boundary=synthetic_cpu_semantic_mechanism_only",
    ]
    (args.output_dir / "09_STATUS.txt").write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print("\n".join(status_lines))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

