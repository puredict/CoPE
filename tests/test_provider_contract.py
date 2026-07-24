from __future__ import annotations

import pytest

from cope.providers.base import assert_secret_free, validate_provider_invocation
from cope.providers.fake import DeterministicFakeProvider
from cope.types import InformationBudget, RecoveryInput


def recovery_input() -> RecoveryInput:
    return RecoveryInput(
        schema_version="recovery-input-v1",
        pair_key="pair",
        original_task="move object",
        observation={"fresh": True, "sha256": "abc"},
        event={"event_type": "object_displacement"},
        public_action_history=(),
        task_progress={"completed": False},
        information_budget=InformationBudget(
            event_fields=("event_type",),
            history_fields=("policy_step",),
            observation_fields=("fresh", "sha256"),
            max_high_level_calls=1,
            max_prompt_tokens=4096,
            max_completion_tokens=1024,
        ),
    )


def test_fake_provider_supports_both_modes_with_identical_common_input() -> None:
    provider = DeterministicFakeProvider()
    common = recovery_input()
    regenerated = provider.regenerate(common)
    patched = provider.patch(
        common,
        {
            "constraints": [
                {
                    "id": "goal",
                    "source": "task",
                    "priority": 1,
                    "lineage": [],
                }
            ]
        },
    )
    validate_provider_invocation(
        regenerated,
        expected_mode="regenerate",
        recovery_input=common,
        metadata=provider.metadata,
    )
    validate_provider_invocation(
        patched,
        expected_mode="patch",
        recovery_input=common,
        metadata=provider.metadata,
    )
    assert regenerated.raw_request["recovery_input"] == patched.raw_request["recovery_input"]
    assert provider.metadata.is_fake is True


def test_secret_like_provider_log_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        assert_secret_free({"authorization": "Bearer should-never-be-logged"})


def test_provider_contract_rejects_changed_common_input() -> None:
    provider = DeterministicFakeProvider()
    common = recovery_input()
    invocation = provider.regenerate(common)
    invocation.raw_request["recovery_input"]["original_task"] = "different"
    with pytest.raises(ValueError, match="exact common recovery input"):
        validate_provider_invocation(
            invocation,
            expected_mode="regenerate",
            recovery_input=common,
            metadata=provider.metadata,
        )
