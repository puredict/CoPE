from __future__ import annotations

import csv
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cope.compact_tx import CompactTransactionError, parse_proposal
from cope.libero_predicate_validator import build_predicate_snapshot
from cope.semantic_cancellation import build_cancellation_event
from cope.semantic_live_runner import (
    DEVELOPMENT_STATE_IDS,
    EVENT_TYPES,
    LearnedSemanticError,
    LoadedSemanticConfig,
    finalize_mutation_accounting,
    load_semantic_config,
    make_paired_recovery_inputs,
    build_expected_live_post_state,
    build_live_pre_state,
    commit_live_shared_envelope,
    execute_live_cope_patch,
    parse_live_cope_patch,
    run_learned_semantic_triplet,
    run_oracle_semantic_fixture,
    recorded_state0_expansion_allowed,
    select_validated_cope_execution,
    state0_expansion_allowed,
    validate_case_rows,
)
from cope.semantic_replacement import (
    MilestoneEvent,
    build_replacement_event,
    goal_commitment_id,
)
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import ProviderInvocation, TokenUsage


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
    semantic = run_oracle_semantic_fixture(
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
        run_oracle_semantic_fixture(
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


def test_explicit_pilot_authorization_does_not_weaken_default_state_lock() -> None:
    row = frozen_row(25, "cancel_pending_goal")
    kwargs = {
        "row": row,
        "config": synthetic_config(),
        "original_task": "put both objects in the basket",
        "observation": semantic_observation(row),
        "public_action_history": (),
        "independently_logged_predicates": {
            "cream_cheese_1": True,
            "butter_1": False,
        },
        "simulator_state_before": SIM_HASH,
        "controller_action_count_before": 120,
    }
    with pytest.raises(ValueError, match="caller-authorized semantic set"):
        run_oracle_semantic_fixture(**kwargs)
    authorized = run_oracle_semantic_fixture(**kwargs, authorized_state_ids={25, 26})
    assert authorized["semantic_pass"] is True


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


def _event_for(row: dict[str, str]) -> dict[str, Any]:
    milestone = MilestoneEvent(120, row["done_object"], row["pending_object"], 5)
    if row["event_type"] == "replace_pending_goal":
        return build_replacement_event(
            milestone,
            pair_key=row["case_id"],
            replacement_object=row["replacement_object"],
        )
    return build_cancellation_event(milestone, pair_key=row["case_id"])


def _cope_output(event: dict[str, Any]) -> dict[str, Any]:
    result = {
        "event_id": event["event_id"],
        "operation": "Override" if event["event_type"] == "replace_pending_goal" else "Expire",
        "patch_id": f"learned:{event['event_id']}",
        "target_id": event["target_commitment_id"],
    }
    if event["event_type"] == "replace_pending_goal":
        result["replacement_id"] = goal_commitment_id(event["replacement_object"])
    return result


def _compact_output(event: dict[str, Any]) -> dict[str, Any]:
    before = build_live_pre_state(event)
    after = build_expected_live_post_state(event)
    writes: list[dict[str, Any]] = []
    before_commitments = {item["id"]: item for item in before["commitments"]}
    for item in after["commitments"]:
        identifier = item["id"]
        if identifier not in before_commitments:
            writes.append(
                {"op": "add", "path": f"/commitments/+/{identifier}", "value": item}
            )
            continue
        for key, value in item.items():
            if before_commitments[identifier].get(key) != value:
                writes.append(
                    {
                        "op": "replace",
                        "path": f"/commitments/{identifier}/{key}",
                        "value": value,
                    }
                )
    before_entities = {item["id"] for item in before["entities"]}
    for item in after["entities"]:
        if item["id"] not in before_entities:
            writes.append(
                {"op": "add", "path": f"/entities/+/{item['id']}", "value": item}
            )
    for key in (
        "current_goal",
        "plan",
        "pending_restorations",
    ):
        if before[key] != after[key]:
            writes.append({"op": "replace", "path": f"/{key}", "value": after[key]})
    return {
        "schema_version": "generic-compact-transaction-v1",
        "base_version": before["state_version"],
        "event_id": event["event_id"],
        "writes": writes,
    }


class ScriptedProvider:
    def __init__(self, failures: dict[str, str] | None = None) -> None:
        self._inner = OpenAICompatibleRecoveryProvider(
            {
                "provider": "scripted-provider-transport",
                "model": "qwen/qwen3.5-flash-02-23",
                "reasoning_effort": "none",
                "temperature": 0.0,
                "seed": 20260802,
                "max_prompt_tokens": 12000,
                "max_completion_tokens": 4096,
                "max_retries": 0,
                "timeout_seconds": 90.0,
            }
        )
        self.failures = failures or {}
        self.calls: list[str] = []

    @property
    def metadata(self):
        return self._inner.metadata

    @property
    def reasoning_effort(self):
        return self._inner.reasoning_effort

    @property
    def seed(self):
        return self._inner.seed

    def call_contract(self, mode, recovery_input, output_contract):
        self.calls.append(mode)
        raw_request = self._inner.build_audited_request(mode, recovery_input, output_contract)
        if self.failures.get(mode) == "timeout":
            return ProviderInvocation(
                mode=mode,
                raw_request=raw_request,
                raw_response={"error_class": "TimeoutError"},
                parsed_output=None,
                timeout=True,
                validation_failure="provider_timeout",
            )
        event = dict(recovery_input.event)
        if "neutral-label sparse" in output_contract:
            output = _cope_output(event)
            output["operation"] = (
                "N01" if event["event_type"] == "replace_pending_goal" else "N02"
            )
        elif mode == "patch":
            output = _cope_output(event)
        elif mode == "compact":
            output = _compact_output(event)
        else:
            full = build_expected_live_post_state(event)
            output = {
                key: value
                for key, value in full.items()
                if key
                not in {"schema_version", "state_version", "evidence_versions"}
            }
        return ProviderInvocation(
            mode=mode,
            raw_request=raw_request,
            raw_response={"response_sha256": "f" * 64},
            parsed_output=output,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
            latency_seconds=0.01,
        )


def _run_learned(row: dict[str, str], provider: Any | None = None) -> dict[str, Any]:
    return run_learned_semantic_triplet(
        row=row,
        config=synthetic_config(),
        original_task="put both the cream cheese box and the butter in the basket",
        observation=semantic_observation(row),
        public_action_history=({"policy_step": 0, "environment_action": [0.0] * 7},),
        independently_logged_predicates={"cream_cheese_1": True, "butter_1": False},
        simulator_state_probe=lambda: SIM_HASH,
        action_counter=lambda: 120,
        provider=provider or ScriptedProvider(),
    )


@pytest.mark.parametrize("event_type", tuple(EVENT_TYPES))
def test_learned_triplet_is_provider_backed_fair_and_trusted(event_type: str) -> None:
    result = _run_learned(frozen_row(0, event_type))
    assert result["provider_called"] is True
    assert result["fairness_pass"] is True
    assert result["oracle_substitution"] is False
    assert result["fallback_used"] is False
    assert result["post_interruption_action_delta"] == 0
    assert {item["arm"] for item in result["arms"]} == {
        "cope",
        "neutral_patch",
        "compact_tx",
        "fsr_pc",
    }
    assert all(item["provider_status"] == "ok" for item in result["arms"])
    assert all(item["semantic_valid"] is True for item in result["arms"]), [
        (item["arm"], item["parse_or_validation_error"]) for item in result["arms"]
    ]
    assert all(item["trusted_receipt"] is not None for item in result["arms"])
    assert all(
        item["predicate_outcome"]
        == {"done": True, "pending": False, "validator_is_fake": False}
        for item in result["arms"]
    )


def test_rejects_forged_model_receipt() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    forged = {**_cope_output(event), "receipt": {"accepted": True}}
    with pytest.raises(LearnedSemanticError, match="unauthorized extra"):
        parse_live_cope_patch(forged, event)


def test_rejects_stale_version() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    pre_state = build_live_pre_state(event)
    stale = _compact_output(event)
    stale["base_version"] = pre_state["state_version"] - 1
    with pytest.raises(CompactTransactionError, match="base version mismatch"):
        parse_proposal(stale, pre_state, event)


@pytest.mark.parametrize("field", ("target_id", "replacement_id"))
def test_rejects_unknown_target_or_replacement(field: str) -> None:
    event = _event_for(frozen_row(0, "replace_pending_goal"))
    proposal = _cope_output(event)
    proposal[field] = "goal:unknown"
    with pytest.raises(LearnedSemanticError, match="unknown or unauthorized"):
        parse_live_cope_patch(proposal, event)


def test_rejects_unauthorized_extra_mutation() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    proposal = {**_cope_output(event), "mutate_progress": True}
    with pytest.raises(LearnedSemanticError, match="unauthorized extra"):
        execute_live_cope_patch(
            proposal, event, physically_true_objects=("cream_cheese_1",)
        )


def test_rejects_invalid_operation() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    proposal = _cope_output(event)
    proposal["operation"] = "DeleteEverything"
    with pytest.raises(LearnedSemanticError, match="invalid CoPE operation"):
        parse_live_cope_patch(proposal, event)


def test_rejects_oracle_substitution_provider() -> None:
    provider = ScriptedProvider()
    provider._inner._metadata = replace(provider.metadata, is_fake=True)
    with pytest.raises(LearnedSemanticError, match="oracle substitution"):
        _run_learned(frozen_row(0, "cancel_pending_goal"), provider)
    assert provider.calls == []


def test_provider_failure_is_retained_without_silent_fallback() -> None:
    provider = ScriptedProvider({"patch": "timeout"})
    result = _run_learned(frozen_row(0, "cancel_pending_goal"), provider)
    cope = next(item for item in result["arms"] if item["arm"] == "cope")
    assert cope["provider_status"] == "timeout"
    assert cope["semantic_valid"] is False
    assert cope["fallback_used"] is False
    assert result["fallback_used"] is False
    assert provider.calls == ["patch", "patch", "compact", "regenerate"]


def test_rejects_idempotence_violation() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    with pytest.raises(LearnedSemanticError, match="idempotence violation"):
        parse_live_cope_patch(
            _cope_output(event), event, processed_event_ids=(event["event_id"],)
        )


def test_phase_a_rejects_nonzero_action_delta() -> None:
    counts = iter((120, 121))
    row = frozen_row(0, "cancel_pending_goal")
    with pytest.raises(LearnedSemanticError, match="emitted an action"):
        run_learned_semantic_triplet(
            row=row,
            config=synthetic_config(),
            original_task="put both objects in the basket",
            observation=semantic_observation(row),
            public_action_history=(),
            independently_logged_predicates={"cream_cheese_1": True, "butter_1": False},
            simulator_state_probe=lambda: SIM_HASH,
            action_counter=lambda: next(counts),
            provider=ScriptedProvider(),
        )


def test_state0_gate_requires_both_families_and_all_four_provider_ok() -> None:
    replacement = _run_learned(frozen_row(0, "replace_pending_goal"))
    cancellation = _run_learned(frozen_row(0, "cancel_pending_goal"))
    assert state0_expansion_allowed([replacement, cancellation]) is True
    cancellation["arms"][0]["provider_status"] = "timeout"
    assert state0_expansion_allowed([replacement, cancellation]) is False


def test_live_shared_envelope_commits_metadata_outside_provider_patch() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    result = commit_live_shared_envelope(
        event,
        {
            "arm": "cope",
            "semantic_correct": True,
            "trusted_receipt": {"patch": _cope_output(event)},
            "after_state_sha256": "c" * 64,
        },
    )
    assert result["pass"] is True
    assert result["transaction_metadata_model_generated"] is False
    assert result["transaction_meta"]["state_version"] == event["valid_from_state_version"] + 1
    assert result["transaction_meta"]["processed_events"][0]["event_id"] == event["event_id"]
    assert result["transaction_base_version"] == event["valid_from_state_version"]
    assert result["transaction_pre_state_version"] == event["valid_from_state_version"]
    assert result["transaction_post_state_version"] == event["valid_from_state_version"] + 1
    assert result["transaction_evidence_version"] == event["world_version"]
    assert result["transaction_processed_event_id"] == event["event_id"]
    assert len(result["transaction_processed_payload_sha256"]) == 64


@pytest.mark.parametrize(
    ("event_type", "kind", "selected"),
    (
        ("cancel_pending_goal", "halt", ""),
        ("replace_pending_goal", "pick_and_place", "alphabet_soup_1"),
    ),
)
def test_embodied_command_is_derived_from_validated_provider_state(
    event_type: str, kind: str, selected: str
) -> None:
    result = _run_learned(frozen_row(0, event_type))
    cope_arm = next(item for item in result["arms"] if item["arm"] == "cope")
    command = select_validated_cope_execution(cope_arm, event_type)
    assert command["execution_kind"] == kind
    assert command["selected_object"] == selected
    assert command["selection_source"] == "validated_provider_post_state"


def test_embodied_command_rejects_unvalidated_arm() -> None:
    with pytest.raises(LearnedSemanticError, match="accepted CoPE arm"):
        select_validated_cope_execution(
            {"arm": "cope", "semantic_correct": False},
            "cancel_pending_goal",
        )


def test_live_shared_envelope_rejects_model_generated_transaction_metadata() -> None:
    event = _event_for(frozen_row(0, "cancel_pending_goal"))
    patch = _cope_output(event)
    patch["state_version"] = 999
    result = commit_live_shared_envelope(
        event,
        {
            "arm": "cope",
            "semantic_correct": True,
            "trusted_receipt": {"patch": patch},
            "after_state_sha256": "c" * 64,
        },
    )
    assert result["pass"] is False
    assert "transaction metadata" in result["error"]


def test_recorded_state0_gate_avoids_provider_retry() -> None:
    triplets = [
        _run_learned(frozen_row(0, "replace_pending_goal")),
        _run_learned(frozen_row(0, "cancel_pending_goal")),
    ]
    rows = []
    for triplet in triplets:
        for arm in triplet["arms"]:
            rows.append(
                {
                    "case_id": triplet["case_id"],
                    "state_id": 0,
                    "event_type": triplet["event_type"],
                    **{key: arm[key] for key in (
                        "arm", "provider_status", "provider_called", "fairness_pass",
                        "oracle_substitution", "fallback_used", "input_hash",
                        "settings_sha256", "post_interruption_action_delta",
                    )},
                }
            )
    assert recorded_state0_expansion_allowed(rows) is True
    rows[0]["fallback_used"] = True
    assert recorded_state0_expansion_allowed(rows) is False
