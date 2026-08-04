#!/usr/bin/env python3
"""Representation-matched delivery and crash-boundary stress experiment."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cope.governed_delta import governed_oracle_proposal, materialize_governed_delta
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
    execute_typed_sparse_transition,
    fsr_oracle_proposal,
    initialize_typed_sequence_state,
    materialize_fsr_proposal,
    materialize_neutral_json_patch,
    neutral_json_oracle_proposal,
    sequence_state_hash,
    sparse_oracle_proposal,
)
from cope.types import canonical_json, stable_hash


ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc")
SCHEDULES = {
    "nominal": (("event1", "normal"), ("event2", "normal")),
    "immediate_duplicate": (
        ("event1", "normal"), ("event1", "normal"), ("event2", "normal")
    ),
    "delayed_duplicate": (
        ("event1", "normal"), ("event2", "normal"), ("event1", "normal")
    ),
    "out_of_order": (
        ("event2", "normal"), ("event1", "normal"), ("event2", "normal")
    ),
    "same_base_conflict": (
        ("event1", "normal"), ("event2_cancel", "normal"), ("event2", "normal")
    ),
    "crash_before_validation": (
        ("event1", "crash_before_validation"),
        ("event1", "normal"), ("event2", "normal"),
    ),
    "crash_after_stage": (
        ("event1", "crash_after_stage"),
        ("event1", "normal"), ("event2", "normal"),
    ),
    "crash_after_publish_before_ack": (
        ("event1", "publish_without_ack"),
        ("event1", "normal"), ("event2", "normal"),
    ),
}
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def frozen_fixture() -> dict[str, Any]:
    initial = build_initial_sequence_state(
        sequence_id="delivery-stress",
        done_object="alphabet_soup_1",
        pending_object="tomato_sauce_1",
        available_objects=(
            "alphabet_soup_1", "tomato_sauce_1", "cream_cheese_1", "butter_1"
        ),
        world_version=5000,
    )
    event1 = build_sequence_event(
        initial,
        sequence_id="delivery-stress",
        step_index=1,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="cream_cheese_1",
        world_version=5001,
    )
    middle = build_expected_next_state(initial, event1)
    event2 = build_sequence_event(
        middle,
        sequence_id="delivery-stress",
        step_index=2,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="butter_1",
        world_version=5002,
    )
    event2_cancel = build_sequence_event(
        middle,
        sequence_id="delivery-stress-conflict",
        step_index=2,
        done_object="alphabet_soup_1",
        event_type="cancel_pending_goal",
        replacement_object=None,
        world_version=5002,
    )
    return {
        "initial": initial,
        "events": {"event1": event1, "event2": event2, "event2_cancel": event2_cancel},
        "bases": {"event1": initial, "event2": middle, "event2_cancel": middle},
        "expected": {
            "event1": middle,
            "event2": build_expected_next_state(middle, event2),
            "event2_cancel": build_expected_next_state(middle, event2_cancel),
        },
    }


def proposal_for(arm: str, base: Mapping[str, Any], expected: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    if arm == "cope":
        return sparse_oracle_proposal(event, neutral=False)
    if arm == "neutral_patch":
        return neutral_json_oracle_proposal(base, expected, event)
    if arm == "governed_delta":
        return governed_oracle_proposal(base, expected, event)
    if arm == "fsr_pc":
        return fsr_oracle_proposal(expected)
    raise ValueError(arm)


def run_cell(schedule_name: str, arm: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixture = frozen_fixture()
    logical = copy.deepcopy(fixture["initial"])
    typed = (
        initialize_typed_sequence_state(
            sequence_id="delivery-stress",
            done_object="alphabet_soup_1",
            pending_object="tomato_sauce_1",
        )
        if arm == "cope" else None
    )
    proposals = {
        key: proposal_for(arm, fixture["bases"][key], fixture["expected"][key], event)
        for key, event in fixture["events"].items()
    }
    trace: list[dict[str, Any]] = []
    publications = rejections = crashes = staged_aborts = 0
    directives: list[str] = []
    rejection_immutable = True

    for delivery_index, (event_key, action) in enumerate(SCHEDULES[schedule_name], start=1):
        event = fixture["events"][event_key]
        before_logical = copy.deepcopy(logical)
        before_hash = sequence_state_hash(logical)
        before_typed_hash = typed.state_hash if typed is not None else ""
        if action == "crash_before_validation":
            crashes += 1
            trace.append(
                {"delivery_index": delivery_index, "event_key": event_key,
                 "action": action, "outcome": "crash_no_stage",
                 "before_hash": before_hash, "after_hash": before_hash}
            )
            continue
        try:
            if arm == "cope":
                assert typed is not None
                next_typed, candidate, receipt, directive = execute_typed_sparse_transition(
                    typed, logical, event, proposals[event_key], neutral=False,
                    physically_true_objects=("alphabet_soup_1",),
                )
            elif arm == "neutral_patch":
                candidate, receipt, directive = materialize_neutral_json_patch(
                    proposals[event_key], logical, event, ("alphabet_soup_1",)
                )
                next_typed = typed
            elif arm == "governed_delta":
                candidate, receipt, directive = materialize_governed_delta(
                    proposals[event_key], logical, event, ("alphabet_soup_1",)
                )
                next_typed = typed
            else:
                candidate, directive = materialize_fsr_proposal(
                    proposals[event_key], logical, event, ("alphabet_soup_1",)
                )
                receipt = {"accepted": True}
                next_typed = typed
            if action == "crash_after_stage":
                crashes += 1
                staged_aborts += 1
                outcome = "validated_stage_discarded"
            else:
                logical = candidate
                typed = next_typed
                publications += 1
                directives.append(directive)
                outcome = "published_ack_lost" if action == "publish_without_ack" else "published"
                if action == "publish_without_ack":
                    crashes += 1
            trace.append(
                {"delivery_index": delivery_index, "event_key": event_key,
                 "action": action, "outcome": outcome,
                 "before_hash": before_hash,
                 "after_hash": sequence_state_hash(logical),
                 "proposal_sha256": stable_hash(proposals[event_key]),
                 "receipt_accepted": bool(receipt.get("accepted", True)),
                 "directive": directive}
            )
        except Exception as exc:
            rejections += 1
            unchanged = (
                logical == before_logical
                and sequence_state_hash(logical) == before_hash
                and (typed.state_hash if typed is not None else "") == before_typed_hash
            )
            rejection_immutable = rejection_immutable and unchanged
            trace.append(
                {"delivery_index": delivery_index, "event_key": event_key,
                 "action": action, "outcome": "rejected",
                 "exception": f"{type(exc).__name__}:{exc}",
                 "before_hash": before_hash,
                 "after_hash": sequence_state_hash(logical),
                 "caller_unchanged": unchanged}
            )

    expected_final = (
        fixture["expected"]["event2_cancel"]
        if schedule_name == "same_base_conflict"
        else fixture["expected"]["event2"]
    )
    typed_synced = typed is None or typed.revision == int(logical["state_version"])
    row = {
        "schedule": schedule_name,
        "arm": arm,
        "deliveries": len(SCHEDULES[schedule_name]),
        "publications": publications,
        "rejections": rejections,
        "crashes": crashes,
        "staged_aborts": staged_aborts,
        "directive_count": len(directives),
        "final_state_correct": logical == expected_final,
        "final_state_sha256": sequence_state_hash(logical),
        "caller_unchanged_on_rejection": rejection_immutable,
        "typed_revision_synchronized": typed_synced,
        "provider_calls": 0,
        "simulator_states_indexed": 0,
        "passed": (
            publications == 2
            and len(directives) == 2
            and logical == expected_final
            and rejection_immutable
            and typed_synced
        ),
    }
    return row, trace


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    credentials = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if credentials:
        raise RuntimeError("delivery stress refuses credentials: " + ",".join(credentials))
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout
    if dirty.strip():
        raise RuntimeError("delivery stress requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for schedule in SCHEDULES:
        schedule_rows = []
        for arm in ARMS:
            row, trace = run_cell(schedule, arm)
            rows.append(row); schedule_rows.append(row)
            traces.append({"schedule": schedule, "arm": arm, "trace": trace})
        if len({row["final_state_sha256"] for row in schedule_rows}) != 1:
            for row in schedule_rows:
                row["passed"] = False
    passed = sum(bool(row["passed"]) for row in rows)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (args.output_dir / "02_TRACES.txt").write_text(
        "\n".join(canonical_json(item) for item in traces) + "\n", encoding="utf-8"
    )
    status = {
        "schema": "delivery-semantics-stress-v1",
        "runtime_git_commit": runtime_commit,
        "assigned_cells": len(rows),
        "passed_cells": passed,
        "provider_calls": 0,
        "simulator_states_indexed": 0,
        "credential_names_present": [],
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "gate": "PASS" if passed == len(rows) else "FAIL",
    }
    (args.output_dir / "00_STATUS.txt").write_text(canonical_json(status) + "\n", encoding="utf-8")
    (args.output_dir / "03_RESULT.md").write_text(
        "# Delivery-semantics stress result\n\n"
        f"- Gate: **{status['gate']}**\n"
        f"- Passed cells: **{passed}/{len(rows)}**\n"
        "- Required publications per cell: **2**\n"
        "- Provider calls: **0**\n"
        "- Simulator states indexed: **0**\n",
        encoding="utf-8",
    )
    return 0 if passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())

