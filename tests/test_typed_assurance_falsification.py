from pathlib import Path

from experiments.typed_assurance_falsification import aggregate_rows, run_experiment


ROOT = Path(__file__).resolve().parents[1]
CASE_MANIFEST = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"
FAULT_MANIFEST = ROOT / "research/typed_assurance_falsification_2026-08-03/01_FAULT_MANIFEST.csv"


def _results():
    return run_experiment(CASE_MANIFEST, FAULT_MANIFEST)


def test_all_canonical_controls_pass():
    clean, _ = _results()
    assert len(clean) == 36
    assert all(row["pass"] for row in clean)
    assert all(row["common_validator_calls"] == 1 for row in clean)


def test_all_faults_are_noncanonical_and_fail_closed():
    _, faults = _results()
    assert len(faults) == 48
    assert all(row["proposal_changed"] for row in faults)
    assert all(row["full_pipeline_rejected"] for row in faults)
    assert not any(row["end_to_end_fail_open"] for row in faults)
    assert not any(row["uncaught_crash"] for row in faults)
    assert all(row["caller_state_unchanged"] for row in faults)


def test_matched_canonical_guard_equalizes_all_arms():
    _, faults = _results()
    aggregate = aggregate_rows(faults)
    assert {row["arm"] for row in aggregate} == {"cope", "compact_tx", "fsr_pc"}
    assert all(row["parser_or_matched_guard_rejects"] == 16 for row in aggregate)
