from __future__ import annotations

from dataclasses import replace

import pytest

from cope_benchmark.repeated_v2.compiler import CompilationError, compile_directive, compile_ledger, planning_problem_hash
from cope_benchmark.repeated_v2.enums import CommitmentRole, GroundingValidity, Lifecycle, MethodName, Satisfaction
from cope_benchmark.repeated_v2.planner_backend import ControlledMechanismBackend
from cope_benchmark.repeated_v2.schema import (
    BeliefFact, CommitmentOccurrence, ContinuationState, ExecutionContext,
    PersistentLedger, ProgressCertificate, RelationEdge,
)


def slot(identifier="goal@1", *, predicate="inside", arguments=("mug", "shelf"),
         role=CommitmentRole.ACHIEVEMENT_GOAL, **updates):
    identifier = identifier if "@" in identifier else f"{identifier}@1"
    if "dependency_ids" in updates:
        updates["dependency_ids"] = tuple(item if "@" in item else f"{item}@1" for item in updates["dependency_ids"])
    data = dict(family_key=identifier.split("@")[0], occurrence_id=identifier, role=role,
                predicate=predicate, arguments=arguments, lifecycle=Lifecycle.ACTIVE,
                grounding_validity=GroundingValidity.VALID, priority=1.0,
                hardness="hard", source="user", authority="user")
    data.update(updates)
    return CommitmentOccurrence(**data)


def context(*, beliefs=(), progress=()):
    return ExecutionContext(beliefs=beliefs, progress=progress,
                            continuation=ContinuationState(None, None, None, None, (), None, 0))


def certificate(identifier="plate_progress", **updates):
    data = dict(milestone_id=identifier, predicate="inside", arguments=("plate", "rack"),
                satisfaction=Satisfaction.SATISFIED, verifier_record_id="verifier:1",
                evidence_ids=("evidence:1",), verified_at_step=1)
    data.update(updates)
    return ProgressCertificate(**data)


def directive(**updates):
    data = dict(schema_version="cope-repeated-v2/directive-1", initial_facts=[],
                active_goal_occurrence_ids=[], remaining_goals=[], hard_constraints=[],
                soft_preferences=[], forbidden_regressions=[], grounding_bindings=[],
                restore_eligibility=[], progress_certificates=[], continuation_assumptions={},
                ordered_macro_plan=[])
    data.update(updates)
    return data


def compile_direct(value, ctx=None):
    return compile_directive(directive=value, context=ctx or context(),
                             source_method=MethodName.FULL_HISTORY_REPLAN, source_revision=2)


def compile_slots(slots, ctx=None, **updates):
    return compile_ledger(ledger=PersistentLedger(2, tuple(slots)), context=ctx or context(),
                          source_method=MethodName.COPE_TYPED_EDIT, **updates)


def test_compiler_is_pure_under_poisoned_hidden_fields():
    class Poison:
        def __getattribute__(self, name):
            raise AssertionError("compiler attempted to inspect hidden truth")

    ledger = PersistentLedger(2, (slot(),), history_records=({"kind": "unrelated_audit", "task_id": "poison_task"},))
    ctx = context()
    expected = compile_ledger(ledger=ledger, context=ctx, source_method=MethodName.COPE_TYPED_EDIT)
    object.__setattr__(ledger, "hidden_canonical_state", Poison())
    object.__setattr__(ctx, "simulator_truth", Poison())
    actual = compile_ledger(ledger=ledger, context=ctx, source_method=MethodName.COPE_TYPED_EDIT)
    assert planning_problem_hash(expected) == planning_problem_hash(actual)
    assert "poison_task" not in repr(actual)


def test_directive_omissions_and_wrong_occurrence_survive_compilation():
    supplied = directive(active_goal_occurrence_ids=["wrong@99"], remaining_goals=[
        {"occurrence_id": "wrong@99", "predicate": "inside", "arguments": ["mug", "shelf"]}
    ])
    ctx = context(progress=(certificate(),))
    compiled = compile_direct(supplied, ctx)
    assert compiled.active_goal_occurrence_ids == ("wrong@99",)
    assert compiled.forbidden_regressions == ()
    assert compiled.progress_certificates == ()
    assert compiled.soft_preferences == ()
    assert compiled.restore_eligibility == ()
    trace = ControlledMechanismBackend().execute(problem=compiled, context=ctx)
    assert trace.executed_occurrence_ids == ("wrong@99",)


