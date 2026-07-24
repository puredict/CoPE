from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cope.calibration import (
    CalibrationSeedScheme,
    atomic_episode_claim,
    audit_terminal_records,
    build_calibration_entries,
    load_resume_trace,
    partition_entries,
    validate_openvla_action,
    wilson_interval,
)


def _scheme() -> CalibrationSeedScheme:
    return CalibrationSeedScheme(
        name="test",
        base_seed=20260724,
        task_stride=100,
        state_stride=1,
        forbidden_evaluation_seeds=(11, 29, 47),
    )


def test_calibration_entries_are_fixed_unique_and_disjoint_from_evaluation() -> None:
    entries = build_calibration_entries(
        task_ids=(0, 1, 4, 8),
        state_ids=range(5),
        seed_scheme=_scheme(),
    )
    seeds = {int(entry["seed"]) for entry in entries}
    assert len(entries) == 20
    assert len(seeds) == 20
    assert not seeds & {11, 29, 47}
    assert entries[0]["episode_id"] == "calibration__task00__state00__seed20260724"


def test_seed_scheme_rejects_evaluation_overlap() -> None:
    scheme = CalibrationSeedScheme(
        name="bad",
        base_seed=11,
        task_stride=100,
        state_stride=1,
        forbidden_evaluation_seeds=(11,),
    )
    with pytest.raises(ValueError, match="overlaps evaluation seed"):
        scheme.derive(task_ordinal=0, state_id=0)


def test_action_validation_checks_openvla_libero_gripper_transform() -> None:
    validation = validate_openvla_action(
        [0.1, -0.1, 0.2, 0.0, 0.0, 0.0, 0.0],
        [0.1, -0.1, 0.2, 0.0, 0.0, 0.0, 1.0],
        expected_dim=7,
        action_low=[-1.0] * 7,
        action_high=[1.0] * 7,
    )
    assert validation["passed"]
    assert validation["gates"]["gripper_normalize_binarize_invert"]


def test_action_validation_rejects_non_finite_and_non_binary_gripper() -> None:
    validation = validate_openvla_action(
        [float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        expected_dim=7,
        action_low=[-1.0] * 7,
        action_high=[1.0] * 7,
    )
    assert not validation["passed"]
    assert not validation["gates"]["finite"]
    assert not validation["gates"]["environment_gripper_binarized"]


def test_wilson_interval_has_expected_edge_behavior() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lower, upper = wilson_interval(3, 5)
    assert 0.2 < lower < 0.3
    assert 0.85 < upper < 0.9


def test_fixed_worker_partition_is_complete_and_disjoint() -> None:
    entries = build_calibration_entries(
        task_ids=(0, 1, 4, 8),
        state_ids=range(5),
        seed_scheme=_scheme(),
    )
    partitions = [
        partition_entries(entries, worker_id=worker_id, worker_count=8)
        for worker_id in range(8)
    ]
    flattened = [str(entry["episode_id"]) for part in partitions for entry in part]
    assert len(flattened) == 20
    assert len(set(flattened)) == 20
    assert set(flattened) == {str(entry["episode_id"]) for entry in entries}


def test_atomic_claim_allows_exactly_one_concurrent_winner(tmp_path: Path) -> None:
    claim_path = tmp_path / "claims" / "episode.json"

    def attempt(_: int) -> bool:
        try:
            atomic_episode_claim(
                claim_path,
                episode_id="episode",
                worker_id=3,
                worker_count=8,
                config_hash="a" * 64,
                launcher_id="launch",
                resume=False,
            )
        except FileExistsError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        winners = list(executor.map(attempt, range(8)))
    assert sum(winners) == 1
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["worker_id"] == 3


def test_matching_claim_can_resume_but_cannot_change_worker(tmp_path: Path) -> None:
    claim_path = tmp_path / "claim.json"
    atomic_episode_claim(
        claim_path,
        episode_id="episode",
        worker_id=2,
        worker_count=8,
        config_hash="a" * 64,
        launcher_id="first-launch",
        resume=False,
    )
    reused = atomic_episode_claim(
        claim_path,
        episode_id="episode",
        worker_id=2,
        worker_count=8,
        config_hash="a" * 64,
        launcher_id="resumed-launch",
        resume=True,
    )
    assert reused["claim_reused_for_resume"]
    with pytest.raises(ValueError, match="claim identity mismatch"):
        atomic_episode_claim(
            claim_path,
            episode_id="episode",
            worker_id=1,
            worker_count=8,
            config_hash="a" * 64,
            launcher_id="wrong-worker",
            resume=True,
        )


def test_interrupted_trace_is_validated_for_deterministic_replay(tmp_path: Path) -> None:
    trace_path = tmp_path / "attempt-001.jsonl"
    rows = [
        {
            "record_type": "warmup",
            "warmup_step": index,
            "dummy_action": True,
            "reward": 0.0,
            "done": False,
        }
        for index in range(2)
    ]
    rows.append(
        {
            "record_type": "policy_step",
            "policy_step": 0,
            "environment_action": [0.0] * 6 + [1.0],
            "action_validation": {"passed": True},
            "reward": 0.0,
            "done": False,
        }
    )
    trace_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    loaded = load_resume_trace(
        trace_path, expected_warmup_steps=2, policy_step_budget=220
    )
    assert loaded["policy_steps"] == 1
    assert len(loaded["sha256"]) == 64


def test_terminal_audit_requires_exactly_one_fixed_terminal(tmp_path: Path) -> None:
    entries = (
        {
            "episode_id": "episode-a",
            "task_id": 0,
            "initial_state_id": 0,
            "seed": 101,
        },
        {
            "episode_id": "episode-b",
            "task_id": 1,
            "initial_state_id": 1,
            "seed": 102,
        },
    )
    for root, entry in zip((tmp_path / "gpu0", tmp_path / "gpu1"), entries):
        path = root / str(entry["episode_id"]) / "episode.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    **entry,
                    "complete": True,
                    "phase": "calibration",
                    "config_hash": "a" * 64,
                    "checkpoint": {"revision": "revision"},
                }
            ),
            encoding="utf-8",
        )
    audit = audit_terminal_records(
        entries=entries,
        episode_roots=[tmp_path / "gpu0", tmp_path / "gpu1"],
        config_hash="a" * 64,
        checkpoint_revision="revision",
    )
    assert audit["passed"]
    assert audit["terminal_count"] == 2

    duplicate = tmp_path / "gpu2" / "episode-a" / "episode.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(
        (tmp_path / "gpu0" / "episode-a" / "episode.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    duplicate_audit = audit_terminal_records(
        entries=entries,
        episode_roots=[tmp_path / "gpu0", tmp_path / "gpu1", tmp_path / "gpu2"],
        config_hash="a" * 64,
        checkpoint_revision="revision",
    )
    assert not duplicate_audit["passed"]
    assert duplicate_audit["duplicate_episode_ids"] == ["episode-a"]
