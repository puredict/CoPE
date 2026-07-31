#!/usr/bin/env python3
"""Validate paired recovery telemetry and write a leakage-aware report."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


MODES = ("safe_return_switch", "local_stage_switch")
PAIR_FIELDS = (
    "event_step",
    "action_prefix_sha256",
    "sim_state_before_patch_sha256",
    "eef_at_event",
    "held_position_at_event",
)
REFERENCE_NAMES = {
    "safe_return_switch": "state{state}_pre_release_safe_return_switch.csv",
    "local_stage_switch": "state{state}_local_stage_switch.csv",
}
BUDGETS = (230, 240, 250, 260, 270, 280)


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
    parser.add_argument("--exact-reference-dir", type=Path, required=True)
    parser.add_argument("--stage-reference-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[dict[str, str]] = []
    reference_dirs = {
        "safe_return_switch": args.exact_reference_dir,
        "local_stage_switch": args.stage_reference_dir,
    }
    for state in range(5):
        pair: list[dict[str, str]] = []
        for mode in MODES:
            path = args.raw_dir / f"state{state}_{mode}.csv"
            row = load_one(path)
            if row["state_id"] != str(state) or row["mode"] != mode:
                raise ValueError(f"identity mismatch in {path}")
            for field in (
                "patch_preserved_sim_state",
                "patch_emitted_no_action",
                "physical_truth_before_first_patch",
                "physical_truth_before_second_patch",
                "held_at_event",
                "second_patch_accepted",
                "hash_chain_valid",
                "contact_force_proxy_measured",
            ):
                if not truth(row[field]):
                    raise ValueError(f"state {state} {mode} failed {field}")
            if truth(row["force_contact_collision_safety_measured"]):
                raise ValueError("proxy telemetry was mislabeled as safety proof")
            post_steps = int(row["post_event_steps"])
            if post_steps != int(row["environment_steps"]) - int(row["event_step"]):
                raise ValueError(f"state {state} {mode} recovery-step mismatch")

            reference_name = REFERENCE_NAMES[mode].format(state=state)
            reference = load_one(reference_dirs[mode] / reference_name)
            for field in (
                *PAIR_FIELDS,
                "environment_steps",
                "final_goal_success",
                "stale_commitment_executed",
                "within_horizon",
            ):
                if row[field] != reference[field]:
                    raise ValueError(
                        f"telemetry changed state {state} {mode} field {field}"
                    )

            displacements = json.loads(row["object_displacements_m_json"])
            row["done_object_displacement_m"] = str(displacements["cream_cheese_1"])
            row["idle_butter_displacement_m"] = str(displacements["butter_1"])
            row["contact_active_fraction"] = str(
                int(row["contact_active_steps"]) / post_steps
            )
            row["split"] = "development" if state == 0 else "held_out_validation"
            row["source_csv"] = str(path)
            pair.append(row)
            rows.append(row)
        for field in PAIR_FIELDS:
            if len({row[field] for row in pair}) != 1:
                raise ValueError(f"state {state} paired-prefix mismatch: {field}")

    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    for row in rows:
        for field in fields:
            row.setdefault(field, "")
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    held_out = [row for row in rows if row["split"] == "held_out_validation"]

    def selected(mode: str, source=held_out) -> list[dict[str, str]]:
        return [row for row in source if row["mode"] == mode]

    def gate_success(row: dict[str, str]) -> bool:
        return truth(row["final_goal_success"]) and truth(row["within_horizon"])

    exact = selected("safe_return_switch")
    stage = selected("local_stage_switch")
    exact_steps = [int(row["post_event_steps"]) for row in exact]
    stage_steps = [int(row["post_event_steps"]) for row in stage]
    savings = [
        exact_steps[index] - stage_steps[index]
        for index in range(len(exact_steps))
    ]
    peak_force_deltas = [
        float(stage[index]["task_relevant_peak_force_proxy_n"])
        - float(exact[index]["task_relevant_peak_force_proxy_n"])
        for index in range(len(exact))
    ]
    impulse_deltas = [
        float(stage[index]["cumulative_task_relevant_force_impulse_proxy_ns"])
        - float(exact[index]["cumulative_task_relevant_force_impulse_proxy_ns"])
        for index in range(len(exact))
    ]

    budget_lines = []
    for budget in BUDGETS:
        exact_count = sum(step <= budget for step in exact_steps)
        stage_count = sum(step <= budget for step in stage_steps)
        budget_lines.append(
            f"| {budget} | {exact_count}/4 | {stage_count}/4 |"
        )

    pair_lines = []
    for index, state in enumerate(range(1, 5)):
        pair_lines.append(
            "| "
            f"{state} | {exact_steps[index]} | {stage_steps[index]} | "
            f"{savings[index]:+d} | "
            f"{float(exact[index]['task_relevant_peak_force_proxy_n']):.2f} | "
            f"{float(stage[index]['task_relevant_peak_force_proxy_n']):.2f} | "
            f"{peak_force_deltas[index]:+.2f} | "
            f"{float(exact[index]['cumulative_task_relevant_force_impulse_proxy_ns']):.2f} | "
            f"{float(stage[index]['cumulative_task_relevant_force_impulse_proxy_ns']):.2f} | "
            f"{impulse_deltas[index]:+.2f} |"
        )

    def mean(mode_rows: list[dict[str, str]], field: str) -> float:
        return statistics.mean(float(row[field]) for row in mode_rows)

    def maximum(mode_rows: list[dict[str, str]], field: str) -> float:
        return max(float(row[field]) for row in mode_rows)

    report = f"""# Recovery telemetry and held-out validation audit

