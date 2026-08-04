#!/usr/bin/env python3
"""Locked five-arm sequence analysis with neutral and governed co-primary gates."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
V1_SPEC = importlib.util.spec_from_file_location(
    "analyze_sequential_formal_v1", ROOT / "tools" / "analyze_sequential_formal.py"
)
assert V1_SPEC is not None and V1_SPEC.loader is not None
V1 = importlib.util.module_from_spec(V1_SPEC)
V1_SPEC.loader.exec_module(V1)


ARMS = ("cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan")
PRIMARY_CONTROLS = ("neutral_patch", "governed_delta")
SECONDARY_CONTROLS = ("fsr_pc", "full_replan")
EXPECTED_MANIFEST_SHA256 = "9788ceff3c4366e5928bef028cc5e24c594dc30d6c8a559c2403b78bb5a858e5"
BOOL_TRUE = {"1", "true", "yes"}
BOOL_FALSE = {"0", "false", "no"}
BOOLEAN_FIELDS = (
    "substrate_eligible", "provider_called", "parser_valid", "semantic_valid",
    "revision_hash_continuity", "intermediate_invariant_valid",
    "progress_preserved", "stale_commitment_executed",
    "final_intent_satisfied", "action_budget_respected",
    "call_budget_respected",
)
INFRASTRUCTURE_FAILURE_MARKERS = (
    "provider_timeout",
    "provider_transport_outage",
    "provider_http_",
    "ambiguous_interrupted_call_no_retry",
)


def truth(value: str) -> bool:
    return value.strip().lower() in BOOL_TRUE


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--event-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def control_gate(row: dict[str, Any]) -> bool:
    return (
        float(row["holm_efficacy_p"]) < 0.05
        and float(row["paired_risk_difference"]) >= 0.15
        and bool(row["safety_no_excess"])
        and float(row["holm_locality_p"]) < 0.05
        and float(row["locality_median_relative_byte_reduction"]) >= 0.20
    )


def claim_status(
    *, substrate_complete: bool, infrastructure_valid: bool,
    primary: list[dict[str, Any]], task_count: int,
) -> str:
    if not substrate_complete:
        return "INVALID_SUBSTRATE_INCOMPLETE"
    if not infrastructure_valid:
        return "INVALID_INFRASTRUCTURE_FAILURE"
    by_control = {row["control"]: row for row in primary}
    if not bool(by_control["neutral_patch"]["control_gate"]):
        return "NO_GO_PRIMARY_NEUTRAL_COMPARISON"
    if not bool(by_control["governed_delta"]["control_gate"]):
        return "NO_GO_PRIMARY_GOVERNED_COMPARISON"
    if task_count < 2:
        return "NECESSARY_GATE_PASS_SINGLE_TASK_ONLY"
    return "NECESSARY_GATE_PASS_REQUIRES_EXTERNAL_VALIDITY_REVIEW"


def main() -> int:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if __import__("hashlib").sha256(args.manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise ValueError("v2 manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    if len(manifest) != 40 or {row["schema_version"] for row in manifest} != {"cope-sequential-formal-manifest-v2"}:
        raise ValueError("v2 manifest shape or schema mismatch")
    manifest_by_id = {row["sequence_id"]: row for row in manifest}
    expected = {
        (sequence_id, arm, event_index)
        for sequence_id in manifest_by_id for arm in ARMS for event_index in (1, 2)
    }
    with args.event_results.open(newline="", encoding="utf-8") as handle:
        event_rows = list(csv.DictReader(handle))
    keys = [(row["sequence_id"], row["arm"], int(row["event_index"])) for row in event_rows]
    if len(keys) != 400 or len(set(keys)) != 400 or set(keys) != expected:
        raise ValueError("v2 event-result cells are missing, duplicated, or extra")

    by_sequence: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in event_rows:
        by_sequence[row["sequence_id"]].append(row)
        by_pair[(row["sequence_id"], row["arm"])].append(row)
    for sequence_id, rows in by_sequence.items():
        manifest_row = manifest_by_id[sequence_id]
        for row in rows:
            if any(
                row[field].strip().lower() not in BOOL_TRUE | BOOL_FALSE
                for field in BOOLEAN_FIELDS
            ):
                raise ValueError(f"v2 result boolean is noncanonical: {sequence_id}")
            if (
                row["task_id"] != manifest_row["task_id"]
                or row["state_id"] != manifest_row["state_id"]
                or row["prefix_orientation"] != manifest_row["prefix_orientation"]
                or row["sequence_type"] != manifest_row["sequence_type"]
            ):
                raise ValueError(f"v2 result metadata drift: {sequence_id}")
    eligible: list[str] = []
    substrate_failures: list[str] = []
    for sequence_id, rows in by_sequence.items():
        eligibility = {truth(row["substrate_eligible"]) for row in rows}
        if len(eligibility) != 1:
            raise ValueError(f"substrate eligibility diverges: {sequence_id}")
        if not eligibility.pop():
            if any(truth(row["provider_called"]) for row in rows):
                raise ValueError(f"ineligible sequence made provider calls: {sequence_id}")
            substrate_failures.append(sequence_id)
            continue
        for field in ("prefix_action_sha256", "prefix_simulator_sha256"):
            values = {row[field] for row in rows}
            if len(values) != 1 or not is_sha256(next(iter(values))):
                raise ValueError(f"eligible prefix hash drift: {sequence_id}/{field}")
        if any(int(row["retry_count"]) != 0 for row in rows):
            raise ValueError(f"eligible sequence has retry: {sequence_id}")
        for event_index in (1, 2):
            attempted = [
                row for row in rows
                if int(row["event_index"]) == event_index and truth(row["provider_called"])
            ]
            hashes = {row["input_sha256"] for row in attempted}
            if attempted and (len(hashes) != 1 or not is_sha256(next(iter(hashes)))):
                raise ValueError(f"common event-{event_index} input drift: {sequence_id}")
        for row in rows:
            if not truth(row["provider_called"]):
                continue
            parser_valid = truth(row["parser_valid"])
            semantic_valid = truth(row["semantic_valid"])
            if parser_valid and (
                int(row["proposal_bytes"]) <= 0
                or not is_sha256(row["proposal_sha256"])
                or not is_sha256(row["response_sha256"])
            ):
                raise ValueError(f"v2 parsed proposal evidence invalid: {sequence_id}")
            if semantic_valid and not parser_valid:
                raise ValueError(f"v2 semantic/parser flags inconsistent: {sequence_id}")
            if semantic_valid and (
                not is_sha256(row["logical_before_sha256"])
                or not is_sha256(row["logical_after_sha256"])
                or row["failure_class"]
            ):
                raise ValueError(f"v2 semantic evidence inconsistent: {sequence_id}")
            semantic_dependent = (
                "revision_hash_continuity", "intermediate_invariant_valid",
                "progress_preserved", "stale_commitment_executed",
                "final_intent_satisfied", "action_budget_respected",
            )
            if any(truth(row[field]) for field in semantic_dependent) and not semantic_valid:
                raise ValueError(f"v2 outcome/semantic flags inconsistent: {sequence_id}")
            if not semantic_valid and not row["failure_class"]:
                raise ValueError(f"v2 failed call lacks classification: {sequence_id}")
        for arm in ARMS:
            pair = sorted(
                (row for row in rows if row["arm"] == arm),
                key=lambda row: int(row["event_index"]),
            )
            if not truth(pair[0]["provider_called"]):
                raise ValueError(f"eligible event 1 lacks call: {sequence_id}/{arm}")
            event1_ok = truth(pair[0]["parser_valid"]) and truth(pair[0]["semantic_valid"])
            event2_called = truth(pair[1]["provider_called"])
            if event1_ok != event2_called:
                raise ValueError(f"invalid event-2 call dependency: {sequence_id}/{arm}")
            if not event2_called and pair[1]["failure_class"] != "dependency_skip_after_event1_failure":
                raise ValueError(f"invalid event-2 skip: {sequence_id}/{arm}")
        eligible.append(sequence_id)

    sequence_rows: list[dict[str, Any]] = []
    required = (
        "parser_valid", "semantic_valid", "revision_hash_continuity",
        "intermediate_invariant_valid", "progress_preserved",
        "action_budget_respected", "call_budget_respected",
    )
    for sequence_id in sorted(eligible):
        for arm in ARMS:
            rows = sorted(by_pair[(sequence_id, arm)], key=lambda row: int(row["event_index"]))
            stale = any(truth(row["stale_commitment_executed"]) for row in rows)
            invariant = any(
                not truth(row["intermediate_invariant_valid"])
                or not truth(row["revision_hash_continuity"])
                for row in rows
            )
            success = (
                all(all(truth(row[field]) for field in required) for row in rows)
                and not stale and truth(rows[1]["final_intent_satisfied"])
            )
            sequence_rows.append(
                {
                    "sequence_id": sequence_id,
                    "arm": arm,
                    "sequence_success": success,
                    "stale_commitment_executed": stale,
                    "any_invariant_violation": invariant,
                    "proposal_bytes": sum(int(row["proposal_bytes"]) for row in rows),
                    "failure_classes": ";".join(row["failure_class"] for row in rows if row["failure_class"]),
                }
            )
    seq = {(row["sequence_id"], row["arm"]): row for row in sequence_rows}

    def compare(control: str) -> dict[str, Any]:
        b = sum(bool(seq[(sid, "cope")]["sequence_success"]) and not bool(seq[(sid, control)]["sequence_success"]) for sid in eligible)
        c = sum(bool(seq[(sid, control)]["sequence_success"]) and not bool(seq[(sid, "cope")]["sequence_success"]) for sid in eligible)
        cope_success = sum(bool(seq[(sid, "cope")]["sequence_success"]) for sid in eligible)
        other_success = sum(bool(seq[(sid, control)]["sequence_success"]) for sid in eligible)
        return {
            "control": control,
            "eligible_pairs": len(eligible),
            "cope_successes": cope_success,
            "control_successes": other_success,
            "paired_risk_difference": (cope_success - other_success) / len(eligible) if eligible else 0.0,
            "cope_only_wins": b,
            "control_only_wins": c,
            "raw_efficacy_p": V1.exact_mcnemar(b, c),
        }

    primary = [compare(control) for control in PRIMARY_CONTROLS]
    efficacy_adjusted = V1.holm({row["control"]: float(row["raw_efficacy_p"]) for row in primary})
    locality_raw: dict[str, float] = {}
    for row in primary:
        control = str(row["control"])
        valid = [
            sid for sid in eligible
            if all(
                all(truth(event["parser_valid"]) and truth(event["semantic_valid"]) for event in by_pair[(sid, arm)])
                for arm in ("cope", control)
            )
        ]
        reductions = []
        wins = losses = ties = 0
        for sid in valid:
            cope_bytes = int(seq[(sid, "cope")]["proposal_bytes"])
            control_bytes = int(seq[(sid, control)]["proposal_bytes"])
            if control_bytes > 0:
                reductions.append((control_bytes - cope_bytes) / control_bytes)
            if cope_bytes < control_bytes:
                wins += 1
            elif cope_bytes > control_bytes:
                losses += 1
            else:
                ties += 1
        raw_locality = V1.exact_mcnemar(wins, losses)
        locality_raw[control] = raw_locality
        cope_stale = sum(bool(seq[(sid, "cope")]["stale_commitment_executed"]) for sid in eligible)
        control_stale = sum(bool(seq[(sid, control)]["stale_commitment_executed"]) for sid in eligible)
        cope_invariant = sum(bool(seq[(sid, "cope")]["any_invariant_violation"]) for sid in eligible)
        control_invariant = sum(bool(seq[(sid, control)]["any_invariant_violation"]) for sid in eligible)
        row.update(
            {
                "holm_efficacy_p": efficacy_adjusted[control],
                "cope_stale_sequences": cope_stale,
                "control_stale_sequences": control_stale,
                "cope_invariant_sequences": cope_invariant,
                "control_invariant_sequences": control_invariant,
                "safety_no_excess": cope_stale <= control_stale and cope_invariant <= control_invariant,
                "locality_valid_pairs": len(valid),
                "locality_cope_smaller": wins,
                "locality_control_smaller": losses,
                "locality_ties": ties,
                "raw_locality_p": raw_locality,
                "locality_median_relative_byte_reduction": median(reductions) if reductions else 0.0,
            }
        )
    locality_adjusted = V1.holm(locality_raw)
    for row in primary:
        row["holm_locality_p"] = locality_adjusted[str(row["control"])]
        row["control_gate"] = control_gate(row)

    secondary = [compare(control) for control in SECONDARY_CONTROLS]
    secondary_adjusted = V1.holm({row["control"]: float(row["raw_efficacy_p"]) for row in secondary})
    for row in secondary:
        row["holm_secondary_p"] = secondary_adjusted[str(row["control"])]
        row["secondary_cannot_rescue_primary"] = True
    substrate_complete = len(eligible) == 40
    infrastructure_failures = [
        row for row in event_rows
        if truth(row["substrate_eligible"])
        and any(marker in row["failure_class"] for marker in INFRASTRUCTURE_FAILURE_MARKERS)
    ]
    infrastructure_valid = not infrastructure_failures
    task_count = len({row["task_id"] for row in manifest})
    status = claim_status(
        substrate_complete=substrate_complete,
        infrastructure_valid=infrastructure_valid,
        primary=primary,
        task_count=task_count,
    )

    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_SEQUENCE_RESULTS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sequence_rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(sequence_rows)
    with (args.output_dir / "02_COPRIMARY_COMPARISONS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(primary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(primary)
    with (args.output_dir / "03_SECONDARY_COMPARISONS.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(secondary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(secondary)
    (args.output_dir / "00_RESULT.md").write_text(
        "# Sequential formal v2 result\n\n"
        f"- Eligible sequences: **{len(eligible)}/40**\n"
        f"- Shared substrate failures: **{len(substrate_failures)}**\n"
        f"- Neutral control gate: **{primary[0]['control_gate']}**\n"
        f"- Governed control gate: **{primary[1]['control_gate']}**\n"
        f"- Infrastructure failures: **{len(infrastructure_failures)}**\n"
        f"- Joint necessary gate: **{all(bool(row['control_gate']) for row in primary) and substrate_complete and infrastructure_valid}**\n"
        f"- Formal claim status: **{status}**\n\n"
        "Both co-primary controls must pass. Secondary FSR-PC or full-replan "
        "wins cannot rescue either co-primary failure.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
