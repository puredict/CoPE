"""Pure, representation-neutral compilation of accepted v2 method semantics.

There is deliberately no task ID, canonical state, simulator, retrieval hook, or
provider argument. Compilation is a projection, never a semantic repair step.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import Enum
from typing import Any

from .schema import ExecutionContext, PersistentLedger, PlanningProblem, ProgressCertificate
from .enums import MethodName
from .canonical import canonical_sha256, to_primitive


class CompilationError(ValueError):
    """Accepted input cannot be translated without inventing semantics."""


class FrozenMap(Mapping[str, Any]):
    """Small deeply immutable JSON mapping, including a Python hash contract."""

    __slots__ = ("_items",)

    def __init__(self, value: Mapping[str, Any]) -> None:
        if not all(isinstance(key, str) for key in value):
            raise CompilationError("planning mapping keys must be strings")
        object.__setattr__(self, "_items", tuple(sorted((key, freeze(value[key])) for key in value)))

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenMap is immutable")

    def __getitem__(self, key: str) -> Any:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __repr__(self) -> str:
        return f"FrozenMap({dict(self._items)!r})"


def primitive(value: Any) -> Any:
    """Canonical public-record conversion; unknown objects fail closed."""
    try:
        return to_primitive(value)
    except (TypeError, ValueError) as exc:
        raise CompilationError(str(exc)) from exc


def freeze(value: Any) -> Any:
    value = primitive(value)
    if isinstance(value, dict):
        return FrozenMap(value)
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def _sha256(value: Any) -> str:
    return canonical_sha256(value)


def planning_problem_hash(problem: PlanningProblem) -> str:
    return _sha256(problem)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _sequence(value: Any, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (tuple, list)):
        raise CompilationError(f"{name} must be an array")
    return tuple(value)


def _records(value: Any, name: str) -> tuple[FrozenMap, ...]:
    values = _sequence(value, name)
    if not all(isinstance(item, Mapping) for item in values):
        raise CompilationError(f"{name} must contain objects")
    return tuple(FrozenMap(item) for item in values)


def _ids(value: Any, name: str) -> tuple[str, ...]:
    values = _sequence(value, name)
    if not all(isinstance(item, str) and item for item in values):
        raise CompilationError(f"{name} must contain nonempty strings")
    if len(set(values)) != len(values):
        raise CompilationError(f"{name} contains duplicate IDs")
    return values


def _goal_order(goals: tuple[FrozenMap, ...]) -> tuple[FrozenMap, ...]:
    """Stable topological order, without adding absent prerequisite goals.

    A dependency referring to a non-goal remains in the goal record so a backend
    can fail closed. It is never materialized into an extra goal by this helper.
    """
    by_id: dict[str, FrozenMap] = {}
    for goal in goals:
        identifier = goal.get("occurrence_id")
        if not isinstance(identifier, str) or not identifier:
            raise CompilationError("every remaining goal needs an occurrence_id")
        if identifier in by_id:
            raise CompilationError(f"duplicate goal occurrence {identifier}")
        by_id[identifier] = goal
    pending = list(by_id)
    ordered: list[FrozenMap] = []
    done: set[str] = set()
    while pending:
        available = next((identifier for identifier in pending if all(
            dependency not in by_id or dependency in done
            for dependency in _ids(by_id[identifier].get("dependency_ids", ()), "dependency_ids")
        )), None)
        if available is None:
            raise CompilationError("goal dependencies contain a cycle")
        ordered.append(by_id[available])
        done.add(available)
        pending.remove(available)
    return tuple(ordered)


def _progress(value: Any) -> tuple[ProgressCertificate, ...]:
    result = []
    for record in _sequence(value, "progress_certificates"):
        if isinstance(record, ProgressCertificate):
            result.append(record)
        elif isinstance(record, Mapping):
            try:
                result.append(ProgressCertificate.from_dict(primitive(record)))
            except (ValueError, TypeError, KeyError) as exc:
                raise CompilationError(f"invalid progress certificate: {exc}") from exc
        else:
            raise CompilationError("progress certificates must be records")
    return tuple(result)


def _problem(*, source_method: MethodName, source_revision: int, initial_facts: Any,
             active_goal_occurrence_ids: Any, remaining_goals: Any, hard_constraints: Any,
             soft_preferences: Any, forbidden_regressions: Any, grounding_bindings: Any,
             restore_eligibility: Any, progress_certificates: Any,
             continuation_assumptions: Any) -> PlanningProblem:
    if isinstance(source_revision, bool) or not isinstance(source_revision, int) or source_revision < 0:
        raise CompilationError("source_revision must be a nonnegative integer")
    if not isinstance(continuation_assumptions, Mapping):
        raise CompilationError("continuation_assumptions must be an object")
    data = dict(
        source_method=MethodName(source_method), source_revision=source_revision,
        initial_facts=_records(initial_facts, "initial_facts"),
        active_goal_occurrence_ids=_ids(active_goal_occurrence_ids, "active_goal_occurrence_ids"),
        remaining_goals=_goal_order(_records(remaining_goals, "remaining_goals")),
        hard_constraints=_records(hard_constraints, "hard_constraints"),
        soft_preferences=_records(soft_preferences, "soft_preferences"),
        forbidden_regressions=_ids(forbidden_regressions, "forbidden_regressions"),
        grounding_bindings=_records(grounding_bindings, "grounding_bindings"),
        restore_eligibility=_records(restore_eligibility, "restore_eligibility"),
        progress_certificates=_progress(progress_certificates),
        continuation_assumptions=FrozenMap(continuation_assumptions),
    )
    # Inconsistent method semantics are not silently repaired. The backend can
    # diagnose a goal whose occurrence was not included in the active target set.
    return PlanningProblem(problem_id=f"problem:{_sha256(data)}", **data)


_DIRECTIVE_FIELDS = frozenset({
    "initial_facts", "active_goal_occurrence_ids", "remaining_goals", "hard_constraints",
    "soft_preferences", "forbidden_regressions", "grounding_bindings", "restore_eligibility",
    "progress_certificates", "continuation_assumptions",
})
_DIRECTIVE_EXTRAS = frozenset({
    "schema_version", "ordered_macro_plan", "current_subgoal", "current_target_occurrence_hypothesis",
})


def compile_directive(*, directive: Mapping[str, Any], context: ExecutionContext,
                      source_method: MethodName, source_revision: int) -> PlanningProblem:
    """Translate an accepted directive; context never fills its omitted semantics."""
    if not isinstance(directive, Mapping):
        raise CompilationError("directive must be an object")
    missing = _DIRECTIVE_FIELDS - directive.keys()
    extra = directive.keys() - _DIRECTIVE_FIELDS - _DIRECTIVE_EXTRAS
    if missing or extra:
        raise CompilationError(f"directive field mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    data = {key: directive[key] for key in _DIRECTIVE_FIELDS}
    continuation = dict(data["continuation_assumptions"])
    for key in ("ordered_macro_plan", "current_subgoal", "current_target_occurrence_hypothesis"):
        if key in directive:
            if key in continuation and primitive(continuation[key]) != primitive(directive[key]):
                raise CompilationError(f"conflicting explicit {key}")
            continuation[key] = directive[key]
    data["continuation_assumptions"] = continuation
    return _problem(source_method=source_method, source_revision=source_revision, **data)


def _slot_record(slot: Any, dependencies: tuple[str, ...]) -> FrozenMap:
    # Do not traverse provenance/history metadata: it is not planner semantics.
    return FrozenMap({
        "occurrence_id": slot.occurrence_id, "family_key": slot.family_key,
        "role": _value(slot.role), "predicate": slot.predicate, "arguments": slot.arguments,
        "priority": slot.priority, "hardness": slot.hardness,
        "grounding_validity": _value(slot.grounding_validity), "dependency_ids": dependencies,
    })


def compile_ledger(*, ledger: PersistentLedger, context: ExecutionContext,
                   source_method: MethodName, initial_facts: Any = None,
                   progress_certificates: Any = None,
                   continuation_assumptions: Any = None) -> PlanningProblem:
    """Project accepted commitments and explicitly supplied public execution facts.

    Explicit regeneration fields override public-context defaults, including empty
    arrays/objects. Restore guards are copied, never evaluated or refreshed here.
    """
    dependencies = {slot.occurrence_id: list(slot.dependency_ids) for slot in ledger.slots}
    for edge in ledger.relations:
        relation = _value(edge.relation)
        if relation == "depends_on" and edge.source_id in dependencies:
            dependencies[edge.source_id].append(edge.target_id)
        elif relation == "precedes" and edge.target_id in dependencies:
            dependencies[edge.target_id].append(edge.source_id)
    goals, constraints, preferences, groundings, restores = [], [], [], [], []
    active_ids = []
    for slot in ledger.slots:
        lifecycle = _value(slot.lifecycle)
        if lifecycle == "suspended":
            checks = tuple(record for record in ledger.history_records
                           if record.get("kind") == "validation"
                           and record.get("occurrence_id") == slot.occurrence_id)
            restores.append(FrozenMap({
                "occurrence_id": slot.occurrence_id, "lifecycle": lifecycle,
                "restore_guard": slot.restore_guard, "evidence_ids": slot.evidence_ids,
                "grounding_validity": _value(slot.grounding_validity),
                "validation_records": checks,
            }))
        if lifecycle != "active":
            continue
        record = _slot_record(slot, tuple(dict.fromkeys(dependencies[slot.occurrence_id])))
        role = _value(slot.role)
        if role == "achievement_goal":
            goals.append(record)
            active_ids.append(slot.occurrence_id)
        elif role == "grounding_binding":
            groundings.append(record)
        elif _value(slot.hardness) == "hard" or role == "safety_requirement":
            constraints.append(record)
        else:
            preferences.append(FrozenMap({**dict(record), "weight": slot.priority}))
    progress = tuple(context.progress) if progress_certificates is None else _progress(progress_certificates)
    preserved = tuple(certificate.milestone_id for certificate in progress
                      if _value(certificate.satisfaction) == "satisfied"
                      and getattr(certificate, "currently_preserved", True))
    if initial_facts is None:
        initial_facts = tuple({
            "key": fact.key, "value": fact.value, "confidence": fact.confidence,
            "evidence_ids": fact.evidence_ids, "timestamp": fact.timestamp,
        } for fact in context.beliefs)
    if continuation_assumptions is None:
        continuation_assumptions = primitive(context.continuation)
    return _problem(
        source_method=source_method, source_revision=ledger.revision,
        initial_facts=initial_facts, active_goal_occurrence_ids=active_ids,
        remaining_goals=goals, hard_constraints=constraints, soft_preferences=preferences,
        forbidden_regressions=tuple(dict.fromkeys(preserved)), grounding_bindings=groundings,
        restore_eligibility=restores, progress_certificates=progress,
        continuation_assumptions=continuation_assumptions,
    )
