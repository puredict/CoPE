#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import inspect
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import cope.generic_typed_interpreter as generic_module
from cope.compact_tx import (
    CompactTransactionError,
    CompactTransactionRejected,
    execute_compact_transaction,
    parse_proposal,
)
from cope.generic_typed_interpreter import (
    GenericTypedInterpreterError,
    apply_generic_typed_patch,
)
from cope.native_ntrack import (
    NativeCase,
    NativeOutputError,
    derive_post_state,
    load_manifest,
    materialize_patch,
    parse_full_state,
    parse_patch,
    state_without_history,
    validate_and_compile,
)
from cope.types import canonical_json, stable_hash
from experiments.typed_assurance_falsification import canonical_outputs, mutate


ARMS = ("cope_exact", "cope_generic", "compact_tx", "fsr_pc")
EXPECTED_EXCEPTIONS = (
    NativeOutputError,
    GenericTypedInterpreterError,
    CompactTransactionError,
    CompactTransactionRejected,
    KeyError,
    TypeError,
    ValueError,
)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def arm_key(arm: str) -> str:
    return "cope" if arm.startswith("cope_") else arm


def mutate_four_arm(fault_id: str, arm: str, case: NativeCase, canonical: Any) -> Any:
    if fault_id.startswith("F"):
        return mutate(fault_id, arm_key(arm), case, canonical)
    proposal = copy.deepcopy(canonical)
    if fault_id not in {"O01", "O02", "O03", "O04", "O05", "O06"}:
        raise ValueError(f"unknown omission fault {fault_id}")
    if arm.startswith("cope_"):
        proposal["operations"] = []
    elif arm == "compact_tx":
        proposal["writes"] = []
    else:
        proposal = state_without_history(case.pre_state)
    return proposal


def parse_arm(arm: str, proposal: Any, case: NativeCase) -> Any:
    if arm.startswith("cope_"):
        return parse_patch(proposal)
    if arm == "compact_tx":
        return parse_proposal(proposal, case.pre_state, case.event)
    return parse_full_state(proposal)


def materialize_arm(arm: str, parsed: Any, case: NativeCase) -> tuple[dict[str, Any], int]:
    if arm == "cope_exact":
        return materialize_patch(parsed, case.pre_state, case.event), 0
    if arm == "cope_generic":
        return apply_generic_typed_patch(parsed, case.pre_state, case.event), 0
    if arm == "compact_tx":
        calls = 0

        def accept_only(candidate: Mapping[str, Any], state: Mapping[str, Any], event: Mapping[str, Any]) -> str:
            nonlocal calls
            calls += 1
            return "TEST_ONLY_ACCEPT"

        result = execute_compact_transaction(parsed, case.pre_state, case.event, accept_only)
        return result.post_state, calls
    return copy.deepcopy(parsed), 0


