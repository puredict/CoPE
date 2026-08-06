from __future__ import annotations

import copy

from cope_benchmark.adapters import FORMAL_METHODS, formal_run_gate
from cope_benchmark.interruption_scheduler import schedules_are_paired_equal
from cope_benchmark.interruptions import InterruptionEvent, InterruptionType
from cope_benchmark.repeated_manifest import (
    generate_manifest_rows,
    validate_manifest_rows,
)


def _digests():
    return {(task_id, state): f"{task_id * 10 + state:064x}" for task_id in (0, 1, 4, 8) for state in range(5)}


def test_full_manifest_has_240_pairs_and_480_formal_episodes() -> None:
    rows = generate_manifest_rows(
        initial_state_digests=_digests(),
        source_commit="570d78333ee977c8ae6de3d97120b23272c4c660",
        checkpoint=None,
        dependency_commits={
            "method/cope-state-semantics": None,
            "main_experiment_adapters": None,
        },
    )
    validation = validate_manifest_rows(rows, expect_full=True)
    assert validation["passed"], validation
    assert validation["row_count"] == 240
    assert validation["formal_episode_count"] == 480
    assert validation["interruption_count_rows"] == {0: 60, 1: 60, 2: 60, 3: 60}
    assert set(validation["event_type_counts"]) == {value.value for value in InterruptionType}


def test_method_pair_receives_byte_equivalent_method_independent_schedule() -> None:
    row = generate_manifest_rows(
        initial_state_digests=_digests(),
        source_commit="570d78333ee977c8ae6de3d97120b23272c4c660",
        checkpoint=None,
        dependency_commits={},
        states=(0,),
        seeds=(11,),
        interruption_counts=(3,),
    )[0]
    per_method = {method: copy.deepcopy(row["event_schedule"]) for method in FORMAL_METHODS}
    first = [InterruptionEvent.from_dict(value) for value in per_method[FORMAL_METHODS[0]]]
    second = [InterruptionEvent.from_dict(value) for value in per_method[FORMAL_METHODS[1]]]
    assert schedules_are_paired_equal(first, second)


def test_preregistered_no_go_zone_does_not_contain_calibrated_reset_eef() -> None:
    rows = generate_manifest_rows(
        initial_state_digests=_digests(),
        source_commit="570d78333ee977c8ae6de3d97120b23272c4c660",
        checkpoint=None,
        dependency_commits={},
        states=(0,),
        seeds=(11, 29, 47),
        interruption_counts=(1, 2, 3),
    )
    reset_eef_by_task = {
        0: (-0.038, -0.005, 0.713),
        1: (-0.057, -0.014, 0.680),
        4: (-0.052, -0.015, 0.688),
        8: (-0.199, 0.016, 1.186),
    }
    for row in rows:
        for event in row["event_schedule"]:
            if event["event_type"] != InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS.value:
                continue
            payload = event["payload"]
            point = reset_eef_by_task[row["pair_fields"]["task_id"]]
            assert not all(
                lower <= coordinate <= upper
                for coordinate, lower, upper in zip(
                    point,
                    payload["minimum"],
                    payload["maximum"],
                )
            )


def test_formal_gate_rejects_missing_dependencies_and_fake_provider() -> None:
    config = {
        "checkpoint": "fake://openvla",
        "adapters": {method: None for method in FORMAL_METHODS},
        "dependency_commits": {},
    }
    errors = formal_run_gate(config, phase="formal", adapter_provider_ids={"cope_patch": "fake"})
    assert any("checkpoint" in error for error in errors)
    assert any("adapter factory" in error for error in errors)
    assert any("full 40-character commit SHA" in error for error in errors)
    assert any("provider" in error for error in errors)


def test_clean_calibration_gate_does_not_require_recovery_adapters() -> None:
    config = {
        "checkpoint": "openvla/openvla-7b-finetuned-libero",
        "adapters": {},
        "dependency_commits": {},
    }
    assert formal_run_gate(config, phase="clean_calibration") == []
