from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from experiments.sequential_formal_runner import RESULT_FIELDS


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_sequential_formal", ROOT / "tools" / "analyze_sequential_formal.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exact_mcnemar_known_all_discordant_result():
    assert MODULE.exact_mcnemar(10, 0) == 0.001953125
    assert MODULE.exact_mcnemar(0, 10) == 0.001953125
    assert MODULE.exact_mcnemar(0, 0) == 1.0


def test_clopper_pearson_and_odds_cover_boundaries():
    low, high = MODULE.clopper_pearson(10, 10)
    assert 0.69 < low < 0.70
    assert high == 1.0
    assert MODULE.odds(0.0) == 0.0
    assert MODULE.odds(1.0) == float("inf")


def test_holm_is_monotone_and_familywise_adjusted():
    adjusted = MODULE.holm({"a": 0.01, "b": 0.04})
    assert adjusted == {"a": 0.02, "b": 0.04}


def test_decisive_gate_has_frozen_practical_safety_and_locality_thresholds():
    accepted = dict(
        success_p=0.049,
        risk_difference=0.15,
        safety_no_excess=True,
        locality_p=0.049,
        locality_median_relative_reduction=0.20,
    )
    assert MODULE.decisive_experiment_gate(**accepted) is True
    for field, failing in (
        ("success_p", 0.05),
        ("risk_difference", 0.149),
        ("safety_no_excess", False),
        ("locality_p", 0.05),
        ("locality_median_relative_reduction", 0.199),
    ):
        case = dict(accepted)
        case[field] = failing
        assert MODULE.decisive_experiment_gate(**case) is False


def test_analysis_pipeline_applies_frozen_decisive_gate(tmp_path, monkeypatch):
    manifest = ROOT / "manifests" / "sequential_formal_40x4x2_v1.csv"
    with manifest.open(newline="", encoding="utf-8") as handle:
        sequences = list(csv.DictReader(handle))
    event_results = tmp_path / "events.csv"
    rows = []
    for sequence_index, sequence in enumerate(sequences):
        for arm in ("cope", "neutral_patch", "fsr_pc", "full_replan"):
            for event_index in (1, 2):
                row = dict.fromkeys(RESULT_FIELDS, "")
                row.update(
                    sequence_id=sequence["sequence_id"], arm=arm,
                    event_index=event_index, substrate_eligible=True,
                    provider_called=True, retry_count=0, parser_valid=True,
                    semantic_valid=True, revision_hash_continuity=True,
                    intermediate_invariant_valid=True, progress_preserved=True,
                    stale_commitment_executed=False, final_intent_satisfied=True,
                    action_budget_respected=True, call_budget_respected=True,
                    proposal_bytes=(100 if arm == "cope" else 200),
                    prompt_tokens=10, completion_tokens=5, latency_seconds=0.1,
                    failure_class="",
                    input_sha256=f"input-{sequence['sequence_id']}-{event_index}",
                    prefix_action_sha256=f"action-{sequence['sequence_id']}",
                    prefix_simulator_sha256=f"sim-{sequence['sequence_id']}",
                )
                if arm == "neutral_patch" and sequence_index < 8 and event_index == 2:
                    row["final_intent_satisfied"] = False
                    row["failure_class"] = "synthetic_incorrect_final_intent"
                rows.append(row)
    with event_results.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    output = tmp_path / "analysis"
    monkeypatch.setattr(
        sys, "argv",
        [
            "analyze", "--manifest", str(manifest),
            "--event-results", str(event_results), "--output-dir", str(output),
        ],
    )
    assert MODULE.main() == 0
    with (output / "02_COMPARISONS.csv").open(newline="", encoding="utf-8") as handle:
        primary = next(csv.DictReader(handle))
    assert float(primary["paired_risk_difference"]) == pytest.approx(0.2)
    assert float(primary["exact_mcnemar_p"]) == 0.0078125
    assert float(primary["locality_median_relative_byte_reduction"]) == 0.5
    assert primary["decisive_experiment_gate"] == "True"

    rows[0]["input_sha256"] = "contaminated-arm-specific-input"
    contaminated = tmp_path / "contaminated.csv"
    with contaminated.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    monkeypatch.setattr(
        sys, "argv",
        [
            "analyze", "--manifest", str(manifest),
            "--event-results", str(contaminated),
            "--output-dir", str(tmp_path / "rejected"),
        ],
    )
    with pytest.raises(ValueError, match="common event-1 input drift"):
        MODULE.main()
