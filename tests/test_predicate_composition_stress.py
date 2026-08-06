from pathlib import Path

from cope.decomposed_validator import PREDICATE_GROUPS
from experiments.predicate_composition_stress import run_experiment


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"
MUTATIONS = ROOT / "research/predicate_composition_2026-08-03/01_MUTATION_MANIFEST.csv"


def _run():
    return run_experiment(CASES, MUTATIONS)


def test_clean_controls_and_composition_shape():
    clean, faults, _ = _run()
    assert len(clean) == 12
    assert all(row["pass"] for row in clean)
    assert len(faults) == 64
    assert sum(row["combination_size"] == 1 for row in faults) == 8
    assert sum(row["combination_size"] == 2 for row in faults) == 21
    assert sum(row["combination_size"] == 3 for row in faults) == 35


def test_every_candidate_is_rejected_with_exact_attribution():
    _, faults, _ = _run()
    assert all(row["candidate_changed"] for row in faults)
    assert all(not row["exact_validator_accepted"] for row in faults)
    assert all(not row["decomposed_validator_accepted"] for row in faults)
    assert all(row["attribution_exact"] for row in faults)
    assert all(row["caller_state_unchanged"] for row in faults)


def test_each_predicate_group_has_a_singleton_ablation_fail_open():
    _, _, ablation = _run()
    assert len(ablation) == 8
    assert tuple(row["predicate_group"] for row in ablation) == PREDICATE_GROUPS
    assert all(row["would_fail_open_if_group_removed"] for row in ablation)
    assert all(row["pass"] for row in ablation)
