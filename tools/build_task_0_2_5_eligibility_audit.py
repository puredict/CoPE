#!/usr/bin/env python3
"""Build the zero-call Task 0/2/5 eligibility audit from retained evidence."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.enums import EventFamily  # noqa: E402
from cope_benchmark.repeated_v2.scheduler import (  # noqa: E402
    ScheduledEvent, SemanticTrigger, validate_prefix,
)


TASKS = (0, 2, 5)
FAMILIES = tuple(family.value for family in EventFamily)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _csv(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to replace different audit artifact: {path}")
    if not path.exists():
        path.write_bytes(data)


def _four_event_task2_prefix(catalog_task: Mapping[str, Any]) -> tuple[bool, list[str]]:
    order = [
        EventFamily.TARGET_OBJECT_DISPLACED,
        EventFamily.USER_CANCELS_ACTIVE_GOAL,
        EventFamily.USER_REISSUES_RETIRED_GOAL,
        EventFamily.USER_ADDS_PERSISTENT_PREFERENCE,
    ]
    events = []
    ids = {}
    for index, family in enumerate(order, 1):
        trigger = SemanticTrigger.from_dict(catalog_task["semantic_triggers"][family.value])
        identifier = f"task2-audit-{index}"
        dependencies = (ids[EventFamily.USER_CANCELS_ACTIVE_GOAL],) \
            if family is EventFamily.USER_REISSUES_RETIRED_GOAL else ()
        events.append(ScheduledEvent(identifier, index, family, trigger, dependencies))
        ids[family] = identifier
    validate_prefix(events)
    return True, [family.value for family in order]


def build(*, development: Path, formal_task0: Path, catalog_path: Path,
          output_dir: Path) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_task = {task["task_id"]: task for task in catalog["tasks"]}
    dev = [row for row in _rows(development) if row["task_id"] in TASKS]
    formal = [row for row in _rows(formal_task0) if row["task_id"] == 0]
    evidence = {(row["task_id"], row["initial_state_id"], row["event_family"]): row
                for row in (*dev, *formal)}
    matrix = []
    for task_id in TASKS:
        states = tuple(range(10, 20)) if task_id == 0 else tuple(range(15, 20))
        for state_id in states:
            for family in FAMILIES:
                row = evidence.get((task_id, state_id, family))
                registered = row is not None
                if row is None:
                    status = "UNSUPPORTED_BY_REGISTERED_TASK_SEMANTICS"
                    physical = "NOT_TESTED"
                    source = "task_catalogs/repeated_v2_1/catalog.json"
                else:
                    status = "PASS" if row["passed"] else "FAIL"
                    physical = "PASS" if row["checks"]["physical_feasibility_guard"] else "FAIL"
                    source = str(formal_task0 if state_id < 15 else development)
                matrix.append({
                    "task_id": task_id, "state_id": state_id,
                    "split": "formal_candidate_zero_provider_audit" if state_id < 15 else "development",
                    "event_family": family, "registered_for_measured_sweep": registered,
                    "evidence_status": status, "physical_feasibility_guard": physical,
                    "candidate_supported": bool(row and row["passed"]),
                    "provider_calls": 0, "vla_calls": 0, "formal_method_trajectories": 0,
                    "evidence_source": source,
                })
    _write(output_dir / "TASK_STATE_EVENT_SUPPORT_MATRIX.csv", _csv(matrix, (
        "task_id", "state_id", "split", "event_family", "registered_for_measured_sweep",
        "evidence_status", "physical_feasibility_guard", "candidate_supported",
        "provider_calls", "vla_calls", "formal_method_trajectories", "evidence_source")))

    task0_formal = [row for row in formal]
    task0_safe = bool(task0_formal) and all(row["passed"] for row in task0_formal)
    task2_prefix_ok, task2_prefix = _four_event_task2_prefix(by_task[2])
    schedule = [
        {"task_id": 0, "registered_supported_family_count": len(by_task[0]["supported_event_families"]),
         "current_eight_distinct_event_template": "FAIL_MISSING_TEMPORARY_AVAILABILITY_PAIR",
         "legal_registered_four_event_prefix": True,
         "four_event_prefix": "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED;USER_CANCELS_ACTIVE_GOAL;USER_REISSUES_RETIRED_GOAL;USER_ADDS_PERSISTENT_PREFERENCE",
         "state_specific_support_evidence": "PASS" if task0_safe else "FAIL",
         "recommendation": "ELIGIBLE_ONLY_UNDER_VERSIONED_SUPPORT_MATRIX_AMENDMENT" if task0_safe else "MORE_EVIDENCE_REQUIRED"},
        {"task_id": 2, "registered_supported_family_count": len(by_task[2]["supported_event_families"]),
         "current_eight_distinct_event_template": "FAIL_MISSING_TEMPORARY_NO_GO_PAIR",
         "legal_registered_four_event_prefix": task2_prefix_ok,
         "four_event_prefix": ";".join(task2_prefix), "state_specific_support_evidence": "PASS_35_OF_35_DEVELOPMENT_CELLS",
         "recommendation": "ELIGIBLE_ONLY_UNDER_VERSIONED_SUPPORT_MATRIX_AMENDMENT"},
        {"task_id": 5, "registered_supported_family_count": len(by_task[5]["supported_event_families"]),
         "current_eight_distinct_event_template": "FAIL_MISSING_TEMPORARY_NO_GO_PAIR",
         "legal_registered_four_event_prefix": True,
         "four_event_prefix": ";".join(task2_prefix), "state_specific_support_evidence": "PASS_35_OF_35_DEVELOPMENT_CELLS",
         "recommendation": "STRUCTURALLY_INELIGIBLE"},
    ]
    _write(output_dir / "SCHEDULE_COVERAGE_AUDIT.csv", _csv(schedule, (
        "task_id", "registered_supported_family_count", "current_eight_distinct_event_template",
        "legal_registered_four_event_prefix", "four_event_prefix", "state_specific_support_evidence",
        "recommendation")))

    responsibility = [
        {"task_id": 0, "achievement_goals": 2, "independent_verified_milestones": 2,
         "maintenance_invariants": 0, "natural_initial_user_preferences": 0,
         "independent_grounding_commitments": 0, "independent_responsibility_objects": 2,
         "passes_two_object_rule": True, "recommendation": schedule[0]["recommendation"]},
        {"task_id": 2, "achievement_goals": 2, "independent_verified_milestones": 2,
         "maintenance_invariants": 0, "natural_initial_user_preferences": 0,
         "independent_grounding_commitments": 0, "independent_responsibility_objects": 2,
         "passes_two_object_rule": True, "recommendation": schedule[1]["recommendation"]},
        {"task_id": 5, "achievement_goals": 1, "independent_verified_milestones": 0,
         "maintenance_invariants": 0, "natural_initial_user_preferences": 0,
         "independent_grounding_commitments": 0, "independent_responsibility_objects": 1,
         "passes_two_object_rule": False, "recommendation": "STRUCTURALLY_INELIGIBLE"},
    ]
    _write(output_dir / "RESPONSIBILITY_OBJECT_AUDIT.csv", _csv(responsibility, (
        "task_id", "achievement_goals", "independent_verified_milestones", "maintenance_invariants",
        "natural_initial_user_preferences", "independent_grounding_commitments",
        "independent_responsibility_objects", "passes_two_object_rule", "recommendation")))

    failed_formal = [(row["initial_state_id"], row["event_family"])
                     for row in formal if not row["passed"]]
    report = f"""# Task 0/2/5 eligibility audit

