"""Synthetic unit fixtures ONLY; never written as experiment output."""
import copy
import json

import pytest

from cope_benchmark.repeated_v2.analysis import (
    CHECKPOINTS, METHODS, analyze_protocol, audit_cells, comparison_evidence,
    correct_secondary_family, read_records, write_artifacts,
)


def fixture(protocol="end_to_end", condition="evidence_matched"):
    manifest, rows = [], []
    for index in range(3):
        mid = f"synthetic-unit-test-{index}"
        manifest.append(dict(master_episode_id=mid, pair_fields={"task_id":index},
            protocol_prefixes={p:{"event_count":ks[-1],"checkpoints":list(ks)} for p,ks in CHECKPOINTS.items()},
            information_conditions=[condition], methods={"non_oracle":list(METHODS),"oracle":[]},
            master_schedule_sha256="a"*64))
        for method in METHODS:
            for k in range(CHECKPOINTS[protocol][-1]+1):
                success = method in METHODS[:2] or k == 0
                rows.append(dict(information_condition=condition, protocol=protocol,
                    master_episode_id=mid, method=method, event_index=k,
                    status="COMPLETED", success=success, high_level_calls=int(k>0),
                    phase="formal", fixture=False,
                    evidence_admissibility="formal", freeze_sha256="b"*64,
                    master_schedule_sha256="a"*64, metrics={
                    "planning_fidelity_exact":int(success),"planning_fidelity_macro_f1":int(success),
                    "fidelity_precedes_execution":True,"history_corruption":not success,
                    "completed_step_regression":False,"wrong_occurrence_execution":[],
                    "hard_constraint_violations":[],"timeout":False,"manual_intervention":False,
                    "required_events_reached":True}))
    return manifest, rows


def analyze(manifest, rows, protocol="end_to_end"):
    return analyze_protocol(manifest,rows,protocol=protocol,condition="evidence_matched",
        comparator="full_state_regeneration", freeze_sha256="b"*64,replicates=40)


def test_complete_paired_curve_and_fidelity_mapping():
    a = analyze(*fixture())
    assert a["integrity"]["valid"]
    primary = next(row for row in a["paired_tests"] if row["primary"])
    assert primary["n_pairs"] == 3
    assert primary["risk_difference"] == 1
    assert len(a["summary_by_checkpoint"]) == len(METHODS)*4
    evidence = comparison_evidence(a, evidence_parity=True, reasoner_call_parity=True)
    assert evidence.cope_corruption_rate == 0
    assert evidence.comparator_corruption_rate == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "condition", "bool_index", "drift", "fake"])
def test_integrity_stops_before_numerics(mutation):
    manifest, rows = fixture()
    if mutation == "missing": rows.pop()
    if mutation == "duplicate": rows.append(copy.deepcopy(rows[0]))
    if mutation == "extra": rows.append(dict(rows[0],event_index=99))
    if mutation == "condition": rows[0]["information_condition"]="token_matched"
    if mutation == "bool_index": rows[0]["event_index"]=False
    if mutation == "drift": rows[0]["freeze_sha256"]="c"*64
    if mutation == "fake": rows[0]["evidence_admissibility"]="synthetic"
    before = copy.deepcopy(rows)
    a = analyze(manifest,rows)
    assert not a["integrity"]["valid"]
    assert not a["paired_tests"]
    assert "noninferiority" not in a
    assert rows == before


@pytest.mark.parametrize("value", ["false", None, 0.2, float("nan")])
def test_malformed_success_rejected(value):
    manifest, rows = fixture()
    rows[0]["success"] = value
    assert not analyze(manifest,rows)["integrity"]["valid"]


def test_timeout_success_and_baseline_call_rejected():
    manifest,rows=fixture()
    rows[0]["evaluation"]={"timeout":True}
    assert not analyze(manifest,rows)["integrity"]["valid"]
    rows[0].pop("evaluation")
    rows[0]["high_level_calls"]=1
    assert not analyze(manifest,rows)["integrity"]["valid"]


def test_missing_mechanism_metric_stays_unknown():
    manifest, rows=fixture()
    rows[1]["metrics"].pop("history_corruption")
    a=analyze(manifest,rows)
    assert a["integrity"]["valid"]
    assert comparison_evidence(a).cope_corruption_rate is None


