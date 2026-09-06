"""Integrity-first analysis of continuous repeated-v2 trajectories.

Raw records are immutable inputs. Missing cells are never reconstructed, imputed,
silently dropped, or turned into successes. Protocols and information conditions
remain separate. Baseline K=0 is a checkpoint, never an injected event or call.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .statistics import (holm_adjust, master_session_cluster_bootstrap,
                         noninferiority, paired_risk_difference, wilson_interval)

COPE = "cope_typed_edit"
GENERIC = "generic_persistent_edit"
NONPERSISTENT = ("full_state_regeneration", "full_history_replan", "rag_replan",
                 "summary_memory_replan", "skill_local_replan", "classical_execution_monitor")
METHODS = (COPE, GENERIC) + NONPERSISTENT
CHECKPOINTS = {"controlled": (0, 1, 2, 4, 8), "end_to_end": (0, 1, 2, 4)}
FAILURE_FIELDS = ("history_corruption", "completed_step_regression",
                  "wrong_occurrence_execution", "stale_restore", "invalid_restore",
                  "hard_constraint_violations", "timeout", "manual_intervention",
                  "invalid_transaction", "wrong_target_actions", "redundant_actions")
LATENCY_FIELDS = ("high_level_calls", "input_tokens", "output_tokens", "reasoner_seconds",
                  "validation_seconds", "compilation_seconds", "planning_seconds",
                  "vla_inference_seconds", "time_to_resume", "vla_steps")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Strict JSONL reader, regardless of extension; rejects duplicate keys/torn rows."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    records = []
    for i, line in enumerate(Path(path).read_text().splitlines(keepends=True), 1):
        if not line.endswith("\n") or not line.strip():
            raise ValueError(f"torn or blank record at line {i}")
        value = json.loads(line, object_pairs_hook=pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        if not isinstance(value, dict):
            raise ValueError(f"record {i} is not an object")
        records.append(value)
    return records


def _key(row: Mapping[str, Any]) -> tuple:
    # A protocol directory may hold just one information condition, but it must
    # still be explicit: otherwise identically named sessions could be pooled.
    return (row.get("information_condition", row.get("condition")), row.get("protocol"),
            row.get("master_episode_id"), row.get("method"), row.get("event_index"))


def _metric(row: Mapping[str, Any], name: str) -> Any:
    found = []
    for source in (row.get("metrics", {}), row.get("evaluation", {}), row):
        if isinstance(source, Mapping) and name in source:
            found.append(source[name])
    if any(value != found[0] for value in found[1:]):
        raise ValueError(f"contradictory copies of {name}")
    return found[0] if found else None


def _binary(value: Any) -> int:
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ValueError("outcome must be a literal bool or integer 0/1")
    return int(value)


def _success(row: Mapping[str, Any]) -> int:
    values = [source[key] for source in (row, row.get("metrics", {}), row.get("evaluation", {}))
              if isinstance(source, Mapping) for key in ("success", "final_active_task_success_after_last_event") if key in source]
    present = [_binary(value) for value in values]
    if not present or any(value != present[0] for value in present):
        raise ValueError("missing or contradictory success outcomes")
    return present[0]


def _incidence(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict)):
        return int(bool(value))
    if type(value) in (int, float, bool) and math.isfinite(value) and value >= 0:
        return int(value > 0)
    raise ValueError("failure metric must be nonnegative count, bool, or collection")


def audit_cells(manifest: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]],
                *, protocol: str, condition: str, freeze_sha256: str | None = None) -> dict:
    """Audit one complete protocol/condition, including noncheckpoint event cells."""
    errors: list[str] = []
    if protocol not in CHECKPOINTS:
        return {"valid": False, "errors": ["unsupported protocol"], "expected_cells": 0,
                "observed_cells": len(records), "missing": [], "duplicate": [], "unexpected": []}
    expected, masters = set(), {}
    for row in manifest:
        mid = row.get("master_episode_id")
        if not isinstance(mid, str) or not mid or mid in masters:
            errors.append("missing/duplicate manifest master identity")
            continue
        masters[mid] = row
        try:
            spec = row["protocol_prefixes"][protocol]
            if type(row["pair_fields"]["task_id"]) not in (int, str):
                errors.append(f"{mid}: invalid task identity")
            methods = row["methods"]["non_oracle"] + row["methods"]["oracle"]
            if set(row["methods"]["non_oracle"]) != set(METHODS) or len(methods) != len(set(methods)):
                errors.append(f"{mid}: incorrect or duplicate method roster")
            if condition not in row["information_conditions"]:
                errors.append(f"{mid}: condition absent from frozen manifest")
            if tuple(spec["checkpoints"]) != CHECKPOINTS[protocol] or spec["event_count"] != CHECKPOINTS[protocol][-1]:
                errors.append(f"{mid}: incorrect continuous protocol prefix")
            for method in methods:
                for event in range(spec["event_count"] + 1):
                    expected.add((condition, protocol, mid, method, event))
        except (KeyError, TypeError, ValueError):
            errors.append(f"{mid}: malformed manifest")
    if not masters:
        errors.append("empty manifest; no eligible formal master sessions")
    observed = Counter()
    for i, row in enumerate(records):
        key = _key(row)
        if "condition" in row and "information_condition" in row and row["condition"] != row["information_condition"]:
            errors.append(f"row {i}: contradictory information-condition identity")
        try:
            observed[key] += 1
        except TypeError:
            errors.append(f"row {i}: non-scalar cell identity")
            continue
        if type(key[-1]) is not int:
            errors.append(f"row {i}: event index must be an integer")
        try:
            success = _success(row)
            for field in FAILURE_FIELDS:
                _incidence(_metric(row, field))
            for failure in ("timeout", "manual_intervention", "wrong_occurrence_execution",
                            "hard_constraint_violations", "completed_step_regression"):
                incidence = _incidence(_metric(row, failure))
                if incidence is None:
                    errors.append(f"row {i}: unmeasured mandatory evaluator outcome {failure}")
                if incidence and success:
                    errors.append(f"row {i}: {failure} incorrectly scored as success")
            reached = _metric(row, "required_events_reached")
            if type(reached) is not bool or success and not reached:
                errors.append(f"row {i}: missing/contradictory event-reach evidence")
            for name in ("planning_fidelity_exact", "planning_fidelity_macro_f1"):
                metric = _metric(row, name)
                if metric is not None and (type(metric) not in (int, float, bool) or
                    not math.isfinite(metric) or not 0 <= metric <= 1):
                    errors.append(f"row {i}: invalid {name}")
        except ValueError as exc:
            errors.append(f"row {i}: {exc}")
        status = str(row.get("status", ""))
        if status.upper() not in {"COMPLETE", "COMPLETED", "SUCCESS", "METHOD_FAILURE", "FAILED",
                                  "UNREACHED_DUE_TO_PRIOR_FAILURE", "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE",
                                  "CHECKPOINT", "VALID", "METHOD_TIMEOUT", "METHOD_TERMINATED_BEFORE_REQUIRED_EVENT",
                                  "METHOD_REJECTED_TERMINATED", "METHOD_PLANNING_FAILURE", "METHOD_COMPILATION_FAILURE",
                                  "METHOD_ADAPTATION_FAILURE", "METHOD_RECOVERY_EXECUTION_FAILURE", "EVENT_TRIGGER_WINDOW_MISSED"}:
            errors.append(f"row {i}: inadmissible status {status!r}")
        elif status.upper() not in {"COMPLETE", "COMPLETED", "SUCCESS", "CHECKPOINT", "VALID"}:
            try:
                if _success(row):
                    errors.append(f"row {i}: failure/unreached cell incorrectly scored as success")
            except ValueError:
                pass
        if key[3] == "oracle_persistent_update":
            if row.get("evidence_admissibility") != "diagnostic_oracle" or row.get("privileged") is not True:
                errors.append(f"row {i}: oracle lacks explicit diagnostic privileged label")
        elif row.get("evidence_admissibility") != "formal" or row.get("privileged", False) is not False:
            errors.append(f"row {i}: evidence is not non-privileged formal evidence")
        if row.get("phase") != "formal" or row.get("fixture") is not False:
            errors.append(f"row {i}: missing/nonformal phase or fixture evidence")
        if freeze_sha256 is not None and row.get("freeze_sha256") != freeze_sha256:
            errors.append(f"row {i}: frozen identity mismatch")
        master = masters.get(key[2], {})
        if row.get("master_schedule_sha256") != master.get("master_schedule_sha256") or not row.get("master_schedule_sha256"):
            errors.append(f"row {i}: master schedule identity mismatch")
        try:
            calls = _metric(row, "high_level_calls")
            if type(calls) is not int or calls < 0 or key[-1] == 0 and calls != 0:
                errors.append(f"row {i}: missing/invalid event reasoner call count")
            if type(calls) is int and (calls > 1 or "UNREACHED" in status.upper() and calls != 0):
                errors.append(f"row {i}: duplicate or phantom reasoner call")
        except ValueError as exc:
            errors.append(f"row {i}: {exc}")
    missing = sorted(expected - set(observed), key=str)
    unexpected = sorted(set(observed) - expected, key=str)
    duplicate = sorted((key for key, count in observed.items() if count > 1), key=str)
    if missing or unexpected or duplicate:
        errors.append("missing, duplicate, or unexpected cells invalidate analysis")
    trajectories = defaultdict(list)
    for row in records:
        key = _key(row)
        if all(type(x) is str for x in key[:4]) and type(key[-1]) is int:
            trajectories[key[:4]].append(row)
    for key, rows in trajectories.items():
        failure = None
        for row in sorted(rows, key=lambda r:r["event_index"]):
            status = str(row.get("status", "")).upper()
            if "UNREACHED" in status:
                if failure is None:
                    errors.append(f"{key}: unreached cell has no prior retained terminal failure")
                elif row.get("source_boundary_event_index") != failure[0] or row.get("prior_failure") != failure[1]:
                    errors.append(f"{key}: unreached source boundary/failure mismatch")
                if not isinstance(row.get("source_boundary_sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",row["source_boundary_sha256"]):
                    errors.append(f"{key}: unreached source snapshot digest absent")
            elif failure is not None:
                errors.append(f"{key}: a terminal failure was followed by a restarted/recovered cell")
            elif status not in {"COMPLETE", "COMPLETED", "SUCCESS", "CHECKPOINT", "VALID"}:
                failure = (row["event_index"], row.get("status"))
    return {"valid": not errors, "errors": errors, "expected_cells": len(expected),
            "observed_cells": len(records), "master_sessions": len(masters),
            "missing": missing, "duplicate": duplicate, "unexpected": unexpected}


def _rate(rows: Sequence[Mapping[str, Any]], metric: str) -> float | None:
    values = [_incidence(_metric(row, metric)) for row in rows]
    return sum(values) / len(values) if values and None not in values else None


def _mean_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> float | None:
    values = [_metric(row, metric) for row in rows]
    if not values or any(type(x) not in (int, float, bool) or not math.isfinite(x) for x in values):
        return None
    return sum(values) / len(values)


def _temporal_link(row: Mapping[str, Any]) -> bool:
    """Require the measured planning problem to be the problem executed afterward."""
    problem = row.get("planning_problem")
    if not isinstance(problem, Mapping) or _metric(row, "fidelity_precedes_execution") is not True:
        return False
    digest = hashlib.sha256(_canonical(problem).encode()).hexdigest()
    if any(_metric(row, name) != digest for name in ("planning_problem_sha256",
            "pre_execution_fidelity_problem_sha256", "execution_problem_sha256")):
        return False
    before, after = _metric(row, "fidelity_evaluated_at"), _metric(row, "execution_started_at")
    return all(type(x) in (int,float) and math.isfinite(x) and x >= 0 for x in (before,after)) and before <= after


def analyze_protocol(manifest: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]],
                     *, protocol: str, condition: str, comparator: str,
                     freeze_sha256: str, replicates: int = 10000, seed: int = 20260906) -> dict:
    """Numerical summaries only after the entire expected cell set passes integrity."""
    integrity = audit_cells(manifest, records, protocol=protocol, condition=condition,
                            freeze_sha256=freeze_sha256)
    result = {"protocol": protocol, "condition": condition, "comparator": comparator,
              "integrity": integrity, "summary_by_checkpoint": [], "summary_by_task": [],
              "paired_tests": [], "failure_taxonomy": [], "latency_breakdown": [],
              "planning_fidelity": []}
    if comparator not in NONPERSISTENT:
        integrity["errors"].append("primary comparator not frozen from allowed development candidates")
        integrity["valid"] = False
    if not integrity["valid"]:
        return result
    checkpoints = CHECKPOINTS[protocol]
    terminal = checkpoints[-1]
    by_method = defaultdict(list)
    curves = defaultdict(lambda: defaultdict(dict))
    task_ids = {row["master_episode_id"]: row["pair_fields"]["task_id"] for row in manifest}
    task_rows = defaultdict(list)
    for row in records:
        method, mid, k = row["method"], row["master_episode_id"], row["event_index"]
        by_method[method].append(row)
        if k in checkpoints:
            curves[method][mid][k] = _success(row)
            task_rows[(method, task_ids[mid], k)].append(row)
    for method, masters in sorted(curves.items()):
        for k in checkpoints:
            vals = [curve[k] for curve in masters.values()]
            low, high = wilson_interval(sum(vals), len(vals))
            result["summary_by_checkpoint"].append(dict(protocol=protocol, condition=condition,
                method=method, checkpoint=k, master_sessions=len(vals), successes=sum(vals),
                success_rate=sum(vals)/len(vals), wilson_lower=low, wilson_upper=high))
    for (method, task, k), rows in sorted(task_rows.items(), key=lambda x: str(x[0])):
        n, s = len(rows), sum(_success(row) for row in rows)
        low, high = wilson_interval(s, n)
        result["summary_by_task"].append(dict(protocol=protocol, condition=condition, method=method,
            task_id=task, checkpoint=k, master_sessions=n, successes=s, success_rate=s/n,
            wilson_lower=low, wilson_upper=high))
    for method in METHODS:
        if method == COPE:
            continue
        paired = paired_risk_difference({mid: c[terminal] for mid, c in curves[COPE].items()},
            {mid: c[terminal] for mid, c in curves[method].items()}, replicates=replicates, seed=seed)
        result["paired_tests"].append(dict(protocol=protocol, condition=condition, checkpoint=terminal,
            treatment=COPE, comparator=method, primary=(protocol == "end_to_end" and
            condition == "evidence_matched" and method == comparator), **paired))
    result["noninferiority"] = noninferiority(
        {mid: c[terminal] for mid, c in curves[COPE].items()},
        {mid: c[terminal] for mid, c in curves[GENERIC].items()}, replicates=replicates, seed=seed)
    result["degradation"] = master_session_cluster_bootstrap(curves[COPE], curves[comparator],
        checkpoints=checkpoints, replicates=replicates, seed=seed)["slopes"]
    for method, rows in sorted(by_method.items()):
        terminal_rows = [row for row in rows if row["event_index"] == terminal]
        events = [row for row in rows if row["event_index"] > 0]
        for field in FAILURE_FIELDS:
            per_master = defaultdict(list)
            for row in events:
                per_master[row["master_episode_id"]].append(_incidence(_metric(row, field)))
            observed = [int(any(v)) for v in per_master.values() if None not in v]
            result["failure_taxonomy"].append(dict(protocol=protocol, condition=condition,
                method=method, failure=field, master_sessions=len(per_master),
                measured_sessions=len(observed), affected_sessions=sum(observed) if observed else None,
                incidence=sum(observed)/len(observed) if observed else None,
                complete=len(observed)==len(per_master)))
        # This opportunity composite has the fixed scheduled-event denominator.
        # An explicit durable unreached failure contributes zero, never a new row.
        fidelity = [0 if "UNREACHED" in str(row["status"]).upper() else
                    _metric(row, "planning_fidelity_exact") for row in events]
        opportunity = (sum(fidelity)/len(fidelity) if fidelity and all(
            type(x) in (int, bool) and x in (0, 1) for x in fidelity) else None)
        reached_events = [r for r in events if "UNREACHED" not in str(r["status"]).upper()]
        result["planning_fidelity"].append(dict(protocol=protocol, condition=condition, method=method,
            pre_execution_exact_match=opportunity,
            reached_only_exact_match=_mean_metric(reached_events, "planning_fidelity_exact"),
            scheduled_events=len(events), reached_events=len(reached_events),
            unreached_fraction=1-len(reached_events)/len(events),
            field_macro_f1=_mean_metric(events, "planning_fidelity_macro_f1"),
            terminal_corruption=_rate(terminal_rows, "history_corruption"),
            terminal_regression=_rate(terminal_rows, "completed_step_regression"),
            fidelity_precedes_execution=all("UNREACHED" in str(r["status"]).upper() or
                _temporal_link(r) for r in events)))
        result["failure_taxonomy"].append(dict(protocol=protocol, condition=condition, method=method,
            failure="early_failure_or_unreached", master_sessions=len(curves[method]),
            measured_sessions=len(curves[method]), affected_sessions=len({r["master_episode_id"]
            for r in events if r["status"] not in {"COMPLETE","COMPLETED","SUCCESS","CHECKPOINT","VALID"}}),
            incidence=len({r["master_episode_id"] for r in events if r["status"] not in
            {"COMPLETE","COMPLETED","SUCCESS","CHECKPOINT","VALID"}})/len(curves[method]),complete=True))
        for field in LATENCY_FIELDS:
            per_master = defaultdict(list)
            for row in events:
                per_master[row["master_episode_id"]].append(_metric(row, field))
            sums = [sum(v) for v in per_master.values() if all(type(x) in (int, float)
                    and math.isfinite(x) and x >= 0 for x in v)]
            result["latency_breakdown"].append(dict(protocol=protocol, condition=condition, method=method,
                metric=field, measured_sessions=len(sums), master_sessions=len(per_master),
                mean_session_total=sum(sums)/len(sums) if sums else None,
                complete=len(sums)==len(per_master)))
    return result


def comparison_evidence(analysis: Mapping[str, Any], *, evidence_parity: bool | None = None,
                        reasoner_call_parity: bool | None = None):
    """Map audited estimates to binding gates; missing measurements stay unknown."""
    from .claim_decision import ComparisonEvidence
    if not analysis["integrity"]["valid"]:
        raise ValueError("invalid cells cannot become claim evidence")
    if analysis["condition"] != "evidence_matched":
        raise ValueError("secondary token-matched condition cannot supply binding runtime claim evidence")
    method = analysis["comparator"]
    paired = next(r for r in analysis["paired_tests"] if r["comparator"] == method)
    generic = next(r for r in analysis["paired_tests"] if r["comparator"] == GENERIC)
    fidelity = {r["method"]: r for r in analysis["planning_fidelity"]}
    def incidence(arm, failure):
        row = next(r for r in analysis["failure_taxonomy"] if r["method"] == arm and r["failure"] == failure)
        return row["incidence"] if row["complete"] else None
    slopes = analysis["degradation"]
    return ComparisonEvidence(protocol=analysis["protocol"], checkpoint=CHECKPOINTS[analysis["protocol"]][-1],
        risk_difference=paired["risk_difference"], paired_ci_lower=paired["ci_lower"],
        paired_ci_upper=paired["ci_upper"], degradation_slope_difference=slopes["difference"],
        degradation_ci_lower=slopes["ci_lower"], cope_corruption_rate=incidence(COPE,"history_corruption"),
        comparator_corruption_rate=incidence(method,"history_corruption"),
        cope_regression_rate=incidence(COPE,"completed_step_regression"),
        comparator_regression_rate=incidence(method,"completed_step_regression"),
        cope_pre_execution_fidelity=fidelity[COPE]["pre_execution_exact_match"],
        comparator_pre_execution_fidelity=fidelity[method]["pre_execution_exact_match"],
        fidelity_precedes_execution=fidelity[COPE]["fidelity_precedes_execution"] and
                                   fidelity[method]["fidelity_precedes_execution"],
        generic_ni_lower=analysis["noninferiority"]["ci_lower"],
        evidence_parity=evidence_parity, reasoner_call_parity=reasoner_call_parity,
        generic_risk_difference=generic["risk_difference"], generic_ci_lower=generic["ci_lower"],
        generic_ci_upper=generic["ci_upper"])


def correct_secondary_family(analyses: Sequence[dict]) -> dict:
    """Fixed 13-slot Holm family; unobserved slots never become result cells."""
    rows = [r for a in analyses if a["condition"] == "evidence_matched"
            for r in a["paired_tests"] if not r["primary"]]
    pvalues = {f"{r['protocol']}/{r['comparator']}": r["mcnemar_p"] for r in rows}
    if len(pvalues) != len(rows) or len(rows) > 13:
        raise ValueError("duplicate or unexpected secondary hypothesis")
    # Missing hypotheses count against multiplicity; p=1 only exists internally.
    padded = {**pvalues, **{f"unobserved-slot-{i}": 1.0 for i in range(13-len(rows))}}
    adjusted = holm_adjust(padded)
    for row in rows:
        row["holm_p"] = adjusted[f"{row['protocol']}/{row['comparator']}"]
        row["holm_family_complete"] = len(rows) == 13
    return {"prespecified_size": 13, "observed_hypotheses": len(rows), "complete": len(rows)==13}


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] = ()) -> None:
    names = list(dict.fromkeys([*fields, *(key for row in rows for key in row)]))
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _canonical(value) if isinstance(value, (dict, list, tuple)) else value
                             for key, value in row.items()})


def write_artifacts(output_dir: str | Path, analyses: Sequence[dict], decision: Any,
                    *, provenance: Mapping[str, Any], notes: Sequence[str] = ()) -> Path:
    """Exclusive MD/CSV/TXT delivery. No numeric tables from invalid evidence."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    decision_markdown = decision.to_markdown() if hasattr(decision, "to_markdown") else None
    decision = asdict(decision) if hasattr(decision, "__dataclass_fields__") else dict(decision)
    with (output / "integrity_report.txt").open("x") as handle:
        handle.write(json.dumps({"analyses": [a["integrity"] for a in analyses],
                                 "provenance": dict(provenance)}, indent=2, allow_nan=False)+"\n")
    valid = [] if decision.get("status") == "INVALID_RUN" else [a for a in analyses if a["integrity"]["valid"]]
    tables = ("summary_by_checkpoint", "summary_by_task", "planning_fidelity", "paired_tests",
              "failure_taxonomy", "latency_breakdown")
    for name in tables:
        write_csv(output / f"{name}.csv", [row for a in valid for row in a[name]], ("protocol", "condition"))
    write_csv(output / "summary_by_method.csv", [r for a in valid for r in a["summary_by_checkpoint"]
              if r["checkpoint"] == CHECKPOINTS[a["protocol"]][-1]], ("protocol", "condition", "method"))
    write_csv(output / "history_corruption.csv", [r for a in valid for r in a["failure_taxonomy"]
              if r["failure"] in ("history_corruption", "completed_step_regression")], ("protocol", "condition", "method"))
    for name, key in (("noninferiority", "noninferiority"), ("degradation_slopes", "degradation")):
        write_csv(output / f"{name}.csv", [dict(protocol=a["protocol"], condition=a["condition"],
                  **a[key]) for a in valid], ("protocol", "condition"))
    write_csv(output / "degradation_curve.csv", [r for a in valid for r in a["summary_by_checkpoint"]],
              ("protocol", "condition", "method", "checkpoint", "success_rate", "wilson_lower", "wilson_upper"))
    table = ["# Paper table", "", "| Protocol | Condition | Method | K | Success | Wilson 95% |",
             "|---|---|---|---:|---:|---:|"]
    for a in valid:
        for r in a["summary_by_checkpoint"]:
            if r["checkpoint"] == CHECKPOINTS[a["protocol"]][-1]:
                table.append(f"| {r['protocol']} | {r['condition']} | {r['method']} | {r['checkpoint']} | "
                             f"{r['successes']}/{r['master_sessions']} | {r['wilson_lower']:.3f}–{r['wilson_upper']:.3f} |")
    if not valid:
        table += ["", "No admissible formal outcome cells. Empty tables do not denote zero performance."]
    (output / "paper_table.md").write_text("\n".join(table)+"\n")
    curves_md = ["# Degradation curves", "", "Each point is a checkpoint on the same continuous master sessions. "
                 "CSV includes descriptive Wilson intervals; the paired slope test uses joint session resampling.", ""]
    for a in valid:
        for method in (COPE, GENERIC, a["comparator"]):
            curve = [r for r in a["summary_by_checkpoint"] if r["method"] == method]
            curves_md += [f"## {a['protocol']} / {a['condition']} / {method}", "", "```mermaid", "xychart-beta",
                '    x-axis "Interruption checkpoint K" [' + ', '.join(str(r["checkpoint"]) for r in curve) + '] ',
                '    y-axis "Active-task success probability" 0 --> 1',
                '    line [' + ', '.join(f"{r['success_rate']:.6f}" for r in curve) + ']', "```", ""]
    if not valid:
        curves_md.append("No curve drawn: no admissible formal observations.")
    (output / "paper_curves.md").write_text("\n".join(curves_md)+"\n")
    status = decision.get("status", "BLOCKED_FORMAL_EVIDENCE_UNAVAILABLE")
    report = ["# Repeated-interruption v2 report", "", f"Decision: **{status}**.", "", *notes, "",
              "Controlled mechanism and learned-VLA evidence are separate. Each master session is one statistical unit; "
              "all checkpoints come from its continuous trajectory. Missing or invalid cells are never imputed or dropped.", "",
              "The prespecified degradation analysis is a paired master-session bootstrap of probability-scale slopes "
              "against log2(K+1). Wilson intervals are descriptive per-method intervals; paired bootstrap intervals "
              "support comparisons. A singular primary exact McNemar test remains unadjusted; 13 secondary contrasts "
              "belong to one Holm family. The non-inferiority margin is −0.05 with a one-sided 95% lower bound.", "",
              "Failure categories overlap. Missing mechanism or timing metrics remain unmeasured and cannot pass claim gates.", "",
              "See paper_table.md and degradation_curve.csv for the table and curve data. All output formats are MD/CSV/TXT.", "",
              "Statistical references: [exact McNemar](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html), "
              "[paired resampling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).", "",
              "## Provenance", "", "```json", json.dumps(dict(provenance), indent=2, allow_nan=False), "```", ""]
    if not valid:
        report.insert(4, "No formal performance estimate is available. This is a blocked/invalid evidence report, not a negative experiment result.")
    (output / "REPORT.md").write_text("\n".join(report))
    claim = ["# Claim decision", "", f"**{status}**", "", "```json",
             json.dumps(decision, indent=2, allow_nan=False), "```", ""]
    (output / "CLAIM_DECISION.md").write_text(decision_markdown or "\n".join(claim))
    return output
