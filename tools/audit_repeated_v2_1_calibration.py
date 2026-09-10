#!/usr/bin/env python3
"""Audit immutable v2.1 clean-calibration shards and publish compact evidence.

The input directories are mirrors of completed remote shards.  Raw traces stay
outside the repository; every published row retains their measured SHA-256 and
the auditor verifies those bytes before admitting a cell.  This command never
loads a simulator, model, provider, or GPU and refuses partial/duplicate grids
or overwrites.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.repeated_v2.calibration_v2_1 import (  # noqa: E402
    CALIBRATION_RECORD_VERSION,
    CALIBRATION_STATE_IDS,
    CALIBRATION_TECHNICAL_SEED,
    PROTOCOL_VERSION,
    group_duplicate_trajectories,
    summarize_task_calibration,
    validate_calibration_record,
)
from cope_benchmark.repeated_v2.canonical import canonical_sha256  # noqa: E402
from cope_benchmark.task_progress import get_task_definition  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _jsonl(rows) -> bytes:
    return b"".join(_encoded(row) for row in rows)


def _csv(rows, fields=None) -> bytes:
    rows = list(rows)
    names = fields or list(rows[0])
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=names, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def _episode_directories(inputs: list[Path]) -> list[Path]:
    result = []
    for root in inputs:
        if not root.is_dir():
            raise ValueError(f"calibration shard is unavailable: {root}")
        if (root / "INFRASTRUCTURE_STOP.txt").exists():
            raise ValueError(f"calibration shard has an infrastructure stop: {root}")
        if not (root / "COMPLETED_SUBSET.txt").is_file():
            raise ValueError(f"calibration shard is incomplete: {root}")
        result.extend(sorted(root.glob("task_*_state_*_seed_*")))
    return result


def audit(inputs: list[Path]) -> tuple[list[dict], list[dict], list[dict]]:
    records, admissions, protocols = [], [], []
    gates = set()
    for shard in inputs:
        protocol_path = shard / "PROTOCOL.txt"
        protocol = _json(protocol_path)
        protocols.append({"shard": str(shard), "sha256": _sha(protocol_path), "protocol": protocol})
        gate_path = shard / "VLA_GATE_EVIDENCE.txt"
        gate = _json(gate_path)
        if gate.get("passed") is not True or gate.get("status") != "ACTUAL_ACTION_PROBE_PASSED":
            raise ValueError(f"shard has no passing production VLA gate: {shard}")
        gates.add(_sha(gate_path))
    if len(gates) != 1:
        raise ValueError("calibration shards used different production VLA gate bytes")
    for episode in _episode_directories(inputs):
        record_path = episode / "CALIBRATION_RECORD.txt"
        terminal_path = episode / "TERMINAL.txt"
        trace_path = episode / "ACTION_TRACE.txt"
        observation_paths = (episode / "INITIAL_OBSERVATION.txt", episode / "TERMINAL_OBSERVATION.txt")
        if not all(path.is_file() for path in (record_path, terminal_path, trace_path, *observation_paths)):
            raise ValueError(f"incomplete terminal evidence: {episode}")
        record = _json(record_path)
        validate_calibration_record(record)
        terminal = _json(terminal_path)
        checks = {
            "record_schema": record["schema_version"] == CALIBRATION_RECORD_VERSION,
            "terminal_hash": _sha(terminal_path) == record["evidence_sha256"],
            "trace_hash": _sha(trace_path) == record["full_trace_sha256"] == terminal["action_trace"]["sha256"],
            "initial_observation_hash": _sha(observation_paths[0]) == terminal["initial_observation"]["sha256"],
            "terminal_observation_hash": _sha(observation_paths[1]) == terminal["terminal_observation"]["sha256"],
            "identity_match": all(record[key] == terminal["policy_identity"][key] for key in (
                "provider_id", "policy_model_id", "checkpoint_sha256",
                "runtime_client_sha256", "runtime_inference_sha256")),
            "nonprivileged_learned_policy": terminal["learned_policy"] is True
            and terminal["uses_privileged_state"] is False,
            "clean_zero_interruptions": terminal["clean_episode"] is True
            and terminal["interruption_count"] == 0,
            "finite_action_validation": terminal["all_action_validations_pass"] is True,
            "no_manual_intervention": record["manual_intervention"] is False,
        }
        if not all(checks.values()):
            raise ValueError(f"terminal admission failed for {episode}: {checks}")
        records.append(record)
        admissions.append({
            "schema_version": "repeated_v2_1_calibration_admission_v1",
            "task_id": record["task_id"], "initial_state_id": record["initial_state_id"],
            "policy_seed": record["policy_seed"], "record": record,
            "record_artifact": {"path": str(record_path), "sha256": _sha(record_path)},
            "terminal_artifact": {"path": str(terminal_path), "sha256": _sha(terminal_path)},
            "trace_artifact": {"path": str(trace_path), "sha256": _sha(trace_path)},
            "checks": checks, "admitted": True,
        })
    expected = {(task, state, CALIBRATION_TECHNICAL_SEED)
                for task in range(10) for state in CALIBRATION_STATE_IDS}
    actual = {(r["task_id"], r["initial_state_id"], r["policy_seed"]) for r in records}
    if len(records) != len(actual) or actual != expected:
        raise ValueError(f"calibration grid differs: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    records.sort(key=lambda r: (r["task_id"], r["initial_state_id"], r["policy_seed"]))
    admissions.sort(key=lambda r: (r["task_id"], r["initial_state_id"], r["policy_seed"]))
    return records, admissions, protocols


def _milestone_witnesses(admissions: list[dict]) -> tuple[list[dict], list[dict]]:
    rows = []
    for admission in admissions:
        trace = Path(admission["trace_artifact"]["path"])
        samples = []
        with trace.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                record = json.loads(line)
                if record.get("record_type") not in {"initial", "environment_result"}:
                    continue
                progress = record.get("progress")
                if isinstance(progress, dict):
                    samples.append((line_number, record.get("policy_step", 0), progress["current"]))
        definition = get_task_definition("libero_10", admission["task_id"])
        commitments = [predicate.name for predicate in definition.predicates if predicate.commitment]
        for name in commitments:
            true_indices = [index for index, sample in enumerate(samples) if sample[2].get(name) is True]
            preserved = []
            for index in true_indices:
                if index + 1 >= len(samples) or samples[index + 1][2].get(name) is not True:
                    continue
                if any(samples[index][2].get(other) is False for other in commitments if other != name):
                    preserved.append({
                        "start_line": samples[index][0], "end_line": samples[index + 1][0],
                        "start_policy_step": samples[index][1], "end_policy_step": samples[index + 1][1],
                    })
            rows.append({
                "task_id": admission["task_id"], "initial_state_id": admission["initial_state_id"],
                "milestone": name, "observed_true": bool(true_indices),
                "terminally_satisfied": bool(samples and samples[-1][2].get(name) is True),
                "preserved_while_another_goal_pending": bool(preserved),
                "first_preservation_witness": json.dumps(preserved[0], separators=(",", ":")) if preserved else "",
                "trace_sha256": admission["trace_artifact"]["sha256"],
            })
    summaries = []
    for task_id in range(10):
        task_rows = [row for row in rows if row["task_id"] == task_id]
        names = sorted({row["milestone"] for row in task_rows})
        summaries.append({
            "task_id": task_id,
            "commitment_predicate_count": len(names),
            "two_independently_verifiable_milestones": len(names) >= 2,
            "milestones_observed_true": sum(any(row["observed_true"] for row in task_rows
                                                 if row["milestone"] == name) for name in names),
            "completed_milestone_preservable": any(
                row["preserved_while_another_goal_pending"] for row in task_rows),
            "preservation_witness_count": sum(
                row["preserved_while_another_goal_pending"] for row in task_rows),
        })
    return rows, summaries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    records, admissions, protocols = audit([path.resolve() for path in args.input])
    milestone_rows, structural_rows = _milestone_witnesses(admissions)
    summaries = [summarize_task_calibration(task, [r for r in records if r["task_id"] == task])
                 for task in range(10)]
    groups = [group for task in range(10)
              for group in group_duplicate_trajectories([r for r in records if r["task_id"] == task])]
    completion_rows = [{"task_id": r["task_id"], "initial_state_id": r["initial_state_id"],
                        "policy_seed": r["policy_seed"], "success": r["success"],
                        "completion_policy_steps": r["completion_policy_steps"],
                        "termination_reason": r["termination_reason"]} for r in records]
    trace_rows = [{"task_id": r["task_id"], "initial_state_id": r["initial_state_id"],
                   "policy_seed": r["policy_seed"], "initial_state_sha256": r["initial_state_sha256"],
                   "raw_policy_action_sequence_sha256": r["raw_policy_action_sequence_sha256"],
                   "environment_policy_action_sequence_sha256": r["environment_policy_action_sequence_sha256"],
                   "full_trace_sha256": r["full_trace_sha256"]} for r in records]
    group_rows = []
    for index, group in enumerate(groups, 1):
        group_rows.append({"duplicate_group_id": f"trajectory-{index:03d}",
                           "task_id": group["task_id"],
                           "initial_state_identity": group["initial_state_identity"],
                           "action_trajectory_sha256": group["action_trajectory_sha256"],
                           "nominal_count": group["nominal_run_count"],
                           "members": json.dumps(group["members"], separators=(",", ":")),
                           "success": group["success"],
                           "completion_policy_steps": group["completion_policy_steps"]})
    summary_rows = []
    for summary in summaries:
        summary_rows.append({**summary,
            "completion_times": json.dumps(summary["completion_times"], separators=(",", ":")),
            "success_interval": json.dumps(summary["success_interval"], separators=(",", ":")),
            "semantic_catalog_gate": "PENDING_PHASE5",
            "final_eligibility_reason": ("PENDING_SEMANTIC_AND_FEASIBILITY_GATES"
                if summary["eligible_success_rate"] else
                (summary["horizon_gate"] if summary["horizon"] is None else "CLEAN_SUCCESS_RATE_OUTSIDE_FROZEN_INTERVAL")),
        })
    out = args.output_dir.resolve()
    protocol_projection = [{key: p["protocol"][key] for key in (
        "version", "task_suite", "initial_state_ids", "policy_seeds", "environment_seed",
        "collection_ceiling_policy_steps", "settling_controls", "stop_rule")}
        for p in protocols]
    projection_hashes = {canonical_sha256(value) for value in protocol_projection}
    if len(projection_hashes) != 1:
        raise ValueError("shards differ on the method-independent calibration protocol projection")
    protocol_audit = {
        "schema_version": "repeated_v2_1_calibration_protocol_audit_v1",
        "protocol_version": PROTOCOL_VERSION,
        "task_independent_projection": protocol_projection[0],
        "task_independent_projection_sha256": next(iter(projection_hashes)),
        "task_scoped_protocols": [{"shard": value["shard"], "sha256": value["sha256"]}
                                  for value in protocols],
        "all_projections_identical": True,
        "provider_calls": 0,
        "vla_calls": 0,
    }
    artifacts = {
        "CLEAN_CALIBRATION_ALL_TASKS.jsonl": _jsonl(records),
        "CALIBRATION_ADMISSION_RECORDS.jsonl": _jsonl(admissions),
        "CLEAN_CALIBRATION_SUMMARY.csv": _csv(summary_rows),
        "CLEAN_COMPLETION_TIMES.csv": _csv(completion_rows),
        "CLEAN_ACTION_TRACE_HASHES.csv": _csv(trace_rows),
        "CLEAN_DUPLICATE_GROUPS.csv": _csv(group_rows),
        "CLEAN_MILESTONE_WITNESSES.csv": _csv(milestone_rows),
        "CLEAN_STRUCTURAL_WITNESS_SUMMARY.csv": _csv(structural_rows),
        "CALIBRATION_PROTOCOL_AUDIT.json": _encoded(protocol_audit),
    }
    for name, data in artifacts.items():
        _write(out / name, data)
    table = "\n".join(
        f"| {s['task_id']} | {s['nominal_trajectories']} | {s['unique_trajectories']} | "
        f"{s['successful_unique_trajectories_by_collection_ceiling']} | {s['clean_success_rate']} | "
        f"{s['completion_times']} | {s['horizon']} | {s['horizon_gate']} |"
        for s in summaries)
    report = f"""# v2.1 clean calibration report