def test_compiler_refuses_missing_or_hidden_directive_fields():
    supplied = directive()
    del supplied["remaining_goals"]
    with pytest.raises(CompilationError, match="missing"):
        compile_direct(supplied)
    with pytest.raises(CompilationError, match="extra"):
        compile_direct(directive(hidden_canonical_state={"goal": "secret"}))


def test_explicit_empty_regeneration_context_is_never_refilled():
    ctx = context(beliefs=(BeliefFact("inside(plate,rack)", True, 1, ("evidence:1",), 0),),
                  progress=(certificate(),))
    compiled = compile_slots([slot()], ctx, initial_facts=(), progress_certificates=(), continuation_assumptions={})
    assert compiled.initial_facts == ()
    assert compiled.progress_certificates == ()
    assert compiled.forbidden_regressions == ()
    assert dict(compiled.continuation_assumptions) == {}


def test_occurrence_identity_survives_same_predicate_progress_and_retirement():
    old = slot("old@1", lifecycle=Lifecycle.EXPIRED, retired_event_id="event:1")
    new = slot("new@2")
    ctx = context(progress=(certificate("old@1", arguments=("mug", "shelf")),))
    compiled = compile_slots([old, new], ctx)
    assert compiled.active_goal_occurrence_ids == ("new@2",)
    assert tuple(goal["occurrence_id"] for goal in compiled.remaining_goals) == ("new@2",)
    trace = ControlledMechanismBackend().execute(problem=compiled, context=ctx)
    assert trace.executed_occurrence_ids == ("new@2",)


def test_dependency_order_only_uses_present_semantics():
    first, second = slot("first"), slot("second", dependency_ids=("first",))
    compiled = compile_slots([second, first])
    assert tuple(goal["occurrence_id"] for goal in compiled.remaining_goals) == ("first@1", "second@1")
    retired = replace(first, lifecycle=Lifecycle.EXPIRED, retired_event_id="event:1")
    omitted = compile_slots([second, retired])
    assert tuple(goal["occurrence_id"] for goal in omitted.remaining_goals) == ("second@1",)
    assert omitted.remaining_goals[0]["dependency_ids"] == ("first@1",)
    assert ControlledMechanismBackend().solve(problem=omitted, context=context()).status == "blocked"


def test_dependency_relation_directions_and_cycle_rejection():
    ledger = PersistentLedger(1, (slot("last"), slot("first")),
                              (RelationEdge("first@1", "precedes", "last@1"),))
    compiled = compile_ledger(ledger=ledger, context=context(), source_method=MethodName.COPE_TYPED_EDIT)
    assert tuple(goal["occurrence_id"] for goal in compiled.remaining_goals) == ("first@1", "last@1")
    with pytest.raises(CompilationError, match="cycle"):
        compile_slots([slot("a", dependency_ids=("b",)), slot("b", dependency_ids=("a",))])


def test_restore_guards_and_stale_checks_are_copied_without_reactivation():
    suspended = slot("paused", lifecycle=Lifecycle.SUSPENDED, restore_guard={"requires": ["fresh-visible"]})
    check = {"kind": "validation", "occurrence_id": "paused@1", "result": True,
             "validated_at_event_index": 1, "evidence_ids": ["old:evidence"]}
    ledger = PersistentLedger(9, (suspended,), history_records=(check,))
    compiled = compile_ledger(ledger=ledger, context=context(), source_method=MethodName.COPE_TYPED_EDIT)
    assert compiled.remaining_goals == ()
    assert compiled.active_goal_occurrence_ids == ()
    record = compiled.restore_eligibility[0]
    assert record["validation_records"][0]["validated_at_event_index"] == 1
    assert "eligible" not in record
    assert ControlledMechanismBackend().execute(problem=compiled, context=context()).executed_occurrence_ids == ()


