"""Operator-synthesis tests: the planner must CONSTRUCT sequences under
event-conditioned goals, with physically valid operator semantics."""

from __future__ import annotations

import numpy as np
import pytest

from rekep_repair.execution.executor import Executor
from rekep_repair.policies import OnlineRepairPolicy, TemplateRepairPolicy
from rekep_repair.repair.abstract_state import (
    SYMBOLIC_OPS,
    WorldPredicates,
    goal_from_predicates,
    state_from_predicates,
)
from rekep_repair.repair.planner import RepairPlanner
from rekep_repair.repair.template_library import TEMPLATES
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def _apply(plan, init):
    s = init
    for name in plan:
        op = SYMBOLIC_OPS[name]
        assert op.precondition(s), f"{name} precondition violated in {s.true_flags()}"
        s = op.effect(s)
    return s


def _plan_for(**kw):
    p = WorldPredicates(**kw)
    init, goal = state_from_predicates(p), goal_from_predicates(p)
    return init, goal, RepairPlanner().plan(init, goal, k=3)


def test_obstacle_plan_satisfies_event_goal():
    init, goal, res = _plan_for(obstacle_present=True, unsafe_clearance=True)
    assert res.goal_reached
    assert goal.satisfied_by(_apply(res.best, init))
    assert res.n_expanded > 1                      # it actually searched


def test_slip_plan_stabilizes_only_after_regrasp():
    """P0: a released object cannot be stabilized by the gripper."""
    init, goal, res = _plan_for(object_slipped=True)
    plan = res.best
    assert goal.satisfied_by(_apply(plan, init))
    assert plan.index("ReacquireTarget") < plan.index("Stabilize")


def test_stabilize_inapplicable_while_ungrasped():
    p = WorldPredicates(object_slipped=True)
    s = SYMBOLIC_OPS["Suspend"].effect(state_from_predicates(p))
    assert not s.object_grasped
    assert not SYMBOLIC_OPS["Stabilize"].applicable(s), \
        "Stabilize must require object_grasped"


def test_relocation_requires_target_contract_update():
    init, goal, res = _plan_for(target_relocated=True)
    plan = res.best
    assert "UpdateTargetContract" in plan
    assert goal.satisfied_by(_apply(plan, init))
    assert "aligned_to_current_target" in goal.required_true


def test_compound_goal_is_union_and_plan_is_not_a_template():
    init, goal, res = _plan_for(obstacle_present=True, unsafe_clearance=True,
                                object_slipped=True)
    plan = res.best
    assert goal.satisfied_by(_apply(plan, init))
    assert {"safe_clearance", "object_grasped", "object_stable"} <= goal.required_true
    assert "obstacle_present" in goal.required_false
    stored = {tuple(t) for ts in TEMPLATES.values() for t in ts}
    assert tuple(plan) not in stored


def test_unresolved_requirements_are_detected_as_residual():
    """A plan that ignores an active requirement must show a residual."""
    p = WorldPredicates(object_slipped=True)
    init, goal = state_from_predicates(p), goal_from_predicates(p)
    # a plan that never reacquires leaves object_grasped unmet
    partial = _apply(("Suspend",), init)
    assert goal.residual(partial), "must report unmet requirements"
    assert "object_grasped" in goal.residual(partial)


def test_wait_requires_clearance_no_implicit_retreat():
    init, goal, res = _plan_for(obstacle_present=True, unsafe_clearance=True)
    suspended = SYMBOLIC_OPS["Suspend"].effect(init)
    assert not SYMBOLIC_OPS["WaitUntilClear"].applicable(suspended)
    plan = res.best
    assert plan.index("Retreat") < plan.index("WaitUntilClear")


def test_wait_needs_no_gripper_stabilization_when_object_released():
    """Physical semantics: a released, stationary object needs no gripper hold."""
    p = WorldPredicates(obstacle_present=True, unsafe_clearance=True, object_slipped=True)
    s = state_from_predicates(p)
    s = SYMBOLIC_OPS["Suspend"].effect(s)
    s = SYMBOLIC_OPS["Retreat"].effect(s)
    assert not s.object_grasped and not s.object_stable
    assert SYMBOLIC_OPS["WaitUntilClear"].applicable(s)


def _compound_cfg():
    return SceneConfig(
        p_init=np.array([0.2, 0.0]), slip_time=2, drop_offset=np.array([0.18, 0.03]),
        obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]), 0.12, 2, 40),
    )


def _safe_delivery(env, cfg, report) -> bool:
    return bool(env.grasped
                and np.linalg.norm(env.state[:2] - env.goal) < cfg.eps_goal
                and not report["collided"])


def test_compound_event_online_delivers_template_does_not():
    cfg = _compound_cfg()
    e1 = Synthetic2DEnv(cfg, seed=0)
    r1 = Executor(e1).run(OnlineRepairPolicy()).report()
    e2 = Synthetic2DEnv(cfg, seed=0)
    r2 = Executor(e2).run(TemplateRepairPolicy()).report()
    assert _safe_delivery(e1, cfg, r1), "synthesis should safely deliver"
    assert not _safe_delivery(e2, cfg, r2), "template instantiation should not"


def test_repeated_repairs_graph_stays_consistent():
    cfg = SceneConfig(slip_time=40, drop_offset=np.array([0.0, -0.20]))
    pol = OnlineRepairPolicy()
    Executor(Synthetic2DEnv(cfg, seed=0)).run(pol)
    assert pol.program.order_graph_consistent()
    assert len(pol.program._order) == len(set(pol.program._order))
