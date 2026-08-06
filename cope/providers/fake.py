from __future__ import annotations

from dataclasses import asdict
from typing import Any

from cope.providers.base import HighLevelRecoveryProvider
from cope.types import (
    ProviderInvocation,
    ProviderMetadata,
    RecoveryInput,
    TokenUsage,
)


class DeterministicFakeProvider(HighLevelRecoveryProvider):
    """Test-only provider. Formal-run guards reject it unconditionally."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._metadata = ProviderMetadata(
            provider="deterministic_test_fake",
            model="deterministic-test-fake-v1",
            temperature=float(config.get("temperature", 0.0)),
            max_prompt_tokens=int(config.get("max_prompt_tokens", 4096)),
            max_completion_tokens=int(config.get("max_completion_tokens", 1024)),
            max_retries=int(config.get("max_retries", 1)),
            timeout_seconds=float(config.get("timeout_seconds", 30.0)),
            is_fake=True,
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def regenerate(self, recovery_input: RecoveryInput) -> ProviderInvocation:
        parsed = {
            "schema_version": "full-state-v1",
            "constraints": [
                {
                    "id": "regenerated:goal",
                    "source": "full_regeneration",
                    "priority": 100,
                    "lineage": [],
                    "text": recovery_input.original_task,
                }
            ],
            "plan": [{"step": "relocalize affected object"}, {"step": "complete original task"}],
            "controller_prompt": (
                f"relocalize the affected object at its current position, then {recovery_input.original_task}"
            ),
        }
        request = {
            "mode": "regenerate",
            "recovery_input": recovery_input.as_payload(),
            "output_schema": "full-state-v1",
        }
        return ProviderInvocation(
            mode="regenerate",
            raw_request=request,
            raw_response={"output": parsed, "fake": True},
            parsed_output=parsed,
            usage=TokenUsage(prompt_tokens=32, completion_tokens=24),
        )

    def patch(
        self,
        recovery_input: RecoveryInput,
        constraint_state: dict[str, Any],
    ) -> ProviderInvocation:
        target_id = "goal"
        constraints = constraint_state.get("constraints", [])
        if constraints and isinstance(constraints[0], dict):
            target_id = str(constraints[0].get("id", target_id))
        parsed = {
            "schema_version": "typed-patch-v1",
            "operations": [
                {
                    "op": "Override",
                    "target_id": target_id,
                    "payload": {
                        "replacement": {
                            "slot_id": f"{target_id}-after-move",
                            "constraint_type": "task_goal",
                            "content": {
                                "instruction": (
                                    "relocalize the affected object at its current position, "
                                    f"then {recovery_input.original_task}"
                                )
                            },
                            "source": "planner",
                            "priority": 100,
                        }
                    },
                    "reason": "oracle event reports that the affected object moved",
                }
            ],
            "controller_hint": (
                f"relocalize the affected object at its current position, then {recovery_input.original_task}"
            ),
        }
        request = {
            "mode": "patch",
            "recovery_input": recovery_input.as_payload(),
            "constraint_state": constraint_state,
            "output_schema": "typed-patch-v1",
        }
        return ProviderInvocation(
            mode="patch",
            raw_request=request,
            raw_response={"output": parsed, "fake": True, "state_hash_input": asdict(recovery_input)},
            parsed_output=parsed,
            usage=TokenUsage(prompt_tokens=32, completion_tokens=20),
        )


def create_fake_provider(config: dict[str, Any]) -> DeterministicFakeProvider:
    return DeterministicFakeProvider(config)
