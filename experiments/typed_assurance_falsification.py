#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from cope.compact_tx import (
    CompactTransactionError,
    CompactTransactionRejected,
    execute_compact_transaction,
    parse_proposal,
    proposal_from_verbose_carrier,
)
from cope.native_ntrack import (
    NativeCase,
    NativeOutputError,
    derive_post_state,
    expected_patch,
    load_manifest,
    materialize_patch,
    parse_full_state,
    parse_patch,
    state_without_history,
    validate_and_compile,
)
from cope.tx_exec import execute_transaction
from cope.types import canonical_json, stable_hash


ARMS = ("cope", "compact_tx", "fsr_pc")
EXPECTED_EXCEPTIONS = (
    NativeOutputError,
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


def canonical_outputs(case: NativeCase) -> dict[str, Any]:
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
    return {
        "oracle": oracle,
        "cope": expected_patch(case.pre_state, case.event),
        "compact_tx": proposal_from_verbose_carrier(verbose.carrier),
        "fsr_pc": oracle,
    }


def _authorized_effect(case: NativeCase) -> dict[str, Any]:
    event = copy.deepcopy(case.event)
    event["issuer"] = "task_owner"
    event["authority"] = 100
    event["input_state_version"] = case.pre_state["state_version"]
    event.pop("duplicate_delivery", None)
    return event


def _replace_strings(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for before, after in replacements.items():
            result = result.replace(before, after)
        return result
    if isinstance(value, list):
        return [_replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_strings(item, replacements) for key, item in value.items()}
    return copy.deepcopy(value)


def mutate(fault_id: str, arm: str, case: NativeCase, canonical: Any) -> Any:
    proposal = copy.deepcopy(canonical)
    if fault_id == "F01":
        return "FREE_TEXT_COMMAND"
    if fault_id == "F02":
        proposal["schema_version"] = "unknown-schema-v999"
    elif fault_id == "F03":
        key = {"cope": "event_id", "compact_tx": "event_id", "fsr_pc": "current_goal"}[arm]
        del proposal[key]
    elif fault_id == "F04":
        proposal["unauthorized_extra_field"] = True
    elif fault_id == "F05":
        if arm == "cope":
            proposal["input_state_version"] = case.pre_state["state_version"] - 1
        elif arm == "compact_tx":
            proposal["base_version"] = case.pre_state["state_version"] - 1
        else:
            proposal["evidence_versions"]["input_state_version"] = case.pre_state["state_version"] - 1
    elif fault_id == "F06":
        if arm in {"cope", "compact_tx"}:
            proposal["event_id"] = "wrong:event-id"
        else:
            proposal["evidence_versions"]["event_id"] = "wrong:event-id"
    elif fault_id in {"F07", "F08"}:
        authorized = _authorized_effect(case)
        if arm == "cope":
            proposal = expected_patch(case.pre_state, authorized)
        elif arm == "compact_tx":
            verbose = execute_transaction(case.pre_state, authorized, validate_and_compile)
            proposal = proposal_from_verbose_carrier(verbose.carrier)
        else:
            proposal = state_without_history(derive_post_state(case.pre_state, authorized))
    elif fault_id == "F09":
        if arm == "cope":
            proposal["operations"].append({"op": "drop_progress_ledger"})
        elif arm == "compact_tx":
            proposal["writes"].append({"op": "replace", "path": "/progress_ledger", "value": []})
        else:
            proposal["progress_ledger"] = []
    elif fault_id == "F10":
        if arm == "cope":
            proposal["operations"] = [
                item for item in proposal["operations"] if item.get("op") != "cancel_executing_action"
            ]
        elif arm == "compact_tx":
            plan_write = next((item for item in proposal["writes"] if item["path"] == "/plan"), None)
            if plan_write is None:
                proposal["writes"].append({"op": "replace", "path": "/plan", "value": copy.deepcopy(case.pre_state["plan"])})
            else:
                plan_write["value"] = copy.deepcopy(case.pre_state["plan"])
        else:
            proposal["plan"] = copy.deepcopy(case.pre_state["plan"])
    elif fault_id == "F11":
        if arm == "cope":
            proposal["operations"][0]["target_id"] = "unknown:commitment"
        elif arm == "compact_tx":
            selected = next(item for item in proposal["writes"] if "/commitments/deliver:b/" in item["path"])
            selected["path"] = selected["path"].replace("deliver:b", "unknown:commitment")
        else:
            pre_b = next(item for item in case.pre_state["commitments"] if item["id"] == "deliver:b")
            proposal["commitments"] = [item for item in proposal["commitments"] if item["id"] != "deliver:b"]
            proposal["commitments"].append(copy.deepcopy(pre_b))
            unknown = copy.deepcopy(pre_b)
            unknown["id"] = "unknown:commitment"
            unknown["lifecycle_status"] = "cancelled"
            proposal["commitments"].append(unknown)
    elif fault_id == "F12":
        if arm == "cope":
            proposal["operations"].append(copy.deepcopy(proposal["operations"][0]))
        elif arm == "compact_tx":
            proposal["writes"].append(copy.deepcopy(proposal["writes"][0]))
        else:
            replacement = next(item for item in proposal["commitments"] if item["id"] == "deliver:c")
            proposal["commitments"].append(copy.deepcopy(replacement))
    elif fault_id == "F13":
        if arm == "cope":
            proposal["operations"][0]["replacement_id"] = "deliver:x"
        else:
            proposal = _replace_strings(proposal, {"package_c": "package_x", "deliver:c": "deliver:x"})
    elif fault_id == "F14":
        if arm == "cope":
            proposal["operations"] = []
        elif arm == "compact_tx":
            proposal["writes"] = []
        else:
            proposal = state_without_history(case.pre_state)
    elif fault_id == "F15":
        if arm == "cope":
            proposal["operations"].append({"op": "acknowledge_event"})
        elif arm == "compact_tx":
            selected = next(item for item in proposal["writes"] if item["path"] == "/state_version")
            selected["value"] += 1
        else:
            proposal["state_version"] += 1
    elif fault_id == "F16":
        if arm == "cope":
            proposal["operations"].append({"op": "cancel_commitment", "target_id": "deliver:a"})
        elif arm == "compact_tx":
            proposal["writes"].append({
                "op": "replace",
                "path": "/commitments/deliver:a/lifecycle_status",
                "value": "cancelled",
            })
        else:
            next(item for item in proposal["commitments"] if item["id"] == "deliver:a")["lifecycle_status"] = "cancelled"
    else:
        raise ValueError(f"unknown fault {fault_id}")
    return proposal


def parse_arm(arm: str, proposal: Any, case: NativeCase) -> Any:
    if arm == "cope":
        return parse_patch(proposal)
    if arm == "compact_tx":
        return parse_proposal(proposal, case.pre_state, case.event)
    return parse_full_state(proposal)


def materialize_arm(arm: str, parsed: Any, case: NativeCase) -> tuple[dict[str, Any], int]:
    if arm == "cope":
        return materialize_patch(parsed, case.pre_state, case.event), 0
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
    semantic_intent: str,
) -> dict[str, Any]:
    oracle = state_without_history(derive_post_state(case.pre_state, case.event))
    caller_before = canonical_json(case.pre_state)
    proposal_changed = canonical_json(proposal) != canonical_json(canonical)
    parser_accepted = False
    materializer_accepted = False
    matched_guard_rejected = False
    candidate: dict[str, Any] | None = None
    representation_callbacks = 0
    common_calls = 0
    common_accepted = False
    first_layer = ""
    exception_class = ""
    exception_message = ""
    uncaught_crash = False
    parsed = None
    try:
        try:
            parsed = parse_arm(arm, proposal, case)
            parser_accepted = True
        except EXPECTED_EXCEPTIONS as exc:
            first_layer = "schema_parser"
            exception_class = type(exc).__name__
            exception_message = str(exc)
        if parser_accepted:
            matched_guard_rejected = canonical_json(parsed) != canonical_json(canonical)
            try:
                candidate, representation_callbacks = materialize_arm(arm, parsed, case)
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
    except Exception as exc:  # unexpected harness or implementation crash is data
        uncaught_crash = True
        first_layer = "uncaught_crash"
        exception_class = type(exc).__name__
        exception_message = str(exc)

    candidate_differs = candidate is not None and canonical_json(candidate) != canonical_json(oracle)
    representation_fail_open = bool(materializer_accepted and candidate_differs)
    end_to_end_fail_open = bool(common_accepted and candidate_differs)
    full_pipeline_rejected = not common_accepted
    caller_unchanged = canonical_json(case.pre_state) == caller_before
    parser_or_matched_guard_rejects = bool(not parser_accepted or matched_guard_rejected)
    is_clean = fault_id == "CLEAN"
    passed = bool(
        (common_accepted and not candidate_differs and proposal_changed is False)
        if is_clean
        else (
            proposal_changed
            and full_pipeline_rejected
            and parser_or_matched_guard_rejects
            and not uncaught_crash
        )
    ) and caller_unchanged
    return {
        "fault_id": fault_id,
        "case_id": case.case_id,
        "family": case.family,
        "arm": arm,
        "mutation_class": mutation_class,
        "semantic_intent": semantic_intent,
        "proposal_sha256": stable_hash(proposal),
        "canonical_proposal_sha256": stable_hash(canonical),
        "proposal_changed": proposal_changed,
        "parser_accepted": parser_accepted,
        "native_materializer_accepted": materializer_accepted,
        "native_representation_callback_calls": representation_callbacks,
        "candidate_differs_oracle": candidate_differs if candidate is not None else "",
        "representation_fail_open": representation_fail_open,
        "common_validator_calls": common_calls,
        "common_validator_accepted": common_accepted,
        "full_pipeline_rejected": full_pipeline_rejected,
        "end_to_end_fail_open": end_to_end_fail_open,
        "matched_canonical_guard_rejected": matched_guard_rejected,
        "parser_or_matched_guard_rejects": parser_or_matched_guard_rejects,
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
    if len(rows) != 16 or len({row["fault_id"] for row in rows}) != 16:
        raise ValueError("fault manifest must contain exactly 16 unique faults")
    return rows


def run_experiment(case_manifest: Path, fault_manifest: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = load_manifest(case_manifest)
    by_id = {case.case_id: case for case in cases}
    canonical = {case.case_id: canonical_outputs(case) for case in cases}
    clean_rows = []
    for case in cases:
        for arm in ARMS:
            clean_rows.append(
                evaluate_cell(
                    case,
                    arm,
                    copy.deepcopy(canonical[case.case_id][arm]),
                    canonical[case.case_id][arm],
                    fault_id="CLEAN",
                    mutation_class="control",
                    semantic_intent="canonical output",
                )
            )
    fault_rows = []
    for assignment in load_faults(fault_manifest):
        case = by_id[assignment["source_case"]]
        for arm in ARMS:
            clean_proposal = canonical[case.case_id][arm]
            proposal = mutate(assignment["fault_id"], arm, case, clean_proposal)
            fault_rows.append(
                evaluate_cell(
                    case,
                    arm,
                    proposal,
                    clean_proposal,
                    fault_id=assignment["fault_id"],
                    mutation_class=assignment["mutation_class"],
                    semantic_intent=assignment["semantic_intent"],
                )
            )
    return clean_rows, fault_rows


def aggregate_rows(fault_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for arm in ARMS:
        selected = [row for row in fault_rows if row["arm"] == arm]
        layers = Counter(row["first_rejection_layer"] for row in selected)
        result.append({
            "arm": arm,
            "fault_cells": len(selected),
            "parser_rejected": layers["schema_parser"],
            "native_representation_guard_rejected": layers["native_representation_guard"],
            "common_validator_rejected": layers["common_validator"],
            "accepted": layers["accepted"],
            "representation_fail_open": sum(bool(row["representation_fail_open"]) for row in selected),
            "end_to_end_fail_open": sum(bool(row["end_to_end_fail_open"]) for row in selected),
            "parser_or_matched_guard_rejects": sum(bool(row["parser_or_matched_guard_rejects"]) for row in selected),
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
    clean_rows, fault_rows = run_experiment(args.case_manifest, args.fault_manifest)
    aggregate = aggregate_rows(fault_rows)
    write_csv(args.output_dir / "02_CLEAN_CONTROLS.csv", clean_rows)
    write_csv(args.output_dir / "03_FAULT_RESULTS.csv", fault_rows)
    write_csv(args.output_dir / "04_AGGREGATE.csv", aggregate)
    clean_pass = sum(bool(row["pass"]) for row in clean_rows)
    fault_pass = sum(bool(row["pass"]) for row in fault_rows)
    end_fail_open = sum(bool(row["end_to_end_fail_open"]) for row in fault_rows)
    crashes = sum(bool(row["uncaught_crash"]) for row in fault_rows)
    mutations = sum(bool(row["proposal_changed"]) for row in fault_rows)
    caller_mutations = sum(not bool(row["caller_state_unchanged"]) for row in fault_rows)
    rep_by_arm = {
        row["arm"]: int(row["representation_fail_open"])
        for row in aggregate
    }
    typed_gate = rep_by_arm["cope"] < rep_by_arm["compact_tx"] and rep_by_arm["cope"] < rep_by_arm["fsr_pc"]
    matched_equalizes = all(int(row["parser_or_matched_guard_rejects"]) == 16 for row in aggregate)
    typing_specificity_gate = typed_gate and not matched_equalizes
    decision = bool(
        clean_pass == 36
        and fault_pass == 48
        and mutations == 48
        and end_fail_open == 0
        and crashes == 0
        and caller_mutations == 0
    )
    lines = [
        "schema_version=typed-assurance-falsification-status-v1",
        f"clean_pass={clean_pass}/36",
        f"fault_pass={fault_pass}/48",
        f"mutated_noncanonical={mutations}/48",
        f"representation_fail_open_cope={rep_by_arm['cope']}/16",
        f"representation_fail_open_compact_tx={rep_by_arm['compact_tx']}/16",
        f"representation_fail_open_fsr_pc={rep_by_arm['fsr_pc']}/16",
        f"end_to_end_fail_open={end_fail_open}/48",
        f"uncaught_crash={crashes}/48",
        f"caller_state_mutation={caller_mutations}/48",
        f"native_typed_assurance_gate={typed_gate}",
        f"matched_canonical_guard_equalizes={matched_equalizes}",
        f"typing_specificity_gate={typing_specificity_gate}",
        f"decision={'PASS' if decision else 'FAIL'}",
        "evidence_class=offline_deterministic_fault_injection",
        "learned_provider_calls=0",
        "gpu_llm_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "05_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if decision else 2


if __name__ == "__main__":
    raise SystemExit(main())
