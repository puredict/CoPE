#!/usr/bin/env python3
"""Validate and summarize paired oracle interruption-timing canaries."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable


TIMINGS = ("post_lift", "mid_transfer", "pre_release")
MODES = ("stale_continue", "safe_return_switch")
PAIR_FIELDS = (
    "event_step",
    "action_prefix_sha256",
    "sim_state_before_patch_sha256",
    "eef_at_event",
    "held_position_at_event",
    "physical_truth_before_first_patch",
    "physical_truth_before_second_patch",
)


def truth(value: str) -> bool:
    return value.strip().lower() == "true"


def load_rows(raw_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(raw_dir.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            loaded = list(csv.DictReader(handle))
        if len(loaded) != 1:
            raise ValueError(f"expected one row in {path}, found {len(loaded)}")
        loaded[0]["source_csv"] = str(path)
        rows.extend(loaded)
    return rows


def validate_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    materialized = list(rows)
    grouped: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[int, str, str]] = set()
    for row in materialized:
        key = (int(row["state_id"]), row["timing"], row["mode"])
        if key in seen:
            raise ValueError(f"duplicate episode {key}")
        seen.add(key)
        grouped[(key[0], key[1])].append(row)
        for field in (
            "oracle_execution",
            "oracle_operation_selection",
            "patch_preserved_sim_state",
            "patch_emitted_no_action",
            "physical_truth_before_first_patch",
            "physical_truth_before_second_patch",
            "held_at_event",
            "second_patch_accepted",
            "hash_chain_valid",
        ):
            if not truth(row[field]):
                raise ValueError(f"integrity field {field} failed for {key}")
        for field in (
            "learned_policy_used",
            "held_in_region_at_event",
            "force_contact_collision_safety_measured",
        ):
            if truth(row[field]):
                raise ValueError(f"scope field {field} invalid for {key}")
        if (
            row["sim_state_before_patch_sha256"]
            != row["sim_state_after_patch_sha256"]
        ):
            raise ValueError(f"semantic patch changed simulator state for {key}")
        for field in (
            "action_prefix_sha256",
            "sim_state_before_patch_sha256",
            "sim_state_after_patch_sha256",
        ):
            value = row[field]
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"invalid SHA-256 field {field} for {key}")

    for pair_key, pair in grouped.items():
        if len(pair) != 2 or {row["mode"] for row in pair} != set(MODES):
            raise ValueError(f"incomplete paired arms for {pair_key}")
        for field in PAIR_FIELDS:
            values = {row[field] for row in pair}
            if len(values) != 1:
                raise ValueError(
                    f"paired-prefix mismatch for {pair_key}: {field}={values}"
                )
    return sorted(
        materialized,
        key=lambda row: (
            int(row["state_id"]),
            TIMINGS.index(row["timing"]),
            MODES.index(row["mode"]),
        ),
    )


def write_combined(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def report_text(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Oracle second-replacement timing sensitivity",
        "",
        "Date: 2026-07-31",
        "",
        "Environment: Python 3.10.12, MuJoCo 2.3.7, robosuite 1.4.1,",
        "LIBERO 0.1.0, NumPy 1.26.4; CPU execution with GPU visibility disabled.",
        "",
        "> Evidence class: privileged oracle mechanism canary. This is a real",
        "> MuJoCo/LIBERO execution experiment, but it is not a learned-policy or",
        "> end-to-end CoPE evaluation.",
        "",
        "## Integrity gates",
        "",
        f"- Episodes: {len(rows)} ({len(rows) // 2} independently reset pairs).",
        "- Every pair has an identical pre-event low-level action SHA-256.",
        "- Every pair has an identical pre-event MuJoCo state SHA-256.",
        "- EEF and held-object event poses match within their serialized values.",
        "- Every semantic patch emitted zero simulator actions and left the",
        "  MuJoCo state hash unchanged.",
        "- Completed progress was queried from the simulator before each patch;",
        "  it was never asserted unconditionally by the experiment runner.",
        "",
        "## Results",
        "",
        "| Event timing | Mean event step | Stale updated-goal success | Safe recovery success | Stale object executed | Safe mean steps | Mean overhead | Min horizon margin |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    timing_stats: dict[str, dict[str, int]] = {}
    for timing in TIMINGS:
        stale = [
            row
            for row in rows
            if row["timing"] == timing and row["mode"] == "stale_continue"
        ]
        safe = [
            row
            for row in rows
            if row["timing"] == timing and row["mode"] == "safe_return_switch"
        ]
        stale_success = sum(truth(row["final_goal_success"]) for row in stale)
        safe_success = sum(
            truth(row["final_goal_success"])
            and truth(row["within_horizon"])
            and truth(row["expected_outcome_observed"])
            for row in safe
        )
        stale_executed = sum(truth(row["stale_commitment_executed"]) for row in stale)
        physical_goal_success = sum(
            truth(row["final_goal_success"]) for row in safe
        )
        horizon_failures = sum(
            not truth(row["within_horizon"]) for row in safe
        )
        safe_steps = [int(row["environment_steps"]) for row in safe]
        event_steps = [int(row["event_step"]) for row in safe]
        stale_by_state = {int(row["state_id"]): row for row in stale}
        overhead = [
            int(row["environment_steps"])
            - int(stale_by_state[int(row["state_id"])]["environment_steps"])
            for row in safe
        ]
        lines.append(
            f"| {timing} | {statistics.mean(event_steps):.1f} | "
            f"{stale_success}/{len(stale)} | "
            f"{safe_success}/{len(safe)} | {stale_executed}/{len(stale)} | "
            f"{statistics.mean(safe_steps):.1f} | "
            f"{statistics.mean(overhead):.1f} | {600 - max(safe_steps)} |"
        )
        timing_stats[timing] = {
            "total": len(safe),
            "gate_success": safe_success,
            "physical_goal_success": physical_goal_success,
            "horizon_failures": horizon_failures,
        }
    return_errors_mm = [
        1000.0 * float(row["safe_return_error_m"])
        for row in rows
        if row["mode"] == "safe_return_switch"
    ]
    lines.extend(
        [
            "",
            f"Safe-return position error: mean {statistics.mean(return_errors_mm):.2f} mm; "
            f"maximum {max(return_errors_mm):.2f} mm.",
            "",
            "## Observed late-recovery boundary",
            "",
            (
                "At pre-release, the updated physical goal was reached in "
                f"{timing_stats['pre_release']['physical_goal_success']}/"
                f"{timing_stats['pre_release']['total']} trials, while the full "
                "600-step recovery gate passed in "
                f"{timing_stats['pre_release']['gate_success']}/"
                f"{timing_stats['pre_release']['total']}. "
                f"{timing_stats['pre_release']['horizon_failures']} trials crossed "
                "the horizon."
            ),
            "",
            "Because every patch integrity gate passes before recovery begins,",
            "late failures are attributable to the cost of exact return-and-switch,",
            "not to rejection of the persistent commitment edit. This motivates a",
            "bounded local staging/drop operator or direct redirection when valid,",
            "rather than always returning the obsolete object to its original pose.",
            "",
            "## Interpretation boundary",
            "",
            "The canary isolates one mechanism: after a commitment changes while",
            "an obsolete object is held, a persistent semantic patch alone does not",
            "stop the running skill. Explicit return-and-switch repair is required.",
            "The experiment uses oracle object identity, oracle event timing, oracle",
            "operation selection, privileged geometry, and a custom simulator-predicate",
            "goal because the original LIBERO BDDL goal still names butter.",
            "",
            "The reported safety evidence is limited to grasp retention, release,",
            "return-position error, target predicates, and the 600-step horizon.",
            "Force, contact impulse, collision severity, and human safety are not",
            "measured and must not be inferred from these rows.",
            "",
            "The five states, when all are present, are LIBERO's five official initial",
            "layouts; they are not independent random seeds. This small canary is for",
            "mechanism qualification, not a powered headline comparison.",
            "",
            "## Reproduction",
            "",
            "GPU inference is not used. Run with `CUDA_VISIBLE_DEVICES=\"\"`",
            "and the repository's existing LIBERO environment:",
            "",
            "```bash",
            "export HF_HOME=/home/lijingsu/vla/cache/huggingface",
            "export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers",
            "export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
            "export CUDA_VISIBLE_DEVICES=\"\"",
            "scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \\",
            "  experiments/oracle_interruption_timing_gate.py \\",
            "  --state-id 0 --timing post_lift --mode safe_return_switch \\",
            "  --output-csv /new/non_overwriting/path.csv",
            "```",
            "",
            "Repeat states `0..4`, timings `post_lift`, `mid_transfer`, and",
            "`pre_release`, and both modes. Then run the strict summarizer.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = validate_rows(load_rows(args.raw_dir))
    if not rows:
        raise ValueError("no episode CSVs found")
    write_combined(rows, args.output_csv)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report_text(rows), encoding="utf-8")
    print(f"validated {len(rows)} rows and {len(rows) // 2} paired prefixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
