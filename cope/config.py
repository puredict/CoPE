from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cope.types import InformationBudget, METHOD_NAMES, stable_hash


@dataclass(frozen=True)
class PhaseSelection:
    task_ids: tuple[int, ...]
    initial_state_ids: tuple[int, ...]
    seeds: tuple[int, ...]

    @property
    def pair_count(self) -> int:
        return len(self.task_ids) * len(self.initial_state_ids) * len(self.seeds)


@dataclass(frozen=True)
class ComparisonConfig:
    schema_version: str
    study_id: str
    checkpoint_id: str
    checkpoint_path: str
    checkpoint_sha256: str | None
    task_suite: str
    max_policy_steps: int
    warmup_env_steps: int
    resolution: int
    event_source: str
    methods: tuple[str, ...]
    pilot: PhaseSelection
    formal: PhaseSelection
    detected: PhaseSelection
    information_budget: InformationBudget
    provider: dict[str, Any]
    engine: dict[str, Any]
    disturbance_manifest: str
    output_root: str
    manual_intervention_allowed: bool
    reset_allowed: bool
    rollback_allowed: bool
    prompt_template_version: str

    @property
    def config_hash(self) -> str:
        return stable_hash(asdict(self))

    def selection(self, phase: str) -> PhaseSelection:
        if phase == "pilot":
            return self.pilot
        if phase == "formal":
            return self.formal
        if phase == "detected":
            return self.detected
        raise ValueError(f"unknown phase {phase!r}")


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        value = yaml.safe_load(text)
    except ImportError:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("PyYAML is required to read non-JSON YAML configs") from exc
    if not isinstance(value, dict):
        raise ValueError("comparison config must be an object")
    return value


def _selection(value: Any, label: str) -> PhaseSelection:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    result = PhaseSelection(
        task_ids=tuple(int(item) for item in value.get("task_ids", [])),
        initial_state_ids=tuple(int(item) for item in value.get("initial_state_ids", [])),
        seeds=tuple(int(item) for item in value.get("seeds", [])),
    )
    if not result.task_ids or not result.initial_state_ids or not result.seeds:
        raise ValueError(f"{label} selection cannot be empty")
    if min(result.task_ids + result.initial_state_ids + result.seeds) < 0:
        raise ValueError(f"{label} selection values must be >= 0")
    return result


def load_comparison_config(path: str | Path) -> ComparisonConfig:
    config_path = Path(path)
    data = _load_yaml_or_json(config_path)
    budgets = data.get("budgets", {})
    high_level = data.get("high_level", {})
    selections = data.get("selections", {})
    artifacts = data.get("artifacts", {})
    permissions = data.get("permissions", {})
    checkpoint = data.get("checkpoint", {})
    methods = tuple(data.get("methods", []))
    if methods != METHOD_NAMES:
        raise ValueError(f"methods must be the exact ordered six-condition set {METHOD_NAMES}")
    information_budget = InformationBudget(
        event_fields=tuple(high_level.get("event_fields", [])),
        history_fields=tuple(high_level.get("history_fields", [])),
        observation_fields=tuple(high_level.get("observation_fields", [])),
        max_high_level_calls=int(high_level.get("max_calls", 0)),
        max_prompt_tokens=int(high_level.get("max_prompt_tokens", 0)),
        max_completion_tokens=int(high_level.get("max_completion_tokens", 0)),
    )
    result = ComparisonConfig(
        schema_version=str(data.get("schema_version", "")),
        study_id=str(data.get("study_id", "")),
        checkpoint_id=str(checkpoint.get("id", "")),
        checkpoint_path=str(checkpoint.get("path", "")),
        checkpoint_sha256=checkpoint.get("sha256"),
        task_suite=str(data.get("task_suite", "")),
        max_policy_steps=int(budgets.get("policy_steps", 0)),
        warmup_env_steps=int(budgets.get("warmup_env_steps", 0)),
        resolution=int(data.get("resolution", 0)),
        event_source=str(data.get("event_source", "")),
        methods=methods,
        pilot=_selection(selections.get("pilot"), "pilot"),
        formal=_selection(selections.get("formal"), "formal"),
        detected=_selection(selections.get("detected"), "detected"),
        information_budget=information_budget,
        provider=dict(data.get("provider", {})),
        engine=dict(data.get("engine", {})),
        disturbance_manifest=str(data.get("disturbance_manifest", "")),
        output_root=str(artifacts.get("output_root", "")),
        manual_intervention_allowed=bool(permissions.get("manual_intervention", False)),
        reset_allowed=bool(permissions.get("reset", False)),
        rollback_allowed=bool(permissions.get("rollback", False)),
        prompt_template_version=str(high_level.get("prompt_template_version", "")),
    )
    if result.schema_version != "cope-main-comparison-v1":
        raise ValueError("schema_version must be cope-main-comparison-v1")
    if not result.study_id or not result.checkpoint_id or not result.checkpoint_path:
        raise ValueError("study_id and checkpoint id/path are required")
    if not result.task_suite or not result.disturbance_manifest or not result.output_root:
        raise ValueError("task_suite, disturbance_manifest, and output_root are required")
    if result.max_policy_steps <= 0 or result.warmup_env_steps < 0 or result.resolution <= 0:
        raise ValueError("budgets/resolution are invalid")
    if result.event_source not in {"oracle", "detected"}:
        raise ValueError("event_source must be oracle or detected")
    if result.manual_intervention_allowed or result.reset_allowed or result.rollback_allowed:
        raise ValueError("ranked comparison forbids manual intervention, reset, and rollback")
    if result.pilot.pair_count != 4:
        raise ValueError(f"pilot must preregister exactly 4 pair keys, got {result.pilot.pair_count}")
    if result.formal.pair_count != 120:
        raise ValueError(f"formal must preregister exactly 120 pair keys, got {result.formal.pair_count}")
    if (
        len(result.formal.task_ids) != 5
        or len(result.formal.initial_state_ids) != 8
        or len(result.formal.seeds) != 3
    ):
        raise ValueError("formal selection must be 5 tasks x 8 initial states x 3 seeds")
    if result.detected.pair_count < 30:
        raise ValueError(f"detected sensitivity must preregister at least 30 pair keys, got {result.detected.pair_count}")
    if not result.prompt_template_version:
        raise ValueError("prompt_template_version is required")
    return result