This audit admits exactly 100 real `openvla_native` clean trajectories: ten distinct calibration initial states for each LIBERO-10 task and the frozen technical seed 101. Raw episode artifacts were hash-verified from immutable shard mirrors. No nominal seed replicate is treated as an independent sample.

| Task | Nominal | Unique | Successful unique at ceiling | Success rate at H_clean | Completion steps | H_clean | Horizon gate |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
{table}

The collection ceiling was 520 learned-policy controls after ten recorded settling controls. `H_clean` follows `{PROTOCOL_VERSION}`: `clip(ceil(1.20 * nearest-rank empirical Q95), 320, 520)`, only with at least three successful unique trajectories. The unchanged eligibility interval is inclusive `[0.40, 0.95]`.

All shards used byte-identical production VLA gate evidence. Shard protocol records have separate hashes because they bind their assigned task IDs, BDDL bytes, and state bytes; their method-independent protocol projections are byte-identical with SHA-256 `{canonical_sha256(protocol_projection[0])}`. No CoPE-versus-baseline result was inspected or generated.

`CLEAN_MILESTONE_WITNESSES.csv` reports observational clean-trace evidence separately from the BDDL predicate definitions. A preservation witness requires one goal predicate to remain true across consecutive policy observations while another goal predicate is still false; it is not inferred from terminal success alone.
"""
    _write(out / "CALIBRATION_REPORT.md", report.encode())
    print(json.dumps({"status": "CALIBRATION_V2_1_AUDIT_PASS", "records": len(records),
                      "unique_trajectories": sum(s["unique_trajectories"] for s in summaries),
                      "eligible_by_clean_gate": [s["task_id"] for s in summaries if s["eligible_success_rate"]],
                      "output_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()},
                      "provider_calls": 0, "vla_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
