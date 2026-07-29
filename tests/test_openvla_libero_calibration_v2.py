from __future__ import annotations

import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from cope.calibration import atomic_episode_claim, canonical_hash, partition_entries
from cope.calibration_v2 import (
    PROTOCOL_LABEL,
    audit_v2_terminals,
    build_v2_entries,
    directory_inventory,
    ensure_output_separation,
    infrastructure_attempts,
    load_v2_resume_trace,
    read_jsonl,
    validate_config_contract,
    validate_static_manifest,
)
from experiments.openvla_libero_calibration import _load_yaml
from experiments.openvla_libero_calibration_v2 import worker


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/openvla_libero_10_calibration_v2.yaml"
MANIFEST_PATH = ROOT / "manifests/openvla_libero_10_calibration_v2.jsonl"


def _config() -> dict:
    return _load_yaml(CONFIG_PATH)


def _terminal(entry: dict, config_hash: str) -> dict:
    return {
        **entry,
        "schema_version": "openvla-libero-clean-calibration-v2-episode",
        "complete": True,
        "valid_experimental_terminal": True,
        "infrastructure_failure": False,
        "phase": "calibration",
        "protocol_label": PROTOCOL_LABEL,
        "config_hash": config_hash,
        "checkpoint": {
            "revision": "80970322773f81baa2e22fe495d0487b93a05cfa"
        },
        "warmup_steps_consumed": 10,
        "policy_step_budget": 520,
        "policy_steps_consumed": 520,
        "environment_steps_consumed": 530,
        "success": False,
        "termination_reason": "policy_step_budget_exhausted",
    }


def test_libero10_v2_requires_520_policy_steps_not_220() -> None:
    config = _config()
    validate_config_contract(config)
    assert config["runtime"]["policy_step_budget"] == 520
    bad = deepcopy(config)
    bad["runtime"]["policy_step_budget"] = 220
    with pytest.raises(ValueError, match="520"):
        validate_config_contract(bad)


def test_ten_warmups_are_separate_from_520_policy_inferences(tmp_path: Path) -> None:
    config = _config()
    entry = build_v2_entries(config)[0]
    config_hash = canonical_hash(config)
    path = tmp_path / entry["episode_id"] / "episode.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_terminal(entry, config_hash)), encoding="utf-8")
    audit = audit_v2_terminals(
        config=config,
        entries=(entry,),
        episode_roots=(tmp_path,),
        config_hash=config_hash,
    )
    assert audit["passed"]
    assert audit["terminals"][0]["environment_steps_consumed"] == 520 + 10

    bad = _terminal(entry, config_hash)
    bad["environment_steps_consumed"] = 540
    path.write_text(json.dumps(bad), encoding="utf-8")
    audit = audit_v2_terminals(
        config=config,
        entries=(entry,),
        episode_roots=(tmp_path,),
        config_hash=config_hash,
    )
    assert not audit["passed"]
    assert any("environment step accounting" in error for error in audit["errors"])


def test_manifest_has_15_unique_deterministic_entries() -> None:
    config = _config()
    first = build_v2_entries(config)
    second = build_v2_entries(config)
    assert first == second
    assert len(first) == 15
    assert len({entry["episode_id"] for entry in first}) == 15
    assert tuple(read_jsonl(MANIFEST_PATH)) == first
    assert validate_static_manifest(config, MANIFEST_PATH) == first


def test_atomic_claim_has_one_winner_and_same_worker_resume(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"

    def claim(_: int) -> bool:
        try:
            atomic_episode_claim(
                path,
                episode_id="episode",
                worker_id=2,
                worker_count=8,
                config_hash="a" * 64,
                launcher_id="v2",
                resume=False,
            )
        except FileExistsError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(claim, range(8))) == 1
    resumed = atomic_episode_claim(
        path,
        episode_id="episode",
        worker_id=2,
        worker_count=8,
        config_hash="a" * 64,
        launcher_id="v2-resume",
        resume=True,
    )
    assert resumed["claim_reused_for_resume"]
    with pytest.raises(ValueError, match="identity mismatch"):
        atomic_episode_claim(
            path,
            episode_id="episode",
            worker_id=3,
            worker_count=8,
            config_hash="a" * 64,
            launcher_id="wrong-worker",
            resume=True,
        )


def test_worker_partition_is_disjoint_and_loader_is_outside_episode_loop() -> None:
    entries = build_v2_entries(_config())
    partitions = [
        partition_entries(entries, worker_id=worker_id, worker_count=8)
        for worker_id in range(8)
    ]
    flattened = [entry["episode_id"] for group in partitions for entry in group]
    assert len(flattened) == len(set(flattened)) == 15
    assert max(map(len, partitions)) == 2
    source = inspect.getsource(worker)
    assert source.count("load_model_and_processor(loader_cfg)") == 1
    assert '"shared_inference_port": None' in source


def test_task_state_seed_and_checkpoint_contracts_fail_closed(tmp_path: Path) -> None:
    config = _config()
    bad_task = deepcopy(config)
    bad_task["task_ids"] = [1, 5, 8]
    with pytest.raises(ValueError, match="task IDs"):
        validate_config_contract(bad_task)
    bad_checkpoint = deepcopy(config)
    bad_checkpoint["checkpoint"]["revision"] = "mutable-main"
    with pytest.raises(ValueError, match="checkpoint revision"):
        validate_config_contract(bad_checkpoint)
    bad_processor = deepcopy(config)
    bad_processor["checkpoint"]["processor_loader"] = "different"
    with pytest.raises(ValueError, match="processor"):
        validate_config_contract(bad_processor)

    mutated = list(read_jsonl(MANIFEST_PATH))
    mutated[0] = {**mutated[0], "seed": 123}
    path = tmp_path / "mutated.jsonl"
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in mutated),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="deterministic rebuild"):
        validate_static_manifest(config, path)