def test_retired_occurrences_never_enter_restore_candidates():
    overridden = slot("replaced", lifecycle=Lifecycle.OVERRIDDEN, retired_event_id="event:1",
                      restore_guard={"hypothesis": "available"})
    expired = slot("expired", lifecycle=Lifecycle.EXPIRED, retired_event_id="event:1",
                   restore_guard={"hypothesis": "available"})
    compiled = compile_slots([overridden, expired])
    assert compiled.restore_eligibility == ()
    assert compiled.active_goal_occurrence_ids == ()


def test_separate_roles_priorities_and_invalidated_progress_are_preserved():
    pref = slot("pref", role=CommitmentRole.USER_PREFERENCE, hardness="soft", priority=0.25)
    safety = slot("safety", role=CommitmentRole.SAFETY_REQUIREMENT)
    binding = slot("binding", role=CommitmentRole.GROUNDING_BINDING)
    ctx = context(progress=(certificate("kept"), certificate("invalidated", currently_preserved=False,
                                                               affected_by_event_ids=("event:2",))))
    compiled = compile_slots([slot(), pref, safety, binding], ctx)
    assert compiled.soft_preferences[0]["weight"] == 0.25
    assert compiled.hard_constraints[0]["occurrence_id"] == "safety@1"
    assert compiled.grounding_bindings[0]["occurrence_id"] == "binding@1"
    assert compiled.forbidden_regressions == ("kept",)
    assert len(compiled.progress_certificates) == 2


def test_planning_snapshot_is_deeply_immutable_and_canonical():
    first = compile_direct(directive(soft_preferences=[{"weight": 1.0, "predicate": "gentle", "arguments": ["mug"]}]))
    second = compile_direct(directive(soft_preferences=[{"arguments": ["mug"], "predicate": "gentle", "weight": 1}]))
    assert planning_problem_hash(first) == planning_problem_hash(second)
    assert first.sha256 == planning_problem_hash(first)
    with pytest.raises(TypeError):
        first.soft_preferences[0]["weight"] = 99
    with pytest.raises((AttributeError, TypeError)):
        first.soft_preferences[0]["arguments"].append("secret")


def test_controlled_smoke_obeys_supplied_goals_constraints_and_progress():
    safety = slot("safety", predicate="keep_clear", arguments=("robot", "hazard"), role=CommitmentRole.SAFETY_REQUIREMENT)
    ctx = context(beliefs=(BeliefFact("keep_clear(robot,hazard)", True, 1, ("evidence:1",), 0),), progress=(certificate(),))
    compiled = compile_slots([slot(), safety], ctx)
    backend = ControlledMechanismBackend()
    plan = backend.solve(problem=compiled, context=ctx)
    trace = backend.execute(problem=compiled, context=ctx)
    assert plan.status == "planned"
    assert trace.status == "succeeded"
    assert plan.result_kind == trace.result_kind == "controlled_mechanism"
    assert backend.learned_policy is False
    assert backend.uses_hidden_truth is False
    assert trace.executed_occurrence_ids == ("goal@1",)
    assert plan.macro_actions[0]["compiled_instruction"]["forbidden_regressions"] == ("plate_progress",)
    assert plan.macro_actions[0]["serialized_instruction"]
    assert hash(plan)
    assert trace.sha256 == backend.execute(problem=compiled, context=ctx).sha256


def test_unknown_or_unproven_constraint_is_not_silently_satisfied():
    for constraint in ({"unknown_constraint": "keep safe"}, {"predicate": "unobserved", "arguments": []}):
        problem = compile_direct(directive(hard_constraints=[constraint]))
        trace = ControlledMechanismBackend().execute(problem=problem, context=context())
        assert trace.status == "blocked"
        assert trace.executed_occurrence_ids == ()


def test_backend_does_not_read_context_to_heal_directive_initial_facts():
    problem = compile_direct(directive(hard_constraints=[{"predicate": "safe", "arguments": []}]))
    ctx = context(beliefs=(BeliefFact("safe", True, 1, ("evidence:1",), 0),))
    trace = ControlledMechanismBackend().execute(problem=problem, context=ctx)
    assert trace.status == "blocked"
    assert "CONSTRAINT_UNPROVEN" in trace.diagnostics[0]


