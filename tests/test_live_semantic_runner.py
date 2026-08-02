from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from cope.libero_predicate_validator import build_predicate_snapshot
from cope.semantic_cancellation import build_cancellation_event
from cope.semantic_live_runner import (
    DEVELOPMENT_STATE_IDS,
    EVENT_TYPES,
    LoadedSemanticConfig,
    finalize_mutation_accounting,
    load_semantic_config,
    make_paired_recovery_inputs,
    run_semantic_wiring,
    validate_case_rows,
)
from cope.semantic_replacement import MilestoneEvent, build_replacement_event


COMMIT = "298dac707bb0d57aad050978d6e81d7aab93090d"
OBS_HASH = "a" * 64
SIM_HASH = "b" * 64


def frozen_row(state_id: int, event_type: str) -> dict[str, str]:
    return {
        "case_id": f"state{state_id}-{event_type}",
        "state_id": str(state_id),
        "event_type": event_type,
        "done_object": "cream_cheese_1",
        "pending_object": "butter_1",
        "replacement_object": (
            "alphabet_soup_1" if event_type == "replace_pending_goal" else ""
        ),
        "stable_steps": "5",
    }


def test_development_state_lock_rejects_reserved_state() -> None:
    assert DEVELOPMENT_STATE_IDS == frozenset(range(5))
    rows = [
        frozen_row(state_id, event_type)
        for state_id in range(5)
        for event_type in EVENT_TYPES
    ]
    rows[-1]["state_id"] = "25"
    with pytest.raises(ValueError, match="outside the consumed development range"):
        validate_case_rows(rows)


def test_case_manifest_rejects_retuned_objects_or_threshold() -> None:
    rows = [
        frozen_row(state_id, event_type)
        for state_id in range(5)
        for event_type in EVENT_TYPES
    ]
    rows[0]["stable_steps"] = "4"
    with pytest.raises(ValueError, match="stability threshold"):
        validate_case_rows(rows)


def test_paired_recovery_input_is_byte_identical() -> None:
    event = {"event_id": "event-1", "event_type": "cancel_pending_goal"}
    observation = {"sha256": OBS_HASH, "predicate_snapshot": {"policy_step": 3}}
    native, cope, payload = make_paired_recovery_inputs(
        pair_key="pair",
        original_task="put both objects in the basket",
        observation=observation,
        event=event,
        public_action_history=({"policy_step": 0, "environment_action": [0.0] * 7},),
        task_progress={"physically_true_objects": ["cream_cheese_1"]},
        observation_fields=("sha256", "predicate_snapshot"),
    )
    assert payload
    assert native.input_hash == cope.input_hash
    assert native.as_payload() == cope.as_payload()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_semantic_config_loader_verifies_artifacts_and_reserve_manifest(tmp_path: Path) -> None:
    reserve = tmp_path / "reserve.csv"
    reserve.write_text(
        "state_id,event_type,status\n"
        "25,replace_pending_goal,reserved_uninspected\n"
        "26,cancel_pending_goal,reserved_uninspected\n",
        encoding="utf-8",
    )
    bddl = tmp_path / "task.bddl"
    init_states = tmp_path / "task.pruned_init"
    bddl.write_text("task", encoding="utf-8")
    init_states.write_bytes(b"states")
    config = tmp_path / "config.csv"
    fields = [
        "schema_version",
        "task_suite",
        "task_id",
        "observation_fields",
        "event_types",
        "reserved_state_ids",
        "rollout_authorized",
        "pilot_manifest_path",
        "predicate_producer_commit",
        "predicate_snapshot_schema",
        "predicate_factory",
        "bddl_path",
        "bddl_sha256",
        "init_states_path",
        "init_states_sha256",
    ]
    row = {
        "schema_version": "cope-semantic-task1-pilot-config-v1",
        "task_suite": "libero_10",
        "task_id": "1",
        "observation_fields": "sha256;predicate_snapshot",
        "event_types": "replace_pending_goal;cancel_pending_goal",
        "reserved_state_ids": "25;26",
        "rollout_authorized": "false",
        "pilot_manifest_path": "reserve.csv",
        "predicate_producer_commit": COMMIT,
        "predicate_snapshot_schema": "cope-libero-predicate-snapshot-v1",
        "predicate_factory": (
            "cope.libero_predicate_validator:create_libero_predicate_validator"
        ),
        "bddl_path": str(bddl),
        "bddl_sha256": _sha(bddl),
        "init_states_path": str(init_states),
        "init_states_sha256": _sha(init_states),
    }
    with config.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    loaded = load_semantic_config(config, repo_root=tmp_path)
    assert loaded.row["task_id"] == "1"
    assert loaded.reserved_state_ids == frozenset({25, 26})
    assert loaded.predicate_engine_config["predicate_snapshot"]["test_only"] is False


