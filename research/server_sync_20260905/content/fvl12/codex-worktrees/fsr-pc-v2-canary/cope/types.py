from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


METHOD_NAMES: tuple[str, ...] = (
    "clean",
    "reactive_disturbed",
    "structured_relocalize_prompt",
    "stage_backtrack_subgoal",
    "history_augmented_full_regeneration",
    "cope_patch",
)

DISTURBED_METHODS: tuple[str, ...] = METHOD_NAMES[1:]

PATCH_OPERATION_TYPES: tuple[str, ...] = (
    "Insert",
    "Suspend",
    "Override",
    "Demote",
    "Revalidate",
    "Restore",
    "Expire",
)

FULL_STATE_OUTPUT_SCHEMA = "full-state-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True)
class InformationBudget:
    event_fields: tuple[str, ...]
    history_fields: tuple[str, ...]
    observation_fields: tuple[str, ...]
    max_high_level_calls: int
    max_prompt_tokens: int
    max_completion_tokens: int

    def __post_init__(self) -> None:
        if self.max_high_level_calls < 0:
            raise ValueError("max_high_level_calls must be >= 0")
        if self.max_prompt_tokens <= 0 or self.max_completion_tokens <= 0:
            raise ValueError("token ceilings must be > 0")


@dataclass(frozen=True)
class RecoveryInput:
    """The common public input supplied to both high-level methods."""

    schema_version: str
    pair_key: str
    original_task: str
    observation: dict[str, Any]
    event: dict[str, Any]
    public_action_history: tuple[dict[str, Any], ...]
    task_progress: dict[str, Any]
    information_budget: InformationBudget

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def input_hash(self) -> str:
        return stable_hash(self.as_payload())


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("token usage cannot be negative")


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    temperature: float
    max_prompt_tokens: int
    max_completion_tokens: int
    max_retries: int
    timeout_seconds: float
    is_fake: bool = False

    @property
    def fairness_fingerprint(self) -> str:
        return stable_hash(asdict(self))


@dataclass(frozen=True)
class ProviderInvocation:
    mode: str
    raw_request: dict[str, Any]
    raw_response: Any
    parsed_output: dict[str, Any] | None
    usage: TokenUsage = field(default_factory=TokenUsage)
    retry_count: int = 0
    timeout: bool = False
    parse_failure: str | None = None
    validation_failure: str | None = None
    latency_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in {"regenerate", "patch"}:
            raise ValueError(f"invalid provider invocation mode {self.mode!r}")
        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")
        if self.latency_seconds < 0:
            raise ValueError("latency_seconds must be >= 0")


