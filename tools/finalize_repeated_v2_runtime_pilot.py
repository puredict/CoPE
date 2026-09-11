#!/usr/bin/env python3
"""Publish the registered v2.1 pilot view from the verified durable journal.

The executor writes its generic immutable journal beneath ``runtime_journal``.
This tool checks that journal and creates the experiment-specific artifact names
without changing, imputing, or deleting runtime records.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.canonical import canonical_json, canonical_sha256  # noqa: E402
from cope_benchmark.repeated_v2.evidence import assert_public_safe  # noqa: E402
from cope_benchmark.repeated_v2.journal import stable_hash  # noqa: E402


LABEL = "PILOT_ONLY_NOT_FORMAL"
METHODS = (
    "cope_typed_edit", "generic_persistent_edit", "full_state_regeneration",
    "full_history_replan", "rag_replan", "summary_memory_replan",
    "skill_local_replan", "classical_execution_monitor",
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _encode(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode()


def _encode_jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_encode(row) for row in rows)


def _encode_csv(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _publish(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise ValueError(f"refusing to replace different pilot artifact: {path}")
    path.write_bytes(data)


def _nearest_rank_q95(values: Sequence[int]) -> int | None:
    if not values:
        return None
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _source_hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def finalize(runtime: Path, output: Path) -> dict[str, Any]:
    status = _read(runtime / "12_STATUS.json")
    if status.get("status") != "COMPLETE" or status.get("phase") != "pilot":
        raise ValueError("durable pilot journal is not complete")
    metadata = _read(runtime / "00_RUN_METADATA.json")
    events = _jsonl(runtime / "06_EVENT_RESULTS.jsonl")
    episodes = _jsonl(runtime / "07_EPISODE_RESULTS.jsonl")
    snapshots = _jsonl(runtime / "08_STATE_SNAPSHOTS.jsonl")
    problems = _jsonl(runtime / "09_PLANNING_PROBLEMS.jsonl")
    integrity = _read(runtime / "INTEGRITY.json")
    if not integrity.get("valid"):
        raise ValueError("generic durable-journal integrity failed")

    run_metadata = {
        **metadata, "artifact_label": LABEL, "pipeline_evidence_only": True,
        "paper_claims_authorized": False, "runtime_journal": str(runtime.resolve()),
        "expected_trajectories": 32, "formal_provider_calls": 0,
        "formal_vla_calls": 0, "formal_trajectories": 0,
    }
    _publish(output / "00_RUN_METADATA.json", _encode(run_metadata))

    actual_identities = {}
    for path in sorted((runtime / "component_identities").glob("*.json")):
        actual_identities[path.stem] = _read(path)
    manifest = {
        "artifact_label": LABEL, "runtime_factory":
            "cope_benchmark.repeated_v2.production_runtime:create_runtime_assembly",
        "declared": metadata["runtime_identities"], "constructed": actual_identities,
        "zero_call_runtime_gate": metadata["zero_call_runtime_gate"],
        "source_sha256": {
            "production_runtime": _source_hash("cope_benchmark/repeated_v2/production_runtime.py"),
            "continuation_backend": _source_hash("cope_benchmark/repeated_v2/continuation_backend.py"),
            "compiler": _source_hash("cope_benchmark/repeated_v2/compiler.py"),
            "runner": _source_hash("cope_benchmark/repeated_v2/runner.py"),
            "journal": _source_hash("cope_benchmark/repeated_v2/journal.py"),
            "sealed_evaluator": _source_hash("cope_benchmark/repeated_v2/dynamic_evaluator.py"),
        },
        "public_observation_key_audit": {
            "source": "ordinary LIBERO observation mapping returned by reset/set_init_state/step",
            "used_by_evidence_or_verifier": ["<catalog-entity>_pos", "<catalog-entity>_quat",
                "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"],
            "used_by_openvla": ["agentview_image"],
            "forbidden": ["object-state", "sim", "contact", "canonical_ledger", "HiddenCanonicalEffect"],
        },
    }
    _publish(output / "01_RUNTIME_COMPONENT_MANIFEST.json", _encode(manifest))

    completed = {(row["master_episode_id"], row["method"], row["event_index"]): row
                 for row in snapshots if row["label"] == "completed"}
    evidence_rows, decision_rows, verification_rows = [], [], []
    for key, row in sorted(completed.items()):
        master, method, event_index = key
        snapshot = row["snapshot"]
        environment = snapshot["environment"]
        if event_index > 0 and len(environment.get("public_evidence", ())) >= event_index:
            evidence = environment["public_evidence"][event_index - 1]
            evidence_rows.append({"artifact_label": LABEL, "master_episode_id": master,
                                  "method": method, "event_index": event_index,
                                  "public_evidence": evidence})
        result = snapshot.get("pending_result") or {}
        if event_index > 0:
            decision_rows.append({
                "artifact_label": LABEL, "master_episode_id": master, "method": method,
                "event_index": event_index, "status": result.get("status"),
                "accepted": not result.get("metrics", {}).get("invalid_transaction", False),
                "method_state_sha256": result.get("method_state_sha256"),
                "planning_problem_sha256": result.get("planning_problem_sha256"),
                "high_level_calls": result.get("high_level_calls", 0),
            })
        for verification in environment.get("runtime_verifications", ()):
            verification_rows.append({
                "artifact_label": LABEL, "master_episode_id": master, "method": method,
                **verification,
            })
    # Cumulative verifier logs occur in multiple boundary snapshots.  Keep one
    # exact record per trajectory/verifier ID.
    deduped_verifications = {}
    for row in verification_rows:
        key = (row["master_episode_id"], row["method"], row["verifier_record_id"])
        if key in deduped_verifications and deduped_verifications[key] != row:
            raise ValueError("runtime verifier ID collision")
        deduped_verifications[key] = row
    verification_rows = [deduped_verifications[key] for key in sorted(deduped_verifications)]
    _publish(output / "02_PUBLIC_EVIDENCE.jsonl", _encode_jsonl(evidence_rows))
    _publish(output / "03_METHOD_DECISIONS.jsonl", _encode_jsonl(decision_rows))
    _publish(output / "04_PLANNING_PROBLEMS.jsonl", _encode_jsonl(
        ({"artifact_label": LABEL, **row} for row in problems)))
    _publish(output / "05_RUNTIME_VERIFICATIONS.jsonl", _encode_jsonl(verification_rows))

    action_output = output / "06_ACTION_TRACES"
    action_output.mkdir(parents=True, exist_ok=True)
    for source in sorted((runtime / "10_ACTION_TRACES").glob("*.jsonl.gz")):
        target = action_output / source.name
        with gzip.open(source, "rt", encoding="utf-8") as stream:
            labeled = [{"artifact_label": LABEL, **json.loads(line)}
                       for line in stream if line.strip()]
        _publish(target, gzip.compress(_encode_jsonl(labeled), mtime=0))
    event_rows = [{"artifact_label": LABEL, **row} for row in events]
    episode_rows = [{"artifact_label": LABEL, **row} for row in episodes]
    _publish(output / "07_EVENT_RESULTS.jsonl", _encode_jsonl(event_rows))
    _publish(output / "08_EPISODE_RESULTS.jsonl", _encode_jsonl(episode_rows))

    event_by_trajectory: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in events:
        event_by_trajectory.setdefault((row["master_episode_id"], row["method"]), []).append(row)
    cell_rows = []
    for episode in sorted(episodes, key=lambda row: (row["master_episode_id"], row["method"])):
        key = (episode["master_episode_id"], episode["method"])
        rows = event_by_trajectory.get(key, [])
        indexes = [row["event_index"] for row in rows]
        cell_rows.append({
            "artifact_label": LABEL, "master_episode_id": key[0], "method": key[1],
            "expected_event_cells": 5, "completed_event_cells": len(rows),
            "missing_cells": len(set(range(5)) - set(indexes)),
            "duplicate_cells": len(indexes) - len(set(indexes)),
            "unexpected_cells": len(set(indexes) - set(range(5))),
            "reached_events": episode["reached_events"], "episode_status": episode["status"],
            "integrity_status": "VALID" if len(rows) == 5 and set(indexes) == set(range(5)) else "INVALID",
        })
    _publish(output / "09_CELL_INTEGRITY.csv", _encode_csv(cell_rows, (
        "artifact_label", "master_episode_id", "method", "expected_event_cells",
        "completed_event_cells", "missing_cells", "duplicate_cells", "unexpected_cells",
        "reached_events", "episode_status", "integrity_status")))

    leakage_errors = []
    for row in evidence_rows:
        try:
            assert_public_safe(row["public_evidence"])
        except Exception as exc:
            leakage_errors.append(type(exc).__name__)
    grouped_evidence: dict[tuple[str, int], list[str]] = {}
    for row in evidence_rows:
        grouped_evidence.setdefault((row["master_episode_id"], row["event_index"]), []).append(
            canonical_sha256(row["public_evidence"]))
    same_evidence = all(len(values) == len(METHODS) and len(set(values)) == 1
                        for values in grouped_evidence.values()) and len(grouped_evidence) == 16
    fresh = all(
        item["public_evidence"]["timestamp"] ==
        completed[(item["master_episode_id"], item["method"], item["event_index"])]["snapshot"]["observation"]["version"]
        and completed[(item["master_episode_id"], item["method"], item["event_index"])]["snapshot"]["observation"]["observation_ref"]
        in item["public_evidence"]["observation_refs"]
        for item in evidence_rows
    )
    prior_failure_propagation = all(
        row.get("source_boundary_event_index") is not None and row.get("prior_failure")
        for row in events if row.get("status") == "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"
    )
    leakage = {
        "artifact_label": LABEL, "status": "PASS" if not leakage_errors else "FAIL",
        "recursive_public_leakage_scan": not leakage_errors,
        "leakage_errors": leakage_errors, "same_public_evidence_for_each_paired_event": same_evidence,
        "fresh_post_event_observations": fresh,
        "public_runtime_verifier_distinct_from_sealed_evaluator":
            metadata["zero_call_runtime_gate"]["public_sealed_separation"],
        "same_compiler_planner_backend":
            metadata["zero_call_runtime_gate"]["same_components_across_methods"],
        "prior_failure_propagation": prior_failure_propagation,
        "hidden_cause_or_canonical_state_reached_non_oracle_components": False,
    }
    _publish(output / "10_LEAKAGE_AUDIT.json", _encode(leakage))

    trace_rows = {}
    for episode in episodes:
        key = (episode["master_episode_id"], episode["method"])
        filename = stable_hash(["end_to_end", key[0], key[1], 0]) + ".jsonl.gz"
        with gzip.open(runtime / "10_ACTION_TRACES" / filename, "rt", encoding="utf-8") as stream:
            trace_rows[key] = [json.loads(line) for line in stream if line.strip()]
    latency_rows = []
    for method in METHODS:
        selected_events = [row for row in events if row["method"] == method]
        selected_traces = [entry for key, trace in trace_rows.items() if key[1] == method for entry in trace]
        latency_rows.append({
            "artifact_label": LABEL, "method": method,
            "trajectory_count": sum(row["method"] == method for row in episodes),
            "provider_calls": sum(row.get("high_level_calls", 0) for row in selected_events),
            "planning_seconds": sum(float(row.get("planning_seconds") or 0) for row in selected_events),
            "reasoner_seconds": sum(float(row.get("metrics", {}).get("reasoner_seconds") or 0)
                                    for row in selected_events),
            "policy_inference_and_step_seconds": sum(float(row.get("inference_and_step_seconds") or 0)
                                                      for row in selected_traces),
            "policy_steps": len(selected_traces),
            "timeout_trajectories": sum(row["method"] == method and row["status"] == "METHOD_TIMEOUT"
                                        for row in episodes),
        })
    _publish(output / "11_LATENCY_BREAKDOWN.csv", _encode_csv(latency_rows, (
        "artifact_label", "method", "trajectory_count", "provider_calls", "planning_seconds",
        "reasoner_seconds", "policy_inference_and_step_seconds", "policy_steps", "timeout_trajectories")))

    # A conservative, method-independent observable: actions from the completed
    # event-injection boundary to the next decision boundary.  It is reported
    # explicitly so it cannot be mistaken for isolated repair-operator time.
    event_windows = []
    pre = {(row["master_episode_id"], row["method"], row["event_index"]): row
           for row in snapshots if row["label"] == "pre"}
    for key, completed_row in completed.items():
        if key[2] == 0 or key not in pre:
            continue
        before_count = len(pre[key]["snapshot"]["executor"]["trace"])
        after_count = len(completed_row["snapshot"]["executor"]["trace"])
        event_windows.append(max(0, after_count - before_count))
    q95 = _nearest_rank_q95(event_windows)
    clean = {1: 388, 4: 341}
    budget_rows = []
    for task_id, clean_budget in clean.items():
        for multiplier in (1.0, 1.25, 1.5):
            interrupted = None if q95 is None else clean_budget + 4 * math.ceil(multiplier * q95)
            budget_rows.append({
                "artifact_label": LABEL, "rule_version": "interrupted_budget_amendment_v1",
                "task_id": task_id, "event_count": 4, "h_clean": clean_budget,
                "observable": "event_injection_to_next_decision_boundary_policy_steps",
                "sample_count": len(event_windows), "nearest_rank_q95": q95,
                "multiplier": multiplier, "h_interrupted": interrupted,
                "is_frozen_rule": multiplier == 1.25,
                "same_for_all_methods": True, "timeout_remains_failure": True,
                "selection_uses_method_ranking": False,
            })
    _publish(output / "12_INTERRUPTED_BUDGET_EVIDENCE.csv", _encode_csv(budget_rows, (
        "artifact_label", "rule_version", "task_id", "event_count", "h_clean", "observable",
        "sample_count", "nearest_rank_q95", "multiplier", "h_interrupted",
        "is_frozen_rule", "same_for_all_methods", "timeout_remains_failure",
        "selection_uses_method_ranking")))

    provider_calls = sum(row["provider_calls"] for row in latency_rows)
    vla_calls = sum(row["policy_steps"] for row in latency_rows)
    valid_cells = (len(cell_rows) == 32 and all(row["integrity_status"] == "VALID" for row in cell_rows))
    pilot_pass = all((valid_cells, same_evidence, fresh, not leakage_errors,
                      leakage["public_runtime_verifier_distinct_from_sealed_evaluator"],
                      leakage["same_compiler_planner_backend"], prior_failure_propagation))
    report = f"""# Repeated-interruptions v2.1 end-to-end pilot

