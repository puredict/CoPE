"""Strict, recursively immutable records at the v2 information boundaries."""

from __future__ import annotations

import math
import types
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from .canonical import canonical_sha256, freeze_json, to_primitive
from .enums import CommitmentRole, EventFamily, GroundingValidity, Lifecycle, MethodName, Satisfaction


def _typed(value: Any, annotation: Any, path: str) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if annotation is Any:
        return freeze_json(value)
    if origin in (types.UnionType, Union):
        for candidate in args:
            try:
                return _typed(value, candidate, path)
            except (TypeError, ValueError):
                pass
        raise ValueError(f"invalid optional/union value at {path}")
    if annotation is type(None):
        if value is not None:
            raise ValueError(f"expected null at {path}")
        return None
    if origin is tuple:
        if not isinstance(value, (tuple, list)):
            raise ValueError(f"expected array at {path}")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_typed(v, args[0], f"{path}[{i}]") for i, v in enumerate(value))
        if len(value) != len(args):
            raise ValueError(f"wrong tuple length at {path}")
        return tuple(_typed(v, a, path) for v, a in zip(value, args))
    if origin is Mapping:
        if not isinstance(value, Mapping):
            raise ValueError(f"expected object at {path}")
        if any(type(k) is not str for k in value):
            raise ValueError(f"non-string object key at {path}")
        return freeze_json({k: _typed(v, args[1], f"{path}.{k}") for k, v in value.items()})
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and issubclass(annotation, Record):
        if type(value) is annotation:
            return value
        if isinstance(value, Mapping):
            return annotation.from_dict(value)
        raise ValueError(f"expected {annotation.__name__} at {path}")
    if annotation is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"expected finite number at {path}")
        return float(value)
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"expected {annotation.__name__} at {path}")
        if annotation is str and not value.strip():
            raise ValueError(f"empty string at {path}")
        if annotation is int and value < 0:
            raise ValueError(f"negative integer at {path}")
        return value
    raise TypeError(f"unsupported schema annotation {annotation!r} at {path}")


class Record:
    def __post_init__(self) -> None:
        hints = get_type_hints(type(self))
        for member in fields(self):
            object.__setattr__(self, member.name, _typed(getattr(self, member.name), hints[member.name], member.name))
        self._validate()

    def _validate(self) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]):
        if not isinstance(value, Mapping):
            raise ValueError(f"{cls.__name__} requires an object")
        unknown = set(value) - {f.name for f in fields(cls) if f.init}
        if unknown:
            raise ValueError(f"unknown {cls.__name__} fields: {sorted(unknown)}")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError(f"incomplete {cls.__name__}: {exc}") from exc

    @property
    def sha256(self) -> str:
        return canonical_sha256(self)


