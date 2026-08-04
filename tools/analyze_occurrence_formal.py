#!/usr/bin/env python3
"""Locked paired analysis for the occurrence-sensitive learned formal gate."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("formal_v1", ROOT / "tools" / "analyze_sequential_formal.py")
assert SPEC is not None and SPEC.loader is not None
V1 = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V1)

from cope.occurrence_prompting import ARMS, build_recovery_input
from cope.occurrence_sequence import build_recurrence_case
from cope.formal_artifact_validation import validate_event_results_artifacts
from cope.types import canonical_json
from experiments.occurrence_formal_runner import RESULT_FIELDS
from experiments.occurrence_formal_preflight import EXPECTED_MANIFEST_SHA256, validate_manifest


PRIMARY = ("neutral_patch", "governed_delta")
SECONDARY = ("fsr_pc", "full_replan")
TRUE = {"1", "true", "yes"}
FALSE = {"0", "false", "no"}
BOOLEAN_FIELDS = (
    "provider_called", "parser_valid", "semantic_valid", "canonical_valid",
    "history_valid", "directive_valid",
)
INFRA = ("provider_timeout", "provider_transport_outage", "provider_http_", "ambiguous_interrupted_call_no_retry")


def truth(value: Any) -> bool:
    return str(value).strip().lower() in TRUE


@lru_cache(maxsize=None)
def _expected_input_sha256(
    case_id: str, done_object: str, recurring_object: str,
    intermediate_object: str, recurrence_depth: int,
) -> str:
    pre, event, _ = build_recurrence_case(
        case_id=case_id, done_object=done_object,
        recurring_object=recurring_object,
        intermediate_object=intermediate_object,
        recurrence_depth=recurrence_depth,
    )
    return build_recovery_input(
        case_id=case_id, pre_state=pre, event=event,
    ).input_hash


def expected_input_sha256(row: dict[str, str]) -> str:
    return _expected_input_sha256(
        row["case_id"], row["done_object"], row["recurring_object"],
        row["intermediate_object"], int(row["recurrence_depth"]),
    )


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


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


def failure_taxonomy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        output.append({
            "arm": arm,
            "cells": len(arm_rows),
            "infrastructure_failures": sum(
                any(marker in row["failure_class"] for marker in INFRA)
                for row in arm_rows
            ),
            "parser_failures": sum(not truth(row["parser_valid"]) for row in arm_rows),
            "semantic_failures_after_parse": sum(
                truth(row["parser_valid"]) and not truth(row["semantic_valid"])
                for row in arm_rows
            ),
            "canonical_failures_after_semantics": sum(
                truth(row["semantic_valid"]) and not truth(row["canonical_valid"])
                for row in arm_rows
            ),
            "history_failures_after_semantics": sum(
                truth(row["semantic_valid"]) and not truth(row["history_valid"])
                for row in arm_rows
            ),
            "directive_failures_after_semantics": sum(
                truth(row["semantic_valid"]) and not truth(row["directive_valid"])
                for row in arm_rows
            ),
            "complete_successes": sum(all(truth(row[field]) for field in (
                "parser_valid", "semantic_valid", "canonical_valid",
                "history_valid", "directive_valid",
            )) for row in arm_rows),
        })
    return output


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
    validate_event_results_artifacts(
        event_results=args.event_results, csv_rows=rows,
        result_fields=RESULT_FIELDS,
        expected_manifest_sha256=EXPECTED_MANIFEST_SHA256,
    )
    keys = [(row["case_id"], row["arm"], int(row["event_index"])) for row in rows]
    if len(keys) != 200 or len(set(keys)) != 200 or set(keys) != expected:
        raise ValueError("occurrence result cells are missing, duplicated, or extra")
    by = {(row["case_id"], row["arm"]): row for row in rows}
    for case, manifest_row in cases.items():
        group = [by[(case, arm)] for arm in ARMS]
        expected_hash = expected_input_sha256(manifest_row)
        hashes = {row["input_sha256"] for row in group if truth(row["provider_called"])}
        if hashes != {expected_hash}:
            raise ValueError(f"occurrence common input drift: {case}")
        if any(int(row["retry_count"]) != 0 for row in group):
            raise ValueError(f"occurrence retry detected: {case}")
        if any(not truth(row["provider_called"]) for row in group):
            raise ValueError(f"occurrence cell lacks provider call: {case}")
        for row in group:
            if any(
                row[field].strip().lower() not in TRUE | FALSE
                for field in BOOLEAN_FIELDS
            ):
                raise ValueError(f"occurrence result boolean is noncanonical: {case}")
            if (
                row["sequence_id"] != case
                or row["triple_index"] != manifest_row["triple_index"]
                or row["recurrence_depth"] != manifest_row["recurrence_depth"]
            ):
                raise ValueError(f"occurrence result metadata drift: {case}")
            parser_valid = truth(row["parser_valid"])
            semantic_valid = truth(row["semantic_valid"])
            invariant_flags = (
                truth(row["canonical_valid"]), truth(row["history_valid"]),
                truth(row["directive_valid"]),
            )
            if semantic_valid and not parser_valid:
                raise ValueError(f"occurrence semantic/parser flags inconsistent: {case}")
            if any(invariant_flags) and not semantic_valid:
                raise ValueError(f"occurrence invariant/semantic flags inconsistent: {case}")
            complete_success = all(truth(row[field]) for field in (
                "parser_valid", "semantic_valid", "canonical_valid",
                "history_valid", "directive_valid",
            ))
            if parser_valid and (
                int(row["proposal_bytes"]) <= 0
                or not is_sha256(row["proposal_sha256"])
            ):
                raise ValueError(f"occurrence parsed proposal evidence invalid: {case}")
            if semantic_valid and not is_sha256(row["candidate_sha256"]):
                raise ValueError(f"occurrence candidate evidence invalid: {case}")
            if complete_success and (
                row["failure_class"] or not is_sha256(row["response_sha256"])
            ):
                raise ValueError(f"occurrence success evidence inconsistent: {case}")
            if not parser_valid and not row["failure_class"]:
                raise ValueError(f"occurrence parser failure lacks classification: {case}")
            if parser_valid and not semantic_valid and not row["failure_class"]:
                raise ValueError(f"occurrence semantic failure lacks classification: {case}")
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
    taxonomy = failure_taxonomy(rows)
    with (args.output_dir / "03_FAILURE_TAXONOMY.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(taxonomy[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(taxonomy)
    (args.output_dir / "00_RESULT.md").write_text(
        "# Occurrence-sensitive learned formal result\n\n"
        f"- Infrastructure failures: **{len(infrastructure_failures)}**\n"
        f"- Neutral gate: **{primary[0]['control_gate']}**\n"
        f"- Governed gate: **{primary[1]['control_gate']}**\n"
        f"- Claim status: **{status}**\n\n"
        "Both primary controls must pass; secondary controls cannot rescue a failure.\n",
        encoding="utf-8",
    )
    decision = {
        "schema": "occurrence-formal-analysis-decision-v1",
        "result_cells": len(rows),
        "infrastructure_valid": infrastructure_valid,
        "neutral_gate": bool(primary[0]["control_gate"]),
        "governed_gate": bool(primary[1]["control_gate"]),
        "joint_primary_gate": bool(
            infrastructure_valid and all(row["control_gate"] for row in primary)
        ),
        "claim_status": status,
        "secondary_can_rescue": False,
    }
    (args.output_dir / "04_DECISION.txt").write_text(
        canonical_json(decision) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
