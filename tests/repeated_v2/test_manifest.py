"""Synthetic catalog fixtures exercise complete counts; never formal evidence."""
from copy import deepcopy
from pathlib import Path

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_json, canonical_sha256
from cope_benchmark.repeated_v2.config import load_config, validate_config
from cope_benchmark.repeated_v2.manifest import (
    build_manifest, event_cell_keys, expected_counts, read_manifest, validate_manifest, write_manifest,
)
from cope_benchmark.repeated_v2.scheduler import MasterSchedule
from tests.repeated_v2.catalog_fixtures import synthetic_catalog

ROOT = Path(__file__).resolve().parents[2]
SHA = "84e1e742579899adb67efee92cef16efca063b31"


def config():
    return load_config(ROOT / "configs/repeated_interruptions_v2_formal.yaml")


@pytest.mark.parametrize("tasks,masters,trajectories,cells,checkpoints", [
    (8, 120, 4320, 25920, 19440), (10, 150, 5400, 32400, 24300),
])
def test_exact_counts(tasks, masters, trajectories, cells, checkpoints):
    value = expected_counts(tasks, config())
    assert value["unique_master_sessions"] == masters
    assert value["all_conditions"]["method_trajectories"] == trajectories
    assert value["all_conditions"]["event_cells"] == cells
    assert value["all_conditions"]["checkpoint_records"] == checkpoints
    assert value["per_condition"]["by_protocol"]["controlled"]["event_cells"] == masters * 9 * 8
    assert value["per_condition"]["by_protocol"]["end_to_end"]["event_cells"] == masters * 9 * 4
    assert value["all_conditions"]["oracle_trajectories"] == masters * 4


def test_manifest_is_one_master_schedule_not_independent_k_episodes(tmp_path):
    catalog = synthetic_catalog(task_count=8)
    rows = build_manifest(config(), catalog, source_commit=SHA, allow_synthetic=True)
    assert len(rows) == 120
    assert canonical_json(rows) == canonical_json(build_manifest(config(), catalog, source_commit=SHA, allow_synthetic=True))
    keys = list(event_cell_keys(rows))
    assert len(keys) == len(set(keys)) == 25920
    for row in rows:
        schedule = MasterSchedule.from_dict(row["master_schedule"])
        assert schedule.master_episode_id == row["master_episode_id"]
        assert row["master_schedule_sha256"] == canonical_sha256(schedule)
        assert schedule.prefix(4, protocol="end_to_end") == schedule.events[:4]
        for k in (0,1,2,4,8):
            assert schedule.prefix(k) == schedule.events[:k]
    assert validate_manifest(rows, config(), catalog, source_commit=SHA, allow_synthetic=True)["passed"]
    target = tmp_path / "manifest.jsonl"
    write_manifest(target, rows)
    assert read_manifest(target) == rows
    with pytest.raises(FileExistsError):
        write_manifest(target, rows)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "extra", "schedule", "task"])
def test_manifest_rejects_edited_or_missing_sessions(damage):
    catalog = synthetic_catalog(task_count=8)
    rows = build_manifest(config(), catalog, source_commit=SHA, allow_synthetic=True)
    if damage == "missing":
        rows.pop()
    elif damage == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif damage == "extra":
        extra = deepcopy(rows[0])
        extra["master_episode_id"] = "unexpected"
        rows.append(extra)
    elif damage == "schedule":
        rows[0]["master_schedule"]["events"].reverse()
    else:
        rows[0]["pair_fields"]["task_id"] = 9
    assert not validate_manifest(rows, config(), catalog, source_commit=SHA, allow_synthetic=True)["passed"]


def test_config_rejects_scientific_drift_and_duplicate_keys(tmp_path):
    for section, key, value in [
        ("task_selection", "min_tasks", 4), ("task_selection", "formal_policy_seeds", [101,131]),
        ("events", "min_steps_between_events", 0), ("reasoner", "semantic_retries", 1),
        ("vla", "forbid_privileged_state", False), ("kernel", "legacy_demoted_mode_forbidden", False),
    ]:
        bad = config()
        bad[section][key] = value
        assert validate_config(bad)
    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text("schema_version: first\nschema_version: second\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_config(bad_path)


def test_manifest_read_rejects_torn_duplicate_key_and_blank_lines(tmp_path):
    target = tmp_path / "manifest.jsonl"
    for data in ('{}', '{"id":1,"id":2}\n', '\n'):
        target.write_text(data)
        with pytest.raises(ValueError):
            read_manifest(target)