@dataclass(frozen=True)
class FullStateOutput:
    schema_version: str
    constraints: tuple[dict[str, Any], ...]
    plan: tuple[dict[str, Any], ...]
    controller_prompt: str

    @classmethod
    def from_mapping(cls, value: Any) -> "FullStateOutput":
        data = _require_mapping(value, "full-state output")
        schema_version = _require_nonempty_string(data.get("schema_version"), "schema_version")
        if schema_version != FULL_STATE_OUTPUT_SCHEMA:
            raise ValueError(f"unsupported full-state schema {schema_version!r}")
        constraints = data.get("constraints")
        plan = data.get("plan")
        if not isinstance(constraints, list) or not all(isinstance(item, Mapping) for item in constraints):
            raise ValueError("constraints must be a list of objects")
        if not constraints:
            raise ValueError("constraints must contain at least one task commitment")
        if not isinstance(plan, list) or not all(isinstance(item, Mapping) for item in plan):
            raise ValueError("plan must be a list of objects")
        if not plan:
            raise ValueError("plan must contain at least one nonterminal step")
        normalized_constraints: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(constraints):
            normalized = dict(item)
            constraint_id = _require_nonempty_string(normalized.get("id"), f"constraints[{index}].id")
            if constraint_id in seen_ids:
                raise ValueError(f"duplicate regenerated constraint id {constraint_id!r}")
            seen_ids.add(constraint_id)
            _require_nonempty_string(normalized.get("source"), f"constraints[{index}].source")
            priority = normalized.get("priority")
            if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
                raise ValueError(f"constraints[{index}].priority must be a nonnegative integer")
            lineage = normalized.get("lineage")
            if not isinstance(lineage, list) or not all(
                isinstance(identifier, str) and identifier for identifier in lineage
            ):
                raise ValueError(f"constraints[{index}].lineage must be a list of stable IDs")
            normalized_constraints.append(normalized)
        normalized_plan = tuple(dict(item) for item in plan)
        diagnostic_prompt = _require_nonempty_string(
            data.get("controller_prompt"), "controller_prompt"
        )
        compiled_prompt = cls.compile_controller_prompt(
            tuple(normalized_constraints), normalized_plan
        )
        if diagnostic_prompt != compiled_prompt:
            raise ValueError("controller_prompt does not match the neutral full-state compiler")
        return cls(
            schema_version=schema_version,
            constraints=tuple(normalized_constraints),
            plan=normalized_plan,
            controller_prompt=compiled_prompt,
        )

    @staticmethod
    def compile_controller_prompt(
        constraints: tuple[dict[str, Any], ...],
        plan: tuple[dict[str, Any], ...],
    ) -> str:
        candidates = [
            item
            for item in constraints
            if isinstance(item.get("text"), str) and str(item["text"]).strip()
        ]
        if not candidates:
            raise ValueError("neutral full-state compiler requires a textual task commitment")
        selected = sorted(
            candidates,
            key=lambda item: (-int(item["priority"]), str(item["id"])),
        )[0]
        task = str(selected["text"]).strip()
        requires_relocalization = any(
            "relocalize" in canonical_json(step).lower() for step in plan
        )
        if requires_relocalization:
            return f"relocalize the affected object at its current position, then {task}"
        return task

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchOperation:
    op: str
    target_id: str | None
    payload: dict[str, Any]
    reason: str

    @classmethod
    def from_mapping(cls, value: Any, index: int = 0) -> "PatchOperation":
        data = _require_mapping(value, f"operations[{index}]")
        op = _require_nonempty_string(data.get("op"), f"operations[{index}].op")
        if op not in PATCH_OPERATION_TYPES:
            raise ValueError(f"operations[{index}].op {op!r} is not a typed CoPE operation")
        target_id = data.get("target_id")
        if target_id is not None:
            target_id = _require_nonempty_string(target_id, f"operations[{index}].target_id")
        if op != "Insert" and target_id is None:
            raise ValueError(f"operations[{index}] {op} requires target_id")
        payload = data.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError(f"operations[{index}].payload must be an object")
        return cls(
            op=op,
            target_id=target_id,
            payload=dict(payload),
            reason=_require_nonempty_string(data.get("reason"), f"operations[{index}].reason"),
        )


@dataclass(frozen=True)
class PatchOutput:
    schema_version: str
    operations: tuple[PatchOperation, ...]
    controller_hint: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "PatchOutput":
        data = _require_mapping(value, "patch output")
        raw_operations = data.get("operations")
        if not isinstance(raw_operations, list):
            raise ValueError("operations must be a list")
        if not raw_operations:
            raise ValueError("operations must contain at least one typed patch")
        operations = tuple(PatchOperation.from_mapping(item, index) for index, item in enumerate(raw_operations))
        hint = data.get("controller_hint")
        if hint is not None:
            hint = _require_nonempty_string(hint, "controller_hint")
        return cls(
            schema_version=_require_nonempty_string(data.get("schema_version"), "schema_version"),
            operations=operations,
            controller_hint=hint,
        )

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MethodDecision:
    method: str
    controller_prompt: str
    recovery_input_hash: str | None = None
    provider_calls: tuple[ProviderInvocation, ...] = ()
    constraint_state_before: dict[str, Any] | None = None
    constraint_state_after: dict[str, Any] | None = None
    patch_operations: tuple[dict[str, Any], ...] = ()
    revalidation_result: tuple[dict[str, Any], ...] = ()
    unaffected_slot_preservation: dict[str, Any] | None = None
    regenerated_state: dict[str, Any] | None = None

    @property
    def high_level_call_count(self) -> int:
        return len(self.provider_calls)

    @property
    def prompt_tokens(self) -> int:
        return sum(call.usage.prompt_tokens for call in self.provider_calls)

    @property
    def completion_tokens(self) -> int:
        return sum(call.usage.completion_tokens for call in self.provider_calls)
