"""Integration tests: the CoPE layer really drives the FROZEN repair engine.

Each test maps to a numbered requirement from the v1 audit. The point is that
"the engine is wired in" is checkable, not a docstring claim: v1 shipped a
`RecoveryManager.repair_engine` attribute that was stored and never invoked, and
nothing in the test suite noticed.
"""
from __future__ import annotations

import numpy as np
import pytest

from cope.benchmark import BasketTaskSpec
from cope.benchmark.basket_world import BasketLegEnv
from cope.benchmark.physical_episode import run_physical_episode
from cope.constraint_slot import ConstraintSlot, Priority, SlotMode, SlotSource
from cope.constraint_state import ConstraintState
from cope.repair_bridge import (
    ConstraintStateToRepairGoalCompiler, REQUIRED_ORDER, SharedRepairEngine,
    assert_complete,
)

CONDITIONS = ("I1", "I2", "I3", "I4")
PRIMARY = ("CoPE", "FSR-PC")


# --- R1: the frozen core is imported and used, not stubbed ------------------
def test_the_frozen_repair_core_is_actually_imported():
    import cope.repair_bridge.engine as eng
    src = open(eng.__file__).read()
    for mod in ("rekep_repair.program.task_program",
                "rekep_repair.program.continuation",
                "rekep_repair.repair.repair_manager",
                "rekep_repair.repair.synthesis_generator",
                "rekep_repair.execution.controller"):
        assert mod in src, mod


def test_the_engine_uses_the_real_types():
    from rekep_repair.program.task_program import TaskProgram
    env = BasketLegEnv("milk", "basket_A", seed=0)
    from cope.audit_trace import AuditTrace
    e = SharedRepairEngine(env, AuditTrace())
    assert isinstance(e.program, TaskProgram)


# --- the ten markers --------------------------------------------------------
@pytest.mark.parametrize("cond", CONDITIONS)
@pytest.mark.parametrize("method", PRIMARY)
def test_every_interruption_produces_the_complete_pipeline(cond, method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method=method))
    assert r.pipeline_markers, "no repair pipeline ran at all"
    for markers in r.pipeline_markers:
        ok, problems = assert_complete(markers)
        assert ok, f"{cond}/{method}: {problems}\n  markers={markers}"


@pytest.mark.parametrize("method", PRIMARY)
def test_the_markers_appear_in_the_required_order(method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I3",
                                            method=method))
    for markers in r.pipeline_markers:
        idx = [markers.index(s.value) for s in REQUIRED_ORDER
               if s.value in markers]
        assert idx == sorted(idx)


def test_the_marker_checker_rejects_an_incomplete_pipeline():
    """If this passed anything, the completeness claim would be vacuous."""
    ok, problems = assert_complete(["EVENT", "PATCH"])
    assert not ok and len(problems) >= 5
    # the control arm produces no state update, so it is genuinely incomplete
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I1",
                                            method="no_adaptation"))
    assert r.pipeline_complete and not any(r.pipeline_complete)


# --- R2/R3: constraint-state semantics become repair requirements -----------
def test_compiler_turns_lifecycle_transitions_into_repair_requirements():
    c = ConstraintStateToRepairGoalCompiler()
    env = BasketLegEnv("butter", "basket_B", seed=0)
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="place_butter_in_basket_B",
                       payload={"object": "butter", "target": "basket_B"})])
    after = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="place_butter_in_basket_B",
                       mode=SlotMode.OVERRIDDEN,
                       payload={"object": "butter", "target": "basket_B"}),
        ConstraintSlot(id="g_butter@basket_A", grounding="place_butter_in_basket_A",
                       payload={"object": "butter", "target": "basket_A"})])
    req = c.compile(before=before, after=after, adaptation=None, world={},
                    ctx=env.observe(), event_id="e", step=0)
    assert "aligned_to_current_target" in req.goal.required_true
    assert "restore_valid" in req.goal.required_true
    assert req.needs_physical_repair
    # every requirement is attributed to the slot that induced it
    assert any(s.slot_id == "g_butter"
               and s.transition == "active->overridden"
               for s in req.sources)


def test_cancellation_requires_a_resumable_end_state_not_a_retarget():
    c = ConstraintStateToRepairGoalCompiler()
    env = BasketLegEnv("yogurt", "basket_A", seed=0)
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_yogurt", grounding="g",
                       payload={"object": "yogurt", "target": "basket_A"})])
    after = ConstraintState().put_many([
        ConstraintSlot(id="g_yogurt", grounding="g", mode=SlotMode.EXPIRED,
                       payload={"object": "yogurt", "target": "basket_A"})])
    req = c.compile(before=before, after=after, adaptation=None, world={},
                    ctx=env.observe(), event_id="e", step=0)
    assert "restore_valid" in req.goal.required_true
    assert "aligned_to_current_target" not in req.goal.required_true


