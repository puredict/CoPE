#!/usr/bin/env python3
"""Build source-backed v2.1 task certificates from audited evidence artifacts.

The builder derives records from the retained v2 inventory, the enumerated
LIBERO state inventory, admitted clean calibration, and the disjoint dev-state
feasibility sweep.  It never calls a provider, model, simulator, or policy and
refuses to overwrite any artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.calibration_v2_1 import summarize_task_calibration  # noqa: E402
from cope_benchmark.repeated_v2.canonical import canonical_sha256  # noqa: E402
from cope_benchmark.repeated_v2.task_catalog import (  # noqa: E402
    CATALOG_SCHEMA_VERSION_V2_1,
    EVENT_FAMILIES,
    STRUCTURAL_CHECKS,
    TaskCatalog,
    select_eligible_tasks,
    task_catalog_gaps,
)
from cope_benchmark.task_progress import get_task_definition  # noqa: E402


OLD_GAP_MATRIX = ROOT / "research/repeated_v2_formal_readiness_20260906/GAP_MATRIX.csv"
OLD_CATALOG = ROOT / "task_catalogs/repeated_v2.json"
INVENTORY = ROOT / "research/repeated_v2_formal_readiness_v2_1/LIBERO_INIT_STATE_INVENTORY.csv"
PROTOCOL_DOC = ROOT / "docs/repeated_v2/PROTOCOL_AMENDMENT_V2_1_HORIZON_AND_INDEPENDENCE.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _encoded(value: Any, *, pretty: bool = False) -> bytes:
    kwargs = {"sort_keys": True, "ensure_ascii": False, "allow_nan": False}
    if pretty:
        kwargs["indent"] = 2
    else:
        kwargs["separators"] = (",", ":")
    return (json.dumps(value, **kwargs) + "\n").encode()


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _source(uri: str, path: Path, description: str) -> dict[str, str]:
    return {"uri": uri, "sha256": _sha(path), "description": description}


def _bool(value: str) -> bool:
    if value not in {"True", "False", "true", "false"}:
        raise ValueError(f"expected literal Boolean, got {value!r}")
    return value.lower() == "true"


def _trigger(family: str, entity: str | None) -> dict[str, Any]:
    predicates = {
        "TARGET_OBJECT_DISPLACED": "goal_pending_and_target_publicly_localized",
        "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED": "active_goal_grounding_publicly_changed",
        "TEMPORARY_NO_GO_APPEARS": "active_goal_requires_workspace_transit",
        "TEMPORARY_NO_GO_CLEARS": "temporary_no_go_is_publicly_observed",
        "USER_ADDS_PERSISTENT_PREFERENCE": "active_goal_exists",
        "TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE": "goal_pending_and_target_publicly_localized",
        "TOOL_OR_TARGET_AVAILABLE_AGAIN": "target_availability_restoration_observed",
        "USER_REPLACES_ACTIVE_GOAL": "user_instruction_targets_active_occurrence",
        "USER_CANCELS_ACTIVE_GOAL": "user_instruction_targets_active_occurrence",
        "USER_REISSUES_RETIRED_GOAL": "user_instruction_reissues_retired_goal_family",
    }
    guards = {
        "TARGET_OBJECT_DISPLACED": "catalog_target_displacement_guard",
        "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED": "catalog_receptacle_displacement_guard",
        "TEMPORARY_NO_GO_APPEARS": "catalog_no_go_clearance_guard",
        "TEMPORARY_NO_GO_CLEARS": "catalog_no_go_retirement_guard",
        "USER_ADDS_PERSISTENT_PREFERENCE": "positive_preference_limits_guard",
        "TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE": "catalog_ungrasped_availability_guard",
        "TOOL_OR_TARGET_AVAILABLE_AGAIN": "catalog_release_and_revalidation_guard",
        "USER_REPLACES_ACTIVE_GOAL": "source_grounded_alternative_goal_guard",
        "USER_CANCELS_ACTIVE_GOAL": "active_occurrence_not_retired_guard",
        "USER_REISSUES_RETIRED_GOAL": "retired_family_fresh_id_guard",
    }
    moves = family in {
        "TARGET_OBJECT_DISPLACED", "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED",
        "TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE",
        "TOOL_OR_TARGET_AVAILABLE_AGAIN",
    }
    return {
        "predicate": predicates[family], "earliest_policy_step": 0,
        "latest_policy_step": 520, "physical_feasibility_guard": guards[family],
        "min_steps_since_previous_event": 10, "moves_object": moves,
        "intervention_entity": entity if moves else None,
        "forced_external_displacement": False,
    }


def _build(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    base = _json(args.base_catalog)
    base_tasks = {int(task["task_id"]): task for task in base["tasks"]}
    inventory_rows = _csv_rows(args.inventory)
    calibration = _jsonl(args.calibration_dir / "CLEAN_CALIBRATION_ALL_TASKS.jsonl")
    structural_rows = _csv_rows(args.structural_replay_dir / "REPLAY_STRUCTURAL_WITNESS_SUMMARY.csv")
    structural = {int(row["task_id"]): row for row in structural_rows}
    protocol = _json(args.calibration_dir / "CALIBRATION_PROTOCOL_AUDIT.json")
    feasibility = _jsonl(args.feasibility_dir / "SEMANTIC_FEASIBILITY_RESULTS.jsonl")
    parameters = _json(args.parameters)
    if len(inventory_rows) != 500 or len(calibration) != 100:
        raise ValueError("catalog inputs require exactly 500 states and 100 calibration cells")
    if protocol.get("all_projections_identical") is not True:
        raise ValueError("calibration protocol projection audit did not pass")
    feasibility_ref = str((args.feasibility_dir / "SEMANTIC_FEASIBILITY_RESULTS.jsonl").resolve())
    tasks, certificates = [], []
    source_files = {
        "inventory": args.inventory,
        "calibration": args.calibration_dir / "CLEAN_CALIBRATION_ALL_TASKS.jsonl",
        "calibration_admission": args.calibration_dir / "CALIBRATION_ADMISSION_RECORDS.jsonl",
        "calibration_structural": args.structural_replay_dir / "REPLAY_STRUCTURAL_WITNESS_SUMMARY.csv",
        "calibration_milestones": args.structural_replay_dir / "REPLAY_MILESTONE_WITNESSES.csv",
        "calibration_protocol": args.calibration_dir / "CALIBRATION_PROTOCOL_AUDIT.json",
        "feasibility": args.feasibility_dir / "SEMANTIC_FEASIBILITY_RESULTS.jsonl",
        "feasibility_summary": args.feasibility_dir / "SEMANTIC_FEASIBILITY_SUMMARY.csv",
        "parameters": args.parameters,
        "task_progress": ROOT / "cope_benchmark/task_progress.py",
        "compiler": ROOT / "cope_benchmark/repeated_v2/compiler.py",
        "continuation_backend": ROOT / "cope_benchmark/repeated_v2/continuation_backend.py",
        "dynamic_evaluator": ROOT / "cope_benchmark/repeated_v2/dynamic_evaluator.py",
        "protocol": PROTOCOL_DOC,
    }
    for path in source_files.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    for task_id in range(10):
        old = json.loads(json.dumps(base_tasks[task_id]))
        definition = get_task_definition("libero_10", task_id)
        task_calibration = sorted(
            (row for row in calibration if row["task_id"] == task_id),
            key=lambda row: row["initial_state_id"],
        )
        task_feasibility = [row for row in feasibility if row["task_id"] == task_id]
        states = {row["state_id"]: row["state_sha256"] for row in inventory_rows
                  if int(row["task_id"]) == task_id}
        if set(states) != {str(i) for i in range(50)} or len(task_calibration) != 10:
            raise ValueError(f"task {task_id} input grid is incomplete")
        families = []
        event_checks = {}
        for family in EVENT_FAMILIES:
            rows = [row for row in task_feasibility if row["event_family"] == family]
            if not rows:
                continue
            covered = sorted(row["initial_state_id"] for row in rows)
            passed = covered == list(range(15, 20)) and all(row["passed"] for row in rows)
            if passed:
                families.append(family)
            event_checks[family] = {
                "passed": passed, "covered_state_ids": covered,
                "evidence_refs": [f"{feasibility_ref}#task={task_id}&family={family}"],
                "event_state_cells": len(rows),
                "passing_event_state_cells": sum(bool(row["passed"]) for row in rows),
            }
        target_entity = definition.target_joints[0].removesuffix("_joint0")
        task_parameters = parameters["task_parameters"][str(task_id)]
        safe = {}
        parameter_ref = str(args.parameters.resolve())
        if "TARGET_OBJECT_DISPLACED" in families:
            safe["TARGET_OBJECT_DISPLACED"] = {
                "entity": target_entity,
                "region": {"frame": "pre_event_entity", "delta_xy": task_parameters["target_delta_xy"]},
                "evidence_refs": [parameter_ref, f"{feasibility_ref}#task={task_id}&family=TARGET_OBJECT_DISPLACED"],
            }
        if "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED" in families:
            grounding_entity = definition.receptacle_joints[0].removesuffix("_joint0")
            safe["GOAL_RECEPTACLE_OR_GROUNDING_CHANGED"] = {
                "entity": grounding_entity,
                "region": {"frame": "pre_event_entity",
                           "delta_xy": task_parameters["grounding_delta_xy"]},
                "evidence_refs": [parameter_ref,
                    f"{feasibility_ref}#task={task_id}&family=GOAL_RECEPTACLE_OR_GROUNDING_CHANGED"],
            }
        for family in ("TEMPORARY_NO_GO_APPEARS", "TEMPORARY_NO_GO_CLEARS"):
            if family in families:
                safe[family] = {
                    "entity": target_entity,
                    "region": {"construction": task_parameters["no_go_rule"],
                               "half_width": task_parameters["no_go_half_width"]},
                    "evidence_refs": [parameter_ref, f"{feasibility_ref}#task={task_id}&family={family}"],
                }
        for family in ("TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE", "TOOL_OR_TARGET_AVAILABLE_AGAIN"):
            if family in families:
                safe[family] = {
                    "entity": target_entity,
                    "region": {"accessible_xyz_bounds": [[-0.35, 0.35], [-0.36, 0.36], [0.30, 1.20]],
                               "unavailable_rule": task_parameters["availability_unavailable_rule"],
                               "release_delta_xy": task_parameters["availability_release_delta_xy"]},
                    "evidence_refs": [parameter_ref, f"{feasibility_ref}#task={task_id}&family={family}"],
                }
        goals = old["initial_achievement_goals"]
        structural_source = structural[task_id]
        independent_pass = len({(g["predicate"], tuple(g["arguments"])) for g in goals}) >= 2
        preservation_pass = _bool(structural_source["completed_milestone_preservable"])
        milestones = []
        for index, milestone in enumerate(old["milestone_predicates"]):
            milestones.append({
                **milestone,
                "independent": independent_pass,
                "can_remain_valid": preservation_pass and index == 0,
                "evidence_refs": [str(source_files["calibration_milestones"].resolve()),
                                  str(source_files["calibration_structural"].resolve())],
            })
        alternative_goals, replaceable = [], []
        replacement_rows = [row for row in task_feasibility
                            if row["event_family"] == "USER_REPLACES_ACTIVE_GOAL"]
        if "USER_REPLACES_ACTIVE_GOAL" in families:
            examples = [row["evidence"]["alternative_goal"] for row in replacement_rows]
            first = examples[0]
            if not all(value == first and value.get("simulator_predicate_available") for value in examples):
                raise ValueError(f"task {task_id} replacement alternative differs across dev states")
            source_goal = goals[task_parameters["alternative_goal"]["source_goal_index"]]
            alternative_goals = [{
                "family_key": first["family_key"], "predicate": first["predicate"],
                "arguments": first["arguments"],
                "source_ref": f"{feasibility_ref}#task={task_id}&family=USER_REPLACES_ACTIVE_GOAL",
                "derivation": "existing LIBERO object/target inventory plus actual predicate-availability audit",
            }]
            replaceable = [source_goal["family_key"]]
        unsupported = [family for family in EVENT_FAMILIES if family not in families]
        task_sources = list(old["source_refs"])
        task_sources.extend([
            _source(str(args.inventory.resolve()), args.inventory, "All 50 installed LIBERO initialization-state hashes."),
            _source(str(source_files["calibration_admission"].resolve()), source_files["calibration_admission"],
                    "Hash-admitted production OpenVLA clean calibration."),
            _source(feasibility_ref, source_files["feasibility"],
                    "Zero-provider reserve-frozen dev-state semantic feasibility sweep."),
            _source(str(source_files["task_progress"].resolve()), source_files["task_progress"],
                    "Exact task-progress predicate bindings."),
        ])
        old.update({
            "maintenance_invariants": [{
                "kind": "preserve_verified_progress_unless_directly_invalidated",
                "predicate": goal["predicate"], "arguments": goal["arguments"],
                "family_key": goal["family_key"],
                "authority": "Experiment-1 frozen success definition",
                "source_ref": str(PROTOCOL_DOC.resolve()),
            } for goal in goals],
            "hard_safety_constraints": [
                {"key": "active_no_go_zones_respected", "predicate": "no_go_zone_respected",
                 "arguments": [], "verifier": "shared_runtime_constraint_monitor",
                 "source_ref": str(PROTOCOL_DOC.resolve())},
                {"key": "retired_occurrences_not_intentionally_executed",
                 "predicate": "target_occurrence_is_active", "arguments": [],
                 "verifier": "SealedDynamicEvaluator", "source_ref": str(PROTOCOL_DOC.resolve())},
            ],
            "soft_preference_templates": [{
                "template_id": "handle_gently_v1", "predicate": "gentle_action_limits",
                "translation_ceiling": 0.035, "eef_speed_ceiling": 0.22,
                "contact_impulse_proxy_ceiling": 0.12, "scope": "persistent_until_explicitly_retired",
                "verifier": "shared_runtime_constraint_monitor", "source_ref": str(PROTOCOL_DOC.resolve()),
            }],
            "milestone_predicates": milestones,
            "alternative_valid_goals": alternative_goals,
            "replaceable_goal_families": replaceable,
            "safe_event_injection_poses": safe,
            "supported_event_families": families,
            "semantic_triggers": {
                family: _trigger(
                    family,
                    (definition.receptacle_joints[0].removesuffix("_joint0")
                     if family == "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED" else target_entity),
                )
                for family in families
            },
            "dynamic_evaluator_predicates": [
                {"predicate": goal["predicate"], "arguments": goal["arguments"],
                 "family_key": goal["family_key"], "source_ref": goal["source_ref"]}
                for goal in goals + alternative_goals
            ],
            "planner_compiler_metadata": {
                "compiler": "compile_ledger", "compiler_pure_projection": True,
                "compiler_source_sha256": _sha(source_files["compiler"]),
                "continuation_backend": "continuation_carrying_repair_v2",
                "continuation_backend_representation_neutral": True,
                "continuation_backend_source_sha256": _sha(source_files["continuation_backend"]),
                "dynamic_evaluator": "sealed_dynamic_v2.1",
                "dynamic_evaluator_source_sha256": _sha(source_files["dynamic_evaluator"]),
                "calibration_protocol_projection_sha256": protocol["task_independent_projection_sha256"],
                "unsupported_event_families": unsupported,
            },
            "initial_state_digests": states,
            "structural_checks": {
                "two_independently_verifiable_milestones": {
                    "passed": independent_pass,
                    "evidence_refs": [str(source_files["calibration_structural"].resolve()),
                                      str(source_files["task_progress"].resolve())],
                },
                "completed_milestone_preservable": {
                    "passed": preservation_pass,
                    "evidence_refs": [str(source_files["calibration_milestones"].resolve())],
                },
                "safe_changeable_grounding": {
                    "passed": event_checks.get("TARGET_OBJECT_DISPLACED", {}).get("passed", False),
                    "evidence_refs": [f"{feasibility_ref}#task={task_id}&family=TARGET_OBJECT_DISPLACED"],
                },
                "cross_skill_requirement_or_persistent_preference": {
                    "passed": independent_pass or event_checks.get("USER_ADDS_PERSISTENT_PREFERENCE", {}).get("passed", False),
                    "evidence_refs": [str(PROTOCOL_DOC.resolve()),
                                      f"{feasibility_ref}#task={task_id}&family=USER_ADDS_PERSISTENT_PREFERENCE"],
                },
            },
            "event_feasibility": {family: event_checks[family] for family in families},
            "calibration_records": task_calibration,
            "source_refs": task_sources,
            "unresolved_fields": [],
        })
        tasks.append(old)
        certificate_body = {
            "schema_version": "repeated_v2_1_task_semantics_certificate_v1",
            "task_id": task_id, "task_name": old["task_name"],
            "automatically_derived_fields": [
                "original_instruction", "object_aliases", "receptacle_region_aliases",
                "initial_achievement_goals", "initial_state_digests", "dynamic_evaluator_predicates",
            ],
            "manually_audited_fields": [
                "maintenance_invariants", "hard_safety_constraints", "soft_preference_templates",
                "milestone_predicates", "alternative_valid_goals", "replaceable_goal_families",
                "semantic_triggers", "safe_event_injection_poses", "supported_event_families",
                "planner_compiler_metadata",
            ],
            "evidence_sources": task_sources,
            "unsupported_event_families": unsupported,
            "unresolved_fields": [],
            "structural_checks": old["structural_checks"],
            "event_feasibility": old["event_feasibility"],
            "clean_calibration": summarize_task_calibration(task_id, task_calibration),
        }
        certificate_body["certificate_sha256"] = canonical_sha256(certificate_body)
        certificates.append(certificate_body)
    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION_V2_1,
        "task_suite": "libero_10", "selection_rule": "all_semantically_eligible",
        "provenance_kind": "source_backed", "tasks": tasks,
    }
    validated = TaskCatalog.from_dict(catalog)
    completeness_gaps = list(task_catalog_gaps(validated))
    if completeness_gaps:
        raise ValueError("built catalog has unresolved evidence/schema gaps: " + "; ".join(completeness_gaps))
    selected, selection_status = [], "ELIGIBLE_TASKS_SELECTED"
    try:
        selected = [task.task_id for task in select_eligible_tasks(validated)]
    except Exception as exc:
        selection_status = getattr(exc, "status", type(exc).__name__)
        # Derive the per-task outcomes below; do not erase a complete catalog
        # merely because fewer than eight tasks passed scientific eligibility.
        for task in validated.tasks:
            summary = summarize_task_calibration(task.task_id, task.calibration_records)
            if (all(task.structural_checks[name]["passed"] for name in STRUCTURAL_CHECKS)
                    and all(task.event_feasibility[name]["passed"] for name in task.supported_event_families)
                    and summary["eligible_success_rate"]):
                selected.append(task.task_id)
    selected = sorted(set(selected))
    metadata = {
        "schema_version": "repeated_v2_1_catalog_build_receipt_v1",
        "catalog_sha256": canonical_sha256(catalog), "eligible_task_ids": selected,
        "eligible_task_count": len(selected), "selection_status": selection_status,
        "provider_calls": 0, "vla_calls": 0, "formal_trajectories": 0,
        "source_sha256": {name: _sha(path) for name, path in source_files.items()},
    }
    return catalog, certificates, metadata


def _gaps(catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for task in catalog["tasks"]:
        task_id = task["task_id"]
        summary = summarize_task_calibration(task_id, task["calibration_records"])
        reasons = []
        if summary["horizon_gate"] != "HORIZON_ESTIMATED":
            reasons.append(("calibration", summary["horizon_gate"],
                            "additional preregistered unique calibration states with successful trajectories",
                            "clean_horizon_and_task_eligibility"))
        elif not summary["eligible_success_rate"]:
            reasons.append(("calibration", "CLEAN_SUCCESS_RATE_OUTSIDE_FROZEN_INTERVAL",
                            "measured clean success within the unchanged inclusive [0.40,0.95] interval",
                            "task_eligibility"))
        for check in STRUCTURAL_CHECKS:
            if not task["structural_checks"][check]["passed"]:
                reasons.append(("structural_and_milestones", check,
                                "additional source-grounded and observed structural witness",
                                "task_eligibility"))
        for family, check in task["event_feasibility"].items():
            if not check["passed"]:
                reasons.append(("semantic_feasibility", family,
                                "passing reserve-frozen audit on every dev state 15-19",
                                "semantic_feasibility;task_eligibility"))
        for index, (category, root, evidence, gate) in enumerate(reasons, 1):
            rows.append({
                "gap_id": f"V21-T{task_id:02d}-{index:02d}", "task_id": task_id,
                "task_name": task["task_name"], "category": category,
                "root_cause": root, "root_cause_unit_id": f"T{task_id:02d}:{root}",
                "automatic_fixability": "REQUIRES_NEW_MEASURED_EVIDENCE",
                "required_evidence": evidence, "blocking_gate": gate,
                "cascade_class": "one_root_cause_many_derived_cells",
            })
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-catalog", type=Path, default=OLD_CATALOG)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--structural-replay-dir", type=Path, required=True)
    parser.add_argument("--feasibility-dir", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--research-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ("base_catalog", "inventory", "calibration_dir", "structural_replay_dir",
                 "feasibility_dir", "parameters"):
        setattr(args, name, getattr(args, name).resolve())
    catalog, certificates, metadata = _build(args)
    catalog_dir = args.catalog_dir.resolve()
    if catalog_dir.exists():
        raise FileExistsError(catalog_dir)
    catalog_dir.mkdir(parents=True)
    _write_new(catalog_dir / "catalog.json", _encoded(catalog, pretty=True))
    for task in catalog["tasks"]:
        _write_new(catalog_dir / f"task_{task['task_id']:02d}.json", _encoded(task, pretty=True))
    certificate_dir = args.research_dir.resolve() / "task_certificates"
    if certificate_dir.exists():
        raise FileExistsError(certificate_dir)
    certificate_dir.mkdir(parents=True)
    for certificate in certificates:
        _write_new(certificate_dir / f"TASK_{certificate['task_id']:02d}_SEMANTICS_CERTIFICATE.json",
                   _encoded(certificate, pretty=True))
    old_rows = _csv_rows(OLD_GAP_MATRIX)
    old_units = len({row["root_cause_unit_id"] for row in old_rows})
    after = _gaps(catalog)
    fields = ("gap_id", "task_id", "task_name", "category", "root_cause",
              "root_cause_unit_id", "automatic_fixability", "required_evidence",
              "blocking_gate", "cascade_class")
    _write_new(args.research_dir / "GAP_MATRIX_V2_1.csv", _csv_bytes(after, fields))
    category_counts: dict[str, int] = {}
    for row in after:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    summary = f"""# v2.1 gap summary

