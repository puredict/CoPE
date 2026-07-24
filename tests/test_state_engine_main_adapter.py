from __future__ import annotations

import pytest

from cope.engine import CoPEEngineProtocolError, apply_guarded_patch, validate_engine
from cope.methods.base import CoPEPatchMethod
from cope.providers.fake import DeterministicFakeProvider
from cope.state_engine_adapter import ENGINE_SOURCE_COMMIT, CoPEStateEngineAdapter
from cope.types import InformationBudget, PatchOutput, RecoveryInput


def recovery_input() -> RecoveryInput:
    return RecoveryInput(
        schema_version="recovery-input-v1",
        pair_key="pair",
        original_task="put the bowl on the plate",
        observation={"fresh": True, "sha256": "frame"},
        event={"event_type": "object_displacement"},
        public_action_history=(),
        task_progress={"completed": False},
        information_budget=InformationBudget(
            event_fields=("event_type",),
            history_fields=(),
            observation_fields=("fresh", "sha256"),
            max_high_level_calls=1,
            max_prompt_tokens=100,
            max_completion_tokens=100,
        ),
    )


def make_engine(*, validator: bool = False) -> CoPEStateEngineAdapter:
    config = {
        "authority_priority": 100,
        "authorized_sources": ["task", "planner", "perception"],
    }
    if validator:
        config["revalidation_validator_factory"] = (
            "tests.fakes:create_true_revalidation_validator"
        )
    engine = CoPEStateEngineAdapter(config)
    engine.initialize(
        "put the bowl on the plate",
        {
            "pair_key": "pair",
            "event_source": "oracle",
            "policy_step_budget": 220,
            "git_commit": "git",
            "config_hash": "config",
            "checkpoint_id": "checkpoint",
        },
    )
    return engine


def test_real_engine_commit_is_exposed_and_fake_validator_is_not_formal_ready() -> None:
    engine = make_engine(validator=True)
    assert engine.metadata["engine_commit"] == ENGINE_SOURCE_COMMIT
    with pytest.raises(CoPEEngineProtocolError, match="fake revalidation validator"):
        validate_engine(engine, formal=True)


def test_atomic_override_uses_committed_engine_and_compiles_controller_prompt() -> None:
    engine = make_engine()
    patch = PatchOutput.from_mapping(
        {
            "schema_version": "typed-patch-v1",
            "operations": [
                {
                    "op": "Override",
                    "target_id": "goal",
                    "reason": "object moved",
                    "payload": {
                        "replacement": {
                            "slot_id": "goal-after-move",
                            "constraint_type": "task_goal",
                            "content": {
                                "instruction": "relocalize the bowl, then put it on the plate"
                            },
                            "source": "planner",
                            "priority": 100,
                        }
                    },
                }
            ],
        }
    )
    result = apply_guarded_patch(engine, patch, recovery_input())
    before = {slot["id"]: slot for slot in result.state_before["constraints"]}
    after = {slot["id"]: slot for slot in result.state_after["constraints"]}
    assert before["goal"]["mode"] == "active"
    assert after["goal"]["mode"] == "overridden"
    assert after["goal-after-move"]["lineage"] == ["goal", "goal-after-move"]
    assert "goal-after-move" in result.controller_prompt


def test_real_engine_revalidate_then_restore_is_guarded_in_one_atomic_patch() -> None:
    engine = make_engine(validator=True)
    suspended = PatchOutput.from_mapping(
        {
            "schema_version": "typed-patch-v1",
            "operations": [
                {
                    "op": "Suspend",
                    "target_id": "goal",
                    "payload": {},
                    "reason": "pose invalid",
                }
            ],
        }
    )
    apply_guarded_patch(engine, suspended, recovery_input())
    restored = PatchOutput.from_mapping(
        {
            "schema_version": "typed-patch-v1",
            "operations": [
                {
                    "op": "Revalidate",
                    "target_id": "goal",
                    "payload": {"evidence": {"pose_consistent": True}},
                    "reason": "check current observation",
                },
                {
                    "op": "Restore",
                    "target_id": "goal",
                    "payload": {},
                    "reason": "successful check",
                },
            ],
        }
    )
    result = apply_guarded_patch(engine, restored, recovery_input())
    assert result.revalidations[0]["success"] is True
    goal = next(slot for slot in result.state_after["constraints"] if slot["id"] == "goal")
    assert goal["mode"] == "active"
    assert goal["evidence_refs"]


def test_method_provider_and_committed_engine_adapter_integrate_end_to_end() -> None:
    provider = DeterministicFakeProvider()
    method = CoPEPatchMethod(
        provider,
        lambda config: CoPEStateEngineAdapter(config),
        {
            "authority_priority": 100,
            "authorized_sources": ["task", "planner", "perception"],
        },
        formal=False,
    )
    method.prepare(
        "put the bowl on the plate",
        {
            "pair_key": "pair",
            "event_source": "oracle",
            "policy_step_budget": 220,
        },
    )
    decision = method.on_event(
        original_prompt="put the bowl on the plate",
        target_joint="bowl_joint0",
        recovery_input=recovery_input(),
    )
    assert decision.high_level_call_count == 1
    assert decision.unaffected_slot_preservation["passed"] is True
    assert "goal-after-move" in decision.controller_prompt
