"""Deterministic symbolic backend for controlled-mechanism experiments only.

This executor is an abstract Boolean-literal interpreter, not a learned VLA or
physical simulator. It realizes only explicit supplied goal literals/effects,
checks supplied constraints after every action, and never reconstructs a task.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Protocol

from .canonical import canonical_json, canonical_sha256, to_primitive
from .compiler import planning_problem_hash
from .schema import ExecutionContext, ExecutionTrace, PlanningProblem, Record


@dataclass(frozen=True)
class ExecutionPlan(Record):
    provider_id: str
    result_kind: str
    problem_id: str
    planning_problem_sha256: str
    status: str
    macro_actions: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[str, ...] = ()

    def __hash__(self) -> int:
        return int(self.sha256[:15], 16)


@dataclass(frozen=True)
class ControlledExecutionTrace(ExecutionTrace):
    result_kind: str = "controlled_mechanism"
    status: str = "blocked"
    executed_occurrence_ids: tuple[str, ...] = ()
    final_facts: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()


class PlannerBackend(Protocol):
    provider_id: str
    uses_hidden_truth: bool

    def solve(self, *, problem: PlanningProblem, context: ExecutionContext) -> ExecutionPlan: ...


class _Unsupported(ValueError):
    pass


Literal = tuple[str, tuple[str, ...]]


def _literal(record: Mapping[str, Any]) -> tuple[Literal, bool]:
    predicate, arguments = record.get("predicate"), record.get("arguments", ())
    if not isinstance(predicate, str) or not predicate:
        raise _Unsupported("BLOCKED_UNSUPPORTED_PREDICATE_RECORD")
    if not isinstance(arguments, (tuple, list)) or not all(isinstance(arg, str) for arg in arguments):
        raise _Unsupported("BLOCKED_UNSUPPORTED_PREDICATE_ARGUMENTS")
    value = record.get("value", True)
    if type(value) is not bool:
        raise _Unsupported("BLOCKED_NON_BOOLEAN_LITERAL")
    return (predicate, tuple(arguments)), value


def _fact(record: Mapping[str, Any]) -> tuple[Literal, bool] | None:
    if "predicate" in record:
        return _literal(record)
    key, value = record.get("key"), record.get("value")
    # Uncertain numeric/pose facts are retained in the problem, but cannot prove
    # a Boolean hard constraint. Confidence thresholds are not invented here.
    if not isinstance(key, str) or type(value) is not bool:
        return None
    match = re.fullmatch(r"([^(),\s]+)\(([^()]*)\)", key)
    if match:
        arguments = tuple(arg.strip() for arg in match.group(2).split(",")) if match.group(2) else ()
        return (match.group(1), arguments), value
    return (key, ()), value


def _facts(problem: PlanningProblem) -> dict[Literal, bool]:
    facts: dict[Literal, bool] = {}
    for record in problem.initial_facts:
        fact = _fact(record)
        if fact is None:
            continue
        literal, value = fact
        if literal in facts and facts[literal] != value:
            raise _Unsupported("BLOCKED_CONTRADICTORY_INITIAL_FACTS")
        facts[literal] = value
    # Only explicitly preserved verifier records establish progress facts.
    for certificate in problem.progress_certificates:
        if certificate.currently_preserved and certificate.satisfaction.value == "satisfied":
            literal = (certificate.predicate, certificate.arguments)
            if literal in facts and facts[literal] is not True:
                raise _Unsupported("BLOCKED_CONTRADICTORY_PUBLIC_PROGRESS")
            facts[literal] = True
    return facts


def _fact_records(facts: Mapping[Literal, bool]) -> tuple[Mapping[str, Any], ...]:
    return tuple({"predicate": predicate, "arguments": arguments, "value": value}
                 for (predicate, arguments), value in sorted(facts.items()))


def _required_literals(problem: PlanningProblem) -> tuple[tuple[Literal, bool, str], ...]:
    required = []
    for index, constraint in enumerate(problem.hard_constraints):
        literal, value = _literal(constraint)
        required.append((literal, value, str(constraint.get("occurrence_id", f"constraint:{index}"))))
    certificates = {certificate.milestone_id: certificate for certificate in problem.progress_certificates}
    for milestone_id in problem.forbidden_regressions:
        certificate = certificates.get(milestone_id)
        if certificate is None or not certificate.currently_preserved or certificate.satisfaction.value != "satisfied":
            raise _Unsupported(f"BLOCKED_UNPROVEN_PROTECTED_PROGRESS:{milestone_id}")
        required.append(((certificate.predicate, certificate.arguments), True, milestone_id))
    return tuple(required)


def _check_constraints(facts: Mapping[Literal, bool], required: tuple[tuple[Literal, bool, str], ...]) -> None:
    for literal, value, identifier in required:
        if literal not in facts:
            raise _Unsupported(f"BLOCKED_CONSTRAINT_UNPROVEN:{identifier}")
        if facts[literal] != value:
            raise _Unsupported(f"BLOCKED_CONSTRAINT_VIOLATION:{identifier}")


def _check_preconditions(facts: Mapping[Literal, bool], preconditions: Any) -> None:
    if not isinstance(preconditions, (tuple, list)) or not all(isinstance(item, Mapping) for item in preconditions):
        raise _Unsupported("BLOCKED_UNSUPPORTED_PRECONDITIONS")
    for record in preconditions:
        literal, expected = _literal(record)
        if literal not in facts or facts[literal] != expected:
            raise _Unsupported(f"BLOCKED_SKILL_PRECONDITION:{literal[0]}")


def _effect_records(goal: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    if "effects" in goal:
        effects = goal["effects"]
        if not isinstance(effects, (tuple, list)) or not all(isinstance(item, Mapping) for item in effects):
            raise _Unsupported("BLOCKED_UNSUPPORTED_EFFECTS")
        return tuple(effects)
    # This is the complete abstract action model: achieve the supplied literal.
    literal, value = _literal(goal)
    return ({"predicate": literal[0], "arguments": literal[1], "value": value},)


def _goal_sequence(problem: PlanningProblem) -> tuple[Mapping[str, Any], ...]:
    goals = tuple(problem.remaining_goals)
    by_id = {goal.get("occurrence_id"): goal for goal in goals}
    if len(by_id) != len(goals) or any(not isinstance(identifier, str) or not identifier for identifier in by_id):
        raise _Unsupported("BLOCKED_INVALID_GOAL_OCCURRENCES")
    macro_plan = problem.continuation_assumptions.get("ordered_macro_plan", ())
    if not isinstance(macro_plan, (tuple, list)):
        raise _Unsupported("BLOCKED_UNSUPPORTED_MACRO_PLAN")
    if not macro_plan:
        return goals
    requested = []
    for entry in macro_plan:
        # Goal-order mode cannot silently discard supplied skill semantics. A
        # complete action program must explicitly select explicit_skills mode.
        if isinstance(entry, Mapping) and (set(entry) - {"target_occurrence_id", "occurrence_id"}):
            raise _Unsupported("BLOCKED_MACRO_SKILL_REQUIRES_EXPLICIT_MODE")
        if isinstance(entry, Mapping) and "target_occurrence_id" in entry and "occurrence_id" in entry and entry["target_occurrence_id"] != entry["occurrence_id"]:
            raise _Unsupported("BLOCKED_MACRO_PLAN_CONFLICTING_OCCURRENCE")
        identifier = entry if isinstance(entry, str) else (
            entry.get("target_occurrence_id", entry.get("occurrence_id")) if isinstance(entry, Mapping) else None
        )
        if not isinstance(identifier, str) or identifier not in by_id or identifier in requested:
            raise _Unsupported("BLOCKED_MACRO_PLAN_UNKNOWN_OR_DUPLICATE_OCCURRENCE")
        requested.append(identifier)
    if set(requested) != set(by_id):
        raise _Unsupported("BLOCKED_MACRO_PLAN_OMITS_REMAINING_GOAL")
    return tuple(by_id[identifier] for identifier in requested)


class ControlledMechanismBackend:
    """The same provider-free Boolean planner/executor for every method arm."""

    provider_id = "controlled.abstract_boolean.v1"
    result_kind = "controlled_mechanism"
    uses_hidden_truth = False
    learned_policy = False
    uses_privileged_state = False

    def _action(self, *, problem: PlanningProblem, goal: Mapping[str, Any], index: int,
                effects: Any, before: str, facts: Mapping[Literal, bool],
                macro_step: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        literal, _ = _literal(goal)
        identifier = goal["occurrence_id"]
        instruction = {
            "result_kind": self.result_kind, "target_occurrence_id": identifier,
            "goal": goal, "effects": effects, "hard_constraints": problem.hard_constraints,
            "soft_preferences": problem.soft_preferences,
            "forbidden_regressions": problem.forbidden_regressions,
            "grounding_bindings": problem.grounding_bindings,
            "restore_eligibility": problem.restore_eligibility,
            "continuation_assumptions": problem.continuation_assumptions,
        }
        if macro_step is not None:
            instruction["macro_step"] = macro_step
        action = {
            "action_id": macro_step["action_id"] if macro_step is not None else f"macro:{index}",
            "target_occurrence_id": identifier, "predicate": literal[0], "arguments": literal[1],
            "effects": effects, "compiled_instruction": instruction,
            "serialized_instruction": canonical_json(instruction),
            "before_facts_sha256": before, "after_facts_sha256": canonical_sha256(_fact_records(facts)),
        }
        if macro_step is not None:
            action["skill"] = macro_step["skill"]
        return action

    def _explicit_skills(self, problem: PlanningProblem, facts: dict[Literal, bool],
                         required: tuple[tuple[Literal, bool, str], ...]):
        goals = {goal.get("occurrence_id"): goal for goal in problem.remaining_goals}
        if len(goals) != len(problem.remaining_goals) or any(not isinstance(identifier, str) or not identifier for identifier in goals):
            raise _Unsupported("BLOCKED_INVALID_GOAL_OCCURRENCES")
        active = set(problem.active_goal_occurrence_ids)
        available = {certificate.milestone_id for certificate in problem.progress_certificates
                     if certificate.currently_preserved and certificate.satisfaction.value == "satisfied"}
        available.update(str(record["occurrence_id"]) for record in problem.hard_constraints
                         if "occurrence_id" in record)
        for identifier, goal in goals.items():
            _literal(goal)
            if identifier not in active:
                raise _Unsupported(f"BLOCKED_NONACTIVE_TARGET:{identifier}")
            if goal.get("grounding_validity", "valid") != "valid":
                raise _Unsupported(f"BLOCKED_GROUNDING_NOT_VALID:{identifier}")
            dependencies = goal.get("dependency_ids", ())
            if not isinstance(dependencies, (tuple, list)) or not all(isinstance(item, str) for item in dependencies):
                raise _Unsupported(f"BLOCKED_UNSUPPORTED_DEPENDENCIES:{identifier}")
        plan = problem.continuation_assumptions.get("ordered_macro_plan", ())
        if not isinstance(plan, (tuple, list)):
            raise _Unsupported("BLOCKED_UNSUPPORTED_MACRO_PLAN")
        actions, action_ids = [], set()
        for step in plan:
            if not isinstance(step, Mapping) or not {"action_id", "skill", "target_occurrence_id", "preconditions", "effects"} <= step.keys():
                raise _Unsupported("BLOCKED_UNSUPPORTED_EXPLICIT_SKILL")
            identifier = step["target_occurrence_id"]
            if not isinstance(identifier, str) or identifier not in goals or identifier not in active:
                raise _Unsupported("BLOCKED_MACRO_PLAN_UNKNOWN_OCCURRENCE")
            action_id = step["action_id"]
            if not isinstance(action_id, str) or not action_id or action_id in action_ids:
                raise _Unsupported("BLOCKED_INVALID_MACRO_ACTION_ID")
            if not isinstance(step["skill"], str) or not step["skill"].strip():
                raise _Unsupported("BLOCKED_INVALID_SKILL_NAME")
            if any(dependency not in available for dependency in goals[identifier].get("dependency_ids", ())):
                raise _Unsupported(f"BLOCKED_UNSATISFIED_DEPENDENCY:{identifier}")
            action_ids.add(action_id)
            _check_preconditions(facts, step["preconditions"])
            effects = step["effects"]
            if not isinstance(effects, (tuple, list)) or not all(isinstance(item, Mapping) for item in effects):
                raise _Unsupported("BLOCKED_UNSUPPORTED_EFFECTS")
            before = canonical_sha256(_fact_records(facts))
            for effect in effects:
                literal, value = _literal(effect)
                facts[literal] = value
            _check_constraints(facts, required)
            actions.append(self._action(problem=problem, goal=goals[identifier], index=len(actions),
                                        effects=effects, before=before, facts=facts, macro_step=step))
            goal_literal, desired = _literal(goals[identifier])
            if facts.get(goal_literal) == desired:
                available.add(identifier)
        for identifier, goal in goals.items():
            literal, desired = _literal(goal)
            if facts.get(literal) != desired:
                raise _Unsupported(f"BLOCKED_FINAL_GOAL_UNSATISFIED:{identifier}")
        return tuple(actions), facts

    def _simulate(self, problem: PlanningProblem) -> tuple[tuple[Mapping[str, Any], ...], dict[Literal, bool]]:
        facts = _facts(problem)
        required = _required_literals(problem)
        _check_constraints(facts, required)
        execution_mode = problem.continuation_assumptions.get("execution_mode", "abstract_goals")
        if execution_mode == "explicit_skills":
            return self._explicit_skills(problem, facts, required)
        if execution_mode != "abstract_goals":
            raise _Unsupported("BLOCKED_UNKNOWN_EXECUTION_MODE")
        available = {certificate.milestone_id for certificate in problem.progress_certificates
                     if certificate.currently_preserved and certificate.satisfaction.value == "satisfied"}
        available.update(str(record["occurrence_id"]) for record in problem.hard_constraints
                         if "occurrence_id" in record)
        active = set(problem.active_goal_occurrence_ids)
        actions = []
        for goal in _goal_sequence(problem):
            identifier = goal["occurrence_id"]
            if identifier not in active:
                raise _Unsupported(f"BLOCKED_NONACTIVE_TARGET:{identifier}")
            if goal.get("grounding_validity", "valid") != "valid":
                raise _Unsupported(f"BLOCKED_GROUNDING_NOT_VALID:{identifier}")
            dependencies = goal.get("dependency_ids", ())
            if not isinstance(dependencies, (tuple, list)) or not all(isinstance(item, str) for item in dependencies):
                raise _Unsupported(f"BLOCKED_UNSUPPORTED_DEPENDENCIES:{identifier}")
            if any(dependency not in available for dependency in dependencies):
                raise _Unsupported(f"BLOCKED_UNSATISFIED_DEPENDENCY:{identifier}")
            literal, desired = _literal(goal)
            _check_preconditions(facts, goal.get("preconditions", ()))
            effects = _effect_records(goal)
            before = canonical_sha256(_fact_records(facts))
            for effect in effects:
                effect_literal, value = _literal(effect)
                facts[effect_literal] = value
            _check_constraints(facts, required)
            if facts.get(literal) != desired:
                raise _Unsupported(f"BLOCKED_EXPLICIT_EFFECTS_DO_NOT_ACHIEVE_GOAL:{identifier}")
            actions.append(self._action(problem=problem, goal=goal, index=len(actions),
                                        effects=effects, before=before, facts=facts))
            available.add(identifier)
        # Every supplied remaining goal must hold at completion, including goals
        # undone by another supplied effect. No new action repairs conflicts.
        for goal in problem.remaining_goals:
            literal, desired = _literal(goal)
            if facts.get(literal) != desired:
                raise _Unsupported(f"BLOCKED_FINAL_GOAL_CONFLICT:{goal['occurrence_id']}")
        return tuple(actions), facts

    def solve(self, *, problem: PlanningProblem, context: ExecutionContext) -> ExecutionPlan:
        # Public context is part of the neutral backend protocol. The compiled
        # problem has already selected its initial facts; context cannot heal it.
        del context
        try:
            actions, _ = self._simulate(problem)
            status, diagnostics = "planned", ()
        except _Unsupported as exc:
            actions, status, diagnostics = (), "blocked", (str(exc),)
        return ExecutionPlan(
            provider_id=self.provider_id, result_kind=self.result_kind,
            problem_id=problem.problem_id, planning_problem_sha256=planning_problem_hash(problem),
            status=status, macro_actions=actions, diagnostics=diagnostics,
        )

    def execute(self, *, problem: PlanningProblem, context: ExecutionContext) -> ControlledExecutionTrace:
        plan = self.solve(problem=problem, context=context)
        if plan.status == "planned":
            _, facts = self._simulate(problem)
            status, final_facts = "succeeded", _fact_records(facts)
            executed = tuple(action["target_occurrence_id"] for action in plan.macro_actions)
        else:
            status, final_facts, executed = "blocked", (), ()
        summary = {
            "record_type": "controlled_execution_summary", "provider_id": self.provider_id,
            "result_kind": self.result_kind, "status": status,
            "learned_policy": False, "diagnostics": plan.diagnostics,
            "scope": "Boolean symbolic execution; no physical or learned-policy success claim",
        }
        records = (summary,) + tuple({"record_type": "macro_action", **to_primitive(action)}
                                   for action in plan.macro_actions)
        return ControlledExecutionTrace(
            trace_id=f"trace:{canonical_sha256({'problem': plan.planning_problem_sha256, 'records': records})}",
            planning_problem_sha256=plan.planning_problem_sha256, records=records,
            result_kind=self.result_kind, status=status, executed_occurrence_ids=executed,
            final_facts=final_facts, diagnostics=plan.diagnostics,
        )
