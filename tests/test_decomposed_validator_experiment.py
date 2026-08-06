from pathlib import Path

from experiments.decomposed_validator_experiment import (
    predicate_coverage,
    run_experiment,
    source_audit,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"
FAULTS = ROOT / "research/generic_typed_interpreter_2026-08-03/01_FAULT_MANIFEST.csv"


def _run():
    return run_experiment(CASES, FAULTS)


def test_validator_source_is_oracle_free():
    assert source_audit()["pass"]


def test_clean_candidates_have_no_false_rejection():
    clean, _ = _run()
    assert len(clean) == 48
    assert all(row["candidate_materialized"] for row in clean)
    assert all(row["exact_validator_accepted"] for row in clean)
    assert all(row["decomposed_validator_accepted"] for row in clean)
    assert all(row["exact_decomposed_parity"] for row in clean)


def test_decomposed_validator_matches_exact_on_all_materialized_faults():
    _, faults = _run()
    materialized = [row for row in faults if row["candidate_materialized"]]
    assert len(faults) == 88
    assert len(materialized) == 39
    assert sum(row["native_rejected"] for row in faults) == 49
    assert all(row["candidate_incorrect"] for row in materialized)
    assert all(not row["exact_validator_accepted"] for row in materialized)
    assert all(not row["decomposed_validator_accepted"] for row in materialized)
    assert all(row["violated_group_count"] > 0 for row in materialized)
    assert all(row["full_decomposed_pipeline_rejected"] for row in faults)


def test_predicate_ablation_has_no_clean_false_positive():
    clean, faults = _run()
    coverage = predicate_coverage(clean, faults)
    assert len(coverage) == 8
    assert all(row["clean_false_positive_count"] == 0 for row in coverage)
