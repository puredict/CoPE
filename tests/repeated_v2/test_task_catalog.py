import copy
import json

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_sha256
from cope_benchmark.repeated_v2.task_catalog import (
    CatalogBlockedError, DEFAULT_CATALOG_PATH, TaskCatalog, load_task_catalog, select_eligible_tasks, task_catalog_gaps,
)
from tests.repeated_v2.catalog_fixtures import synthetic_catalog


def test_real_catalog_enumerates_all_ten_and_cannot_be_selected():
    catalog = load_task_catalog()
    assert DEFAULT_CATALOG_PATH.exists()
    assert [task.task_id for task in catalog.tasks] == list(range(10))
    assert catalog.provenance_kind == "source_backed"
    assert len(catalog.tasks[5].initial_achievement_goals) == 1
    assert catalog.tasks[6].initial_achievement_goals[1]["arguments"][1] == "living_room_table_plate_right_region"
    assert {task.task_id for task in catalog.tasks if task.initial_state_digests} == {1, 5, 7}
    assert all(not task.calibration_records for task in catalog.tasks)
    assert task_catalog_gaps(catalog) == task_catalog_gaps(load_task_catalog())
    with pytest.raises(CatalogBlockedError, match="BLOCKED_TASK_CATALOG_GAPS"):
        select_eligible_tasks(catalog)


@pytest.mark.parametrize("count", [8, 9, 10])
def test_include_every_eligible_task(count):
    catalog = synthetic_catalog(count)
    assert [task.task_id for task in select_eligible_tasks(catalog, allow_synthetic=True)] == list(range(count))


def test_less_than_eight_blocks_without_relaxing_rule():
    with pytest.raises(CatalogBlockedError, match="BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS"):
        select_eligible_tasks(synthetic_catalog(7), allow_synthetic=True)


def test_formal_selection_rejects_synthetic_catalog():
    with pytest.raises(CatalogBlockedError, match="synthetic"):
        select_eligible_tasks(synthetic_catalog())


@pytest.mark.parametrize("field", ["milestone_predicates", "hard_safety_constraints", "soft_preference_templates",
                                  "alternative_valid_goals", "safe_event_injection_poses", "semantic_triggers",
                                  "dynamic_evaluator_predicates", "planner_compiler_metadata", "initial_state_digests",
                                  "event_feasibility", "calibration_records"])
def test_any_semantic_gap_blocks_catalog_even_with_nine_other_tasks(field):
    raw = synthetic_catalog().to_dict()
    raw["tasks"][9][field] = {} if isinstance(raw["tasks"][9][field], dict) else []
    with pytest.raises(CatalogBlockedError, match="task 9"):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)


def test_task_catalog_snapshot_is_deeply_immutable_and_hash_stable():
    raw = synthetic_catalog().to_dict()
    catalog = TaskCatalog.from_dict(raw)
    original = canonical_sha256(catalog.to_dict())
    raw["tasks"][0]["semantic_triggers"].clear()
    assert canonical_sha256(catalog.to_dict()) == original
    with pytest.raises(TypeError):
        catalog.tasks[0].structural_checks["safe_changeable_grounding"]["passed"] = False
    copy_out = catalog.to_dict()
    copy_out["tasks"][0]["calibration_records"].clear()
    assert canonical_sha256(catalog.to_dict()) == original


@pytest.mark.parametrize("mutation", ["missing_task", "duplicate_task", "method_difference", "nan", "malformed_goal"])
def test_malformed_and_selective_catalog_schemas_block(mutation):
    raw = synthetic_catalog().to_dict()
    if mutation == "missing_task":
        raw["tasks"].pop()
    elif mutation == "duplicate_task":
        raw["tasks"][9] = copy.deepcopy(raw["tasks"][0])
    elif mutation == "method_difference":
        raw["selection_rule"] = "maximize_cope_minus_baseline"
    elif mutation == "nan":
        raw["tasks"][0]["planner_compiler_metadata"]["confidence"] = float("nan")
    else:
        raw["tasks"][0]["initial_achievement_goals"] = [1]
    with pytest.raises(CatalogBlockedError):
        TaskCatalog.from_dict(raw)


def test_duplicate_json_keys_and_unknown_task_fields_fail_closed(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"one","schema_version":"two"}')
    with pytest.raises(CatalogBlockedError, match="duplicate"):
        load_task_catalog(path)
    raw = synthetic_catalog().to_dict()
    raw["tasks"][0]["method_success_delta"] = 1
    path.write_text(json.dumps(raw))
    with pytest.raises(CatalogBlockedError, match="invalid task record schema"):
        load_task_catalog(path)


def test_fixed_step_trigger_and_missing_feasibility_cannot_be_admitted():
    raw = synthetic_catalog().to_dict()
    next(iter(raw["tasks"][0]["semantic_triggers"].values()))["predicate"] = "policy_step_gte"
    with pytest.raises(CatalogBlockedError, match="fixed-step"):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)
    raw = synthetic_catalog().to_dict()
    next(iter(raw["tasks"][0]["event_feasibility"].values()))["passed"] = None
    with pytest.raises(CatalogBlockedError, match="unverified event feasibility"):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)


def test_calibration_backbone_must_be_identical_across_tasks():
    raw = synthetic_catalog().to_dict()
    for record in raw["tasks"][0]["calibration_records"]:
        record["checkpoint_sha256"] = "d" * 64
    with pytest.raises(CatalogBlockedError, match="share a clean calibration"):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)


def test_catalog_cli_supports_package_flags_and_labels_blocked_candidates(tmp_path, capsys, monkeypatch):
    from cope_benchmark.repeated_v2.config import SPECIFICATION
    from tools.build_repeated_v2_task_catalog import main

    monkeypatch.setenv("COPE_REASONER_FACTORY", "must_never_be_imported:factory")
    destination = tmp_path / "task_catalog_v2.json"
    args = ["--config", str(SPECIFICATION), "--calibration-dir", str(tmp_path / "missing"), "--output", str(destination)]
    assert main(args) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "BLOCKED_TASK_CATALOG_GAPS"
    assert printed["selected_task_ids"] == []
    assert printed["provider_calls"] == printed["vla_calls"] == 0
    assert any("BLOCKED_CALIBRATION_EVIDENCE" in blocker for blocker in printed["blockers"])
    assert load_task_catalog(destination).to_dict() == load_task_catalog().to_dict()
    assert json.loads(destination.with_name(destination.name + ".status.json").read_text()) == printed
    with pytest.raises(FileExistsError):
        main(args)


@pytest.mark.parametrize("field,value", [("arguments", 1), ("arguments", [["object"]]), ("predicate", []), ("family_key", {})])
def test_nested_goal_schema_cannot_raise_unstructured_errors(field, value):
    raw = synthetic_catalog().to_dict()
    raw["tasks"][0]["initial_achievement_goals"][0][field] = value
    with pytest.raises(CatalogBlockedError):
        TaskCatalog.from_dict(raw)
