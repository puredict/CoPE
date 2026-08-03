#!/usr/bin/env python3
"""Locked sequence-level analysis for the 40x4x2 formal experiment."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import beta


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.sequential_prompting import ARMS


BOOL_TRUE = {"1", "true", "yes"}
PRACTICAL_RISK_DIFFERENCE_MIN = 0.15
LOCALITY_MEDIAN_RELATIVE_REDUCTION_MIN = 0.20
SEQUENCE_FIELDS = (
    "sequence_id",
    "state_id",
    "prefix_orientation",
    "sequence_type",
    "arm",
    "sequence_success",
    "stale_commitment_executed",
    "any_invariant_violation",
    "proposal_bytes",
    "prompt_tokens",
    "completion_tokens",
    "latency_seconds",
    "failure_classes",
)


def truth(value: str) -> bool:
    return value.strip().lower() in BOOL_TRUE


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def clopper_pearson(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 1.0
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha / 2, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return lower, upper


def odds(probability: float) -> float:
    if probability >= 1.0:
        return math.inf
    if probability <= 0.0:
        return 0.0
    return probability / (1.0 - probability)


def holm(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: p_values[key])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, key in enumerate(ordered):
        value = min(1.0, (total - rank) * p_values[key])
        running = max(running, value)
        adjusted[key] = running
    return adjusted


def decisive_experiment_gate(
    *, success_p: float, risk_difference: float, safety_no_excess: bool,
    locality_p: float, locality_median_relative_reduction: float,
) -> bool:
    """Frozen necessary gate; cross-task evidence is still separately required."""
    return (
        success_p < 0.05
        and risk_difference >= PRACTICAL_RISK_DIFFERENCE_MIN
        and safety_no_excess
        and locality_p < 0.05
        and locality_median_relative_reduction
        >= LOCALITY_MEDIAN_RELATIVE_REDUCTION_MIN
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--event-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    if len(manifest) != 40:
        raise ValueError("locked manifest must contain 40 sequences")
    manifest_by_id = {row["sequence_id"]: row for row in manifest}
    expected = {
        (sequence_id, arm, event_index)
        for sequence_id in manifest_by_id
        for arm in ARMS
        for event_index in (1, 2)
    }
    with args.event_results.open(newline="", encoding="utf-8") as handle:
        event_rows = list(csv.DictReader(handle))
    keys = [
        (row["sequence_id"], row["arm"], int(row["event_index"]))
        for row in event_rows
    ]
    if len(keys) != 320 or len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError("event-result cells are missing, duplicated, or extra")
    by_sequence: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in event_rows:
        by_sequence[row["sequence_id"]].append(row)
        by_pair[(row["sequence_id"], row["arm"])].append(row)
    eligible: list[str] = []
    substrate_failures: list[str] = []
    for sequence_id, rows in by_sequence.items():
        values = {truth(row["substrate_eligible"]) for row in rows}
        if len(values) != 1:
            raise ValueError(f"substrate eligibility diverges for {sequence_id}")
        is_eligible = values.pop()
        calls = [truth(row["provider_called"]) for row in rows]
        if is_eligible:
            for field in ("prefix_action_sha256", "prefix_simulator_sha256"):
                hashes = {row[field] for row in rows}
                if len(hashes) != 1 or not next(iter(hashes)):
                    raise ValueError(
                        f"eligible sequence has divergent {field}: {sequence_id}"
                    )
            if any(int(row["retry_count"]) != 0 for row in rows):
                raise ValueError(f"eligible sequence has a retry: {sequence_id}")
            for event_index in (1, 2):
                attempted = [
                    row for row in rows
                    if int(row["event_index"]) == event_index
                    and truth(row["provider_called"])
                ]
                input_hashes = {row["input_sha256"] for row in attempted}
                if attempted and (len(input_hashes) != 1 or not next(iter(input_hashes))):
                    raise ValueError(
                        f"common event-{event_index} input drift: {sequence_id}"
                    )
            for arm in ARMS:
                pair = sorted(
                    (row for row in rows if row["arm"] == arm),
                    key=lambda row: int(row["event_index"]),
                )
                if not truth(pair[0]["provider_called"]):
                    raise ValueError(f"eligible event 1 lacks provider call: {sequence_id}/{arm}")
                if not truth(pair[1]["provider_called"]):
                    event1_ok = truth(pair[0]["parser_valid"]) and truth(pair[0]["semantic_valid"])
                    if event1_ok or pair[1]["failure_class"] != "dependency_skip_after_event1_failure":
                        raise ValueError(f"invalid event-2 dependency skip: {sequence_id}/{arm}")
            eligible.append(sequence_id)
        else:
            if any(calls):
                raise ValueError(f"ineligible sequence made provider calls: {sequence_id}")
            substrate_failures.append(sequence_id)
    sequence_rows: list[dict[str, Any]] = []
    for sequence_id in sorted(eligible):
        for arm in ARMS:
            rows = sorted(by_pair[(sequence_id, arm)], key=lambda row: int(row["event_index"]))
            both_fields = (
                "parser_valid",
                "semantic_valid",
                "revision_hash_continuity",
                "intermediate_invariant_valid",
                "progress_preserved",
                "action_budget_respected",
                "call_budget_respected",
            )
            no_stale = not any(truth(row["stale_commitment_executed"]) for row in rows)
            success = (
                all(all(truth(row[field]) for field in both_fields) for row in rows)
                and no_stale
                and truth(rows[1]["final_intent_satisfied"])
            )
            sequence_rows.append(
                {
                    "sequence_id": sequence_id,
                    "state_id": int(manifest_by_id[sequence_id]["state_id"]),
                    "prefix_orientation": manifest_by_id[sequence_id]["prefix_orientation"],
                    "sequence_type": manifest_by_id[sequence_id]["sequence_type"],
                    "arm": arm,
                    "sequence_success": success,
                    "stale_commitment_executed": not no_stale,
                    "any_invariant_violation": not all(
                        truth(row["intermediate_invariant_valid"])
                        and truth(row["revision_hash_continuity"])
                        for row in rows
                    ),
                    "proposal_bytes": sum(int(row["proposal_bytes"]) for row in rows),
                    "prompt_tokens": sum(int(row["prompt_tokens"]) for row in rows),
                    "completion_tokens": sum(int(row["completion_tokens"]) for row in rows),
                    "latency_seconds": sum(float(row["latency_seconds"]) for row in rows),
                    "failure_classes": ";".join(
                        row["failure_class"] for row in rows if row["failure_class"]
                    ),
                }
            )
    outcome = {
        (row["sequence_id"], row["arm"]): bool(row["sequence_success"])
        for row in sequence_rows
    }

    def comparison(other: str) -> dict[str, Any]:
        b = sum(outcome[(sid, "cope")] and not outcome[(sid, other)] for sid in eligible)
        c = sum(outcome[(sid, other)] and not outcome[(sid, "cope")] for sid in eligible)
        cope_rate = sum(outcome[(sid, "cope")] for sid in eligible) / len(eligible) if eligible else 0.0
        other_rate = sum(outcome[(sid, other)] for sid in eligible) / len(eligible) if eligible else 0.0
        low_p, high_p = clopper_pearson(b, b + c)
        return {
            "comparison": f"cope_vs_{other}",
            "eligible_pairs": len(eligible),
            "cope_successes": sum(outcome[(sid, "cope")] for sid in eligible),
            "other_successes": sum(outcome[(sid, other)] for sid in eligible),
            "cope_success_rate": cope_rate,
            "other_success_rate": other_rate,
            "paired_risk_difference": cope_rate - other_rate,
            "cope_only_wins_b": b,
            "other_only_wins_c": c,
            "exact_mcnemar_p": exact_mcnemar(b, c),
            "discordant_win_probability": b / (b + c) if b + c else 0.5,
            "discordant_win_probability_ci_low": low_p,
            "discordant_win_probability_ci_high": high_p,
            "matched_odds_ratio": odds(b / (b + c)) if b + c else 1.0,
            "matched_odds_ratio_ci_low": odds(low_p),
            "matched_odds_ratio_ci_high": odds(high_p),
        }

    comparisons = [comparison("neutral_patch"), comparison("fsr_pc"), comparison("full_replan")]
    sequence_by_pair = {
        (row["sequence_id"], row["arm"]): row for row in sequence_rows
    }
    primary = comparisons[0]
    valid_locality_ids = [
        sid for sid in eligible
        if all(
            all(
                truth(event["parser_valid"]) and truth(event["semantic_valid"])
                for event in by_pair[(sid, arm)]
            )
            for arm in ("cope", "neutral_patch")
        )
    ]
    paired_reductions = []
    locality_wins = locality_losses = locality_ties = 0
    for sid in valid_locality_ids:
        cope_bytes = int(sequence_by_pair[(sid, "cope")]["proposal_bytes"])
        neutral_bytes = int(sequence_by_pair[(sid, "neutral_patch")]["proposal_bytes"])
        if neutral_bytes > 0:
            paired_reductions.append((neutral_bytes - cope_bytes) / neutral_bytes)
        if cope_bytes < neutral_bytes:
            locality_wins += 1
        elif cope_bytes > neutral_bytes:
            locality_losses += 1
        else:
            locality_ties += 1
    locality_p = exact_mcnemar(locality_wins, locality_losses)
    locality_median = median(paired_reductions) if paired_reductions else 0.0
    cope_rows = [row for row in sequence_rows if row["arm"] == "cope"]
    neutral_rows = [row for row in sequence_rows if row["arm"] == "neutral_patch"]
    cope_stale = sum(bool(row["stale_commitment_executed"]) for row in cope_rows)
    neutral_stale = sum(bool(row["stale_commitment_executed"]) for row in neutral_rows)
    cope_invariant = sum(bool(row["any_invariant_violation"]) for row in cope_rows)
    neutral_invariant = sum(bool(row["any_invariant_violation"]) for row in neutral_rows)
    safety_no_excess = cope_stale <= neutral_stale and cope_invariant <= neutral_invariant
    primary.update(
        {
            "cope_stale_sequences": cope_stale,
            "other_stale_sequences": neutral_stale,
            "cope_invariant_violation_sequences": cope_invariant,
            "other_invariant_violation_sequences": neutral_invariant,
            "safety_no_excess": safety_no_excess,
            "locality_valid_pairs": len(valid_locality_ids),
            "locality_cope_smaller": locality_wins,
            "locality_neutral_smaller": locality_losses,
            "locality_ties": locality_ties,
            "locality_exact_sign_p": locality_p,
            "locality_median_relative_byte_reduction": locality_median,
            "decisive_experiment_gate": decisive_experiment_gate(
                success_p=float(primary["exact_mcnemar_p"]),
                risk_difference=float(primary["paired_risk_difference"]),
                safety_no_excess=safety_no_excess,
                locality_p=locality_p,
                locality_median_relative_reduction=locality_median,
            ),
        }
    )
    secondary_raw = {
        row["comparison"]: float(row["exact_mcnemar_p"])
        for row in comparisons[1:]
    }
    secondary_adjusted = holm(secondary_raw)
    for row in comparisons:
        row["holm_adjusted_p"] = (
            "" if row["comparison"] == "cope_vs_neutral_patch"
            else secondary_adjusted[row["comparison"]]
        )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_SEQUENCE_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=SEQUENCE_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(sequence_rows)
    with (args.output_dir / "02_COMPARISONS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparisons[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(comparisons)
    (args.output_dir / "00_RESULT.md").write_text(
        "# Sequential formal result\n\n"
        f"- Eligible sequence units: **{len(eligible)}/40**\n"
        f"- Shared substrate failures: **{len(substrate_failures)}**\n"
        f"- CoPE success: **{primary['cope_successes']}/{len(eligible)}**\n"
        f"- Neutral patch success: **{primary['other_successes']}/{len(eligible)}**\n"
        f"- Paired risk difference: **{100 * primary['paired_risk_difference']:.1f} pp**\n"
        f"- Discordance b/c: **{primary['cope_only_wins_b']}/{primary['other_only_wins_c']}**\n"
        f"- Exact McNemar p: **{primary['exact_mcnemar_p']:.8g}**\n"
        f"- Safety no-excess gate: **{primary['safety_no_excess']}**\n"
        f"- Locality valid pairs: **{primary['locality_valid_pairs']}**\n"
        f"- Locality median relative byte reduction: **{100 * primary['locality_median_relative_byte_reduction']:.1f}%**\n"
        f"- Locality exact sign p: **{primary['locality_exact_sign_p']:.8g}**\n"
        f"- Decisive experiment gate: **{primary['decisive_experiment_gate']}**\n"
        "\nThe decisive gate is necessary but not sufficient for submission: this locked study has one task identity and does not establish cross-task generalization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
