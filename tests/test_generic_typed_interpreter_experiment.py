from pathlib import Path

from experiments.generic_typed_interpreter_experiment import (
    aggregate_rows,
    run_experiment,
    source_audit,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"
FAULTS = ROOT / "research/generic_typed_interpreter_2026-08-03/01_FAULT_MANIFEST.csv"


def _run():
    return run_experiment(CASES, FAULTS)


def test_generic_interpreter_source_is_oracle_free():
    assert source_audit()["pass"]


def test_four_arm_clean_controls_pass():
    clean, _ = _run()
    assert len(clean) == 48
    assert all(row["pass"] for row in clean)
    assert all(row["common_validator_calls"] == 1 for row in clean)


def test_all_faults_are_changed_and_fail_closed_end_to_end():
    _, faults = _run()
    assert len(faults) == 88
    assert all(row["proposal_changed"] for row in faults)
    assert all(row["full_pipeline_rejected"] for row in faults)
    assert not any(row["end_to_end_fail_open"] for row in faults)
    assert not any(row["uncaught_crash"] for row in faults)
    assert all(row["caller_state_unchanged"] for row in faults)


def test_oracle_removal_exposes_omissions_but_retains_local_commission_guard():
    _, faults = _run()
    aggregate = aggregate_rows(faults)

    def value(axis, arm):
        row = next(item for item in aggregate if item["threat_axis"] == axis and item["arm"] == arm)
        return row["representation_fail_open"]

    assert value("all", "cope_exact") == 0
    assert value("all", "cope_generic") > 0
    assert value("commission_or_structure", "cope_generic") < value("commission_or_structure", "compact_tx")
    assert value("commission_or_structure", "cope_generic") < value("commission_or_structure", "fsr_pc")
    assert value("omission", "cope_generic") > 0