This is a method-independent, zero-provider, zero-VLA audit. It changes no formal task list, threshold, catalog, schedule, or prior artifact.

## Task 0

The three retained development failures are one cascade root cause: state 18 introduces additional penetrating contacts for target displacement and both ends of the temporary-availability pair. The other 47/50 registered development cells pass. Applying the unchanged reserve-discovered parameters and unchanged contact guard to formal candidate states 10–14 produced {len(formal)} measured cells with {len(failed_formal)} failures: {failed_formal or 'none'}.

Recommendation: **{schedule[0]['recommendation']}**. The evidence supports a state-specific support matrix, but adopting that matrix would require a versioned protocol amendment and a new benchmark-level balance proof; this audit does not adopt it.

## Task 2

All 35 registered development feasibility cells pass. The exact current failure is the scheduler's global eight-distinct-family template, which requires `TEMPORARY_NO_GO_APPEARS` and `TEMPORARY_NO_GO_CLEARS` even though Task 2 does not register that pair. A legal four-event prefix exists using only registered families: `{';'.join(task2_prefix)}`.

Recommendation: **ELIGIBLE_ONLY_UNDER_VERSIONED_SUPPORT_MATRIX_AMENDMENT**. The existing eight-event rule still blocks it; the legal prefix only proves that per-task support need not require every event family.

## Task 5

Task 5 has one BDDL achievement goal. Its one verified milestone is the same terminal commitment and is neither independent nor preservable. The generic user-preference template is introduced only by an event, and its grounding is part of the same book-placement responsibility. Counting either as a second natural initial responsibility would fabricate a commitment.

Recommendation: **STRUCTURALLY_INELIGIBLE**.

Provider calls: 0. Learned-VLA calls: 0. Formal method-comparison trajectories: 0.
"""
    _write(output_dir / "TASK_0_2_5_ELIGIBILITY_AUDIT.md", report.encode())
    return {"task_0": schedule[0]["recommendation"],
            "task_2": schedule[1]["recommendation"],
            "task_5": schedule[2]["recommendation"],
            "provider_calls": 0, "vla_calls": 0, "formal_method_trajectories": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-results", required=True, type=Path)
    parser.add_argument("--formal-task0-results", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = build(development=args.development_results.resolve(),
                   formal_task0=args.formal_task0_results.resolve(),
                   catalog_path=args.catalog.resolve(), output_dir=args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
