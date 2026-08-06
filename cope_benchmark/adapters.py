from __future__ import annotations

import importlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .interruptions import InterruptionEvent


FORMAL_METHODS = ("history_augmented_full_regeneration", "cope_patch")
FORBIDDEN_PROVIDER_MARKERS = ("fake", "mock", "scripted", "noop", "dry_run", "fixture")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AdapterDecision:
    instruction: str
    patch_operations: tuple[dict[str, Any], ...] = ()
    modified_slots: tuple[str, ...] = ()
    constraint_state: dict[str, Any] = field(default_factory=dict)
    slot_records: tuple[dict[str, Any], ...] = ()
    revalidation: tuple[dict[str, Any], ...] = ()
    high_level_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryAdapter(Protocol):
    method: str
    provider_id: str

    def start_episode(self, *, task: Mapping[str, Any], initial_instruction: str) -> None: ...

    def on_event(
        self,
        *,
        event: InterruptionEvent,
        event_information: Mapping[str, Any],
        observation: Mapping[str, Any],
        progress: Mapping[str, bool],
    ) -> AdapterDecision: ...

    def current_instruction(self) -> str: ...


class CorrectnessNoOpAdapter:
    """Phase-A-only adapter; the formal-run gate always rejects it."""

    provider_id = "scripted_noop_correctness_only"

    def __init__(self, method: str):
        if method not in FORMAL_METHODS:
            raise ValueError(f"unknown method {method!r}")
        self.method = method
        self._instruction = ""

    def start_episode(self, *, task: Mapping[str, Any], initial_instruction: str) -> None:
        self._instruction = initial_instruction

    def on_event(
        self,
        *,
        event: InterruptionEvent,
        event_information: Mapping[str, Any],
        observation: Mapping[str, Any],
        progress: Mapping[str, bool],
    ) -> AdapterDecision:
        return AdapterDecision(
            instruction=self._instruction,
            provider_metadata={
                "phase": "correctness",
                "not_formal_evidence": True,
                "received_event_id": event.event_id,
            },
        )

    def current_instruction(self) -> str:
        return self._instruction


def load_adapter(factory_spec: str, *, method: str, config: Mapping[str, Any]) -> RecoveryAdapter:
    if method not in FORMAL_METHODS:
        raise ValueError(f"unknown formal method {method!r}")
    if ":" not in factory_spec:
        raise ValueError("adapter factory must be specified as module.path:factory_name")
    module_name, factory_name = factory_spec.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name)
    adapter = factory(method=method, config=dict(config))
    if getattr(adapter, "method", None) != method:
        raise ValueError("adapter factory returned an object for the wrong method")
    for attribute in ("provider_id", "start_episode", "on_event", "current_instruction"):
        if not hasattr(adapter, attribute):
            raise TypeError(f"adapter is missing required attribute {attribute!r}")
    return adapter


def formal_run_gate(
    config: Mapping[str, Any],
    *,
    phase: str,
    adapter_provider_ids: Mapping[str, str] | None = None,
) -> list[str]:
    """Return all reasons a calibration/pilot/formal run is not admissible."""

    if phase == "correctness":
        return []
    errors: list[str] = []
    if phase not in {"clean_calibration", "pilot", "formal"}:
        errors.append(f"unknown phase {phase!r}")
    checkpoint = str(config.get("checkpoint") or "")
    if not checkpoint:
        errors.append("OpenVLA checkpoint is not configured")
    elif checkpoint.startswith(("fake:", "mock:", "scripted:")):
        errors.append("fake/mock/scripted checkpoint is forbidden outside correctness")
    elif checkpoint.startswith("/") and not Path(checkpoint).exists():
        errors.append(f"checkpoint path does not exist: {checkpoint}")

    adapters = config.get("adapters") or {}
    if phase in {"pilot", "formal"}:
        for method in FORMAL_METHODS:
            if not str(adapters.get(method) or ""):
                errors.append(f"adapter factory is not configured for {method}")

    if phase in {"pilot", "formal"}:
        dependencies = config.get("dependency_commits") or {}
        required = ("method/cope-state-semantics", "main_experiment_adapters")
        for dependency in required:
            sha = str(dependencies.get(dependency) or "")
            if not SHA_PATTERN.fullmatch(sha):
                errors.append(
                    f"dependency {dependency} must be pinned to a full 40-character commit SHA"
                )

    if adapter_provider_ids:
        for method, provider_id in adapter_provider_ids.items():
            normalized = str(provider_id).lower()
            if any(marker in normalized for marker in FORBIDDEN_PROVIDER_MARKERS):
                errors.append(f"formal provider for {method} is forbidden: {provider_id}")
    return errors