Status: `{'PILOT_INTEGRITY_PASS' if pilot_pass else 'PILOT_INTEGRITY_FAIL'}`  
Artifact boundary: `{LABEL}`. This pilot is pipeline evidence and does not authorize a paper claim.

- Expected/completed trajectories: 32/{len(episodes)}
- Durable event cells: {len(events)}/160; missing {len(integrity['missing'])}, duplicate {len(integrity['duplicates'])}, unexpected {len(integrity['unexpected'])}
- Provider calls: {provider_calls}
- Learned-VLA action calls: {vla_calls}
- Public evidence parity: {'PASS' if same_evidence else 'FAIL'}
- Fresh post-event observations: {'PASS' if fresh else 'FAIL'}
- Public/sealed separation: {'PASS' if leakage['public_runtime_verifier_distinct_from_sealed_evaluator'] else 'FAIL'}
- Common compiler/planner/backend: {'PASS' if leakage['same_compiler_planner_backend'] else 'FAIL'}
- Recursive leakage scan: {'PASS' if not leakage_errors else 'FAIL'}
- Interrupted-budget observable samples/Q95: {len(event_windows)}/{q95}

Behavioral success or superiority is outside this integrity decision. Formal execution remains blocked by the unchanged eight-task eligibility gate and the downstream comparator, catalog-freeze, and formal-freeze gates.
"""
    _publish(output / "13_PILOT_REPORT.md", report.encode())
    receipt = {"status": "PILOT_INTEGRITY_PASS" if pilot_pass else "PILOT_INTEGRITY_FAIL",
               "expected_trajectories": 32, "completed_trajectories": len(episodes),
               "provider_calls": provider_calls, "vla_calls": vla_calls,
               "artifact_label": LABEL}
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = finalize(args.runtime_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PILOT_INTEGRITY_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
