#!/usr/bin/env python3
"""Validate and summarize the preregistered fresh-state recovery experiment."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


MODES = ("stale_continue", "safe_return_switch", "local_stage_switch")
PAIR_FIELDS = (
    "event_step",
    "action_prefix_sha256",
    "sim_state_before_patch_sha256",
    "eef_at_event",
    "held_position_at_event",
)
INTEGRITY_TRUE_FIELDS = (
    "completed_progress_success",
    "physical_truth_before_first_patch",
    "first_patch_accepted",
    "held_checkpoint_success",
    "patch_preserved_sim_state",
    "patch_emitted_no_action",
    "physical_truth_before_second_patch",
    "held_at_event",
    "second_patch_accepted",
    "hash_chain_valid",
    "contact_force_proxy_measured",
)
KNOWN_SUBSTRATE_FAILURE = "completed progress is not physically true"


def truth(value: str) -> bool:
    return value.strip().lower() == "true"


def load_one(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected one row in {path}, found {len(rows)}")
    return rows[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--prereg-commit", required=True)
    parser.add_argument("--state-start", type=int, default=5)
    parser.add_argument("--state-end", type=int, default=14)
    parser.add_argument("--supersedes", default="")
    return parser.parse_args()


def physical(row: dict[str, str] | None) -> bool:
    return row is not None and truth(row["final_goal_success"])


def hazardous(row: dict[str, str] | None) -> bool:
    if row is None:
        return False
    displacements = json.loads(row["object_displacements_m_json"])
    return bool(
        int(row["robot_protected_contact_steps"]) > 0
        or int(row["robot_environment_contact_steps"]) > 0
        or float(displacements["cream_cheese_1"]) > 0.005
        or float(displacements["butter_1"]) > 0.005
    )


def main() -> int:
    args = parse_args()
    states = tuple(range(args.state_start, args.state_end + 1))
    if len(states) != 10:
        raise ValueError("this preregistered summarizer requires exactly 10 states")
    paired: dict[int, dict[str, dict[str, str] | None]] = {}
    failure_reason: dict[tuple[int, str], str] = {}
    prefix_valid: dict[int, bool] = {}

    for state in states:
        state_rows: dict[str, dict[str, str] | None] = {}
        for mode in MODES:
            csv_path = args.raw_dir / f"state{state}_{mode}.csv"
            log_path = args.raw_dir / f"state{state}_{mode}.txt"
            if not csv_path.exists():
                if not log_path.exists():
                    raise ValueError(f"missing both raw row and log: state {state} {mode}")
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
                if KNOWN_SUBSTRATE_FAILURE not in log_text:
                    raise ValueError(
                        f"unclassified missing raw row: state {state} {mode}"
                    )
                state_rows[mode] = None
                failure_reason[(state, mode)] = KNOWN_SUBSTRATE_FAILURE
                continue

            row = load_one(csv_path)
            if row["state_id"] != str(state) or row["mode"] != mode:
                raise ValueError(f"identity mismatch in {csv_path}")
            for field in INTEGRITY_TRUE_FIELDS:
                if not truth(row[field]):
                    raise ValueError(f"state {state} {mode} failed {field}")
            if truth(row["force_contact_collision_safety_measured"]):
                raise ValueError("proxy telemetry was mislabeled as safety proof")
            if row["sim_state_before_patch_sha256"] != row["sim_state_after_patch_sha256"]:
                raise ValueError(f"state {state} {mode} patch changed MuJoCo state")
            if int(row["post_event_steps"]) != int(row["environment_steps"]) - int(row["event_step"]):
                raise ValueError(f"state {state} {mode} recovery-step mismatch")
            state_rows[mode] = row

        present = [row for row in state_rows.values() if row is not None]
        if len(present) == len(MODES):
            prefix_valid[state] = all(
                len({row[field] for row in present}) == 1 for field in PAIR_FIELDS
            )
            if not prefix_valid[state]:
                raise ValueError(f"state {state} paired-prefix mismatch")
        elif not present and all(
            failure_reason.get((state, mode)) == KNOWN_SUBSTRATE_FAILURE
            for mode in MODES
        ):
            prefix_valid[state] = False
        else:
            raise ValueError(f"state {state} has asymmetric missing arms")
        paired[state] = state_rows

    ledger_fields = (
        "state_id",
        "mode",
        "assigned_status",
        "failure_stage",
        "failure_reason",
        "prefix_integrity_available",
        "event_step",
        "action_prefix_sha256",
        "sim_state_before_patch_sha256",
        "physical_updated_goal_success",
        "within_280_post_event_actions",
        "within_global_600_steps",
        "post_event_steps",
        "stale_commitment_executed",
        "task_relevant_peak_force_proxy_n",
        "task_relevant_force_impulse_proxy_ns",
        "robot_protected_contact_steps",
        "robot_environment_contact_steps",
        "done_object_displacement_m",
        "idle_butter_displacement_m",
        "hazard_proxy_episode",
        "source_csv",
        "source_log",
    )
    ledger: list[dict[str, object]] = []
    for state in states:
        for mode in MODES:
            row = paired[state][mode]
            log_path = args.raw_dir / f"state{state}_{mode}.txt"
            csv_path = args.raw_dir / f"state{state}_{mode}.csv"
            if row is None:
                ledger.append(
                    {
                        "state_id": state,
                        "mode": mode,
                        "assigned_status": "SUBSTRATE_FAILURE_NO_EVENT_ROW",
                        "failure_stage": "completed_progress_validation",
                        "failure_reason": failure_reason[(state, mode)],
                        "prefix_integrity_available": False,
                        "physical_updated_goal_success": False,
                        "within_280_post_event_actions": False,
                        "within_global_600_steps": False,
                        "hazard_proxy_episode": "not_observed",
                        "source_log": str(log_path),
                    }
                )
                continue
            displacements = json.loads(row["object_displacements_m_json"])
            ledger.append(
                {
                    "state_id": state,
                    "mode": mode,
                    "assigned_status": "RAW_ROW_VALIDATED",
                    "failure_stage": "",
                    "failure_reason": "",
                    "prefix_integrity_available": prefix_valid[state],
                    "event_step": row["event_step"],
                    "action_prefix_sha256": row["action_prefix_sha256"],
                    "sim_state_before_patch_sha256": row["sim_state_before_patch_sha256"],
                    "physical_updated_goal_success": physical(row),
                    "within_280_post_event_actions": physical(row) and int(row["post_event_steps"]) <= 280,
                    "within_global_600_steps": physical(row) and truth(row["within_horizon"]),
                    "post_event_steps": row["post_event_steps"],
                    "stale_commitment_executed": truth(row["stale_commitment_executed"]),
                    "task_relevant_peak_force_proxy_n": row["task_relevant_peak_force_proxy_n"],
                    "task_relevant_force_impulse_proxy_ns": row["cumulative_task_relevant_force_impulse_proxy_ns"],
                    "robot_protected_contact_steps": row["robot_protected_contact_steps"],
                    "robot_environment_contact_steps": row["robot_environment_contact_steps"],
                    "done_object_displacement_m": displacements["cream_cheese_1"],
                    "idle_butter_displacement_m": displacements["butter_1"],
                    "hazard_proxy_episode": hazardous(row),
                    "source_csv": str(csv_path),
                    "source_log": str(log_path),
                }
            )
    for item in ledger:
        for field in ledger_fields:
            item.setdefault(field, "")
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ledger_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ledger)

    stale = [paired[state]["stale_continue"] for state in states]
    exact = [paired[state]["safe_return_switch"] for state in states]
    local = [paired[state]["local_stage_switch"] for state in states]
    exact_success = sum(physical(row) for row in exact)
    local_success = sum(physical(row) for row in local)
    stale_negative = sum(
        row is not None and not physical(row) and truth(row["stale_commitment_executed"])
        for row in stale
    )
    exact_280 = sum(
        physical(row) and int(row["post_event_steps"]) <= 280
        for row in exact if row is not None
    )
    local_280 = sum(
        physical(row) and int(row["post_event_steps"]) <= 280
        for row in local if row is not None
    )
    exact_600 = sum(physical(row) and truth(row["within_horizon"]) for row in exact if row)
    local_600 = sum(physical(row) and truth(row["within_horizon"]) for row in local if row)
    prefix_count = sum(prefix_valid.values())

    paired_success_states = [
        state
        for state in states
        if physical(paired[state]["safe_return_switch"])
        and physical(paired[state]["local_stage_switch"])
    ]
    savings = [
        int(paired[state]["safe_return_switch"]["post_event_steps"])  # type: ignore[index]
        - int(paired[state]["local_stage_switch"]["post_event_steps"])  # type: ignore[index]
        for state in paired_success_states
    ]
    local_faster = sum(value > 0 for value in savings)
    median_savings = statistics.median(savings) if savings else float("nan")

    exact_present = [row for row in exact if row is not None]
    local_present = [row for row in local if row is not None]
    exact_hazard = sum(hazardous(row) for row in exact)
    local_hazard = sum(hazardous(row) for row in local)
    exact_robot_protected = sum(int(row["robot_protected_contact_steps"]) > 0 for row in exact_present)
    local_robot_protected = sum(int(row["robot_protected_contact_steps"]) > 0 for row in local_present)
    exact_robot_environment = sum(int(row["robot_environment_contact_steps"]) > 0 for row in exact_present)
    local_robot_environment = sum(int(row["robot_environment_contact_steps"]) > 0 for row in local_present)

    def displaced(row: dict[str, str]) -> bool:
        values = json.loads(row["object_displacements_m_json"])
        return values["cream_cheese_1"] > 0.005 or values["butter_1"] > 0.005

    exact_displacement = sum(displaced(row) for row in exact_present)
    local_displacement = sum(displaced(row) for row in local_present)
    peak_deltas = [
        float(paired[state]["local_stage_switch"]["task_relevant_peak_force_proxy_n"])  # type: ignore[index]
        - float(paired[state]["safe_return_switch"]["task_relevant_peak_force_proxy_n"])  # type: ignore[index]
        for state in paired_success_states
    ]
    impulse_deltas = [
        float(paired[state]["local_stage_switch"]["cumulative_task_relevant_force_impulse_proxy_ns"])  # type: ignore[index]
        - float(paired[state]["safe_return_switch"]["cumulative_task_relevant_force_impulse_proxy_ns"])  # type: ignore[index]
        for state in paired_success_states
    ]

    conditions = {
        "C1_prefix_integrity_10_of_10": prefix_count == 10,
        "C2_local_success_not_fewer_than_exact": local_success >= exact_success,
        "C3_both_at_least_8_of_10": exact_success >= 8 and local_success >= 8,
        "C4_faster_80pct_and_median_at_least_20": bool(
            savings and local_faster / len(savings) >= 0.8 and median_savings >= 20
        ),
        "C5_no_increase_in_hazard_episode_count": bool(
            local_robot_protected <= exact_robot_protected
            and local_robot_environment <= exact_robot_environment
            and local_displacement <= exact_displacement
        ),
    }
    if not conditions["C1_prefix_integrity_10_of_10"]:
        decision = "INCONCLUSIVE — assigned comparison validity failed"
        decision_code = "INCONCLUSIVE_PREFIX_VALIDITY"
    elif all(conditions.values()):
        decision = "RETAIN local staging as an efficiency ablation only"
        decision_code = "RETAIN_EFFICIENCY_ABLATION"
    else:
        decision = "REJECT local staging under the preregistered rule"
        decision_code = "REJECT_PREREGISTERED_RULE"

    pair_lines: list[str] = []
    for state in states:
        e = paired[state]["safe_return_switch"]
        l = paired[state]["local_stage_switch"]
        s = paired[state]["stale_continue"]
        if e is None or l is None or s is None:
            pair_lines.append(
                f"| {state} | SUBSTRATE | SUBSTRATE | SUBSTRATE | NA | NA | NA | NA | NA |"
            )
            continue
        saving = int(e["post_event_steps"]) - int(l["post_event_steps"])
        pair_lines.append(
            f"| {state} | {int(physical(e))} | {int(physical(l))} | "
            f"{int(truth(s['stale_commitment_executed']))} | {e['post_event_steps']} | "
            f"{l['post_event_steps']} | {saving:+d} | {int(hazardous(e))} | {int(hazardous(l))} |"
        )
    condition_lines = [
        f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in conditions.items()
    ]

    def mean_field(source: list[dict[str, str]], field: str) -> float:
        return statistics.mean(float(row[field]) for row in source)

    peak_summary = (
        f"local lower in {sum(value < 0 for value in peak_deltas)}/{len(peak_deltas)}, "
        f"paired mean delta {statistics.mean(peak_deltas):+.2f} N"
        if peak_deltas else "no paired physical successes"
    )
    impulse_summary = (
        f"local lower in {sum(value < 0 for value in impulse_deltas)}/{len(impulse_deltas)}, "
        f"paired mean delta {statistics.mean(impulse_deltas):+.2f} N·s"
        if impulse_deltas else "no paired physical successes"
    )
    failure_states = [state for state in states if not prefix_valid[state]]
    failure_text = (
        "No assigned state was missing an event row."
        if not failure_states
        else (
            f"States {failure_states} produced no event row in all three arms "
            "because completed-progress validation found the cream-cheese "
            "placement physically false. These are method-independent substrate "
            "failures, retained on the assigned denominator and not technically retried."
        )
    )
    supersedes_text = (
        f"This report supersedes `{args.supersedes}`."
        if args.supersedes else ""
    )
    report = f"""# Preregistered fresh-state recovery result

