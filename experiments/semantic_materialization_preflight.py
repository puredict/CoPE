#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Mapping

from cope.semantic_cancellation import (
    apply_oracle_cancellation_patch,
    build_cancellation_event,
    build_oracle_cancellation_state,
    compile_execution_directive,
    validate_oracle_cancellation_state,
)
from cope.semantic_materialization import (
    materialize_cancellation_receipt,
    materialize_replacement_receipt,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    apply_oracle_replacement_patch,
    build_oracle_full_state,
    build_replacement_event,
    compile_controller_prompt,
    validate_oracle_full_state,
)
from cope.types import canonical_json, stable_hash


EXPECTED_CASES = {
    "replace_cream_alphabet_v0",
    "replace_butter_milk_v5",
    "cancel_cream_v0",
    "cancel_butter_v3",
}


def _int(row: Mapping[str, str], field: str) -> int:
    value = int(row[field])
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def run_case(row: Mapping[str, str]) -> dict[str, Any]:
    case_id = row["case_id"]
    event_type = row["event_type"]
    previous_state_version = _int(row, "previous_state_version")
    milestone = MilestoneEvent(
        policy_step=_int(row, "policy_step"),
        done_object=row["done_object"],
        pending_object=row["pending_object"],
        stable_steps=5,
    )
    physically_true = (milestone.done_object,)
    if event_type == "replace_pending_goal":
        event = build_replacement_event(
            milestone,
            pair_key=case_id,
            previous_state_version=previous_state_version,
            replacement_object=row["replacement_object"],
        )
        native = build_oracle_full_state(
            event,
            previous_state_version=previous_state_version,
        )
        receipt = apply_oracle_replacement_patch(
            event,
            physically_true_objects=physically_true,
        )
        materialized = materialize_replacement_receipt(
            receipt,
            event,
            physically_true_objects=physically_true,
        )
        validate_oracle_full_state(
            native,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true,
        )
        validate_oracle_full_state(
            materialized,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true,
        )
        native_directive = compile_controller_prompt(native)
        materialized_directive = compile_controller_prompt(materialized)
    elif event_type == "cancel_pending_goal":
        event = build_cancellation_event(
            milestone,
            pair_key=case_id,
            previous_state_version=previous_state_version,
        )
        native = build_oracle_cancellation_state(
            event,
            previous_state_version=previous_state_version,
        )
        receipt = apply_oracle_cancellation_patch(
            event,
            physically_true_objects=physically_true,
        )
        materialized = materialize_cancellation_receipt(
            receipt,
            event,
            physically_true_objects=physically_true,
        )
        validate_oracle_cancellation_state(
            native,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true,
        )
        validate_oracle_cancellation_state(
            materialized,
            event,
            previous_state_version=previous_state_version,
            physically_true_objects=physically_true,
        )
        native_directive = compile_execution_directive(native)
        materialized_directive = compile_execution_directive(materialized)
    else:
        raise ValueError(f"unsupported event_type {event_type!r}")

    state_equal = canonical_json(native) == canonical_json(materialized)
    directive_equal = native_directive == materialized_directive
    transition = receipt["transition"]
    hash_chain_valid = (
        transition["before_hash"] == receipt["state_before"]["state_hash"]
        and transition["after_hash"] == receipt["state_after"]["state_hash"]
        and transition["audit_record"]["before_hash"] == transition["before_hash"]
        and transition["audit_record"]["after_hash"] == transition["after_hash"]
    )
    passed = bool(
        state_equal
        and directive_equal
        and hash_chain_valid
        and receipt["provider_called"] is False
        and receipt["oracle_operation_selection"] is True
    )
    return {
        "case_id": case_id,
        "event_type": event_type,
        "previous_state_version": previous_state_version,
        "native_valid": True,
        "materialized_valid": True,
        "state_equal": state_equal,
        "native_state_sha256": stable_hash(native),
        "materialized_state_sha256": stable_hash(materialized),
        "directive_equal": directive_equal,
        "compiled_directive": native_directive,
        "receipt_hash_chain_valid": hash_chain_valid,
        "provider_called": receipt["provider_called"],
        "oracle_operation_selection": receipt["oracle_operation_selection"],
        "materialization_emitted_action": False,
        "reserved_state_consumed": False,
        "passed": passed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    case_ids = [row.get("case_id", "") for row in rows]
    if len(rows) != 4 or set(case_ids) != EXPECTED_CASES or len(case_ids) != len(set(case_ids)):
        raise ValueError("preflight manifest is not the frozen four-case assignment")
    results = [run_case(row) for row in rows]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    passed = sum(bool(row["passed"]) for row in results)
    print(f"assigned={len(results)} passed={passed} reserve_consumed=0")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