Date: 2026-07-31

Evidence class: privileged oracle mechanism canary. Contact and force values
are MuJoCo proxies, not calibrated measurements or a safety certificate.

## Measurement correction and invalidated evidence

An adversarial reread found that the first telemetry implementation treated
MuJoCo `cfrc_ext[:, :3]` as force. MuJoCo documents this array in
`rotation:translation` order: the first three components are torque and the
last three are force. The implementation and its unit test were corrected to
use `cfrc_ext[:, 3:]` for force and `cfrc_ext[:, :3]` for torque, then all ten
paired episodes were rerun.

Consequently, force and impulse values in `raw_v1`, `raw_v2`,
`diagnostic_v3`, `diagnostic_v4`, and `contact_diagnostic_v5` are invalid and
must not be cited. Their success predicates, step counts, action/state hashes,
contact pairs, and object displacements do not depend on that component split.
The authoritative force results are from
`raw_v3_corrected_spatial_order`. See the MuJoCo
[mjData API](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html)
and
[mju_transformSpatial](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mju-transformspatial).

## Corrected evaluation split

State 0 was used to diagnose the failed 20 cm staging pilot and choose the
75%-toward-origin staging rule. It is therefore **development data**, not an
independent test. States 1–4 were held out during that rule selection and are
reported separately. The present telemetry run is a confirmatory replay of
those already-observed validation layouts, not a fresh unseen sample.

The telemetry rerun exactly reproduces the earlier action prefix, event
MuJoCo-state hash, terminal predicates, total steps, and horizon outcome for
all 10 method/state rows. Telemetry therefore did not alter behavior.

## Held-out results (states 1–4)

