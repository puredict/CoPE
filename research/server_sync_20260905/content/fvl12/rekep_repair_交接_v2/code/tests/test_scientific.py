"""Scientific-validity tests: relocation correctness, hard rejection of
unresolved requirements, rollout catching collision/timeout, state-dependent
selection, repeated repairs, events during repair, symmetric predicates."""

from __future__ import annotations

import numpy as np
import pytest

from rekep_repair.events.event import Event, EventType
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import (
    OfflineComprehensivePolicy,
    OfflineSingleEventCoveragePolicy,
    OnlineRepairPolicy,
)
from rekep_repair.policies.common import build_params, resume_contract
from rekep_repair.program.continuation import Continuation
from rekep_repair.program.stage import Mode
from rekep_repair.repair.abstract_state import (
    WorldPredicates,
    goal_from_predicates,
    state_from_predicates,
)
from rekep_repair.repair.feasibility_filter import ControlLimits
from rekep_repair.repair.repair_manager import RepairManager
from rekep_repair.repair.rollout_verifier import RolloutVerifier
from rekep_repair.repair.synthesis_generator import SynthesisGenerator
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv

FAR = Obstacle(np.array([9.0, 9.0]), np.array([9.0, 9.0]), 0.05, 0, 0)


# --- P0: target relocation --------------------------------------------------
def _reloc_cfg():
    return SceneConfig(relocation_time=6, relocation_delta=np.array([0.0, 0.30]),
                       obstacle=FAR)


def test_relocation_reaches_moved_goal_not_stale_goal():
    cfg = _reloc_cfg()
    env = Synthetic2DEnv(cfg, seed=0)
    rep = Executor(env).run(OnlineRepairPolicy()).report()
    assert rep["success"], "must succeed against the RELOCATED goal"
    assert rep["goal_error"] <= cfg.eps_goal
    # and it must NOT be sitting at the original goal
    assert rep["stale_goal_error"] > cfg.eps_goal
    assert np.linalg.norm(env.state[:2] - env.goal) <= cfg.eps_goal


def test_relocation_metrics_use_current_world_goal():
    cfg = _reloc_cfg()
    env = Synthetic2DEnv(cfg, seed=0)
    res = Executor(env).run(OnlineRepairPolicy())
    assert np.allclose(res.rollout.goal(), env.goal)
    assert not np.allclose(res.rollout.goal(), cfg.p_goal)


def test_relocation_goal_requires_target_contract():
    p = WorldPredicates(target_relocated=True)
    goal = goal_from_predicates(p)
    assert "aligned_to_current_target" in goal.required_true
    assert "restore_valid" in goal.required_true


# --- P0: hard rejection of unresolved requirements --------------------------
def _cont(handoff=(0.12, 0.0), cfg=None):
    cfg = cfg or SceneConfig()
    h = np.array(handoff, float)
    return Continuation(
        interrupted_stage_id="pour", stage_mode=Mode.POUR,
        state=np.array([h[0], h[1], cfg.theta_pour]),
        ee_pose=np.array([h[0], h[1], cfg.theta_pour]),
        attachment_state={"object": "grasped"}, nominal_target=cfg.p_goal,
        resume_contract=resume_contract(h, cfg.theta_pour),
        handoff_pose=h, timestamp=2, event_id="E-test",
    )


def test_candidate_with_unresolved_requirements_is_rejected():
    """A candidate that leaves an active requirement unmet must be REJECTED,
    not merely penalized."""
    cfg = SceneConfig()
    params = build_params(cfg, handoff_pose=np.array([0.12, 0.0]))
    limits = ControlLimits(cfg.v_max, cfg.w_max, cfg.ws_lo, cfg.ws_hi)
    cont = _cont(cfg=cfg)
    # slip predicates, but we force a generator that never reacquires
    p = WorldPredicates(object_slipped=True)
    goal = goal_from_predicates(p)

    from rekep_repair.repair.candidate import RepairCandidate
    from rekep_repair.repair.operator import OPERATORS

    class NoReacquireGenerator:
        kind = "test"
        def generate(self, event, continuation, abstract_init=None, goal=None):
            ops = ("Suspend", "Realign", "Resume")
            stages = [OPERATORS[n].instantiate(i, event, continuation, params)
                      for i, n in enumerate(ops)]
            return [RepairCandidate("+".join(ops), stages, continuation)]

    mgr = RepairManager(params, limits, anchor_id="pour", successor_id="__succ__",
                        generator=NoReacquireGenerator(), cfg=cfg,
                        horizon_budget=cfg.horizon)
    ctx = Synthetic2DEnv(cfg, seed=0).observe()
    ev = Event(EventType.OBJECT_SLIP, 1.0, ("object",), t=2, event_id="E-test")
    res = mgr.plan(ev, cont, state_from_predicates(p), goal, ctx=ctx)
    assert res.selected is None
    assert res.use_fallback
    assert any("rollout/" in r for _, r in res.rejected)


# --- P1: sequential rollout catches collision and timeout -------------------
def test_rollout_rejects_colliding_ordering():
    """Two symbolically equal plans; only the rollout distinguishes them."""
    cfg = SceneConfig(p_init=np.array([0.2, 0.0]), slip_time=2,
                      drop_offset=np.array([0.18, 0.03]),
                      obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]),
                                        0.12, 2, 40))
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    Executor(env).run(pol)
    trace = "\n".join(pol._trace)
    assert "collision during" in trace, "rollout must catch the colliding ordering"
    assert "SELECTED" in trace
    # the selected plan clears before reacquiring
    sel = [l for l in trace.split("\n") if "SELECTED" in l][0]
    assert sel.index("WaitUntilClear") < sel.index("ReacquireTarget")