def evaluate_cell(
    case: NativeCase,
    arm: str,
    proposal: Any,
    canonical: Any,
    *,
    fault_id: str,
    mutation_class: str,
    threat_axis: str,
    semantic_intent: str,
) -> dict[str, Any]:
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    caller_before = canonical_json(case.pre_state)
    proposal_changed = canonical_json(proposal) != canonical_json(canonical)
    parser_accepted = False
    materializer_accepted = False
    candidate: dict[str, Any] | None = None
    native_callbacks = 0
    common_calls = 0
    common_accepted = False
    first_layer = ""
    exception_class = ""
    exception_message = ""
    uncaught_crash = False
    try:
        try:
            parsed = parse_arm(arm, proposal, case)
            parser_accepted = True
        except EXPECTED_EXCEPTIONS as exc:
            first_layer = "schema_parser"
            exception_class = type(exc).__name__
            exception_message = str(exc)
        if parser_accepted:
            try:
                candidate, native_callbacks = materialize_arm(arm, parsed, case)
                materializer_accepted = True
            except EXPECTED_EXCEPTIONS as exc:
                first_layer = "native_representation_guard"
                exception_class = type(exc).__name__
                exception_message = str(exc)
            if materializer_accepted:
                common_calls += 1
                try:
                    validate_and_compile(candidate, case.pre_state, case.event)
                    common_accepted = True
                    first_layer = "accepted"
                except EXPECTED_EXCEPTIONS as exc:
                    first_layer = "common_validator"
                    exception_class = type(exc).__name__
                    exception_message = str(exc)
    except Exception as exc:
        uncaught_crash = True
        first_layer = "uncaught_crash"
        exception_class = type(exc).__name__
        exception_message = str(exc)

    candidate_differs = candidate is not None and canonical_json(candidate) != canonical_json(oracle)
    representation_fail_open = bool(materializer_accepted and candidate_differs)
    end_to_end_fail_open = bool(common_accepted and candidate_differs)
    caller_unchanged = canonical_json(case.pre_state) == caller_before
    is_clean = fault_id == "CLEAN"
    passed = bool(
        common_accepted and not candidate_differs and not proposal_changed
        if is_clean
        else proposal_changed and not common_accepted and not end_to_end_fail_open and not uncaught_crash
    ) and caller_unchanged
    return {
        "fault_id": fault_id,
        "case_id": case.case_id,
        "family": case.family,
        "arm": arm,
        "mutation_class": mutation_class,
        "threat_axis": threat_axis,
        "semantic_intent": semantic_intent,
        "proposal_sha256": stable_hash(proposal),
        "canonical_proposal_sha256": stable_hash(canonical),
        "proposal_changed": proposal_changed,
        "parser_accepted": parser_accepted,
        "native_materializer_accepted": materializer_accepted,
        "native_representation_callback_calls": native_callbacks,
        "candidate_differs_oracle": candidate_differs if candidate is not None else "",
        "representation_fail_open": representation_fail_open,
        "common_validator_calls": common_calls,
        "common_validator_accepted": common_accepted,
        "full_pipeline_rejected": not common_accepted,
        "end_to_end_fail_open": end_to_end_fail_open,
        "first_rejection_layer": first_layer,
        "exception_class": exception_class,
        "exception_message": exception_message,
        "caller_state_unchanged": caller_unchanged,
        "uncaught_crash": uncaught_crash,
        "pass": passed,
    }


