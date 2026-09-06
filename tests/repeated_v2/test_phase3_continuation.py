"""The frozen search is real; only public perception/verification are mocked."""

from dataclasses import dataclass, field
import json
from types import SimpleNamespace

import pytest

from cope_benchmark.repeated_v2.continuation_backend import (
    ContinuationBackendConfig, ContinuationPlannerBackend, PlannerBackendUnavailable,
    RecoveryGateBlocked, RecoveryVerification, UnsupportedPlanningSemantics,
)


@dataclass(frozen=True)
class NominalPlan:
    provider_id: str = 'test-nominal'
    result_kind: str = 'controlled_mechanism'
    problem_id: str = 'accepted-problem'
    planning_problem_sha256: str = '0' * 64
    status: str = 'planned'
    macro_actions: tuple = ({'target_occurrence_id': 'accepted-goal'},)
    diagnostics: dict = field(default_factory=dict)


class NominalPlanner:
    uses_hidden_truth = False

    def __init__(self):
        self.plan = NominalPlan()
        self.received = None

    def solve(self, *, problem, context):
        self.received = problem
        return self.plan


class PublicVerifier:
    uses_hidden_truth = False
    provider_id = 'mock_public_forward_model'

    def __init__(self, fail_goal=False, fail_restore=False):
        self.calls = []
        self.fail_goal, self.fail_restore = fail_goal, fail_restore

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        facts = dict(kwargs['observation'].abstract_flags)
        for name in kwargs['required_true']:
            facts[name] = True
        for name in kwargs['required_false']:
            facts[name] = False
        if self.fail_goal:
            facts['restore_valid'] = False
        final = (10.0, 10.0, 10.0) if self.fail_restore else kwargs['handoff_state']
        return RecoveryVerification(True, final, facts, 8)


def backend(**kwargs):
    return ContinuationPlannerBackend(nominal_backend=NominalPlanner(), verifier=PublicVerifier(**kwargs))


def flags(**updates):
    return {
        'nominal_suspended': False, 'ee_at_handoff': False,
        'orientation_restored': False, 'safe_clearance': True,
        'object_grasped': True, 'object_stable': False, 'obstacle_present': False,
        'target_changed': False, 'new_target_known': True,
        'aligned_to_current_target': False, 'restore_valid': False,
        **updates,
    }


def context(step=0, *, state=(0.0, 0.0, 0.0), values=None, ref=None, active='public-stage'):
    class Context:
        beliefs = (SimpleNamespace(key='repair_observation', value={
            'state': state, 'abstract_flags': flags() if values is None else values,
        }, timestamp=step, evidence_ids=(ref or f'observation-{step}',)),)
        continuation = SimpleNamespace(active_stage=active)

        @property
        def canonical_truth(self):
            raise AssertionError('hidden truth was accessed')
    return Context()


def problem(required_true=('restore_valid',), required_false=()):
    class AcceptedProblem:
        continuation_assumptions = {'repair': {'required_true': required_true, 'required_false': required_false}}

        @property
        def hidden_effect(self):
            raise AssertionError('hidden event effects were accessed')
    return AcceptedProblem()


def prepare(instance, accepted=None):
    instance.capture(context=context(), event_id='public-event')
    return instance.solve(problem=accepted or problem(), context=context(1))


def complete(instance, *, initial_step=1):
    facts = flags()
    for offset, stage in enumerate(instance.recovery_stages, 1):
        op = stage['operator']
        for key in {
            'Suspend': ('nominal_suspended',), 'Stabilize': ('object_stable',),
            'Realign': ('ee_at_handoff', 'orientation_restored'), 'Resume': ('restore_valid',),
        }[op]:
            facts[key] = True
        instance.complete_recovery_stage(stage_id=stage['stage_id'],
                                         context=context(initial_step + offset, values=facts))


def test_actual_package_search_verify_splice_resume_preserves_accepted_suffix():
    instance = backend()
    accepted = problem()
    plan = prepare(instance, accepted)
    assert instance.nominal_backend.received is accepted
    assert plan.macro_actions[-1]['target_occurrence_id'] == 'accepted-goal'
    assert len(plan.macro_actions) == len(instance.recovery_stages) + 1
    assert len(instance.verifier.calls) >= 1
    assert instance.audit['selected']
    assert len(instance.audit['package_sha256']) == 64
    assert instance._program.order_graph_consistent()
    with pytest.raises(RecoveryGateBlocked, match='locked'):
        instance.resumed_plan()
    complete(instance)
    assert instance.resumed_plan() is instance.nominal_backend.plan
    assert instance.audit['resumed'] is True


@pytest.mark.parametrize('failure', ['fail_goal', 'fail_restore'])
def test_verifier_ok_flag_cannot_bypass_actual_goal_or_handoff(failure):
    instance = backend(**{failure: True})
    with pytest.raises(RecoveryGateBlocked, match='no candidate'):
        prepare(instance)
    assert instance._program.in_repair is False


def test_restore_gate_rejects_public_success_at_wrong_pose():
    instance = backend()
    prepare(instance)
    facts = flags(nominal_suspended=True, object_stable=True, ee_at_handoff=True,
                  orientation_restored=True, restore_valid=True)
    for offset, stage in enumerate(instance.recovery_stages, 2):
        if stage['operator'] == 'Realign':
            with pytest.raises(RecoveryGateBlocked, match='handoff'):
                instance.complete_recovery_stage(stage_id=stage['stage_id'], context=context(offset, state=(3, 3, 3), values=facts))
            break
        instance.complete_recovery_stage(stage_id=stage['stage_id'], context=context(offset, values=facts))
    with pytest.raises(RecoveryGateBlocked):
        instance.resumed_plan()