@pytest.mark.parametrize("mutation", ["failure_success","masked_timeout","masked_success","masked_calls","missing_safety","bad_f1","bad_task"])
def test_adversarial_contradictions_fail_closed(mutation):
    manifest,rows=fixture()
    if mutation == "failure_success": rows[1]["status"]="UNREACHED_DUE_TO_PRIOR_FAILURE"
    if mutation == "masked_timeout": rows[1]["evaluation"]={"timeout":True}
    if mutation == "masked_success": rows[1]["final_active_task_success_after_last_event"]=False
    if mutation == "masked_calls": rows[0]["metrics"]["high_level_calls"]=1
    if mutation == "missing_safety": rows[1]["metrics"].pop("manual_intervention")
    if mutation == "bad_f1": rows[1]["metrics"]["planning_fidelity_macro_f1"]=17
    if mutation == "bad_task": manifest[0].pop("pair_fields")
    assert not analyze(manifest,rows)["integrity"]["valid"]


def test_secondary_condition_cannot_feed_binding_claims():
    manifest,rows=fixture(condition="token_matched")
    a=analyze_protocol(manifest,rows,protocol="end_to_end",condition="token_matched",
        comparator="full_state_regeneration",freeze_sha256="b"*64,replicates=40)
    with pytest.raises(ValueError,match="token-matched"):
        comparison_evidence(a)


def test_temporal_claim_requires_actual_problem_linkage():
    a=analyze(*fixture())
    assert comparison_evidence(a).fidelity_precedes_execution is False


@pytest.mark.parametrize("mutation", ["pilot", "restart", "phantom", "condition_alias", "bad_history", "null_success_alias"])
def test_remaining_adversarial_cases_fail_in_integrity(mutation):
    manifest,rows=fixture()
    if mutation == "pilot": rows[0].update(phase="pilot",fixture=True)
    if mutation == "restart": rows[1].update(status="METHOD_PLANNING_FAILURE",success=False)
    if mutation == "phantom": rows[1].update(status="EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE",success=False)
    if mutation == "condition_alias": rows[0]["condition"]="token_matched"
    if mutation == "bad_history": rows[0]["metrics"]["history_corruption"]="junk"
    if mutation == "null_success_alias": rows[0].update(success=None,final_active_task_success_after_last_event=True)
    assert not analyze(manifest,rows)["integrity"]["valid"]


def test_noncheckpoint_event_cannot_be_dropped():
    manifest,rows=fixture()
    rows=[row for row in rows if row["event_index"] != 3]
    assert not analyze(manifest,rows)["integrity"]["valid"]


def test_holm_primary_outside_fixed_family():
    a,b=analyze(*fixture()),analyze(*fixture("controlled"),protocol="controlled")
    family=correct_secondary_family([a,b])
    assert family == {"prespecified_size":13,"observed_hypotheses":13,"complete":True}
    assert "holm_p" not in next(row for row in a["paired_tests"] if row["primary"])
    assert all("holm_p" in row for row in b["paired_tests"])


def test_no_formal_data_report_empty_tables_exclusive(tmp_path):
    output=tmp_path/"report"
    write_artifacts(output,[],{"status":"BLOCKED_CALIBRATION_UNAVAILABLE"},provenance={})
    assert "No formal performance estimate" in (output/"REPORT.md").read_text()
    assert (output/"summary_by_method.csv").read_text().count("\n") == 1
    assert all(path.suffix in (".md",".csv",".txt") for path in output.iterdir())
    with pytest.raises(FileExistsError):
        write_artifacts(output,[],{},provenance={})


def test_global_integrity_failure_suppresses_otherwise_valid_group_tables(tmp_path):
    analysis = analyze(*fixture())
    assert analysis["integrity"]["valid"]
    output = tmp_path / "invalid-submission"
    write_artifacts(output, [analysis], {"status": "INVALID_RUN"}, provenance={})
    assert (output / "paired_tests.csv").read_text().count("\n") == 1
    assert "No curve drawn" in (output / "paper_curves.md").read_text()
    assert "No formal performance estimate" in (output / "REPORT.md").read_text()


@pytest.mark.parametrize("content", ['{"success":true}', '{"success":true,"success":false}\n', '{"x":NaN}\n', '\n'])
def test_strict_reader_rejects_torn_duplicate_nan_blank(tmp_path,content):
    path=tmp_path/"raw.txt"
    path.write_text(content)
    with pytest.raises(ValueError): read_records(path)