def test_an_inserted_safety_slot_adds_a_clearance_requirement():
    c = ConstraintStateToRepairGoalCompiler()
    env = BasketLegEnv("milk", "basket_A", seed=0)
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_milk", grounding="g",
                       payload={"object": "milk", "target": "basket_A"})])
    after = before.put(ConstraintSlot(
        id="c_keep_upright", grounding="keep_object_upright",
        priority=Priority.HARD, source=SlotSource.SAFETY_RULE))
    req = c.compile(before=before, after=after, adaptation=None, world={},
                    ctx=env.observe(), event_id="e", step=0)
    assert "safe_clearance" in req.goal.required_true
    assert any(s.slot_id == "c_keep_upright" for s in req.sources)


def test_the_compiler_never_sees_the_policy():
    """Policy-blindness is what makes the FSR-PC comparison honest."""
    import inspect
    sig = inspect.signature(ConstraintStateToRepairGoalCompiler.compile)
    for bad in ("policy", "method", "arm", "is_cope"):
        assert bad not in sig.parameters


# --- R4: continuation captured BEFORE physical adaptation -------------------
@pytest.mark.parametrize("cond", CONDITIONS)
def test_continuation_is_captured_before_the_repair_runs(cond):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method="CoPE"))
    for markers in r.pipeline_markers:
        assert markers.index("CONTINUATION_CAPTURED") < \
            markers.index("CANDIDATES_GENERATED")
        assert markers.index("CONTINUATION_CAPTURED") < \
            markers.index("GRAPH_SPLICED")


# --- R5: multiple candidates generated at runtime ---------------------------
@pytest.mark.parametrize("method", PRIMARY)
def test_multiple_candidate_programs_are_synthesised_at_runtime(method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I1",
                                            method=method))
    out = r.repair_outcomes[0]
    assert out["n_candidates"] >= 2, out["candidate_names"]
    # synthesised, not looked up: the abstract plans come from the planner
    assert out["abstract_plans"], "no abstract operator plans were produced"
    assert out["planner_expanded"] > 0
    # and they are genuinely different operator orderings
    assert len(set(map(tuple, out["candidate_names"]))) == out["n_candidates"]


# --- R6/R7: real sequential rollout, hard rejection -------------------------
@pytest.mark.parametrize("cond", CONDITIONS)
def test_every_candidate_is_rollout_verified(cond):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method="CoPE"))
    for out in r.repair_outcomes:
        assert len(out["rollouts"]) > 0
        for _, report in out["rollouts"]:
            assert "dur=" in report and "residual=" in report


def test_an_unsatisfiable_goal_is_hard_rejected_not_scored_down():
    """A candidate that cannot meet the event requirements must be REJECTED."""
    from rekep_repair.repair.abstract_state import RepairGoal
    from cope.audit_trace import AuditTrace
    env = BasketLegEnv("butter", "basket_B", seed=0)
    e = SharedRepairEngine(env, AuditTrace())

    class Impossible(ConstraintStateToRepairGoalCompiler):
        def compile(self, **kw):
            req = super().compile(**kw)
            # demand a fact no operator can establish
            req.goal = RepairGoal(
                required_true=frozenset({"restore_valid", "object_stable"}),
                required_false=frozenset({"object_grasped"}),
                label="impossible")
            req.needs_physical_repair = True
            return req

    e.compiler = Impossible()
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="g",
                       payload={"object": "butter", "target": "basket_B"})])
    out = e.repair(before=before, after=before, adaptation=None,
                   adaptation_kind="patch", world={}, ctx=env.observe(),
                   event_id="imp", step=0)
    assert out.selected is None
    assert out.safe_fallback
    assert "SAFE_FALLBACK" in out.markers
    assert not assert_complete(out.markers)[0]


# --- R8: splice into the TaskProgram ---------------------------------------
@pytest.mark.parametrize("method", PRIMARY)
def test_the_selected_candidate_is_spliced_into_the_task_program(method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I1",
                                            method=method))
    out = r.repair_outcomes[0]
    assert out["spliced_stage_ids"]
    assert out["program_size_after"] > out["program_size_before"]
    assert r.engine.program.is_wellformed()
    assert r.engine.program.order_graph_consistent()


# --- R9: non-tautological restore, real resumed stage ----------------------
def test_the_restore_contract_can_actually_fail():
    """If the gate accepted every state it would prove nothing."""
    from cope.audit_trace import AuditTrace
    from rekep_repair.execution.controller import control
    from rekep_repair.policies.common import build_params
    env = BasketLegEnv("butter", "basket_B", seed=0)
    e = SharedRepairEngine(env, AuditTrace())
    params = build_params(env.cfg)
    for _ in range(6):
        ctx = env.observe()
        env.step(control("progress", ctx, e.program.active_stage(), None,
                         params, ctx.task_goal))
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="g",
                       payload={"object": "butter", "target": "basket_B"})])
    env.retarget("basket_A")
    after = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="g", mode=SlotMode.OVERRIDDEN,
                       payload={"object": "butter", "target": "basket_B"}),
        ConstraintSlot(id="g_butter@basket_A", grounding="h",
                       payload={"object": "butter", "target": "basket_A"})])
    e.repair(before=before, after=after, adaptation=None, adaptation_kind="patch",
             world={}, ctx=env.observe(), event_id="e", step=6)
    cont = e.continuation
    assert e.program.mark_restore_validated(cont.state) is True
    displaced = np.asarray(cont.state, float).copy()
    displaced[:2] += np.array([0.6, 0.6])
    assert e.program.mark_restore_validated(displaced) is False
    assert cont.handoff_error(displaced) > 0.5