def load_faults(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 22 or len({row["fault_id"] for row in rows}) != 22:
        raise ValueError("fault manifest must contain exactly 22 unique assignments")
    return rows


def source_audit() -> dict[str, Any]:
    source = inspect.getsource(generic_module)
    forbidden = ("expected" + "_patch", "derive" + "_post_state", "validate" + "_and_compile")
    hits = [name for name in forbidden if name in source]
    return {
        "module": "cope.generic_typed_interpreter",
        "source_sha256": stable_hash(source),
        "forbidden_symbols": ";".join(forbidden),
        "forbidden_hits": ";".join(hits),
        "pass": not hits,
    }


def run_experiment(case_manifest: Path, fault_manifest: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = load_manifest(case_manifest)
    by_id = {case.case_id: case for case in cases}
    canonical = {case.case_id: canonical_outputs(case) for case in cases}
    clean_rows = []
    for case in cases:
        for arm in ARMS:
            proposal = canonical[case.case_id][arm_key(arm)]
            clean_rows.append(evaluate_cell(
                case, arm, copy.deepcopy(proposal), proposal,
                fault_id="CLEAN", mutation_class="control", threat_axis="control",
                semantic_intent="canonical output",
            ))
    fault_rows = []
    for assignment in load_faults(fault_manifest):
        case = by_id[assignment["source_case"]]
        for arm in ARMS:
            clean_proposal = canonical[case.case_id][arm_key(arm)]
            proposal = mutate_four_arm(assignment["fault_id"], arm, case, clean_proposal)
            fault_rows.append(evaluate_cell(
                case, arm, proposal, clean_proposal,
                fault_id=assignment["fault_id"],
                mutation_class=assignment["mutation_class"],
                threat_axis=assignment["threat_axis"],
                semantic_intent=assignment["semantic_intent"],
            ))
    return clean_rows, fault_rows


def aggregate_rows(fault_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for axis in ("all", "commission_or_structure", "omission"):
        for arm in ARMS:
            selected = [
                row for row in fault_rows
                if row["arm"] == arm and (axis == "all" or row["threat_axis"] == axis)
            ]
            layers = Counter(row["first_rejection_layer"] for row in selected)
            result.append({
                "threat_axis": axis,
                "arm": arm,
                "fault_cells": len(selected),
                "parser_rejected": layers["schema_parser"],
                "native_representation_guard_rejected": layers["native_representation_guard"],
                "common_validator_rejected": layers["common_validator"],
                "accepted": layers["accepted"],
                "representation_fail_open": sum(bool(row["representation_fail_open"]) for row in selected),
                "end_to_end_fail_open": sum(bool(row["end_to_end_fail_open"]) for row in selected),
                "caller_state_mutated": sum(not bool(row["caller_state_unchanged"]) for row in selected),
                "uncaught_crash": sum(bool(row["uncaught_crash"]) for row in selected),
                "passed": sum(bool(row["pass"]) for row in selected),
            })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--fault-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    audit = source_audit()
    clean, faults = run_experiment(args.case_manifest, args.fault_manifest)
    aggregate = aggregate_rows(faults)
    write_csv(args.output_dir / "02_SOURCE_AUDIT.csv", [audit])
    write_csv(args.output_dir / "03_CLEAN_CONTROLS.csv", clean)
    write_csv(args.output_dir / "04_FAULT_RESULTS.csv", faults)
    write_csv(args.output_dir / "05_AGGREGATE.csv", aggregate)

    def count(axis: str, arm: str, field: str) -> int:
        row = next(item for item in aggregate if item["threat_axis"] == axis and item["arm"] == arm)
        return int(row[field])

    clean_pass = sum(bool(row["pass"]) for row in clean)
    fault_pass = sum(bool(row["pass"]) for row in faults)
    changed = sum(bool(row["proposal_changed"]) for row in faults)
    end_fail_open = sum(bool(row["end_to_end_fail_open"]) for row in faults)
    crashes = sum(bool(row["uncaught_crash"]) for row in faults)
    caller_mutations = sum(not bool(row["caller_state_unchanged"]) for row in faults)
    generic_all = count("all", "cope_generic", "representation_fail_open")
    local_gate = bool(
        count("commission_or_structure", "cope_generic", "representation_fail_open")
        < count("commission_or_structure", "compact_tx", "representation_fail_open")
        and count("commission_or_structure", "cope_generic", "representation_fail_open")
        < count("commission_or_structure", "fsr_pc", "representation_fail_open")
    )
    omission_boundary = generic_all > 0 and count("omission", "cope_generic", "representation_fail_open") > 0
    decision = bool(
        audit["pass"] and clean_pass == 48 and fault_pass == 88 and changed == 88
        and end_fail_open == 0 and crashes == 0 and caller_mutations == 0
        and generic_all > 0
    )
    lines = [
        "schema_version=generic-typed-interpreter-status-v1",
        f"source_audit_pass={audit['pass']}",
        f"clean_pass={clean_pass}/48",
        f"fault_pass={fault_pass}/88",
        f"mutated_noncanonical={changed}/88",
    ]
    for arm in ARMS:
        lines.append(f"representation_fail_open_all_{arm}={count('all', arm, 'representation_fail_open')}/22")
    for arm in ARMS:
        lines.append(f"representation_fail_open_commission_{arm}={count('commission_or_structure', arm, 'representation_fail_open')}/14")
    for arm in ARMS:
        lines.append(f"representation_fail_open_omission_{arm}={count('omission', arm, 'representation_fail_open')}/8")
    lines.extend([
        f"end_to_end_fail_open={end_fail_open}/88",
        f"uncaught_crash={crashes}/88",
        f"caller_state_mutation={caller_mutations}/88",
        f"oracle_removal_gate={generic_all > 0}",
        f"local_typed_assurance_gate={local_gate}",
        f"omission_boundary_triggered={omission_boundary}",
        f"decision={'PASS' if decision else 'FAIL'}",
        "evidence_class=offline_deterministic_fault_injection",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ])
    (args.output_dir / "06_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