| Metric | Exact return | Local staging |
|---|---:|---:|
| Updated goal within global 600-step horizon | {sum(gate_success(row) for row in exact)}/4 | {sum(gate_success(row) for row in stage)}/4 |
| Physical updated goal reached | {sum(truth(row['final_goal_success']) for row in exact)}/4 | {sum(truth(row['final_goal_success']) for row in stage)}/4 |
| Mean post-event recovery steps | {statistics.mean(exact_steps):.1f} | {statistics.mean(stage_steps):.1f} |
| Recovery-step range | {min(exact_steps)}–{max(exact_steps)} | {min(stage_steps)}–{max(stage_steps)} |
| Mean task-relevant peak-force proxy (N) | {mean(exact, 'task_relevant_peak_force_proxy_n'):.2f} | {mean(stage, 'task_relevant_peak_force_proxy_n'):.2f} |
| Maximum task-relevant peak-force proxy (N) | {maximum(exact, 'task_relevant_peak_force_proxy_n'):.2f} | {maximum(stage, 'task_relevant_peak_force_proxy_n'):.2f} |
| Mean task-relevant force-impulse proxy (N·s) | {mean(exact, 'cumulative_task_relevant_force_impulse_proxy_ns'):.2f} | {mean(stage, 'cumulative_task_relevant_force_impulse_proxy_ns'):.2f} |
| Max robot/protected-object contact steps | {maximum(exact, 'robot_protected_contact_steps'):.0f} | {maximum(stage, 'robot_protected_contact_steps'):.0f} |
| Max task-object/protected-object contact steps | {maximum(exact, 'task_object_protected_contact_steps'):.0f} | {maximum(stage, 'task_object_protected_contact_steps'):.0f} |
| Max robot-environment contact steps | {maximum(exact, 'robot_environment_contact_steps'):.0f} | {maximum(stage, 'robot_environment_contact_steps'):.0f} |
| Max obsolete-object/basket contact steps | {maximum(exact, 'obsolete_receptacle_contact_steps'):.0f} | {maximum(stage, 'obsolete_receptacle_contact_steps'):.0f} |
| Max preserved cream-cheese displacement (mm) | {1000 * maximum(exact, 'done_object_displacement_m'):.2f} | {1000 * maximum(stage, 'done_object_displacement_m'):.2f} |
| Max idle-butter displacement (mm) | {1000 * maximum(exact, 'idle_butter_displacement_m'):.2f} | {1000 * maximum(stage, 'idle_butter_displacement_m'):.2f} |

Local staging saves a mean of {statistics.mean(savings):.1f} post-event steps
on held-out states (range {min(savings)}–{max(savings)}).

Its task-relevant peak-force proxy is lower in
{sum(delta < 0 for delta in peak_force_deltas)}/4 pairs, with a paired mean
change of {statistics.mean(peak_force_deltas):+.2f} N. Its force-impulse proxy
is lower in {sum(delta < 0 for delta in impulse_deltas)}/4 pairs, with a paired
mean change of {statistics.mean(impulse_deltas):+.2f} N·s. These are reported
as mixed paired telemetry, not converted into a blanket "safer" claim.

### Paired state-level evidence

| State | Exact steps | Local steps | Exact−local steps | Exact peak N | Local peak N | Local−exact peak N | Exact impulse N·s | Local impulse N·s | Local−exact impulse N·s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(pair_lines)}

## Fixed post-event recovery-budget curve

This descriptive, non-preregistered curve separates recovery cost from the
absolute event time. It reports physical updated-goal completion under each
post-event action budget and should not be treated as a tuned headline test.

| Post-event budget | Exact return | Local staging |
|---:|---:|---:|
{chr(10).join(budget_lines)}

## Remaining objections

- Four held-out layouts are still a tiny deterministic sample, not random
  seeds or a powered comparison.
- Staging uses oracle object identity, event timing, geometry, and knowledge
  of the obsolete object's original stable pose.
- Global `cfrc_ext` is dominated by static table support, so the report uses
  only bodies whose names match the robot or four task objects and the norm of
  the documented translation/force components `[3:6]`. Even this filtered
  net-body proxy is not a calibrated robot force sensor or a per-contact
  collision force.
- Contact count and object displacement do not establish collision severity
  or human safety.
- The updated goal is scored with simulator predicates because the original
  LIBERO BDDL goal still names butter.

## Decision

Retain local staging only as an **efficiency ablation**: it reaches the same
physical updated goal with fewer post-event steps, but produces a higher
task-relevant peak-force proxy in every held-out pair. Retain exact return as
the lower-peak comparator in this sample. Neither method has earned a safety
claim, and no threshold was selected after seeing these values.
"""
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print("validated 10 telemetry rows; held-out split contains 8 rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
