from pathlib import Path

from experiments.structure_mutation_falsifier import run_experiment


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"


def test_structure_mutation_run_is_deterministic():
    first = run_experiment(CASES)
    second = run_experiment(CASES)
    first_keys = [(row["mutation_id"], row["operator"], row["path"], row["candidate_sha256"]) for row in first[1]]
    second_keys = [(row["mutation_id"], row["operator"], row["path"], row["candidate_sha256"]) for row in second[1]]
    assert first_keys == second_keys


def test_clean_controls_and_all_mutations_have_valid_evidence_boundary():
    clean, mutations, aggregate = run_experiment(CASES)
    assert len(clean) == 12
    assert all(row["pass"] for row in clean)
    assert mutations
    assert all(row["candidate_changed"] for row in mutations)
    assert all(not row["exact_accepted"] for row in mutations)
    assert not any(row["decomposed_crash"] for row in mutations)
    assert all(row["caller_state_unchanged"] for row in mutations)
    divergences = [row for row in mutations if row["decomposed_accepted"]]
    assert all(row["order_only_divergence"] != row["dangerous_blind_spot"] for row in divergences)
    assert all(not row["order_only_divergence"] and not row["dangerous_blind_spot"] for row in mutations if not row["decomposed_accepted"])
    assert sum(row["retained_candidates"] for row in aggregate) == len(mutations)


def test_every_operator_applicable_to_integer_only_states_is_exercised():
    _, mutations, _ = run_experiment(CASES)
    assert {row["operator"] for row in mutations} == {
        "delete_field", "add_unknown_field", "drop_list_item", "duplicate_list_item",
        "append_scalar", "reverse_list", "mutate_bool", "mutate_int", "mutate_string",
        "mutate_null",
    }