def test_explicit_goal_effects_cannot_regress_protected_progress():
    goal = {"occurrence_id": "g", "predicate": "inside", "arguments": ["mug", "shelf"],
            "effects": [{"predicate": "inside", "arguments": ["mug", "shelf"], "value": True},
                        {"predicate": "inside", "arguments": ["plate", "rack"], "value": False}]}
    problem = compile_direct(directive(active_goal_occurrence_ids=["g"], remaining_goals=[goal],
                                      progress_certificates=[certificate().to_dict()], forbidden_regressions=["plate_progress"]))
    trace = ControlledMechanismBackend().execute(problem=problem, context=context())
    assert trace.status == "blocked"
    assert "CONSTRAINT_VIOLATION:plate_progress" in trace.diagnostics[0]


def test_backend_keeps_invalid_groundings_and_omitted_macro_semantics_visible():
    compiled = compile_slots([slot(grounding_validity=GroundingValidity.INVALID)])
    assert compiled.remaining_goals[0]["grounding_validity"] == "invalid"
    assert ControlledMechanismBackend().execute(problem=compiled, context=context()).status == "blocked"
    goals = [{"occurrence_id": name, "predicate": "done", "arguments": [name]} for name in ("a", "b")]
    problem = compile_direct(directive(active_goal_occurrence_ids=["a", "b"], remaining_goals=goals, ordered_macro_plan=["a"]))
    trace = ControlledMechanismBackend().execute(problem=problem, context=context())
    assert trace.status == "blocked"
    assert "OMITS_REMAINING_GOAL" in trace.diagnostics[0]


def skill_step(identifier, *, skill="place", effects=(), preconditions=(), target="target"):
    return {"action_id": identifier, "skill": skill, "target_occurrence_id": target,
            "preconditions": list(preconditions), "effects": list(effects)}


def explicit_skills_problem(steps, **updates):
    data = {"active_goal_occurrence_ids": ["target"], "remaining_goals": [
        {"occurrence_id": "target", "predicate": "inside", "arguments": ["mug", "shelf"]}
    ], "ordered_macro_plan": steps, "continuation_assumptions": {"execution_mode": "explicit_skills"}}
    data.update(updates)
    return compile_direct(directive(**data))


def test_explicit_skills_preserve_intermediate_actions_and_never_add_goal_effects():
    grasped = {"predicate": "grasped", "arguments": ["mug"]}
    placed = {"predicate": "inside", "arguments": ["mug", "shelf"]}
    steps = [skill_step("take", skill="grasp", effects=[grasped]),
             skill_step("put", effects=[placed], preconditions=[grasped])]
    problem = explicit_skills_problem(steps)
    backend = ControlledMechanismBackend()
    plan = backend.solve(problem=problem, context=context())
    assert plan.status == "planned"
    assert tuple(action["action_id"] for action in plan.macro_actions) == ("take", "put")
    assert tuple(action["skill"] for action in plan.macro_actions) == ("grasp", "place")
    assert plan.macro_actions[0]["effects"] == ({"predicate": "grasped", "arguments": ("mug",)},)
    assert plan.macro_actions[0]["compiled_instruction"]["macro_step"]["action_id"] == "take"
    assert backend.execute(problem=problem, context=context()).executed_occurrence_ids == ("target", "target")
    incomplete = backend.solve(problem=explicit_skills_problem(steps[:1]), context=context())
    assert incomplete.status == "blocked"
    assert incomplete.diagnostics == ("BLOCKED_FINAL_GOAL_UNSATISFIED:target",)
    assert incomplete.macro_actions == ()


