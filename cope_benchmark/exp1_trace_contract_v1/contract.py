"""Immutable records exported by the minimal Experiment-1 trace contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any, ClassVar, TypeVar

from .canonical import canonical_sha256, freeze_json, to_primitive
from .leakage import assert_public_safe
from .occurrence import OCCURRENCE_ALLOCATOR_VERSION

CONTRACT_VERSION = "cope-exp1-trace-contract/v1"
T = TypeVar("T", bound="ContractRecord")


def _require_text(value: str, field_name: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")


def _require_nonnegative(value: int, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return freeze_json(value)


def _freeze_mappings(value: tuple[Mapping[str, Any], ...], field_name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field_name} must be an array")
    return tuple(_freeze_mapping(item, field_name) for item in value)


def _freeze_strings(value: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or any(type(item) is not str for item in value):
        raise ValueError(f"{field_name} must be an array of strings")
    return tuple(value)


class ContractRecord:
    schema_name: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self)

    @classmethod
    def from_dict(cls: type[T], value: Mapping[str, Any]) -> T:
        if not isinstance(value, Mapping):
            raise ValueError(f"{cls.__name__} requires an object")
        allowed = {member.name for member in fields(cls)}
        unknown = set(value) - allowed
        missing = {member.name for member in fields(cls) if member.name not in value}
        if unknown or missing:
            raise ValueError(
                f"invalid {cls.__name__} fields; missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        return cls(**value)


@dataclass(frozen=True)
class PublicEventEvidenceV1(ContractRecord):
    schema_name: ClassVar[str] = "public_event_evidence_v1.schema.json"
    event_id: str
    event_index: int
    hypothesis: str
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int
    provenance: str
    observation_refs: tuple[str, ...]
    user_message: str | None
    affected_entity_hypotheses: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("event_id", "hypothesis", "provenance"):
            _require_text(getattr(self, name), name)
        if type(self.event_index) is not int or self.event_index < 1:
            raise ValueError("event_index must be positive")
        _require_nonnegative(self.timestamp, "timestamp")
        if type(self.confidence) not in (int, float) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be nonempty and unique")
        for name in ("evidence_ids", "observation_refs", "affected_entity_hypotheses"):
            object.__setattr__(self, name, _freeze_strings(getattr(self, name), name))
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class PersistentLedgerSnapshotV1(ContractRecord):
    schema_name: ClassVar[str] = "persistent_ledger_snapshot_v1.schema.json"
    revision: int
    slots: tuple[Mapping[str, Any], ...]
    relations: tuple[Mapping[str, Any], ...]
    history_records: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        _require_nonnegative(self.revision, "revision")
        for name in ("slots", "relations", "history_records"):
            object.__setattr__(self, name, _freeze_mappings(getattr(self, name), name))
        ids = [slot.get("occurrence_id") for slot in self.slots]
        if any(type(item) is not str or not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("ledger slots require unique nonempty occurrence_id values")
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class ProgressCertificateV1(ContractRecord):
    schema_name: ClassVar[str] = "progress_certificate_v1.schema.json"
    milestone_id: str
    predicate: str
    arguments: tuple[str, ...]
    satisfaction: str
    verifier_record_id: str
    evidence_ids: tuple[str, ...]
    verified_at_step: int
    affected_by_event_ids: tuple[str, ...]
    currently_preserved: bool

    def __post_init__(self) -> None:
        for name in ("milestone_id", "predicate", "satisfaction", "verifier_record_id"):
            _require_text(getattr(self, name), name)
        _require_nonnegative(self.verified_at_step, "verified_at_step")
        if not self.evidence_ids:
            raise ValueError("progress certificate requires evidence_ids")
        for name in ("arguments", "evidence_ids", "affected_by_event_ids"):
            object.__setattr__(self, name, _freeze_strings(getattr(self, name), name))
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class ExecutionContextSnapshotV1(ContractRecord):
    schema_name: ClassVar[str] = "execution_context_snapshot_v1.schema.json"
    captured_at_step: int
    beliefs: tuple[Mapping[str, Any], ...]
    progress: tuple[Mapping[str, Any], ...]
    continuation: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_nonnegative(self.captured_at_step, "captured_at_step")
        object.__setattr__(self, "beliefs", _freeze_mappings(self.beliefs, "beliefs"))
        object.__setattr__(self, "progress", _freeze_mappings(self.progress, "progress"))
        object.__setattr__(self, "continuation", _freeze_mapping(self.continuation, "continuation"))
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class PatchRecordV1(ContractRecord):
    schema_name: ClassVar[str] = "patch_record_v1.schema.json"
    patch_id: str
    episode_id: str
    event_index: int
    base_revision: int
    checks: tuple[Mapping[str, Any], ...]
    operations: tuple[Mapping[str, Any], ...]
    confidence: float
    accepted: bool
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.patch_id, "patch_id")
        _require_text(self.episode_id, "episode_id")
        if type(self.event_index) is not int or self.event_index < 1:
            raise ValueError("event_index must be positive")
        _require_nonnegative(self.base_revision, "base_revision")
        if type(self.confidence) not in (int, float) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        object.__setattr__(self, "checks", _freeze_mappings(self.checks, "checks"))
        object.__setattr__(self, "operations", _freeze_mappings(self.operations, "operations"))
        object.__setattr__(
            self, "rejection_reasons", _freeze_strings(self.rejection_reasons, "rejection_reasons")
        )
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class PlanningProblemV1(ContractRecord):
    schema_name: ClassVar[str] = "planning_problem_v1.schema.json"
    problem_id: str
    source_method: str
    source_revision: int
    initial_facts: tuple[Mapping[str, Any], ...]
    active_goal_occurrence_ids: tuple[str, ...]
    remaining_goals: tuple[Mapping[str, Any], ...]
    hard_constraints: tuple[Mapping[str, Any], ...]
    soft_preferences: tuple[Mapping[str, Any], ...]
    forbidden_regressions: tuple[str, ...]
    grounding_bindings: tuple[Mapping[str, Any], ...]
    restore_eligibility: tuple[Mapping[str, Any], ...]
    progress_certificates: tuple[Mapping[str, Any], ...]
    continuation_assumptions: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_text(self.problem_id, "problem_id")
        _require_text(self.source_method, "source_method")
        _require_nonnegative(self.source_revision, "source_revision")
        for name in (
            "initial_facts",
            "remaining_goals",
            "hard_constraints",
            "soft_preferences",
            "grounding_bindings",
            "restore_eligibility",
            "progress_certificates",
        ):
            object.__setattr__(self, name, _freeze_mappings(getattr(self, name), name))
        for name in ("active_goal_occurrence_ids", "forbidden_regressions"):
            object.__setattr__(self, name, _freeze_strings(getattr(self, name), name))
        object.__setattr__(
            self,
            "continuation_assumptions",
            _freeze_mapping(self.continuation_assumptions, "continuation_assumptions"),
        )
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class SealedOutcomeV1(ContractRecord):
    schema_name: ClassVar[str] = "sealed_outcome_v1.schema.json"
    evaluation_id: str
    event_id: str
    outcomes: Mapping[str, Any]
    hidden_truth_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.evaluation_id, "evaluation_id")
        _require_text(self.event_id, "event_id")
        if not re_full_sha256(self.hidden_truth_sha256):
            raise ValueError("hidden_truth_sha256 must be lowercase SHA-256")
        object.__setattr__(self, "outcomes", _freeze_mapping(self.outcomes, "outcomes"))


def re_full_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class RuntimeTraceBundleV1(ContractRecord):
    schema_name: ClassVar[str] = "runtime_trace_bundle_v1.schema.json"
    schema_version: str
    canonical_serialization_version: str
    occurrence_allocator_version: str
    trace_id: str
    episode_id: str
    public_events: tuple[Mapping[str, Any], ...]
    ledger_snapshots: tuple[Mapping[str, Any], ...]
    execution_context_snapshots: tuple[Mapping[str, Any], ...]
    patches: tuple[Mapping[str, Any], ...]
    planning_problems: tuple[Mapping[str, Any], ...]
    progress_certificates: tuple[Mapping[str, Any], ...]
    sealed_outcome_ref: str | None

    def __post_init__(self) -> None:
        from .canonical import CANONICAL_SERIALIZATION_VERSION

        if self.schema_version != CONTRACT_VERSION:
            raise ValueError("wrong trace contract version")
        if self.canonical_serialization_version != CANONICAL_SERIALIZATION_VERSION:
            raise ValueError("wrong canonical serialization version")
        if self.occurrence_allocator_version != OCCURRENCE_ALLOCATOR_VERSION:
            raise ValueError("wrong occurrence allocator version")
        _require_text(self.trace_id, "trace_id")
        _require_text(self.episode_id, "episode_id")
        for name in (
            "public_events",
            "ledger_snapshots",
            "execution_context_snapshots",
            "patches",
            "planning_problems",
            "progress_certificates",
        ):
            object.__setattr__(self, name, _freeze_mappings(getattr(self, name), name))
        if self.sealed_outcome_ref is not None and not re_full_sha256(self.sealed_outcome_ref):
            raise ValueError("sealed_outcome_ref must be a lowercase SHA-256")
        assert_public_safe(self.to_dict())


RECORD_TYPES: tuple[type[ContractRecord], ...] = (
    RuntimeTraceBundleV1,
    PublicEventEvidenceV1,
    PersistentLedgerSnapshotV1,
    ExecutionContextSnapshotV1,
    PatchRecordV1,
    PlanningProblemV1,
    ProgressCertificateV1,
    SealedOutcomeV1,
)
