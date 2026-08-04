#!/usr/bin/env python3
"""Locked paired analysis for the occurrence-sensitive learned formal gate."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("formal_v1", ROOT / "tools" / "analyze_sequential_formal.py")
assert SPEC is not None and SPEC.loader is not None
V1 = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V1)

from cope.occurrence_prompting import ARMS
from experiments.occurrence_formal_preflight import EXPECTED_MANIFEST_SHA256, validate_manifest


PRIMARY = ("neutral_patch", "governed_delta")
SECONDARY = ("fsr_pc", "full_replan")
TRUE = {"1", "true", "yes"}
INFRA = ("provider_timeout", "provider_transport_outage", "provider_http_", "ambiguous_interrupted_call_no_retry")


def truth(value: str) -> bool:
    return value.strip().lower() in TRUE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--event-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def gate(row: dict[str, Any]) -> bool:
    return bool(
        float(row["holm_efficacy_p"]) < 0.05
        and float(row["paired_risk_difference"]) >= 0.15
        and bool(row["safety_no_excess"])
        and float(row["holm_locality_p"]) < 0.05
        and float(row["median_relative_byte_reduction"]) >= 0.20
    )


def claim_status(primary: list[dict[str, Any]], infrastructure_valid: bool) -> str:
    if not infrastructure_valid:
        return "INVALID_INFRASTRUCTURE_FAILURE"
    by = {row["control"]: row for row in primary}
    if not by["neutral_patch"]["control_gate"]:
        return "NO_GO_PRIMARY_NEUTRAL_COMPARISON"
    if not by["governed_delta"]["control_gate"]:
        return "NO_GO_PRIMARY_GOVERNED_COMPARISON"
    return "NECESSARY_SYMBOLIC_GATE_PASS_REQUIRES_EMBODIED_AND_MODEL_REPLICATION"


def main() -> int:
    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if __import__("hashlib").sha256(args.manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise ValueError("occurrence manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    validate_manifest(manifest)
    cases = {row["case_id"]: row for row in manifest}
    expected = {(case, arm, 1) for case in cases for arm in ARMS}
    with args.event_results.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    keys = [(row["case_id"], row["arm"], int(row["event_index"])) for row in rows]
    if len(keys) != 200 or len(set(keys)) != 200 or set(keys) != expected:
        raise ValueError("occurrence result cells are missing, duplicated, or extra")
    by = {(row["case_id"], row["arm"]): row for row in rows}
    for case in cases:
        group = [by[(case, arm)] for arm in ARMS]
        hashes = {row["input_sha256"] for row in group if truth(row["provider_called"])}
        if len(hashes) != 1 or not next(iter(hashes)):
            raise ValueError(f"occurrence common input drift: {case}")
        if any(int(row["retry_count"]) != 0 for row in group):
            raise ValueError(f"occurrence retry detected: {case}")
        if any(not truth(row["provider_called"]) for row in group):
            raise ValueError(f"occurrence cell lacks provider call: {case}")
    infrastructure_failures = [
        row for row in rows if any(marker in row["failure_class"] for marker in INFRA)
    ]
    infrastructure_valid = not infrastructure_failures
    success = {
        (case, arm): all(truth(by[(case, arm)][field]) for field in (
            "parser_valid", "semantic_valid", "canonical_valid", "history_valid", "directive_valid",
        ))
        for case in cases for arm in ARMS
    }

    def compare(control: str) -> dict[str, Any]:
        b = sum(success[(case, "cope")] and not success[(case, control)] for case in cases)
        c = sum(success[(case, control)] and not success[(case, "cope")] for case in cases)
        return {
            "control": control, "paired_cases": 40,
            "cope_successes": sum(success[(case, "cope")] for case in cases),
            "control_successes": sum(success[(case, control)] for case in cases),
            "cope_only_wins": b, "control_only_wins": c,
            "paired_risk_difference": (
                sum(success[(case, "cope")] for case in cases)
                - sum(success[(case, control)] for case in cases)
            ) / 40,
            "raw_efficacy_p": V1.exact_mcnemar(b, c),
        }

    primary = [compare(control) for control in PRIMARY]
    adjusted = V1.holm({row["control"]: row["raw_efficacy_p"] for row in primary})
    locality_raw = {}
    for comparison in primary:
        control = comparison["control"]
        valid = [
            case for case in cases
            if truth(by[(case, "cope")]["semantic_valid"])
            and truth(by[(case, control)]["semantic_valid"])
        ]
        reductions = []
        wins = losses = ties = 0
        for case in valid:
            cope_bytes = int(by[(case, "cope")]["proposal_bytes"])
            other_bytes = int(by[(case, control)]["proposal_bytes"])
            if other_bytes > 0:
                reductions.append((other_bytes - cope_bytes) / other_bytes)
            if cope_bytes < other_bytes: wins += 1
            elif cope_bytes > other_bytes: losses += 1
            else: ties += 1
        raw = V1.exact_mcnemar(wins, losses); locality_raw[control] = raw
        cope_history_failures = sum(not truth(by[(case, "cope")]["history_valid"]) for case in cases)
        control_history_failures = sum(not truth(by[(case, control)]["history_valid"]) for case in cases)
        cope_invariant_failures = sum(
            not truth(by[(case, "cope")]["canonical_valid"])
            or not truth(by[(case, "cope")]["directive_valid"])
            for case in cases
        )
        control_invariant_failures = sum(
            not truth(by[(case, control)]["canonical_valid"])
            or not truth(by[(case, control)]["directive_valid"])
            for case in cases
        )
        comparison.update({
            "holm_efficacy_p": adjusted[control],
            "cope_history_failures": cope_history_failures,
            "control_history_failures": control_history_failures,
            "cope_invariant_failures": cope_invariant_failures,
            "control_invariant_failures": control_invariant_failures,
            "safety_no_excess": (
                cope_history_failures <= control_history_failures
                and cope_invariant_failures <= control_invariant_failures
            ),
            "locality_valid_pairs": len(valid), "cope_smaller": wins,
            "control_smaller": losses, "locality_ties": ties,
            "raw_locality_p": raw,
            "median_relative_byte_reduction": median(reductions) if reductions else 0.0,
        })
    locality_adjusted = V1.holm(locality_raw)
    for comparison in primary:
        comparison["holm_locality_p"] = locality_adjusted[comparison["control"]]
        comparison["control_gate"] = gate(comparison)
    secondary = [compare(control) for control in SECONDARY]
    secondary_adjusted = V1.holm({row["control"]: row["raw_efficacy_p"] for row in secondary})
    for row in secondary:
        row["holm_secondary_p"] = secondary_adjusted[row["control"]]
        row["secondary_cannot_rescue_primary"] = True
    status = claim_status(primary, infrastructure_valid)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "01_COPRIMARY.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(primary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(primary)
    with (args.output_dir / "02_SECONDARY.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(secondary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(secondary)
    (args.output_dir / "00_RESULT.md").write_text(
        "# Occurrence-sensitive learned formal result\n\n"
        f"- Infrastructure failures: **{len(infrastructure_failures)}**\n"
        f"- Neutral gate: **{primary[0]['control_gate']}**\n"
        f"- Governed gate: **{primary[1]['control_gate']}**\n"
        f"- Claim status: **{status}**\n\n"
        "Both primary controls must pass; secondary controls cannot rescue a failure.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