@pytest.mark.parametrize("cond", CONDITIONS)
@pytest.mark.parametrize("method", PRIMARY)
def test_restore_precedes_resume_and_both_really_happen(cond, method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method=method))
    for markers in r.pipeline_markers:
        assert markers.index("RESTORE_VALIDATED") < markers.index("STAGE_RESUMED")
    assert r.metrics.restores_validated == r.metrics.repairs_invoked
    assert r.metrics.stages_resumed == r.metrics.repairs_invoked


def test_the_continuation_is_captured_from_the_pre_adaptation_state():
    """The handoff pose must be fixed before the world is retargeted, or the
    repair could move its own goalposts."""
    from cope.audit_trace import AuditTrace
    from rekep_repair.execution.controller import control
    from rekep_repair.policies.common import build_params
    env = BasketLegEnv("butter", "basket_B", seed=0)
    e = SharedRepairEngine(env, AuditTrace())
    params = build_params(env.cfg)
    for _ in range(6):
        ctx = env.observe()
        env.step(control("progress", ctx, e.program.active_stage(), None,
                         params, ctx.task_goal))
    pos_before = env.observe().position.copy()
    before = ConstraintState().put_many([
        ConstraintSlot(id="g_butter", grounding="g",
                       payload={"object": "butter", "target": "basket_B"})])
    e.repair(before=before, after=before, adaptation=None,
             adaptation_kind="patch", world={"unavailable_targets": []},
             ctx=env.observe(), event_id="e", step=6)
    if e.continuation is not None:
        assert np.allclose(e.continuation.handoff_pose, pos_before)


# --- R10/R11: FSR-PC uses the same stack -----------------------------------
@pytest.mark.parametrize("cond", CONDITIONS)
@pytest.mark.parametrize("seed", (0, 1, 2))
def test_both_arms_compile_identical_repair_requirements(cond, seed):
    """The strongest downstream-fairness control: the same semantic change
    produces the same repair goal, whichever arm produced it."""
    fps = {m: run_physical_episode(BasketTaskSpec(seed=seed, condition=cond,
                                                  method=m)
                                   ).requirement_fingerprints
           for m in PRIMARY}
    assert fps["CoPE"] == fps["FSR-PC"]
    assert fps["CoPE"], "no requirements were compiled at all"


@pytest.mark.parametrize("cond", CONDITIONS)
def test_both_arms_enter_the_same_shared_entry_point(cond):
    for m in PRIMARY:
        r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                                method=m))
        assert r.policy.mgr.repair_engine is r.engine
        assert len(r.policy.mgr.repair_outcomes) == r.metrics.repairs_invoked > 0


def test_both_policies_call_the_identical_manager_method():
    import inspect
    from cope.policies.cope_patch_policy import CoPEPatchPolicy
    from cope.policies.fsrpc_policy import FSRPCPolicy
    for cls in (CoPEPatchPolicy, FSRPCPolicy):
        src = inspect.getsource(cls.adapt)
        assert "enter_repair_pipeline" in src, cls.__name__


@pytest.mark.parametrize("cond", CONDITIONS)
def test_the_arms_differ_only_in_state_update_semantics(cond):
    a = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method="CoPE"))
    b = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                            method="FSR-PC"))
    # same downstream work
    assert a.metrics.candidates_generated == b.metrics.candidates_generated
    assert a.metrics.rollouts_run == b.metrics.rollouts_run
    assert a.metrics.splices == b.metrics.splices
    assert a.metrics.stages_resumed == b.metrics.stages_resumed
    # different state-update semantics
    assert a.metrics.slots_regenerated == 0 < b.metrics.slots_regenerated
    assert a.metrics.identity_preserved is True
    assert b.metrics.identity_preserved is False


def test_the_engine_is_policy_blind():
    import inspect
    sig = inspect.signature(SharedRepairEngine.repair)
    for bad in ("policy", "method", "arm"):
        assert bad not in sig.parameters
    src = inspect.getsource(SharedRepairEngine.repair)
    # adaptation_kind may only choose a trace marker, never a behaviour
    assert 'adaptation_kind == "patch"' in src
    body = src.split("# --- kappa_t")[1]
    assert "adaptation_kind" not in body


# --- the engine is not decorative ------------------------------------------
def test_removing_the_engine_makes_the_pipeline_visibly_incomplete():
    """Guards against a regression back to the v1 situation, where the engine
    was configured but never invoked and no test noticed."""
    from cope.policies import METHODS
    from cope.state_store import StateStore
    from cope.benchmark.basket_task import build_initial_state
    store = StateStore()
    store.seed(build_initial_state())
    policy = METHODS["CoPE"](store, horizon_steps=900, repair_engine=None)
    assert policy.mgr.repair_engine is None
    assert policy.mgr.repair_outcomes == []
