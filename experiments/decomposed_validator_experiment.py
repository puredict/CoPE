#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import inspect
from pathlib import Path
from typing import Any

import cope.decomposed_validator as validator_module
from cope.compact_tx import CompactTransactionError, CompactTransactionRejected
from cope.decomposed_validator import PREDICATE_GROUPS, decomposed_violations
from cope.generic_typed_interpreter import GenericTypedInterpreterError
from cope.native_ntrack import (
    NativeOutputError,
    derive_post_state,
    load_manifest,
    state_without_history,
    validate_and_compile,
)
from cope.types import canonical_json, stable_hash
from experiments.generic_typed_interpreter_experiment import (
    ARMS,
    arm_key,
    load_faults,
    materialize_arm,
    mutate_four_arm,
    parse_arm,
)
from experiments.typed_assurance_falsification import canonical_outputs


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


def source_audit() -> dict[str, Any]:
    source = inspect.getsource(validator_module)
    forbidden = ("expected" + "_patch", "derive" + "_post_state", "validate" + "_and_compile")
    hits = [name for name in forbidden if name in source]
    whole_state_patterns = ("canonical_json(candidate)", "stable_hash(candidate)")
    pattern_hits = [pattern for pattern in whole_state_patterns if pattern in source]
    return {
        "module": "cope.decomposed_validator",
        "source_sha256": stable_hash(source),
        "forbidden_symbols": ";".join(forbidden),
        "forbidden_hits": ";".join(hits),
        "whole_state_compare_patterns": ";".join(whole_state_patterns),
        "whole_state_compare_hits": ";".join(pattern_hits),
        "pass": not hits and not pattern_hits,
    }


def evaluate_proposal(
    case,
    arm: str,
    proposal: Any,
    canonical: Any,
    *,
    sample_type: str,
    fault_id: str,
    threat_axis: str,
    semantic_intent: str,
) -> dict[str, Any]:
    caller_before = canonical_json(case.pre_state)
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    proposal_changed = canonical_json(proposal) != canonical_json(canonical)
    native_rejected = False
    candidate = None
    native_exception = ""
    uncaught_crash = False
    try:
        try:
            parsed = parse_arm(arm, proposal, case)
            candidate, _ = materialize_arm(arm, parsed, case)
        except EXPECTED_EXCEPTIONS as exc:
            native_rejected = True
            native_exception = f"{type(exc).__name__}:{exc}"
    except Exception as exc:
        uncaught_crash = True
        native_exception = f"{type(exc).__name__}:{exc}"

    candidate_materialized = candidate is not None
    candidate_incorrect = bool(candidate_materialized and canonical_json(candidate) != canonical_json(oracle))
    exact_called = False
    exact_accepted = False
    exact_exception = ""
    decomp_called = False
    decomp_accepted = False
    violation_map: dict[str, list[str]] = {group: [] for group in PREDICATE_GROUPS}
    if candidate_materialized:
        exact_called = True
        try:
            validate_and_compile(candidate, case.pre_state, case.event)
            exact_accepted = True
        except EXPECTED_EXCEPTIONS as exc:
            exact_exception = f"{type(exc).__name__}:{exc}"
        decomp_called = True
        violation_map = decomposed_violations(candidate, case.pre_state, case.event)
        decomp_accepted = not any(violation_map.values())
    violated_groups = [group for group in PREDICATE_GROUPS if violation_map[group]]
    violation_codes = [f"{group}:{code}" for group in violated_groups for code in violation_map[group]]
    parity = bool(exact_called == decomp_called and exact_accepted == decomp_accepted)
    full_decomp_rejected = bool(native_rejected or (decomp_called and not decomp_accepted))
    caller_unchanged = canonical_json(case.pre_state) == caller_before
    is_clean = sample_type == "clean"
    passed = bool(
        candidate_materialized and not candidate_incorrect and exact_accepted and decomp_accepted and parity
        if is_clean
        else proposal_changed and full_decomp_rejected and parity and not uncaught_crash
    ) and caller_unchanged
    return {
        "sample_type": sample_type,
        "fault_id": fault_id,
        "case_id": case.case_id,
        "arm": arm,
        "threat_axis": threat_axis,
        "semantic_intent": semantic_intent,
        "proposal_changed": proposal_changed,
        "native_rejected": native_rejected,
        "native_exception": native_exception,
        "candidate_materialized": candidate_materialized,
        "candidate_incorrect": candidate_incorrect if candidate_materialized else "",
        "exact_validator_called": exact_called,
        "exact_validator_accepted": exact_accepted,
        "exact_exception": exact_exception,
        "decomposed_validator_called": decomp_called,
        "decomposed_validator_accepted": decomp_accepted,
        "violated_group_count": len(violated_groups),
        "violated_groups": ";".join(violated_groups),
        "violation_codes": ";".join(violation_codes),
        "exact_decomposed_parity": parity,
        "full_decomposed_pipeline_rejected": full_decomp_rejected,
        "caller_state_unchanged": caller_unchanged,
        "uncaught_crash": uncaught_crash,
        "pass": passed,
    }


