"""Starter contracts for CoPE repeated-interruption v2.

This is not a drop-in implementation. Codex should adapt it into
`cope_benchmark/repeated_v2/schema.py` and keep the invariants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class Lifecycle(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OVERRIDDEN = "overridden"
    EXPIRED = "expired"


class GroundingValidity(str, Enum):
    VALID = "valid"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class Satisfaction(str, Enum):
    UNRESOLVED = "unresolved"
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class CommitmentRole(str, Enum):
    ACHIEVEMENT_GOAL = "achievement_goal"
    MAINTENANCE_INVARIANT = "maintenance_invariant"
    SAFETY_REQUIREMENT = "safety_requirement"
    USER_PREFERENCE = "user_preference"
    GROUNDING_BINDING = "grounding_binding"


class MethodName(str, Enum):
    COPE_TYPED_EDIT = "cope_typed_edit"
    GENERIC_PERSISTENT_EDIT = "generic_persistent_edit"
    FULL_STATE_REGENERATION = "full_state_regeneration"
    FULL_HISTORY_REPLAN = "full_history_replan"
    RAG_REPLAN = "rag_replan"
    SUMMARY_MEMORY_REPLAN = "summary_memory_replan"
    SKILL_LOCAL_REPLAN = "skill_local_replan"
    CLASSICAL_EXECUTION_MONITOR = "classical_execution_monitor"
    ORACLE_PERSISTENT_UPDATE = "oracle_persistent_update"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    hypothesis: str
    confidence: float
    provenance: str
    timestamp: int
    observation_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class EventEvidence:
    event_id: str
    event_index: int
    hypothesis: str
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int
    user_message: str | None = None
    affected_entity_hypotheses: tuple[str, ...] = ()


@dataclass(frozen=True)
class HiddenCanonicalEffect:
    """Scoring-only. Must never enter a non-oracle adapter or prompt."""

    event_id: str
    true_family: str
    affected_occurrence_ids: tuple[str, ...]
    canonical_effect: Mapping[str, Any]
    simulator_intervention: Mapping[str, Any]


@dataclass(frozen=True)
class CommitmentOccurrence:
    family_key: str
    occurrence_id: str
    role: CommitmentRole
    predicate: str
    arguments: tuple[str, ...]
    lifecycle: Lifecycle
    grounding_validity: GroundingValidity
    priority: float
    hardness: str
    source: str
    authority: str
    restore_guard: Mapping[str, Any] = field(default_factory=dict)
    dependency_ids: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    created_event_id: str | None = None
    retired_event_id: str | None = None


@dataclass(frozen=True)
class RelationEdge:
    source_id: str
    relation: str
    target_id: str


@dataclass(frozen=True)
class PersistentLedger:
    revision: int
    slots: tuple[CommitmentOccurrence, ...]
    relations: tuple[RelationEdge, ...]
    history_records: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class BeliefFact:
    key: str
    value: Any
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int


@dataclass(frozen=True)
class ProgressCertificate:
    milestone_id: str
    predicate: str
    arguments: tuple[str, ...]
    satisfaction: Satisfaction
    verifier_record_id: str
    evidence_ids: tuple[str, ...]
    verified_at_step: int


@dataclass(frozen=True)
class ContinuationState:
    active_stage: str | None
    active_skill: str | None
    program_counter: int | None
    held_object_hypothesis: str | None
    resumable_suffix: tuple[str, ...]
    controller_state_ref: str | None
    captured_at_step: int


@dataclass(frozen=True)
class ExecutionContext:
    beliefs: tuple[BeliefFact, ...]
    progress: tuple[ProgressCertificate, ...]
    continuation: ContinuationState


@dataclass(frozen=True)
class PlanningProblem:
    problem_id: str
    source_method: MethodName
    source_revision: int
    initial_facts: tuple[Mapping[str, Any], ...]
    active_goal_occurrence_ids: tuple[str, ...]
    remaining_goals: tuple[Mapping[str, Any], ...]
    hard_constraints: tuple[Mapping[str, Any], ...]
    soft_preferences: tuple[Mapping[str, Any], ...]
    forbidden_regressions: tuple[str, ...]
    grounding_bindings: tuple[Mapping[str, Any], ...]
    restore_eligibility: tuple[Mapping[str, Any], ...]
    progress_certificates: tuple[ProgressCertificate, ...]
    continuation_assumptions: Mapping[str, Any]


@dataclass(frozen=True)
class ActionChunk:
    values: tuple[tuple[float, ...], ...]


class ExperimentMethod(Protocol):
    method: MethodName
    provider_id: str

    def start_episode(
        self,
        *,
        task: Mapping[str, Any],
        ledger: PersistentLedger,
        context: ExecutionContext,
    ) -> None: ...

    def on_event(
        self,
        *,
        evidence: EventEvidence,
        public_history: Sequence[Mapping[str, Any]],
        context: ExecutionContext,
    ) -> Mapping[str, Any]: ...

    def compile_state(self, *, context: ExecutionContext) -> PlanningProblem: ...


class PlannerBackend(Protocol):
    provider_id: str
    uses_hidden_truth: bool

    def solve(
        self,
        *,
        problem: PlanningProblem,
        context: ExecutionContext,
    ) -> Mapping[str, Any]: ...


class VLAAdapter(Protocol):
    provider_id: str
    learned_policy: bool
    uses_privileged_state: bool

    def reset(
        self,
        *,
        task: Mapping[str, Any],
        seed: int,
        initial_observation: Mapping[str, Any],
    ) -> None: ...

    def begin_subgoal(self, compiled_instruction: Mapping[str, Any]) -> None: ...

    def act(self, observation: Mapping[str, Any]) -> ActionChunk: ...

    def close(self) -> None: ...
