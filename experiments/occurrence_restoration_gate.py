#!/usr/bin/env python3
"""Provider-free five-arm gate for occurrence-addressed recurring goals."""

from __future__ import annotations

import argparse
import copy
import csv
from pathlib import Path
from typing import Any, Mapping

from cope.occurrence_sequence import (
    build_event,
    build_initial_state,
    cope_oracle,
    expected_next_state,
    fsr_oracle,
    full_replan_oracle,
    governed_oracle,
    initialize_typed,
    materialize_cope,
    materialize_fsr,
    materialize_full_replan,
    materialize_governed,
    materialize_neutral,
    neutral_oracle,
    occurrence_id,
    validate_event,
)
from cope.types import canonical_json, stable_hash


ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan")
DONE = "alphabet_soup_1"
ORIGINAL = "cream_cheese_1"
INTERMEDIATE = "tomato_sauce_1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def proposal_for(
    arm: str, pre: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    if arm == "cope":
        return cope_oracle(event)
    if arm == "neutral_patch":
        return neutral_oracle(pre, expected, event)
    if arm == "governed_delta":
        return governed_oracle(pre, expected, event)
    if arm == "fsr_pc":
        return fsr_oracle(expected)
    if arm == "full_replan":
        return full_replan_oracle(expected, event)
    raise ValueError(arm)


def materialize(
    arm: str, proposal: Mapping[str, Any], typed: Any,
    pre: Mapping[str, Any], event: Mapping[str, Any],
) -> tuple[dict[str, Any], Any, str]:
    if arm == "cope":
        typed, candidate, _, directive = materialize_cope(
            proposal, typed, pre, event, (DONE,)
        )
    elif arm == "neutral_patch":
        candidate, _, directive = materialize_neutral(proposal, pre, event, (DONE,))
    elif arm == "governed_delta":
        candidate, _, directive = materialize_governed(proposal, pre, event, (DONE,))
    elif arm == "fsr_pc":
        candidate, directive = materialize_fsr(proposal, pre, event, (DONE,))
    else:
        candidate, directive = materialize_full_replan(proposal, pre, event, (DONE,))
    return candidate, typed, directive


def initial(sequence_id: str) -> dict[str, Any]:
    return build_initial_state(
        sequence_id=sequence_id, done_object=DONE, pending_object=ORIGINAL,
        available_objects=(DONE, ORIGINAL, INTERMEDIATE), world_version=100,
    )


def events(sequence_id: str, state: Mapping[str, Any], sequence_type: str):
    event1 = build_event(
        state, sequence_id=sequence_id, step_index=1, done_object=DONE,
        event_type="replace_pending_goal", replacement_object=INTERMEDIATE,
        replacement_occurrence=1, world_version=101,
    )
    middle = expected_next_state(state, event1)
    if sequence_type == "replace_then_restore":
        event2 = build_event(
            middle, sequence_id=sequence_id, step_index=2, done_object=DONE,
            event_type="replace_pending_goal", replacement_object=ORIGINAL,
            replacement_occurrence=2, world_version=102,
        )
    else:
        event2 = build_event(
            middle, sequence_id=sequence_id, step_index=2, done_object=DONE,
            event_type="cancel_pending_goal", replacement_object=None,
            replacement_occurrence=None, world_version=102,
        )
    return event1, event2


