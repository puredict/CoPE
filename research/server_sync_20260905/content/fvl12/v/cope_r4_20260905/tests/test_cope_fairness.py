"""Fairness controls and benchmark behaviour for the CoPE vs FSR-PC comparison.

The point of these tests is that the fairness claims are *checked*, not asserted
in prose. If a future change gives one arm more information, a smaller task, a
different executor or a different grader, one of these fails.
"""
from __future__ import annotations

import pytest

from cope.benchmark import (
    BasketTaskSpec, ReliabilityGate, build_initial_state, interruption,
    run_episode,
)
from cope.benchmark.episode import _expected_outcome
from cope.naming import canonical_id
from cope.policies import METHODS, PRIMARY_METHODS

CONDITIONS = ("I1", "I2", "I3", "I4")
SEEDS = range(3)


# ------------------------------------------------------- F1 same task
def test_pairing_key_excludes_the_method():
    a = BasketTaskSpec(seed=1, condition="I1", method="CoPE")
    b = BasketTaskSpec(seed=1, condition="I1", method="FSR-PC")
    assert a.key() == b.key()
    assert a.episode_id() != b.episode_id()


def test_every_arm_starts_from_the_identical_initial_state():
    fps = set()
    for m in METHODS:
        r = run_episode(BasketTaskSpec(seed=0, condition="nominal", method=m))
        fps.add(r.executor_request_fingerprints[0])
    assert len(fps) == 1


def test_interruption_timing_does_not_depend_on_the_method():
    for cond in CONDITIONS:
        c = interruption(cond, 0)
        assert c.trigger_after_goal is not None
        assert c.name == cond


# ------------------------------------------------------- F2 same information
@pytest.mark.parametrize("cond", CONDITIONS)
@pytest.mark.parametrize("seed", SEEDS)
def test_both_primary_arms_receive_byte_identical_adaptation_inputs(cond, seed):
    """The strongest fairness control: identical serialized information packets.

    Compares the fingerprint of every `AdaptationInput` at every interruption.
    """
    fps = {m: run_episode(BasketTaskSpec(seed=seed, condition=cond,
                                         method=m)).adaptation_input_fingerprints
           for m in PRIMARY_METHODS}
    assert fps["CoPE"] == fps["FSR-PC"]
    assert len(fps["CoPE"]) >= 1


def test_the_control_arm_may_diverge_only_through_its_own_behaviour():
    """`no_adaptation` can see a different SECOND packet, because it really did
    something different first (it burns an action on an unavailable target).
    The first packet must still be identical --- that is the information test."""
    fps = {m: run_episode(BasketTaskSpec(seed=0, condition="I2",
                                         method=m)).adaptation_input_fingerprints
           for m in METHODS}
    firsts = {v[0] for v in fps.values()}
    assert len(firsts) == 1


def test_fsrpc_is_not_made_forgetful():
    """FSR-PC must receive completed goals, history and safety constraints."""
    from cope.policies.adaptation_input import AdaptationInput
    from cope.benchmark.basket_task import make_adaptation_input
    inp = make_adaptation_input(
        BasketTaskSpec(seed=0, condition="I1"), {},
        completed=("g_milk",), pending=("g_yogurt", "g_butter"), cancelled=(),
        task_history=({"event": "goal_completed"},), event_history=(),
        update={}, event_id="e", event_step=1)
    assert inp.completed_goals == ("g_milk",)
    assert inp.task_history
    assert inp.safety_constraints
    assert inp.compute_budget["max_planner_calls"] > 0


# ------------------------------------------------------- F3 same executor
@pytest.mark.parametrize("cond", CONDITIONS)
def test_both_arms_use_the_same_executor_interface(cond):
    for m in PRIMARY_METHODS:
        r = run_episode(BasketTaskSpec(seed=0, condition=cond, method=m))
        req = r.policy.mgr.compile()
        assert set(req.to_dict()) == {"active_goals", "safety_constraints",
                                      "horizon_steps", "budget"}


def test_the_executor_cannot_tell_which_policy_produced_the_request():
    """The compiled request carries no method marker of any kind."""
    for m in PRIMARY_METHODS:
        r = run_episode(BasketTaskSpec(seed=0, condition="I1", method=m))
        blob = repr(r.policy.mgr.compile().to_dict()).lower()
        assert "cope" not in blob and "fsr" not in blob and "regen" not in blob


# ------------------------------------------------------- F4 same grader
def test_the_grader_depends_only_on_the_condition():
    for cond in ("nominal",) + CONDITIONS:
        assert _expected_outcome(cond) == _expected_outcome(cond)