Date: 2026-08-01

Preregistration commit: `{args.prereg_commit}`

Evidence class: privileged oracle mechanism experiment on previously
uninspected LIBERO task-1 initial states {args.state_start}–{args.state_end}. This is not learned-policy CoPE
versus FSR-PC evidence and does not establish safety.

{supersedes_text}

## Assigned denominator and integrity

Valid raw rows: {len(exact_present) + len(local_present) + sum(row is not None for row in stale)}/30.
{failure_text} States with complete matching prefixes: {prefix_count}/10.

| Endpoint | Stale continue | Exact return | Local stage |
|---|---:|---:|---:|
| Physical updated-goal success, assigned denominator | {sum(physical(row) for row in stale)}/10 | {exact_success}/10 | {local_success}/10 |
| Success within fixed 280 post-event actions | {sum(physical(row) and int(row['post_event_steps']) <= 280 for row in stale if row)}/10 | {exact_280}/10 | {local_280}/10 |
| Success within legacy global 600 steps | {sum(physical(row) and truth(row['within_horizon']) for row in stale if row)}/10 | {exact_600}/10 | {local_600}/10 |
| Expected stale commitment executed | {stale_negative}/10 | {sum(row is not None and truth(row['stale_commitment_executed']) for row in exact)}/10 | {sum(row is not None and truth(row['stale_commitment_executed']) for row in local)}/10 |