def _confidence(value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError("confidence must be in [0, 1]")


def _unique(values: tuple[str, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {name}")


@dataclass(frozen=True)
class EvidenceRecord(Record):
    evidence_id: str
    hypothesis: str
    confidence: float
    provenance: str
    timestamp: int
    observation_refs: tuple[str, ...] = ()

    def _validate(self) -> None:
        from .evidence import assert_public_safe
        _confidence(self.confidence)
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class PublicEventPayload(Record):
    event_id: str
    event_index: int
    hypothesis: str
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int
    provenance: str
    observation_refs: tuple[str, ...] = ()
    user_message: str | None = None
    affected_entity_hypotheses: tuple[str, ...] = ()

    def _validate(self) -> None:
        from .evidence import assert_public_safe
        _confidence(self.confidence)
        if self.event_index < 1 or not self.evidence_ids:
            raise ValueError("events require a positive index and evidence references")
        _unique(self.evidence_ids, "evidence_ids")
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class EventEvidence(PublicEventPayload):
    """Agent-visible event evidence; no canonical-family or operator field."""


@dataclass(frozen=True)
class HiddenCanonicalEffect(Record):
    """Scoring/injection only. This object is never a non-oracle method input."""
    event_id: str
    true_family: EventFamily
    affected_occurrence_ids: tuple[str, ...]
    canonical_effect: Mapping[str, Any]
    simulator_intervention: Mapping[str, Any]


@dataclass(frozen=True)
class CommitmentOccurrence(Record):
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

    def _validate(self) -> None:
        from .occurrence import occurrence_number
        if "@" in self.family_key:
            raise ValueError("family key cannot contain @")
        occurrence_number(self.family_key, self.occurrence_id)
        if self.hardness not in ("hard", "soft"):
            raise ValueError("hardness must be hard or soft")
        if self.priority < 0:
            raise ValueError("priority must be nonnegative")
        if self.lifecycle in (Lifecycle.OVERRIDDEN, Lifecycle.EXPIRED) and self.retired_event_id is None:
            raise ValueError("retired occurrences require a retired_event_id")
        if self.lifecycle in (Lifecycle.ACTIVE, Lifecycle.SUSPENDED) and self.retired_event_id is not None:
            raise ValueError("live occurrences cannot have retired_event_id")
        _unique(self.dependency_ids, "dependency_ids")
        _unique(self.evidence_ids, "evidence_ids")
        if self.occurrence_id in self.dependency_ids:
            raise ValueError("an occurrence cannot depend on itself")


@dataclass(frozen=True)
class RelationEdge(Record):
    source_id: str
    relation: str
    target_id: str


@dataclass(frozen=True)
class PersistentLedger(Record):
    revision: int
    slots: tuple[CommitmentOccurrence, ...]
    relations: tuple[RelationEdge, ...] = ()
    history_records: tuple[Mapping[str, Any], ...] = ()

    def _validate(self) -> None:
        from .occurrence import validate_occurrences
        validate_occurrences(self.slots)
        _unique(tuple(slot.occurrence_id for slot in self.slots), "occurrence IDs")
        ids = {slot.occurrence_id for slot in self.slots}
        if len(set((e.source_id, e.relation, e.target_id) for e in self.relations)) != len(self.relations):
            raise ValueError("duplicate relation")
        if any(e.source_id not in ids or e.target_id not in ids for e in self.relations):
            raise ValueError("dangling relation endpoint")
        if any(set(s.dependency_ids) - ids for s in self.slots):
            raise ValueError("dangling dependency")


@dataclass(frozen=True)
class BeliefFact(Record):
    key: str
    value: Any
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int

    def _validate(self) -> None:
        from .evidence import assert_public_safe
        _confidence(self.confidence)
        if not self.evidence_ids:
            raise ValueError("beliefs require evidence references")
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class ProgressCertificate(Record):
    milestone_id: str
    predicate: str
    arguments: tuple[str, ...]
    satisfaction: Satisfaction
    verifier_record_id: str
    evidence_ids: tuple[str, ...]
    verified_at_step: int
    affected_by_event_ids: tuple[str, ...] = ()
    currently_preserved: bool = True

    def _validate(self) -> None:
        if not self.evidence_ids:
            raise ValueError("progress certificates require verifier evidence")
        if self.currently_preserved and self.satisfaction is not Satisfaction.SATISFIED:
            raise ValueError("preserved progress must be verified satisfied")


@dataclass(frozen=True)
class ContinuationState(Record):
    active_stage: str | None
    active_skill: str | None
    program_counter: int | None
    held_object_hypothesis: str | None
    resumable_suffix: tuple[str, ...]
    controller_state_ref: str | None
    captured_at_step: int


@dataclass(frozen=True)
class ExecutionContext(Record):
    beliefs: tuple[BeliefFact, ...]
    progress: tuple[ProgressCertificate, ...]
    continuation: ContinuationState

    def _validate(self) -> None:
        from .evidence import assert_public_safe
        _unique(tuple(b.key for b in self.beliefs), "belief keys")
        _unique(tuple(p.milestone_id for p in self.progress), "milestone IDs")
        assert_public_safe(self.to_dict())


@dataclass(frozen=True)
class PlanningProblem(Record):
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


CompiledPlanningProblem = PlanningProblem


@dataclass(frozen=True)
class MethodProposal(Record):
    method: MethodName
    event_id: str
    raw_output: Mapping[str, Any]


@dataclass(frozen=True)
class AcceptedMethodState(Record):
    method: MethodName
    ledger: PersistentLedger
    accepted_proposal_sha256: str | None = None


@dataclass(frozen=True)
class ExecutionTrace(Record):
    trace_id: str
    planning_problem_sha256: str
    records: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class SealedEvaluation(Record):
    evaluation_id: str
    event_id: str
    outcomes: Mapping[str, Any]
    hidden_truth_sha256: str


def record_json_schema(record_type: type[Record]) -> dict[str, Any]:
    """Structural JSON schema; constructors additionally enforce cross-field invariants."""
    definitions: dict[str, Any] = {}

    def encode(annotation: Any) -> dict[str, Any]:
        origin, args = get_origin(annotation), get_args(annotation)
        if annotation is Any:
            return {}
        if origin in (types.UnionType, Union):
            return {"anyOf": [encode(a) for a in args]}
        if annotation is type(None):
            return {"type": "null"}
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return {"type": "array", "items": encode(args[0])}
            return {"type": "array", "prefixItems": [encode(a) for a in args], "minItems": len(args), "maxItems": len(args)}
        if origin is Mapping:
            return {"type": "object", "additionalProperties": encode(args[1])}
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return {"type": "string", "enum": [v.value for v in annotation]}
        if isinstance(annotation, type) and issubclass(annotation, Record):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(annotation)
                properties = {member.name: encode(hints[member.name]) for member in fields(annotation)}
                for key in ("confidence",):
                    if key in properties:
                        properties[key].update(minimum=0, maximum=1)
                for key in ("event_index",):
                    if key in properties:
                        properties[key]["minimum"] = 1
                if "priority" in properties:
                    properties["priority"]["minimum"] = 0
                if annotation is CommitmentOccurrence:
                    properties["hardness"] = {"enum": ["hard", "soft"]}
                if annotation in (EvidenceRecord, PublicEventPayload, EventEvidence, BeliefFact, ProgressCertificate) and "evidence_ids" in properties:
                    properties["evidence_ids"]["minItems"] = 1
                definitions[name] = {"type": "object", "additionalProperties": False, "properties": properties,
                    "required": [f.name for f in fields(annotation) if f.default is MISSING and f.default_factory is MISSING]}
            return {"$ref": f"#/$defs/{name}"}
        return {str: {"type": "string", "minLength": 1, "pattern": r"\S"},
                int: {"type": "integer", "minimum": 0}, float: {"type": "number"}, bool: {"type": "boolean"}}[annotation]

    reference = encode(record_type)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": record_type.__name__,
            **reference, "$defs": definitions}