def test_v1_and_v2_outputs_cannot_overlap_and_inventory_is_deterministic(
    tmp_path: Path,
) -> None:
    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / "a.txt").write_text("a", encoding="utf-8")
    (v1 / "b.txt").write_text("b", encoding="utf-8")
    assert directory_inventory(v1) == directory_inventory(v1)
    with pytest.raises(ValueError, match="independent"):
        ensure_output_separation(v1_root=v1, v2_root=v1)
    with pytest.raises(ValueError, match="independent"):
        ensure_output_separation(v1_root=v1, v2_root=v1 / "nested")
    _, v2 = ensure_output_separation(v1_root=v1, v2_root=tmp_path / "v2")
    assert v2.name == "v2"


def test_infrastructure_failure_is_not_an_experimental_terminal(tmp_path: Path) -> None:
    config = _config()
    entry = build_v2_entries(config)[0]
    attempt = tmp_path / "workers/gpu0/episodes/x/attempt-001.json"
    attempt.parent.mkdir(parents=True)
    attempt.write_text(
        json.dumps(
            {
                "attempt_status": "infrastructure_failure",
                "episode_id": entry["episode_id"],
                "valid_experimental_terminal": False,
            }
        ),
        encoding="utf-8",
    )
    attempts = infrastructure_attempts(tmp_path)
    assert len(attempts) == 1
    audit = audit_v2_terminals(
        config=config,
        entries=(entry,),
        episode_roots=(tmp_path / "workers/gpu0/episodes",),
        config_hash=canonical_hash(config),
    )
    assert audit["terminal_count"] == 0
    assert audit["missing_episode_ids"] == [entry["episode_id"]]


def test_resume_trace_replays_actions_without_duplicate_inference(tmp_path: Path) -> None:
    path = tmp_path / "attempt-001.jsonl"
    rows = [
        {
            "record_type": "warmup",
            "warmup_step": step,
            "dummy_action": True,
            "reward": 0.0,
            "done": False,
        }
        for step in range(10)
    ]
    rows.append(
        {
            "record_type": "policy_step",
            "policy_step": 0,
            "environment_action": [0.0] * 6 + [1.0],
            "action_validation": {"passed": True},
            "reward": 0.0,
            "done": False,
            "inference_seconds": 1.0,
            "environment_step_seconds": 0.1,
        }
    )
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    resume = load_v2_resume_trace(path)
    assert resume["policy_steps"] == 1
    assert not resume["terminal_success_recorded"]
    assert "model_inference_replayed" not in resume["policy_records"][0]


def test_final_audit_detects_missing_duplicate_unexpected_and_mutation(
    tmp_path: Path,
) -> None:
    config = _config()
    entries = build_v2_entries(config)[:2]
    config_hash = canonical_hash(config)
    first = tmp_path / "gpu0" / entries[0]["episode_id"] / "episode.json"
    first.parent.mkdir(parents=True)
    first.write_text(json.dumps(_terminal(entries[0], config_hash)), encoding="utf-8")
    missing = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=(tmp_path / "gpu0",),
        config_hash=config_hash,
    )
    assert not missing["passed"]
    assert missing["missing_episode_ids"] == [entries[1]["episode_id"]]

    second = tmp_path / "gpu1" / entries[1]["episode_id"] / "episode.json"
    second.parent.mkdir(parents=True)
    second.write_text(json.dumps(_terminal(entries[1], config_hash)), encoding="utf-8")
    complete = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=(tmp_path / "gpu0", tmp_path / "gpu1"),
        config_hash=config_hash,
    )
    assert complete["passed"]

    duplicate = tmp_path / "gpu2" / entries[0]["episode_id"] / "episode.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    duplicated = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=(tmp_path / "gpu0", tmp_path / "gpu1", tmp_path / "gpu2"),
        config_hash=config_hash,
    )
    assert not duplicated["passed"]
    assert duplicated["duplicate_episode_ids"] == [entries[0]["episode_id"]]

    mutated_record = _terminal(entries[1], config_hash)
    mutated_record["description"] = "changed after run"
    second.write_text(json.dumps(mutated_record), encoding="utf-8")
    mutated = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=(tmp_path / "gpu0", tmp_path / "gpu1"),
        config_hash=config_hash,
    )
    assert not mutated["passed"]
    assert any("description mismatch" in error for error in mutated["errors"])

    unexpected = tmp_path / "gpu1" / "unexpected" / "episode.json"
    unexpected.parent.mkdir(parents=True)
    unexpected.write_text(
        json.dumps({**_terminal(entries[1], config_hash), "episode_id": "unexpected"}),
        encoding="utf-8",
    )
    extra = audit_v2_terminals(
        config=config,
        entries=entries,
        episode_roots=(tmp_path / "gpu0", tmp_path / "gpu1"),
        config_hash=config_hash,
    )
    assert not extra["passed"]
    assert extra["unexpected_episode_ids"] == ["unexpected"]