def run_experiment(case_manifest: Path, fault_manifest: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = load_manifest(case_manifest)
    by_id = {case.case_id: case for case in cases}
    canonical = {case.case_id: canonical_outputs(case) for case in cases}
    clean = []
    for case in cases:
        for arm in ARMS:
            proposal = canonical[case.case_id][arm_key(arm)]
            clean.append(evaluate_proposal(
                case, arm, copy.deepcopy(proposal), proposal,
                sample_type="clean", fault_id="CLEAN", threat_axis="control",
                semantic_intent="canonical output",
            ))
    faults = []
    for assignment in load_faults(fault_manifest):
        case = by_id[assignment["source_case"]]
        for arm in ARMS:
            clean_proposal = canonical[case.case_id][arm_key(arm)]
            proposal = mutate_four_arm(assignment["fault_id"], arm, case, clean_proposal)
            faults.append(evaluate_proposal(
                case, arm, proposal, clean_proposal,
                sample_type="fault", fault_id=assignment["fault_id"],
                threat_axis=assignment["threat_axis"], semantic_intent=assignment["semantic_intent"],
            ))
    return clean, faults


def predicate_coverage(clean: list[dict[str, Any]], faults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    materialized_faults = [row for row in faults if row["candidate_materialized"]]
    rows = []
    for group in PREDICATE_GROUPS:
        violated = [row for row in materialized_faults if group in row["violated_groups"].split(";")]
        unique = [row for row in materialized_faults if row["violated_groups"] == group]
        clean_fp = [row for row in clean if group in row["violated_groups"].split(";")]
        rows.append({
            "predicate_group": group,
            "materialized_fault_candidates": len(materialized_faults),
            "fault_candidates_violating_group": len(violated),
            "unique_catch_count": len(unique),
            "ablation_fail_open_count": len(unique),
            "clean_false_positive_count": len(clean_fp),
            "unique_catch_cells": ";".join(f"{row['fault_id']}:{row['arm']}" for row in unique),
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
    audit = source_audit()
    clean, faults = run_experiment(args.case_manifest, args.fault_manifest)
    coverage = predicate_coverage(clean, faults)
    write_csv(args.output_dir / "02_SOURCE_AUDIT.csv", [audit])
    write_csv(args.output_dir / "03_CLEAN_RESULTS.csv", clean)
    write_csv(args.output_dir / "04_FAULT_RESULTS.csv", faults)
    write_csv(args.output_dir / "05_PREDICATE_COVERAGE_ABLATION.csv", coverage)
    clean_pass = sum(bool(row["pass"]) for row in clean)
    materialized = sum(bool(row["candidate_materialized"]) for row in faults)
    native_rejected = sum(bool(row["native_rejected"]) for row in faults)
    incorrect_materialized = sum(bool(row["candidate_incorrect"]) for row in faults if row["candidate_materialized"])
    exact_rejected = sum(bool(row["exact_validator_called"]) and not bool(row["exact_validator_accepted"]) for row in faults)
    decomp_rejected = sum(bool(row["decomposed_validator_called"]) and not bool(row["decomposed_validator_accepted"]) for row in faults)
    parity = sum(bool(row["exact_decomposed_parity"]) for row in clean + faults)
    full_rejected = sum(bool(row["full_decomposed_pipeline_rejected"]) for row in faults)
    crashes = sum(bool(row["uncaught_crash"]) for row in clean + faults)
    caller_mutations = sum(not bool(row["caller_state_unchanged"]) for row in clean + faults)
    decision = bool(
        audit["pass"] and clean_pass == 48 and materialized == 39 and native_rejected == 49
        and incorrect_materialized == 39 and exact_rejected == 39 and decomp_rejected == 39
        and parity == 136 and full_rejected == 88 and crashes == 0 and caller_mutations == 0
    )
    lines = [
        "schema_version=decomposed-validator-status-v1",
        f"source_audit_pass={audit['pass']}",
        f"clean_pass={clean_pass}/48",
        f"fault_native_rejected={native_rejected}/88",
        f"fault_candidates_materialized={materialized}/88",
        f"materialized_fault_candidates_incorrect={incorrect_materialized}/39",
        f"exact_validator_rejected={exact_rejected}/39",
        f"decomposed_validator_rejected={decomp_rejected}/39",
        f"exact_decomposed_parity={parity}/136",
        f"full_decomposed_pipeline_rejected={full_rejected}/88",
        f"uncaught_crash={crashes}/136",
        f"caller_state_mutation={caller_mutations}/136",
        f"clean_specificity_gate={clean_pass == 48}",
        f"frozen_suite_sufficiency_gate={decomp_rejected == 39}",
        f"decision={'PASS' if decision else 'FAIL'}",
        "evidence_class=offline_deterministic_candidate_replay",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "06_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