The retained v2 preflight expanded **{len(old_rows)} derived rows** from **{old_units} root-cause units**. This rebuild operates on the root causes and never treats cascade rows as separate manual tasks.

The v2.1 source-backed catalog has **{len(after)} remaining task-level root causes**. Its mandatory schema/evidence completeness gap count is zero. Remaining rows are measured scientific eligibility failures, grouped by task, category, required evidence, and blocking gate in `GAP_MATRIX_V2_1.csv`.

## Remaining root causes by category

{chr(10).join(f'- `{name}`: {count}' for name, count in sorted(category_counts.items())) or '- None'}

## Cascade handling

State-digest, trigger-field, feasibility, calibration-identity, and collection-marker cascades were regenerated from one upstream artifact per category. A missing or failed upstream certificate remains one root cause even when it affects several derived task/event/state cells. No task-catalog entry was invented to erase a failed measurement.

## Eligibility

- Eligible task IDs: {metadata['eligible_task_ids']}
- Eligible task count: {metadata['eligible_task_count']}
- Selection status: `{metadata['selection_status']}`
- Formal launch minimum: 8 tasks
"""
    _write_new(args.research_dir / "GAP_SUMMARY_V2_1.md", summary.encode())
    counts = [
        {"stage": "before_v2_1", "derived_gap_rows": len(old_rows), "root_cause_units": old_units},
        {"stage": "after_v2_1", "derived_gap_rows": len(after),
         "root_cause_units": len({row["root_cause_unit_id"] for row in after})},
    ]
    _write_new(args.research_dir / "GAP_ROOT_CAUSE_COUNTS_V2_1.csv",
               _csv_bytes(counts, ("stage", "derived_gap_rows", "root_cause_units")))
    metadata["catalog_file_sha256"] = _sha(catalog_dir / "catalog.json")
    metadata["remaining_root_causes"] = len(after)
    _write_new(args.research_dir / "TASK_CATALOG_BUILD_RECEIPT.json", _encoded(metadata, pretty=True))
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0 if metadata["eligible_task_count"] >= 8 else 2


if __name__ == "__main__":
    raise SystemExit(main())
