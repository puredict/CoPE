"""P0-B / P0-C: strong precompiled baseline parity, and the three distinct
success notions."""

from __future__ import annotations

import numpy as np

from rekep_repair.execution.executor import Executor
from rekep_repair.policies import (
    OfflineAtomicOnlyPolicy,
    OfflineBudgetPolicy,
    OfflineExactPolicy,
    OnlineRepairPolicy,
)
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def _compound_cfg():
    return SceneConfig(
        p_init=np.array([0.2, 0.0]), slip_time=2, drop_offset=np.array([0.18, 0.03]),
        obstacle=Obstacle(np.array([0.5, 0.05]), np.array([0.5, 0.05]), 0.12, 2, 40),
    )


def _run(cfg, policy):
    env = Synthetic2DEnv(cfg, seed=0)
    return Executor(env).run(policy).report()


# --- P0-B: parity when the exact branch is precompiled ----------------------
def test_exact_precompiled_offline_matches_online_on_compound():
    """When the exact combination IS precompiled and the baseline may bind and
    verify at runtime, precompilation must NOT be a handicap."""
    cfg = _compound_cfg()
    off = _run(cfg, OfflineExactPolicy())
    on = _run(cfg, OnlineRepairPolicy())
    assert off["safe_delivery"] == on["safe_delivery"] is True
    assert off["collision_free_recovery"] == on["collision_free_recovery"] is True


def test_atomic_only_offline_lacks_compound_coverage():
    """The remaining gap is purely structural coverage."""
    cfg = _compound_cfg()
    off = _run(cfg, OfflineAtomicOnlyPolicy())
    on = _run(cfg, OnlineRepairPolicy())
    assert not off["safe_delivery"]
    assert on["safe_delivery"]


def test_offline_parameterized_uses_same_runtime_machinery():
    """It must capture a continuation, splice, and validate restore -- i.e. the
    only difference from online is the absence of runtime search."""
    cfg = _compound_cfg()
    env = Synthetic2DEnv(cfg, seed=0)
    pol = OfflineExactPolicy()
    Executor(env).run(pol)
    assert pol.program._repair_counter >= 1, "must actually splice a repair"
    assert pol.continuation is not None, "must capture a continuation"
    trace = "\n".join(pol._trace)
    assert "rollout" in trace, "must use the same sequential rollout verifier"
    assert "scored" in trace, "must use the same state-dependent scoring"


def test_offline_precompiles_multiple_orderings_per_combination():
    cfg = _compound_cfg()
    pol = OfflineExactPolicy()
    pol.reset(Synthetic2DEnv(cfg, seed=0))
    key = frozenset({"obstacle_present", "object_slipped"})
    assert len(pol.library.lookup(key)) >= 2, "need several structural orderings"
    assert pol.branch_count > pol.library.combination_count


def test_offline_branch_budget_degrades_coverage():
    cfg = _compound_cfg()
    small = OfflineBudgetPolicy(budget=1)
    big = OfflineExactPolicy()
    small.reset(Synthetic2DEnv(cfg, seed=0))
    big.reset(Synthetic2DEnv(cfg, seed=0))
    assert small.branch_count < big.branch_count
    assert small.graph_size < big.graph_size
    assert small.compile_ops < big.compile_ops


# --- P0-C: three distinct success notions -----------------------------------
def test_three_success_notions_are_reported_separately():
    cfg = _compound_cfg()
    r = _run(cfg, OnlineRepairPolicy())
    for k in ("safe_delivery", "collision_free_recovery", "task_success"):
        assert k in r
    assert isinstance(r["safe_delivery"], bool)


def test_safe_delivery_does_not_imply_task_success():
    """The compound scene is safely delivered but does NOT meet every terminal
    constraint -- so the two must never be conflated."""
    cfg = _compound_cfg()
    r = _run(cfg, OnlineRepairPolicy())
    assert r["safe_delivery"] is True
    assert r["task_success"] is False


def test_task_success_implies_safe_delivery():
    cfg = SceneConfig()          # plain obstacle scene, fully solvable
    r = _run(cfg, OnlineRepairPolicy())
    if r["task_success"]:
        assert r["safe_delivery"] and r["collision_free_recovery"]


# --- deliverable 8: frozen adapter interface --------------------------------
def test_synthetic_adapter_implements_frozen_interface():
    from rekep_repair.adapter import RepairEnvironmentAdapter, SyntheticAdapter
    cfg = SceneConfig()
    ad = SyntheticAdapter(Synthetic2DEnv(cfg, seed=0))
    assert isinstance(ad, RepairEnvironmentAdapter)
    ctx = ad.observe_context()
    assert ctx.task_goal is not None
    assert np.allclose(ad.current_task_goal(), ctx.task_goal)
    assert "object" in ad.attachment_state()
    preds = ad.active_predicates()
    assert hasattr(preds, "key")
    ctx2 = ad.execute_action(np.zeros(3))
    assert ctx2.t == ctx.t + 1




# --- Track B: GPU handoff package is importable & dry-run safe on CPU -------
def test_rekep_adapter_dry_run_satisfies_frozen_interface():
    from rekep_repair.adapter import RepairEnvironmentAdapter
    from rekep_repair.rekep_adapter import ReKepOmniGibsonAdapter
    ad = ReKepOmniGibsonAdapter(dry_run=True)
    assert isinstance(ad, RepairEnvironmentAdapter)
    ctx = ad.reset()
    assert ctx.task_goal is not None and ctx.object_pos is not None
    assert np.allclose(ad.current_task_goal(), ctx.task_goal)
    preds = ad.active_predicates()
    assert hasattr(preds, "key")
    ctx2 = ad.execute_action(np.array([0.05, 0.0, 0.0]))
    assert ctx2.t == ctx.t + 1


def test_rekep_adapter_requires_explicit_dry_run():
    from rekep_repair.rekep_adapter import ReKepOmniGibsonAdapter
    import pytest as _pt
    with _pt.raises(ValueError):
        ReKepOmniGibsonAdapter()          # no rekep_main, no dry_run


def test_gpu_scripts_import_without_gpu_dependencies():
    """Every GPU script must be importable on a CPU-only machine."""
    import importlib.util, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("check_gpu_environment", "run_omni_smoke_test",
                 "run_rekep_baseline"):
        path = root / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        import sys as _sys
        _sys.modules[name] = mod          # dataclasses resolve via sys.modules
        try:
            spec.loader.exec_module(mod)  # must not import torch/omni
            assert hasattr(mod, "main")
            assert "torch" not in _sys.modules, f"{name} imported torch"
            assert "omni" not in _sys.modules, f"{name} imported omni"
        finally:
            _sys.modules.pop(name, None)
