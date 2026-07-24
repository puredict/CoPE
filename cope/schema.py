from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence, TypeAlias

from .errors import INVALID_ENUM, INVALID_JSON_VALUE, SchemaError


SCHEMA_VERSION = "1.0"


class ConstraintMode(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OVERRIDDEN = "overridden"
    DEMOTED = "demoted"
    EXPIRED = "expired"


class ConstraintSource(str, Enum):
    TASK = "task"
    USER = "user"
    SAFETY = "safety"
    PERCEPTION = "perception"
    PLANNER = "planner"
    SYSTEM = "system"


class EventSource(str, Enum):
    ORACLE = "oracle"
    DETECTED = "detected"


FrozenJSON: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["FrozenJSON", ...]
    | Mapping[str, "FrozenJSON"]
)


def _enum_value(enum_type: type[Enum], value: Any, field_name: str) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise SchemaError(
            INVALID_ENUM,
            f"{field_name} has invalid value {value!r}",
            field=field_name,
            value=value,
            allowed=[item.value for item in enum_type],
        ) from exc


def freeze_json(value: Any, *, path: str = "$") -> FrozenJSON:
    """Validate and recursively freeze a JSON value."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaError(INVALID_JSON_VALUE, f"non-finite float at {path}", path=path)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJSON] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SchemaError(
                    INVALID_JSON_VALUE,
                    f"JSON object key at {path} must be a string",
                    path=path,
                    key=repr(key),
                )
            frozen[key] = freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item, path=f"{path}[{index}]") for index, item in enumerate(value))
    raise SchemaError(
        INVALID_JSON_VALUE,
        f"unsupported JSON value {type(value).__name__} at {path}",
        path=path,
        type=type(value).__name__,
    )


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(INVALID_JSON_VALUE, f"{field_name} must be a non-empty string", field=field_name)
    return value


@dataclass(frozen=True)
class ConstraintSlot:
    slot_id: str
    constraint_type: str
    content: Mapping[str, Any]
    source: ConstraintSource | str
    mode: ConstraintMode | str
    priority: int
    created_event_id: str
    last_updated_event_id: str
    parent_slot_id: str | None = None
    overrides_slot_ids: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("slot_id", "constraint_type", "created_event_id", "last_updated_event_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if self.parent_slot_id is not None:
            object.__setattr__(self, "parent_slot_id", _nonempty(self.parent_slot_id, "parent_slot_id"))
        if isinstance(self.priority, bool) or not isinstance(self.priority, int) or not 0 <= self.priority <= 1000:
            raise SchemaError(
                INVALID_JSON_VALUE,
                "priority must be an integer in [0, 1000]",
                field="priority",
                value=self.priority,
            )
        source = _enum_value(ConstraintSource, self.source, "source")
        mode = _enum_value(ConstraintMode, self.mode, "mode")
        content = freeze_json(self.content, path="$.content")
        metadata = freeze_json(self.metadata, path="$.metadata")
        if not isinstance(content, Mapping) or not content:
            raise SchemaError(
                INVALID_JSON_VALUE,
                "content must be a non-empty structured JSON object",
                field="content",
            )
        if not isinstance(metadata, Mapping):
            raise SchemaError(INVALID_JSON_VALUE, "metadata must be a JSON object", field="metadata")
        lineage = tuple(_nonempty(item, "lineage item") for item in self.lineage)
        overrides = tuple(_nonempty(item, "overrides_slot_ids item") for item in self.overrides_slot_ids)
        evidence = tuple(_nonempty(item, "evidence_refs item") for item in self.evidence_refs)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(self, "overrides_slot_ids", overrides)
        object.__setattr__(self, "evidence_refs", evidence)


@dataclass(frozen=True)
class Insert:
    operation_id: str
    slot: ConstraintSlot
    operation_type: str = field(default="insert", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _nonempty(self.operation_id, "operation_id"))


@dataclass(frozen=True)
class Suspend:
    operation_id: str
    slot_id: str
    reason: str
    operation_type: str = field(default="suspend", init=False)

    def __post_init__(self) -> None:
        for name in ("operation_id", "slot_id", "reason"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))


@dataclass(frozen=True)
class Override:
    operation_id: str
    slot_id: str
    replacement: ConstraintSlot
    reason: str
    operation_type: str = field(default="override", init=False)

    def __post_init__(self) -> None:
        for name in ("operation_id", "slot_id", "reason"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))


@dataclass(frozen=True)
class Demote:
    operation_id: str
    slot_id: str
    new_priority: int
    reason: str
    operation_type: str = field(default="demote", init=False)

    def __post_init__(self) -> None:
        for name in ("operation_id", "slot_id", "reason"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if isinstance(self.new_priority, bool) or not isinstance(self.new_priority, int):
            raise SchemaError(INVALID_JSON_VALUE, "new_priority must be an integer", field="new_priority")


@dataclass(frozen=True)
class Revalidate:
    operation_id: str
    slot_id: str
    validation_id: str
    validator_id: str
    evidence: Mapping[str, Any]
    result: bool
    applies_to_last_updated_event_id: str
    reason: str
    operation_type: str = field(default="revalidate", init=False)

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "slot_id",
            "validation_id",
            "validator_id",
            "applies_to_last_updated_event_id",
            "reason",
        ):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if not isinstance(self.result, bool):
            raise SchemaError(INVALID_JSON_VALUE, "result must be boolean", field="result")
        evidence = freeze_json(self.evidence, path="$.evidence")
        if not isinstance(evidence, Mapping):
            raise SchemaError(INVALID_JSON_VALUE, "evidence must be a JSON object", field="evidence")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True)
class Restore:
    operation_id: str
    slot_id: str
    validation_id: str
    reason: str
    operation_type: str = field(default="restore", init=False)

    def __post_init__(self) -> None:
        for name in ("operation_id", "slot_id", "validation_id", "reason"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))


@dataclass(frozen=True)
class Expire:
    operation_id: str
    slot_id: str
    reason: str
    operation_type: str = field(default="expire", init=False)

    def __post_init__(self) -> None:
        for name in ("operation_id", "slot_id", "reason"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))


Operation: TypeAlias = Insert | Suspend | Override | Demote | Revalidate | Restore | Expire


@dataclass(frozen=True)
class Patch:
    patch_id: str
    event_id: str
    reason: str
    operations: tuple[Operation, ...] | Sequence[Operation]
    generator: str
    input_state_hash: str
    created_at: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("patch_id", "event_id", "reason", "generator", "input_state_hash"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if isinstance(self.created_at, bool) or not isinstance(self.created_at, int) or self.created_at < 0:
            raise SchemaError(
                INVALID_JSON_VALUE,
                "created_at must be a non-negative deterministic logical timestamp",
                field="created_at",
            )
        operations = tuple(self.operations)
        if not operations:
            raise SchemaError(INVALID_JSON_VALUE, "operations must not be empty", field="operations")
        metadata = freeze_json(self.metadata, path="$.metadata")
        if not isinstance(metadata, Mapping):
            raise SchemaError(INVALID_JSON_VALUE, "metadata must be a JSON object", field="metadata")
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True)
class PatchContext:
    actor: str
    authority_priority: int
    authorized_sources: tuple[ConstraintSource | str, ...] = ()
    allow_safety_override: bool = False
    event_source: EventSource | str | None = None
    information_budget: int | None = None
    policy_step_budget: int | None = None
    high_level_call_count: int = 0
    pair_key: Mapping[str, Any] = field(default_factory=dict)
    task_progress: Mapping[str, Any] = field(default_factory=dict)
    termination_reason: str | None = None
    manual_intervention: bool = False
    git_commit: str | None = None
    config_hash: str | None = None
    checkpoint_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor", _nonempty(self.actor, "actor"))
        if (
            isinstance(self.authority_priority, bool)
            or not isinstance(self.authority_priority, int)
            or not 0 <= self.authority_priority <= 1000
        ):
            raise SchemaError(
                INVALID_JSON_VALUE,
                "authority_priority must be an integer in [0, 1000]",
                field="authority_priority",
            )
        sources = tuple(_enum_value(ConstraintSource, value, "authorized_sources") for value in self.authorized_sources)
        event_source = (
            None if self.event_source is None else _enum_value(EventSource, self.event_source, "event_source")
        )
        for name in ("information_budget", "policy_step_budget"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise SchemaError(INVALID_JSON_VALUE, f"{name} must be a non-negative integer or null", field=name)
        if (
            isinstance(self.high_level_call_count, bool)
            or not isinstance(self.high_level_call_count, int)
            or self.high_level_call_count < 0
        ):
            raise SchemaError(
                INVALID_JSON_VALUE,
                "high_level_call_count must be a non-negative integer",
                field="high_level_call_count",
            )
        object.__setattr__(self, "authorized_sources", sources)
        object.__setattr__(self, "event_source", event_source)
        for name in ("pair_key", "task_progress", "metadata"):
            value = freeze_json(getattr(self, name), path=f"$.{name}")
            if not isinstance(value, Mapping):
                raise SchemaError(INVALID_JSON_VALUE, f"{name} must be a JSON object", field=name)
            object.__setattr__(self, name, value)

    @classmethod
    def trusted(cls, actor: str = "system", **kwargs: Any) -> "PatchContext":
        return cls(
            actor=actor,
            authority_priority=1000,
            authorized_sources=tuple(ConstraintSource),
            allow_safety_override=True,
            **kwargs,
        )


@dataclass(frozen=True)
class AppliedPatch:
    patch: Patch
    context: PatchContext


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    patch_id: str
    revision: int
    reason: str
    generator: str
    applied_operation_ids: tuple[str, ...]
    affected_slot_ids: tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("event_id", "patch_id", "reason", "generator"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        details = freeze_json(self.details, path="$.details")
        if not isinstance(details, Mapping):
            raise SchemaError(INVALID_JSON_VALUE, "details must be a JSON object", field="details")
        object.__setattr__(self, "applied_operation_ids", tuple(self.applied_operation_ids))
        object.__setattr__(self, "affected_slot_ids", tuple(self.affected_slot_ids))
        object.__setattr__(self, "details", details)


@dataclass(frozen=True)
class ValidationRecord:
    validation_id: str
    slot_id: str
    validator_id: str
    result: bool
    evidence: Mapping[str, Any]
    state_revision: int
    applies_to_last_updated_event_id: str
    event_id: str
    operation_id: str

    def __post_init__(self) -> None:
        for name in (
            "validation_id",
            "slot_id",
            "validator_id",
            "applies_to_last_updated_event_id",
            "event_id",
            "operation_id",
        ):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        evidence = freeze_json(self.evidence, path="$.evidence")
        if not isinstance(evidence, Mapping):
            raise SchemaError(INVALID_JSON_VALUE, "evidence must be a JSON object", field="evidence")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True)
class ConstraintState:
    schema_version: str
    state_id: str
    revision: int
    slots: tuple[ConstraintSlot, ...]
    event_history: tuple[EventRecord, ...]
    patch_history: tuple[AppliedPatch, ...]
    validation_history: tuple[ValidationRecord, ...]
    state_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _nonempty(self.schema_version, "schema_version"))
        object.__setattr__(self, "state_id", _nonempty(self.state_id, "state_id"))
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise SchemaError(INVALID_JSON_VALUE, "revision must be a non-negative integer", field="revision")
        object.__setattr__(self, "slots", tuple(self.slots))
        object.__setattr__(self, "event_history", tuple(self.event_history))
        object.__setattr__(self, "patch_history", tuple(self.patch_history))
        object.__setattr__(self, "validation_history", tuple(self.validation_history))
        object.__setattr__(self, "state_hash", _nonempty(self.state_hash, "state_hash"))

    @classmethod
    def empty(cls, state_id: str) -> "ConstraintState":
        from .serialization import canonical_state_hash

        provisional = cls(
            schema_version=SCHEMA_VERSION,
            state_id=state_id,
            revision=0,
            slots=(),
            event_history=(),
            patch_history=(),
            validation_history=(),
            state_hash="pending",
        )
        return cls(
            schema_version=provisional.schema_version,
            state_id=provisional.state_id,
            revision=provisional.revision,
            slots=provisional.slots,
            event_history=provisional.event_history,
            patch_history=provisional.patch_history,
            validation_history=provisional.validation_history,
            state_hash=canonical_state_hash(provisional),
        )

    def get_slot(self, slot_id: str) -> ConstraintSlot:
        from .errors import SLOT_NOT_FOUND, TransitionError

        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        raise TransitionError(SLOT_NOT_FOUND, f"slot {slot_id!r} does not exist", slot_id=slot_id)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True)
class RevalidationResult:
    success: bool
    validation_id: str
    validator_id: str
    evidence: Mapping[str, Any]
    operation: Revalidate
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    state: ConstraintState
    before_hash: str
    after_hash: str
    accepted: bool
    validation_report: ValidationReport
    applied_operation_ids: tuple[str, ...]
    rejection_reason: str | None
    rejection_code: str | None
    audit_record: Mapping[str, Any]


ValidatorCallable: TypeAlias = Callable[[ConstraintSlot, Mapping[str, Any]], bool]
