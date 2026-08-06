#!/usr/bin/env python3
"""Summarize pre-release local staging against exact return-and-switch."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


PAIR_FIELDS = (
    "event_step",
    "action_prefix_sha256",
    "sim_state_before_patch_sha256",
    "eef_at_event",
    "held_position_at_event",
)


def truth(value: str) -> bool:
    return value.strip().lower() == "true"


def load_one(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected one row in {path}, found {len(rows)}")
    return rows[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-raw-dir", type=Path, required=True)
    parser.add_argument("--exact-raw-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()

    combined: list[dict[str, str]] = []
    for state_id in range(5):
        stage_path = args.stage_raw_dir / f"state{state_id}_local_stage_switch.csv"
        exact_path = (
            args.exact_raw_dir
            / f"state{state_id}_pre_release_safe_return_switch.csv"
        )
        stage = load_one(stage_path)
        exact = load_one(exact_path)
        for field in PAIR_FIELDS:
            if stage[field] != exact[field]:
                raise ValueError(
                    f"state {state_id} prefix mismatch: {field}"
                )
        if stage["sim_state_before_patch_sha256"] != stage[
            "sim_state_after_patch_sha256"
        ]:
            raise ValueError(f"state {state_id} patch changed simulator state")
        for field in (
            "physical_truth_before_first_patch",
            "physical_truth_before_second_patch",
            "held_at_event",
            "second_patch_accepted",
            "hash_chain_valid",
            "patch_preserved_sim_state",
            "patch_emitted_no_action",
            "local_stage_success",
            "local_stage_outside_region",
        ):
            if not truth(stage[field]):
                raise ValueError(f"state {state_id} failed {field}")
        combined.append(
            {
                "state_id": str(state_id),
                "event_step": stage["event_step"],
                "action_prefix_sha256": stage["action_prefix_sha256"],
                "sim_state_sha256": stage["sim_state_before_patch_sha256"],
                "exact_return_steps": exact["environment_steps"],
                "exact_return_goal_success": exact["final_goal_success"],
                "exact_return_within_horizon": exact["within_horizon"],
                "local_stage_steps": stage["environment_steps"],
                "local_stage_goal_success": stage["final_goal_success"],
                "local_stage_within_horizon": stage["within_horizon"],
                "local_stage_error_m": stage["local_stage_error_m"],
                "stale_commitment_executed": stage[
                    "stale_commitment_executed"
                ],
                "step_saving": str(
                    int(exact["environment_steps"])
                    - int(stage["environment_steps"])
                ),
                "stage_source_csv": str(stage_path),
                "exact_source_csv": str(exact_path),
            }
        )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(combined[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(combined)

    exact_gate = sum(
        truth(row["exact_return_goal_success"])
        and truth(row["exact_return_within_horizon"])
        for row in combined
    )
    stage_gate = sum(
        truth(row["local_stage_goal_success"])
        and truth(row["local_stage_within_horizon"])
        for row in combined
    )
    savings = [int(row["step_saving"]) for row in combined]
    errors_mm = [1000 * float(row["local_stage_error_m"]) for row in combined]
    report = f"""# Pre-release local staging recovery canary

Date: 2026-07-31

Evidence class: privileged oracle mechanism canary, not learned-policy or
end-to-end CoPE evaluation.

## Question

When exact return-and-switch approaches or crosses the 600-step horizon, can
the obsolete held object instead be released at a short verified table pose
outside the basket before switching to the replacement object?

## Paired result

- Exact return-and-switch gate success: {exact_gate}/5.
- Local stage-and-switch gate success: {stage_gate}/5.
- Mean step saving: {statistics.mean(savings):.1f} steps; range
  {min(savings)}–{max(savings)}.
- Local staging position error: mean {statistics.mean(errors_mm):.2f} mm;
  maximum {max(errors_mm):.2f} mm.

Every local-staging row matches its exact-return control on the event step,
low-level action-prefix SHA-256, pre-patch MuJoCo-state SHA-256, EEF pose, and
held-object pose. Every patch left the simulator hash unchanged. The staged
alphabet-soup object was released outside the basket and the stale commitment
was not executed in {sum(not truth(row['stale_commitment_executed']) for row in combined)}/5 trials.

## Boundary

The staging pose is oracle-derived: 75% of the basket-to-original-pose vector,
which stops 25% short of the obsolete object's known stable free-table pose,
followed by predicate and position verification. The more aggressive 20 cm
pilot is retained as a failed raw run: it released outside the basket but
missed its staging-pose tolerance. Force, collision severity, and human safety
are not measured. This tests a repair compiler choice; it does not test event
detection, language grounding, or learned control.
"""
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print(f"validated 5 paired prefixes; local stage gate {stage_gate}/5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