def synthetic_config() -> LoadedSemanticConfig:
    return LoadedSemanticConfig(
        row={
            "task_suite": "libero_10",
            "task_id": "1",
            "predicate_producer_commit": COMMIT,
        },
        path=Path("synthetic-unit-test.csv"),
        sha256="c" * 64,
        observation_fields=(
            "encoding",
            "rgb",
            "sha256",
            "width",
            "height",
            "fresh",
            "predicate_snapshot",
        ),
        event_types=EVENT_TYPES,
        reserved_state_ids=frozenset({25, 26}),
        reserve_manifest_sha256="d" * 64,
    )


def semantic_observation(row: dict[str, str]) -> dict:
    milestone = MilestoneEvent(120, row["done_object"], row["pending_object"], 5)
    event = (
        build_replacement_event(
            milestone,
            pair_key=row["case_id"],
            replacement_object=row["replacement_object"],
        )
        if row["event_type"] == "replace_pending_goal"
        else build_cancellation_event(milestone, pair_key=row["case_id"])
    )
    packet = build_predicate_snapshot(
        task_suite="libero_10",
        task_id=1,
        event_id=event["event_id"],
        policy_step=120,
        observation_sha256=OBS_HASH,
        simulator_state_sha256=SIM_HASH,
        producer_commit=COMMIT,
        predicates=(
            ("in", ("cream_cheese_1", "basket_1_contain_region"), True),
            ("in", ("butter_1", "basket_1_contain_region"), False),
        ),
        test_only=False,
        source_kind="live_libero_eval_predicate",
    )
    return {
        "encoding": "png-base64",
        "rgb": "AA==",
        "sha256": OBS_HASH,
        "width": 1,
        "height": 1,
        "fresh": True,
        "predicate_snapshot": packet,
    }


@pytest.mark.parametrize("event_type", tuple(EVENT_TYPES))
def test_semantic_wiring_converges_then_requires_nonmutation(event_type: str) -> None:
    row = frozen_row(0, event_type)
    semantic = run_semantic_wiring(
        row=row,
        config=synthetic_config(),
        original_task="put both the cream cheese box and the butter in the basket",
        observation=semantic_observation(row),
        public_action_history=({"policy_step": 0, "environment_action": [0.0] * 7},),
        independently_logged_predicates={"cream_cheese_1": True, "butter_1": False},
        simulator_state_before=SIM_HASH,
        controller_action_count_before=120,
    )
    result = finalize_mutation_accounting(
        semantic,
        simulator_state_before=SIM_HASH,
        simulator_state_after=SIM_HASH,
        controller_action_count_before=120,
        controller_action_count_after=120,
    )
    assert result["semantic_pass"] is True
    assert result["passed"] is True
    assert result["recovery_input_byte_identical"] is True
    assert result["validator_done_value"] is True
    assert result["validator_pending_value"] is False
    assert result["provider_called"] is False
    assert result["canonical_states_equal"] is True
    assert result["directives_equal"] is True


def test_packet_simulator_binding_is_not_format_only() -> None:
    row = frozen_row(0, "cancel_pending_goal")
    with pytest.raises(ValueError, match="probed simulator state"):
        run_semantic_wiring(
            row=row,
            config=synthetic_config(),
            original_task="put both objects in the basket",
            observation=semantic_observation(row),
            public_action_history=(),
            independently_logged_predicates={
                "cream_cheese_1": True,
                "butter_1": False,
            },
            simulator_state_before="e" * 64,
            controller_action_count_before=120,
        )


def test_mutation_accounting_rejects_action_or_state_change() -> None:
    result = finalize_mutation_accounting(
        {"semantic_pass": True},
        simulator_state_before=SIM_HASH,
        simulator_state_after="e" * 64,
        controller_action_count_before=120,
        controller_action_count_after=121,
    )
    assert result["passed"] is False
    assert result["post_event_policy_actions"] == 1