def test_rollout_reports_guard_timeout():
    cfg = SceneConfig()
    params = build_params(cfg, handoff_pose=np.array([0.12, 0.0]))
    cont = _cont(cfg=cfg)
    verifier = RolloutVerifier(params, cfg, horizon_budget=cfg.horizon)
    from rekep_repair.repair.candidate import RepairCandidate
    from rekep_repair.repair.operator import OPERATORS
    from dataclasses import replace as dcreplace
    # a Wait stage with a 1-step budget cannot outlast a long-lived obstacle
    wait = OPERATORS["WaitUntilClear"].instantiate(0, None, cont, params)
    wait = dcreplace(wait, max_steps=1)
    cand = RepairCandidate("Wait-only", [wait], cont)
    p = WorldPredicates(obstacle_present=True, unsafe_clearance=True)
    rep = verifier.verify(cand, Synthetic2DEnv(cfg, seed=0).observe(),
                          goal_from_predicates(p), cont)
    assert not rep.ok
    assert "timeout" in rep.reason or "horizon" in rep.reason
    assert rep.predicted_guard_failures


# --- P1: state-dependent selection ------------------------------------------
def test_severity_and_geometry_affect_selection_terms():
    """Scoring must consume rollout/severity quantities, not just length."""
    cfg = SceneConfig()
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    Executor(env).run(pol)
    terms = None
    for ln in "\n".join(pol._trace).split("\n"):
        if "scored" in ln:
            terms = ln
            break
    assert terms is not None
    for key in ("safety", "duration", "handoff", "min_clr", "severity"):
        assert key in terms, f"scorer must report {key}"


def test_shorter_plan_wins_when_retreat_unnecessary():
    """With no obstacle (slip only), no Retreat is planned at all."""
    p = WorldPredicates(object_slipped=True)
    from rekep_repair.repair.planner import RepairPlanner
    best = RepairPlanner().plan(state_from_predicates(p),
                                goal_from_predicates(p), k=1).best
    assert "Retreat" not in best and "WaitUntilClear" not in best


def test_retreat_required_when_unsafe():
    p = WorldPredicates(obstacle_present=True, unsafe_clearance=True)
    from rekep_repair.repair.planner import RepairPlanner
    best = RepairPlanner().plan(state_from_predicates(p),
                                goal_from_predicates(p), k=1).best
    assert "Retreat" in best


# --- P1: repeated repairs + events during repair ----------------------------
def _two_event_cfg():
    return SceneConfig(
        p_init=np.array([0.0, 0.0]),
        obstacle=Obstacle(np.array([0.55, 0.05]), np.array([0.55, 0.05]), 0.12, 2, 26),
        slip_time=40, drop_offset=np.array([0.0, -0.18]), horizon=150,
    )


def test_two_interruptions_in_one_episode():
    cfg = _two_event_cfg()
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    rep = Executor(env).run(pol).report()
    assert pol.program._repair_counter >= 2, "expected two repair instances"
    assert len(pol._trace) >= 2
    assert pol.program.order_graph_consistent()
    assert len(pol.program._order) == len(set(pol.program._order))
    assert rep["success"], "task must still complete after two repairs"


def test_events_during_repair_are_deferred_not_ignored():
    """An event arriving mid-repair must be recorded, never silently dropped."""
    cfg = SceneConfig(p_init=np.array([0.2, 0.0]), slip_time=6,
                      drop_offset=np.array([0.0, -0.2]),
                      obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]),
                                        0.12, 2, 40))
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OnlineRepairPolicy()
    Executor(env).run(pol)
    assert hasattr(pol, "deferred_events")
    # the slip lands while the obstacle repair is running
    assert len(pol.deferred_events) > 0, "mid-repair events must be recorded"


# --- P0: symmetric predicate channel ----------------------------------------
def test_all_policies_receive_the_same_predicate_set():
    cfg = SceneConfig(p_init=np.array([0.2, 0.0]), slip_time=2,
                      drop_offset=np.array([0.18, 0.03]),
                      obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]),
                                        0.12, 2, 40))
    env = Synthetic2DEnv(cfg, seed=0)
    for _ in range(3):
        env.step(np.zeros(3))
    preds = env.predicates(cfg.d_react)
    # the very same object both paradigms consume
    assert preds.obstacle_present and preds.object_slipped
    assert preds.key() == frozenset({"obstacle_present", "object_slipped"})
    # and an offline policy keys its branch off exactly this
    pol = OfflineComprehensivePolicy()
    pol.reset(env)
    assert preds.key() in pol.branches


def test_offline_single_is_not_full_combination_coverage():
    cfg = SceneConfig()
    pol = OfflineSingleEventCoveragePolicy()
    pol.reset(Synthetic2DEnv(cfg, seed=0))
    assert pol.branch_count == 3
    assert frozenset({"obstacle_present", "object_slipped"}) not in pol.branches
    comp = OfflineComprehensivePolicy()
    comp.reset(Synthetic2DEnv(cfg, seed=0))
    assert comp.branch_count == 7
    assert comp.graph_size > pol.graph_size