def test_empty_explicit_plan_keeps_missing_execution_visible():
    backend = ControlledMechanismBackend()
    unsatisfied = backend.solve(problem=explicit_skills_problem([]), context=context())
    assert unsatisfied.status == "blocked"
    assert unsatisfied.diagnostics == ("BLOCKED_FINAL_GOAL_UNSATISFIED:target",)
    already_satisfied = explicit_skills_problem([], initial_facts=[
        {"predicate": "inside", "arguments": ["mug", "shelf"]}
    ])
    trace = backend.execute(problem=already_satisfied, context=context())
    assert trace.status == "succeeded"
    assert trace.executed_occurrence_ids == ()


@pytest.mark.parametrize("missing", ["action_id", "skill", "target_occurrence_id", "preconditions", "effects"])
def test_explicit_skill_fields_cannot_be_reconstructed(missing):
    step = skill_step("put", effects=[{"predicate": "inside", "arguments": ["mug", "shelf"]}])
    del step[missing]
    plan = ControlledMechanismBackend().solve(problem=explicit_skills_problem([step]), context=context())
    assert plan.status == "blocked"
    assert plan.diagnostics == ("BLOCKED_UNSUPPORTED_EXPLICIT_SKILL",)


def test_explicit_skill_order_preconditions_and_identity_fail_closed():
    ready = {"predicate": "ready", "arguments": ["mug"]}
    placed = {"predicate": "inside", "arguments": ["mug", "shelf"]}
    prepare = skill_step("prepare", effects=[ready])
    place = skill_step("place", preconditions=[ready], effects=[placed])
    backend = ControlledMechanismBackend()
    reversed_plan = backend.solve(problem=explicit_skills_problem([place, prepare]), context=context())
    assert reversed_plan.diagnostics == ("BLOCKED_SKILL_PRECONDITION:ready",)
    duplicate_plan = backend.solve(problem=explicit_skills_problem([prepare, prepare, place]), context=context())
    assert duplicate_plan.diagnostics == ("BLOCKED_INVALID_MACRO_ACTION_ID",)
    invalid_target = {**place, "target_occurrence_id": ["target"]}
    wrong_plan = backend.solve(problem=explicit_skills_problem([invalid_target]), context=context())
    assert wrong_plan.diagnostics == ("BLOCKED_MACRO_PLAN_UNKNOWN_OCCURRENCE",)


def test_explicit_skills_cannot_regress_supplied_constraints_or_ignore_dependencies():
    placed = {"predicate": "inside", "arguments": ["mug", "shelf"]}
    unsafe = {"predicate": "safe", "arguments": [], "value": False}
    violating = explicit_skills_problem([skill_step("put", effects=[placed, unsafe])],
        initial_facts=[{"predicate": "safe", "arguments": []}],
        hard_constraints=[{"occurrence_id": "safety", "predicate": "safe", "arguments": []}])
    backend = ControlledMechanismBackend()
    assert backend.solve(problem=violating, context=context()).diagnostics == ("BLOCKED_CONSTRAINT_VIOLATION:safety",)
    missing_dependency = explicit_skills_problem([skill_step("put", effects=[placed])], remaining_goals=[
        {"occurrence_id": "target", "predicate": "inside", "arguments": ["mug", "shelf"],
         "dependency_ids": ["omitted-prerequisite"]}
    ])
    assert backend.solve(problem=missing_dependency, context=context()).diagnostics == ("BLOCKED_UNSATISFIED_DEPENDENCY:target",)


def test_abstract_goal_order_cannot_silently_discard_skill_semantics():
    goal = {"occurrence_id": "target", "predicate": "inside", "arguments": ["mug", "shelf"]}
    step = skill_step("put", effects=[])
    problem = compile_direct(directive(active_goal_occurrence_ids=["target"], remaining_goals=[goal],
                                       ordered_macro_plan=[step]))
    plan = ControlledMechanismBackend().solve(problem=problem, context=context())
    assert plan.status == "blocked"
    assert plan.diagnostics == ("BLOCKED_MACRO_SKILL_REQUIRES_EXPLICIT_MODE",)
    malformed_empty = compile_direct(directive(ordered_macro_plan=""))
    assert ControlledMechanismBackend().solve(problem=malformed_empty, context=context()).diagnostics == (
        "BLOCKED_UNSUPPORTED_MACRO_PLAN",
    )