def test_repeat_interruption_retains_the_frozen_program():
    instance = backend()
    prepare(instance)
    complete(instance)
    program = instance._program
    size = program.num_stages()
    stage = instance.audit['active_stage']
    instance.capture(context=context(10, active=stage), event_id='second-event')
    instance.solve(problem=problem(), context=context(11, active=stage))
    assert instance._program is program
    assert program.num_stages() > size
    assert program.order_graph_consistent()
    assert program._pending_continuation.event_id == 'second-event'


def test_missing_goal_remains_missing_and_no_implicit_repair_is_added():
    instance = backend()
    accepted = SimpleNamespace(continuation_assumptions={}, remaining_goals=())
    plan = instance.solve(problem=accepted, context=context())
    assert instance.nominal_backend.received is accepted
    assert plan is instance.nominal_backend.plan
    assert not instance.verifier.calls


@pytest.mark.parametrize('requirements', [('unmodeled_physical_requirement',), ()])
def test_unsupported_or_omitted_restore_requirements_fail_closed(requirements):
    instance = backend()
    with pytest.raises(UnsupportedPlanningSemantics):
        prepare(instance, problem(required_true=requirements))


def test_capture_and_fresh_post_event_evidence_are_mandatory():
    instance = backend()
    with pytest.raises(RecoveryGateBlocked, match='capture'):
        instance.solve(problem=problem(), context=context(1))
    instance.capture(context=context(0), event_id='event')
    with pytest.raises(RecoveryGateBlocked, match='fresh evidence'):
        instance.solve(problem=problem(), context=context(0))
    # Event injection need not advance the simulator clock, but must produce a
    # genuinely new observation record.
    plan = instance.solve(problem=problem(), context=context(0, ref='fresh-after-injection'))
    assert plan.macro_actions[0]['recovery'] is True


def test_unknown_public_fields_and_implicit_boolean_facts_are_rejected():
    instance = backend()
    poisoned = context()
    poisoned.beliefs[0].value['canonical_truth'] = {'do_not_read': True}
    with pytest.raises(UnsupportedPlanningSemantics):
        instance.capture(context=poisoned, event_id='event')
    bad_facts = flags(object_grasped=1)
    with pytest.raises(UnsupportedPlanningSemantics, match='booleans'):
        instance.capture(context=context(values=bad_facts), event_id='event')


def test_dependency_and_truth_capabilities_fail_closed(tmp_path):
    with pytest.raises(PlannerBackendUnavailable, match='BLOCKED_CONTINUATION'):
        ContinuationPlannerBackend(nominal_backend=NominalPlanner(), verifier=PublicVerifier(),
                                   config=ContinuationBackendConfig(package_root=str(tmp_path)))
    privileged = PublicVerifier()
    privileged.uses_hidden_truth = True
    with pytest.raises(PlannerBackendUnavailable, match='truth exclusion'):
        ContinuationPlannerBackend(nominal_backend=NominalPlanner(), verifier=privileged)


def test_stage_completion_is_in_order_and_uses_fresh_observations():
    instance = backend()
    plan = prepare(instance)
    with pytest.raises(RecoveryGateBlocked, match='current'):
        instance.complete_recovery_stage(stage_id=plan.macro_actions[-2]['stage_id'], context=context(3))
    with pytest.raises(RecoveryGateBlocked, match='fresh'):
        instance.complete_recovery_stage(stage_id=plan.macro_actions[0]['stage_id'], context=context(1))


def test_crash_resume_preserves_selected_program_without_verifier_replay():
    instance = backend()
    plan = prepare(instance)
    first = plan.macro_actions[0]
    instance.before_macro(first)
    instance.complete_recovery_stage(stage_id=first['stage_id'], context=context(2, values=flags(nominal_suspended=True)))
    with pytest.raises(RecoveryGateBlocked, match='locked'):
        instance.before_macro(plan.macro_actions[-1])
    snapshot = instance.snapshot()
    restored = backend()
    restored.restore(snapshot, plan_factory=NominalPlan)
    assert not restored.verifier.calls
    assert restored._program.active_id() == instance._program.active_id()
    assert restored.snapshot() == snapshot
    with pytest.raises(RecoveryGateBlocked, match='current'):
        restored.before_macro(first)
    damaged = dict(snapshot)
    damaged['last_observation_step'] = 99
    with pytest.raises(RecoveryGateBlocked, match='integrity'):
        backend().restore(damaged, plan_factory=NominalPlan)


def test_phase2_execution_plan_record_compatibility_and_restore():
    # Use the actual strict immutable phase-2 record: a shape-compatible fixture
    # alone would miss invalid diagnostics elements and serialization failures.
    from cope_benchmark.repeated_v2.planner_backend import ExecutionPlan

    instance = backend()
    instance.nominal_backend.plan = ExecutionPlan(
        provider_id='test-nominal', result_kind='controlled_mechanism',
        problem_id='accepted-problem', planning_problem_sha256='0' * 64,
        status='planned', macro_actions=({'target_occurrence_id': 'accepted-goal'},),
        diagnostics=('original-planner-diagnostic',))
    plan = prepare(instance)
    assert type(plan) is ExecutionPlan
    assert plan.diagnostics[0] == 'original-planner-diagnostic'
    assert json.loads(plan.diagnostics[-1])['continuation_repair']['selected']
    assert len(plan.sha256) == 64
    assert ExecutionPlan.from_dict(plan.to_dict()) == plan
    assert plan.macro_actions[-1] == instance.nominal_backend.plan.macro_actions[-1]
    snapshot = instance.snapshot()
    restored = backend()
    restored.restore(snapshot)
    assert type(restored._nominal_plan) is ExecutionPlan
    assert restored._nominal_plan == instance.nominal_backend.plan
    assert restored.snapshot() == snapshot
    assert not restored.verifier.calls
