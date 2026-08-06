from __future__ import annotations

import pytest

from cope.engine import CoPEEngineProtocolError, apply_guarded_patch
from cope.types import InformationBudget, PatchOutput, RecoveryInput
from tests.fakes import ProtocolFakeEngine


def common_input() -> RecoveryInput:
    return RecoveryInput(
        schema_version="v1",
        pair_key="pair",
        original_task="task",
        observation={"fresh": True},
        event={"event_type": "move"},
        public_action_history=(),
        task_progress={},
        information_budget=InformationBudget(
            event_fields=("event_type",),
            history_fields=(),
            observation_fields=("fresh",),
            max_high_level_calls=1,
            max_prompt_tokens=100,
            max_completion_tokens=100,
        ),
    )


def test_restore_requires_successful_prior_revalidation() -> None:
    engine = ProtocolFakeEngine()
    engine.initialize("task", {})
    patch = PatchOutput.from_mapping(
        {
            "schema_version": "v1",
            "operations": [
                {
                    "op": "Restore",
                    "target_id": "goal",
                    "payload": {},
                    "reason": "blind restore",
                }
            ],
        }
    )
    with pytest.raises(CoPEEngineProtocolError, match="blind restore"):
        apply_guarded_patch(engine, patch, common_input())


def test_revalidate_then_restore_passes_and_preserves_unaffected_slot() -> None:
    engine = ProtocolFakeEngine()
    engine.initialize("task", {})
    patch = PatchOutput.from_mapping(
        {
            "schema_version": "v1",
            "operations": [
                {
                    "op": "Revalidate",
                    "target_id": "goal",
                    "payload": {},
                    "reason": "check current world",
                },
                {
                    "op": "Restore",
                    "target_id": "goal",
                    "payload": {},
                    "reason": "validated restore",
                },
            ],
        }
    )
    result = apply_guarded_patch(engine, patch, common_input())
    assert result.revalidations[0]["success"] is True
    assert result.preservation["passed"] is True
    assert result.preservation["unaffected_ids"] == ["safety"]
