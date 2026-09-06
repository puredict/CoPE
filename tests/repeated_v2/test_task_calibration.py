import copy

import pytest

from cope_benchmark.repeated_v2.task_calibration import (
    CalibrationBlockedError, CalibrationEpisode, calibration_grid, summarize_calibration, validate_calibration_split,
)
from tests.repeated_v2.catalog_fixtures import calibration_records


def test_exact_calibration_grid_and_disjoint_policy_seeds():
    cells = calibration_grid()
    assert len(cells) == 100
    assert len({tuple(cell.values()) for cell in cells}) == 100
    assert {cell["initial_state_id"] for cell in cells} == set(range(5))
    assert {cell["policy_seed"] for cell in cells} == {101, 131}
    assert cells == calibration_grid(reversed(range(10)))
    with pytest.raises(CalibrationBlockedError, match="overlap"):
        validate_calibration_split(policy_seeds=(11, 131))
    with pytest.raises(CalibrationBlockedError, match="frozen"):
        validate_calibration_split(policy_seeds=(103, 137))


@pytest.mark.parametrize("successes,eligible", [(0, False), (3, False), (4, True), (5, True), (9, True), (10, False)])
def test_clean_success_interval_is_inclusive_and_denominator_fixed(successes, eligible):
    summary = summarize_calibration(0, calibration_records(successes=successes), allow_synthetic=True)
    assert summary.total == 10
    assert summary.clean_success_rate == successes / 10
    assert summary.eligible_success_rate is eligible


def test_missing_duplicates_and_foreign_task_records_block():
    records = calibration_records()
    for bad in (records[:-1], records + records[:1], records[:-1] + calibration_records(1)[:1]):
        with pytest.raises(CalibrationBlockedError):
            summarize_calibration(0, bad, allow_synthetic=True)


@pytest.mark.parametrize("key,value", [("success", 1), ("policy_seed", 11), ("learned_policy", False),
                                      ("privileged_policy_state", True), ("clean_episode", False),
                                      ("status", "infrastructure_error"), ("max_policy_steps", 520),
                                      ("checkpoint_sha256", "unknown")])
def test_no_invalid_or_privileged_calibration_record(key, value):
    record = calibration_records()[0]
    record[key] = value
    with pytest.raises(CalibrationBlockedError):
        CalibrationEpisode.from_dict(record)


def test_synthetic_records_do_not_become_formal_evidence():
    with pytest.raises(CalibrationBlockedError, match="synthetic"):
        summarize_calibration(0, calibration_records())


@pytest.mark.parametrize("policy_id", ["mock", "openvla-scripted", "oracle_skill_controller", "fake-policy", "synthetic-vla", "controlled_mechanism"])
def test_a_known_fake_policy_cannot_claim_measured_provenance(policy_id):
    record = calibration_records()[0]
    record.update(policy_id=policy_id, provenance_kind="measured")
    with pytest.raises(CalibrationBlockedError, match="formal calibration forbids"):
        CalibrationEpisode.from_dict(record)


def test_no_method_difference_selection_fields():
    record = calibration_records()[0]
    record["cope_minus_baseline"] = 0.8
    with pytest.raises(CalibrationBlockedError, match="schema"):
        CalibrationEpisode.from_dict(record)


def test_timeout_and_manual_intervention_count_as_failures():
    records = calibration_records()
    records[0]["status"], records[0]["success"] = "timeout", False
    records[1]["status"], records[1]["success"] = "manual_intervention", False
    assert summarize_calibration(0, records, allow_synthetic=True).successes == 3
    records[0]["success"] = True
    with pytest.raises(CalibrationBlockedError, match="must count as failure"):
        summarize_calibration(0, records, allow_synthetic=True)


def test_checkpoints_and_initial_states_must_match():
    records = calibration_records()
    mixed = copy.deepcopy(records)
    mixed[0]["checkpoint_sha256"] = "d" * 64
    with pytest.raises(CalibrationBlockedError, match="one checkpoint"):
        summarize_calibration(0, mixed, allow_synthetic=True)
    with pytest.raises(CalibrationBlockedError, match="state digest mismatch"):
        summarize_calibration(0, records, initial_state_digests={str(i): "f" * 64 for i in range(5)}, allow_synthetic=True)


def test_offline_calibration_cli_uses_config_and_emits_blocked_report(tmp_path, capsys, monkeypatch):
    import json
    from tools.calibrate_repeated_v2_tasks import main
    from cope_benchmark.repeated_v2.config import SPECIFICATION

    monkeypatch.setenv("COPE_VLA_FACTORY", "must_never_be_imported:factory")
    assert main(["--config", str(SPECIFICATION), "--output-dir", str(tmp_path)]) == 2
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads((tmp_path / "calibration_report.json").read_text())
    assert printed == saved
    assert saved["status"] == "BLOCKED_CALIBRATION_EVIDENCE"
    assert saved["expected_cells"] == 100
    assert saved["provider_calls"] == saved["vla_calls"] == 0
    assert not (tmp_path / "calibration_records.json").exists()
    with pytest.raises(FileExistsError):
        main(["--config", str(SPECIFICATION), "--output-dir", str(tmp_path)])