def main() -> int:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    rows: list[dict[str, Any]] = []
    for sequence_type in ("replace_then_cancel", "replace_then_restore"):
        sequence_id = f"occurrence-task7-{sequence_type}"
        for arm in ARMS:
            logical = initial(sequence_id)
            typed = initialize_typed(
                sequence_id=sequence_id, done_object=DONE, pending_object=ORIGINAL
            ) if arm == "cope" else None
            event1, event2 = events(sequence_id, logical, sequence_type)
            for event_index, event in ((1, event1), (2, event2)):
                expected = expected_next_state(logical, event)
                proposal = proposal_for(arm, logical, expected, event)
                candidate, typed, directive = materialize(
                    arm, proposal, typed, logical, event
                )
                records = {row["id"]: row for row in candidate["commitments"]}
                rows.append({
                    "sequence_type": sequence_type, "arm": arm,
                    "event_index": event_index, "provider_calls": 0,
                    "simulator_states_indexed": 0,
                    "candidate_equals_expected": canonical_json(candidate) == canonical_json(expected),
                    "candidate_sha256": stable_hash(candidate),
                    "directive": directive,
                    "proposal_bytes": len(canonical_json(proposal).encode("utf-8")),
                    "original_occurrence_1_status": records[occurrence_id(ORIGINAL, 1)]["lifecycle_status"],
                    "intermediate_occurrence_1_status": records.get(occurrence_id(INTERMEDIATE, 1), {}).get("lifecycle_status", "absent"),
                    "original_occurrence_2_status": records.get(occurrence_id(ORIGINAL, 2), {}).get("lifecycle_status", "absent"),
                })
                logical = candidate

    negative: list[dict[str, Any]] = []
    state = initial("negative")
    event1, event2 = events("negative", state, "replace_then_restore")
    middle = expected_next_state(state, event1)

    def reject(case: str, operation) -> None:
        try:
            operation()
        except Exception as exc:
            negative.append({"case": case, "rejected": True, "error_class": type(exc).__name__})
        else:
            negative.append({"case": case, "rejected": False, "error_class": ""})

    stale = copy.deepcopy(event2); stale["valid_from_state_version"] = 1
    reject("stale_revision", lambda: validate_event(middle, stale))
    wrong_target = copy.deepcopy(event2); wrong_target["target_commitment_id"] = occurrence_id(ORIGINAL, 1)
    reject("wrong_target_occurrence", lambda: validate_event(middle, wrong_target))
    reactivation = build_event(
        middle, sequence_id="negative-reactivate", step_index=2, done_object=DONE,
        event_type="replace_pending_goal", replacement_object=ORIGINAL,
        replacement_occurrence=1, world_version=102,
    )
    reject("reactivate_historical_occurrence", lambda: validate_event(middle, reactivation))
    duplicate_middle = copy.deepcopy(middle)
    duplicate_record = copy.deepcopy(next(row for row in middle["commitments"] if row["id"] == occurrence_id(ORIGINAL, 1)))
    duplicate_record["id"] = occurrence_id(ORIGINAL, 2); duplicate_record["occurrence"] = 2
    duplicate_middle["commitments"].append(duplicate_record)
    reject("duplicate_new_occurrence", lambda: validate_event(duplicate_middle, event2))
    expected2 = expected_next_state(middle, event2)
    omitted = fsr_oracle(expected2)
    omitted["commitments"] = [
        row for row in omitted["commitments"] if row["id"] != occurrence_id(ORIGINAL, 1)
    ]
    reject("omit_historical_occurrence", lambda: materialize_fsr(omitted, middle, event2, (DONE,)))

    if len(rows) != 20 or not all(row["candidate_equals_expected"] for row in rows):
        raise RuntimeError("occurrence five-arm equality gate failed")
    if len(negative) != 5 or not all(row["rejected"] for row in negative):
        raise RuntimeError("occurrence negative gate failed")
    restore_final = [
        row for row in rows
        if row["sequence_type"] == "replace_then_restore" and row["event_index"] == 2
    ]
    if not all(
        row["original_occurrence_1_status"] == "superseded"
        and row["intermediate_occurrence_1_status"] == "superseded"
        and row["original_occurrence_2_status"] == "active"
        and row["directive"] == f"place_in({ORIGINAL}, basket_1_contain_region)"
        for row in restore_final
    ):
        raise RuntimeError("restoration occurrence history is wrong")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with (args.output_dir / "02_NEGATIVE_CASES.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(negative[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(negative)
    status = {
        "schema": "occurrence-restoration-gate-v1", "gate": "PASS",
        "arms": 5, "sequence_types": 2, "event_cells": 20,
        "negative_cases_rejected": 5, "provider_calls": 0,
        "simulator_states_indexed": 0,
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