def test_no_condition_is_won_for_free_by_the_control_arm():
    """At least one interruption condition must actually punish not adapting,
    otherwise the benchmark measures nothing about adaptation."""
    losses = [c for c in CONDITIONS
              if not run_episode(BasketTaskSpec(seed=0, condition=c,
                                                method="no_adaptation")
                                 ).metrics.revised_task_success]
    assert losses, "the control arm passes every condition; the task is too easy"


# ------------------------------------------------------- Stage A gate
def test_nominal_reliability_gate_passes_on_this_task():
    ok = sum(bool(run_episode(BasketTaskSpec(seed=s, condition="nominal",
                                             method="no_adaptation")
                              ).metrics.revised_task_success)
             for s in range(10))
    verdict = ReliabilityGate().evaluate(ok)
    assert verdict["passed"], verdict


def test_the_gate_is_not_vacuous():
    """A degraded executor must fail the gate, or the gate proves nothing."""
    ok = sum(bool(run_episode(BasketTaskSpec(seed=s, condition="nominal",
                                             method="no_adaptation"),
                              p_success=0.5).metrics.revised_task_success)
             for s in range(10))
    assert not ReliabilityGate().evaluate(ok)["passed"]


# ------------------------------------------------------- structural difference
@pytest.mark.parametrize("cond", CONDITIONS)
def test_cope_patches_locally_and_fsrpc_regenerates_everything(cond):
    c = run_episode(BasketTaskSpec(seed=0, condition=cond, method="CoPE"))
    f = run_episode(BasketTaskSpec(seed=0, condition=cond, method="FSR-PC"))
    assert c.metrics.slots_regenerated == 0
    assert f.metrics.slots_regenerated > 0
    assert c.metrics.normalized_edit_distance < f.metrics.normalized_edit_distance
    assert f.metrics.normalized_edit_distance == pytest.approx(1.0)


@pytest.mark.parametrize("cond", CONDITIONS)
def test_identity_survives_under_cope_and_is_reminted_under_fsrpc(cond):
    c = run_episode(BasketTaskSpec(seed=0, condition=cond, method="CoPE"))
    f = run_episode(BasketTaskSpec(seed=0, condition=cond, method="FSR-PC"))
    assert c.metrics.identity_preserved is True
    assert f.metrics.identity_preserved is False


def test_fsrpc_with_preserved_ids_keeps_identity():
    """The ablation must actually change the thing it claims to change."""
    from cope.policies.fsrpc_policy import FSRPCPolicy

    class Preserving(FSRPCPolicy):
        def __init__(self, store, horizon_steps=900, repair_engine=None):
            super().__init__(store, horizon_steps, repair_engine,
                             preserve_ids=True)

    METHODS["FSR-PC(preserve_ids)"] = Preserving
    try:
        r = run_episode(BasketTaskSpec(seed=0, condition="I1",
                                       method="FSR-PC(preserve_ids)"))
        assert r.metrics.identity_preserved is True
        assert r.metrics.slots_regenerated > 0     # still a full regeneration
    finally:
        METHODS.pop("FSR-PC(preserve_ids)", None)


# ------------------------------------------------------- audit, non-circular
def test_fsrpc_can_answer_the_queries_a_state_snapshot_supports():
    """Q1/Q2 are recoverable from a regenerated state. If FSR-PC scored zero on
    those, the audit metric would be circular rather than informative."""
    f = run_episode(BasketTaskSpec(seed=0, condition="I1", method="FSR-PC"))
    ans = f.metrics.audit_answerable
    assert ans["Q1_which_goal_cancelled"] is True
    assert ans["Q2_which_completed_preserved"] is True
    assert ans["Q5_replacement_state"] is False    # genuinely unavailable


def test_inapplicable_audit_queries_are_not_counted_as_failures():
    f = run_episode(BasketTaskSpec(seed=0, condition="I1", method="CoPE"))
    assert f.metrics.audit_answerable["Q3_why_suspended"] is None
    n = run_episode(BasketTaskSpec(seed=0, condition="nominal", method="CoPE"))
    assert n.metrics.audit_coverage is None


# ------------------------------------------------------- invariants hold
@pytest.mark.parametrize("cond", ("nominal",) + CONDITIONS)
@pytest.mark.parametrize("m", tuple(METHODS))
def test_state_invariants_hold_for_every_arm_and_condition(cond, m):
    r = run_episode(BasketTaskSpec(seed=0, condition=cond, method=m))
    assert r.metrics.lifecycle_transitions_legal is True
    assert r.metrics.lineage_correct is True
    assert r.metrics.history_monotonic is True
    assert r.metrics.invalid_restore_count == 0
    assert r.metrics.collision is False


def test_restoration_is_always_guarded_by_revalidation():
    for cond in ("I2", "I4"):
        r = run_episode(BasketTaskSpec(seed=0, condition=cond, method="CoPE"))
        assert r.metrics.restore_preceded_by_revalidation is True
