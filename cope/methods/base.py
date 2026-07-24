from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cope.engine import ConstraintStateEngine, EngineFactory, apply_guarded_patch, validate_engine
from cope.providers.base import HighLevelRecoveryProvider, validate_provider_invocation
from cope.types import FullStateOutput, MethodDecision, PatchOutput, RecoveryInput


class RecoveryMethod(ABC):
    name: str

    def prepare(self, original_task: str, context: dict[str, Any]) -> None:
        del original_task, context

    @abstractmethod
    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        raise NotImplementedError


class MethodExecutionError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        kind: str = "method_error",
        provider_calls: tuple[Any, ...] = (),
        constraint_state_before: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind
        self.provider_calls = provider_calls
        self.constraint_state_before = constraint_state_before


class CleanMethod(RecoveryMethod):
    name = "clean"

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        del target_joint, recovery_input
        return MethodDecision(method=self.name, controller_prompt=original_prompt)


class ReactiveMethod(RecoveryMethod):
    name = "reactive_disturbed"

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        del target_joint
        return MethodDecision(
            method=self.name,
            controller_prompt=original_prompt,
            recovery_input_hash=recovery_input.input_hash,
        )


class RelocalizeMethod(RecoveryMethod):
    name = "structured_relocalize_prompt"

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        from libero_experiment_core import build_recovery_prompt

        prompt, _ = build_recovery_prompt(self.name, original_prompt, target_joint)
        return MethodDecision(
            method=self.name,
            controller_prompt=prompt,
            recovery_input_hash=recovery_input.input_hash,
        )


class StageBacktrackMethod(RecoveryMethod):
    name = "stage_backtrack_subgoal"

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        from libero_experiment_core import build_recovery_prompt

        prompt, _ = build_recovery_prompt(self.name, original_prompt, target_joint)
        return MethodDecision(
            method=self.name,
            controller_prompt=prompt,
            recovery_input_hash=recovery_input.input_hash,
        )


class FullRegenerationMethod(RecoveryMethod):
    name = "history_augmented_full_regeneration"

    def __init__(self, provider: HighLevelRecoveryProvider) -> None:
        self.provider = provider

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        del original_prompt, target_joint
        invocation = self.provider.regenerate(recovery_input)
        try:
            validate_provider_invocation(
                invocation,
                expected_mode="regenerate",
                recovery_input=recovery_input,
                metadata=self.provider.metadata,
            )
            parsed = FullStateOutput.from_mapping(invocation.parsed_output)
        except Exception as exc:
            if invocation.timeout:
                kind = "timeout"
            elif invocation.parse_failure:
                kind = "parse_failure"
            else:
                kind = "validation_failure"
            raise MethodExecutionError(
                f"{type(exc).__name__}: {exc}",
                kind=kind,
                provider_calls=(invocation,),
            ) from exc
        return MethodDecision(
            method=self.name,
            controller_prompt=parsed.controller_prompt,
            recovery_input_hash=recovery_input.input_hash,
            provider_calls=(invocation,),
            regenerated_state=parsed.as_payload(),
        )


class CoPEPatchMethod(RecoveryMethod):
    name = "cope_patch"

    def __init__(
        self,
        provider: HighLevelRecoveryProvider,
        engine_factory: EngineFactory,
        engine_config: dict[str, Any],
        *,
        formal: bool,
    ) -> None:
        self.provider = provider
        self.engine = engine_factory(engine_config)
        self.formal = formal
        validate_engine(self.engine, formal=formal)
        self._prepared = False

    def prepare(self, original_task: str, context: dict[str, Any]) -> None:
        self.engine.initialize(original_task, context)
        validate_engine(self.engine, formal=self.formal)
        self._prepared = True

    def on_event(
        self,
        *,
        original_prompt: str,
        target_joint: str,
        recovery_input: RecoveryInput,
    ) -> MethodDecision:
        del original_prompt, target_joint
        if not self._prepared:
            raise RuntimeError("CoPE method must be prepared before event handling")
        state_before = self.engine.snapshot()
        invocation = self.provider.patch(recovery_input, state_before)
        try:
            validate_provider_invocation(
                invocation,
                expected_mode="patch",
                recovery_input=recovery_input,
                metadata=self.provider.metadata,
            )
            patch = PatchOutput.from_mapping(invocation.parsed_output)
            result = apply_guarded_patch(self.engine, patch, recovery_input)
        except Exception as exc:
            if invocation.timeout:
                kind = "timeout"
            elif invocation.parse_failure:
                kind = "parse_failure"
            elif invocation.validation_failure:
                kind = "validation_failure"
            else:
                kind = "engine_or_schema_validation_failure"
            raise MethodExecutionError(
                f"{type(exc).__name__}: {exc}",
                kind=kind,
                provider_calls=(invocation,),
                constraint_state_before=state_before,
            ) from exc
        return MethodDecision(
            method=self.name,
            controller_prompt=result.controller_prompt,
            recovery_input_hash=recovery_input.input_hash,
            provider_calls=(invocation,),
            constraint_state_before=result.state_before,
            constraint_state_after=result.state_after,
            patch_operations=result.operations,
            revalidation_result=result.revalidations,
            unaffected_slot_preservation=result.preservation,
        )


def build_method(
    name: str,
    *,
    provider: HighLevelRecoveryProvider | None = None,
    engine_factory: EngineFactory | None = None,
    engine_config: dict[str, Any] | None = None,
    formal: bool = False,
) -> RecoveryMethod:
    if name == "clean":
        return CleanMethod()
    if name == "reactive_disturbed":
        return ReactiveMethod()
    if name == "structured_relocalize_prompt":
        return RelocalizeMethod()
    if name == "stage_backtrack_subgoal":
        return StageBacktrackMethod()
    if name == "history_augmented_full_regeneration":
        if provider is None:
            raise ValueError("full regeneration requires a high-level provider")
        return FullRegenerationMethod(provider)
    if name == "cope_patch":
        if provider is None or engine_factory is None:
            raise ValueError("CoPE patch requires both a provider and an engine factory")
        return CoPEPatchMethod(provider, engine_factory, engine_config or {}, formal=formal)
    raise ValueError(f"unknown method {name!r}")
