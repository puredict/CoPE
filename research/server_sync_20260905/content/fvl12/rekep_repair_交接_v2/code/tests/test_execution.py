"""Execution-level property tests (props 9-12) + bounded fallback."""

from __future__ import annotations

import numpy as np

from rekep_repair.execution.executor import Executor
from rekep_repair.execution.fallback import SafeFallback
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv
from rekep_repair.policies import OnlineRepairPolicy, PathOnlyPolicy


def _far_obstacle():
    return Obstacle(p_start=np.array([9.0, 9.0]), p_end=np.array([9.0, 9.0]),
                    radius=0.05, t_enter=0, t_exit=0)


def _no_event_cfg():
    return SceneConfig(obstacle=_far_obstacle())


def _intrusion_cfg():
    return SceneConfig()


def test_identity_repair_preserves_nominal_behavior():
    cfg = _no_event_cfg()
    r_online = Executor(Synthetic2DEnv(cfg, seed=0)).run(OnlineRepairPolicy())
    r_path = Executor(Synthetic2DEnv(cfg, seed=0)).run(PathOnlyPolicy())
    # with no event, the online policy runs the identity repair (no splice), so
    # its controlled trajectory matches the plain nominal controller during
    # motion (episodes may settle/stop one step apart -- a harness detail).
    k = 15
    assert np.allclose(r_online.rollout.positions[:k], r_path.rollout.positions[:k], atol=1e-9)
    assert np.allclose(r_online.rollout.thetas[:k], r_path.rollout.thetas[:k], atol=1e-9)
    # and the program was never structurally modified
    pol = OnlineRepairPolicy()
    Executor(Synthetic2DEnv(cfg, seed=0)).run(pol)
    assert pol.program.num_stages() == 1
    assert not pol.program.in_repair


def test_safe_fallback_unit_bounded():
    fb = SafeFallback(max_fallback_steps=3)
    fb.engage()
    steps = 0
    while not fb.exhausted():
        fb.action()
        steps += 1
        assert steps <= 3
    assert steps == 3


def test_safe_fallback_terminates_within_bounded_horizon():
    # tiny rotation limit -> handoff infeasible -> no candidate survives -> fallback
    cfg = SceneConfig(w_max=0.004)
    pol = OnlineRepairPolicy()
    res = Executor(Synthetic2DEnv(cfg, seed=0)).run(pol)
    assert pol.failed_safe is True
    assert len(res.provenance.records) <= cfg.horizon


def test_provenance_maps_actions_to_event_repair_continuation():
    cfg = _intrusion_cfg()
    pol = OnlineRepairPolicy()
    res = Executor(Synthetic2DEnv(cfg, seed=0)).run(pol)
    reps = res.provenance.repair_records()
    assert len(reps) > 0
    for r in reps:
        assert r.has_complete_provenance()
        assert r.event_id is not None
        assert r.continuation_ts is not None
    assert res.provenance.coverage() >= 0.95


def test_fixed_seed_reproducible():
    cfg = _intrusion_cfg()
    a = Executor(Synthetic2DEnv(cfg, seed=0)).run(OnlineRepairPolicy())
    b = Executor(Synthetic2DEnv(cfg, seed=0)).run(OnlineRepairPolicy())
    assert np.array_equal(a.rollout.positions, b.rollout.positions)
    assert np.array_equal(a.rollout.thetas, b.rollout.thetas)
