"""P0-A: the environment and the rollout verifier must clip actions with the
SAME function.  Diagonal actions are the case that used to diverge: per-axis
clipping admits sqrt(2)*v_max, norm clipping admits v_max."""

from __future__ import annotations

import numpy as np

from rekep_repair.execution.action import clip_action
from rekep_repair.policies.common import build_params
from rekep_repair.repair.rollout_verifier import RolloutVerifier
from rekep_repair.synthetic.dynamics import SceneConfig
from rekep_repair.synthetic.env import Synthetic2DEnv


def test_diagonal_action_is_norm_limited():
    v_max, w_max = 0.06, 0.30
    a = clip_action(np.array([1.0, 1.0, 0.0]), v_max, w_max)
    assert np.linalg.norm(a[:2]) <= v_max + 1e-12
    # per-axis clipping would have given 0.06 on BOTH axes -> norm 0.0849
    assert not np.allclose(a[:2], np.array([v_max, v_max]))


def test_rotation_is_magnitude_limited():
    a = clip_action(np.array([0.0, 0.0, 5.0]), 0.06, 0.30)
    assert np.isclose(a[2], 0.30)
    a = clip_action(np.array([0.0, 0.0, -5.0]), 0.06, 0.30)
    assert np.isclose(a[2], -0.30)


def test_small_action_unchanged():
    a0 = np.array([0.01, -0.02, 0.05])
    assert np.allclose(clip_action(a0, 0.06, 0.30), a0)


def test_env_and_rollout_clip_identically_on_diagonals():
    cfg = SceneConfig()
    env = Synthetic2DEnv(cfg, seed=0)
    verifier = RolloutVerifier(build_params(cfg), cfg, horizon_budget=cfg.horizon)
    rng = np.random.default_rng(0)
    for _ in range(200):
        a = rng.normal(scale=0.5, size=3)
        env_a = env.clip_action(a)
        # the verifier's integration must move the state by the same delta
        s0 = np.zeros(3)
        roll_delta = verifier._apply(s0, a) - s0
        assert np.allclose(env_a, roll_delta, atol=1e-12), (a, env_a, roll_delta)


def test_env_step_respects_norm_limit():
    cfg = SceneConfig()
    env = Synthetic2DEnv(cfg, seed=0)
    p0 = env.state[:2].copy()
    env.step(np.array([10.0, 10.0, 0.0]))      # huge diagonal
    moved = float(np.linalg.norm(env.state[:2] - p0))
    assert moved <= cfg.v_max + 1e-9, moved