## Event-qualified recovery evidence

Paired physical successes: {len(paired_success_states)}/10 assigned states.
Local was faster in {local_faster}/{len(savings)} paired successes. Mean
exact-minus-local saving: {statistics.mean(savings):.1f} actions; median:
{median_savings:.1f} actions.

| Metric, event-qualified arms | Exact return | Local stage |
|---|---:|---:|
| Mean post-event actions | {mean_field(exact_present, 'post_event_steps'):.1f} | {mean_field(local_present, 'post_event_steps'):.1f} |
| Mean task-relevant peak-force proxy (N) | {mean_field(exact_present, 'task_relevant_peak_force_proxy_n'):.2f} | {mean_field(local_present, 'task_relevant_peak_force_proxy_n'):.2f} |
| Mean force-impulse proxy (N·s) | {mean_field(exact_present, 'cumulative_task_relevant_force_impulse_proxy_ns'):.2f} | {mean_field(local_present, 'cumulative_task_relevant_force_impulse_proxy_ns'):.2f} |
| Any preregistered hazard-proxy episode | {exact_hazard}/10 | {local_hazard}/10 |
| Robot/protected-object contact episode | {exact_robot_protected}/10 | {local_robot_protected}/10 |
| Robot/environment contact episode | {exact_robot_environment}/10 | {local_robot_environment}/10 |
| Protected/idle displacement >5 mm | {exact_displacement}/10 | {local_displacement}/10 |

Peak proxy: {peak_summary}. Impulse proxy: {impulse_summary}.

## Per-state evidence

| State | Exact goal | Local goal | Stale executed | Exact actions | Local actions | Exact−local | Exact hazard | Local hazard |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(pair_lines)}

## Frozen decision rule

| Condition | Result |
|---|---|
{chr(10).join(condition_lines)}

Decision: **{decision}**.

The frozen protocol states that a C1 failure invalidates the assigned
comparison, whereas failure of C2–C5 rejects local staging. Any
method-independent substrate failure therefore makes this run inconclusive for
the retain/reject decision. Event-qualified pairs remain conditional mechanism
evidence, but cannot repair an assigned-denominator validity failure. States
{args.state_start}–{args.state_end} may not be reused as fresh data for a
modified rule.
"""
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print(json.dumps({"prefix_states": prefix_count, "exact_success": exact_success,
                      "local_success": local_success, "conditions": conditions,
                      "decision_code": decision_code}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
