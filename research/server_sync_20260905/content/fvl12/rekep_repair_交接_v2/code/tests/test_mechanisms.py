"""B1: assert every ablation actually moves its intended internal variable.

A class name or a disabled flag is not evidence.  Each test below asserts the
specific internal quantity the ablation claims to remove genuinely differs from
the full method -- including for the ablations whose OUTCOME is null.
"""

from __future__ import annotations

import numpy as np
import pytest

from rekep_repair.benchmark import EpisodeSpec, sample_scene
from rekep_repair.benchmark.mismatch import LEVELS, MismatchedEnv
from rekep_repair.benchmark.probe import instrument
from rekep_repair.execution.executor import Executor
from rekep_repair.policies import OnlineRepairPolicy
from rekep_repair.policies.ablations import (
    NoEventCompositionPolicy, NoRealignPolicy, NoRestoreGatePolicy,
    NoRolloutVerificationPolicy, NoStateDependentScoringPolicy, NoSynthesisPolicy,
    NoContinuationContractPolicy,
)
from rekep_repair.synthetic.env import Synthetic2DEnv

EC1 = EpisodeSpec("upright_transport", "obstacle+slip", "high", 3)
# a scene where the sequential rollout demonstrably rejects a candidate
EC_REJ = EpisodeSpec("upright_transport", "obstacle+slip", "high", 4)
EC2 = EpisodeSpec("constrained_place", "slip+relocation", "high", 7)
EC3 = EpisodeSpec("align_insert", "obstacle+relocation", "medium", 11)


def _run(spec, factory, level="none"):
    cfg = sample_scene(spec)
    base = Synthetic2DEnv(cfg, seed=spec.seed)
    env = base if level == "none" else MismatchedEnv(base, LEVELS[level], seed=spec.seed)
    pol = factory()
    pol.reset(env)
    act = instrument(pol)
    rep = Executor(env).run(pol).report()
    return act, rep


# --- ablations that must change the causal path -----------------------------
def test_no_synthesis_changes_plans():
    full, _ = _run(EC2, OnlineRepairPolicy)
    abl, _ = _run(EC2, NoSynthesisPolicy)
    assert full.plans() != abl.plans(), "synthesis ablation must change plans"
    assert full.selections() != abl.selections()


def test_no_rollout_changes_surviving_candidates():
    full, _ = _run(EC_REJ, OnlineRepairPolicy)
    abl, _ = _run(EC_REJ, NoRolloutVerificationPolicy)
    assert any(a.rejected for a in full.activations), \
        "scene must actually exercise rollout rejection"
    surv_full = [a.survived for a in full.activations]
    surv_abl = [a.survived for a in abl.activations]
    rej_full = [a.rejected for a in full.activations]
    rej_abl = [a.rejected for a in abl.activations]
    assert (surv_full != surv_abl) or (rej_full != rej_abl), \
        "removing rollout verification must change which candidates survive"


def test_no_realign_changes_generated_plans():
    full, _ = _run(EC2, OnlineRepairPolicy)
    abl, _ = _run(EC2, NoRealignPolicy)
    gen_full = [a.generated for a in full.activations]
    gen_abl = [a.generated for a in abl.activations]
    assert gen_full != gen_abl
    joined = " ".join(x for a in abl.activations for x in a.generated)
    assert "Realign" not in joined, "Realign must be absent from ablated plans"


def test_no_continuation_contract_changes_handoff():
    full, _ = _run(EC2, OnlineRepairPolicy)
    abl, _ = _run(EC2, NoContinuationContractPolicy)
    assert full.handoffs() != abl.handoffs(), "handoff pose must differ"


# --- the three NULL mechanisms: active internally, null on outcome ----------
def test_no_composition_changes_goal_but_not_plan():
    """The ablation IS active (goal differs) yet the plan does not change,
    because operator preconditions already force the composition."""
    full, frep = _run(EC2, OnlineRepairPolicy)
    abl, arep = _run(EC2, NoEventCompositionPolicy)
    assert full.goals() != abl.goals(), "reduced goal must actually differ"
    assert full.plans() == abl.plans(), (
        "documented finding: preconditions already encode composition")
    assert frep["safe_delivery"] == arep["safe_delivery"]


def test_restore_gate_is_active_but_never_rejects():
    """The gate is exercised, and it never rejects -- a safety invariant that
    holds rather than a success mechanism.  Checked under severe mismatch too."""
    for level in ("none", "severe"):
        full, _ = _run(EC3, OnlineRepairPolicy, level)
        assert len(full.restore_validations) > 0, "gate must be exercised"
        assert all(full.restore_validations), (
            f"gate unexpectedly rejected at {level}; update docs/MECHANISMS.md")


def test_state_scoring_is_contested_but_outcome_neutral():
    """Selection is genuinely contested (>1 surviving candidate) yet structural
    scoring yields the same outcome."""
    full, frep = _run(EC3, OnlineRepairPolicy)
    abl, arep = _run(EC3, NoStateDependentScoringPolicy)
    assert any(len(a.survived) > 1 for a in full.activations), \
        "need a contested decision for this test to be meaningful"
    assert frep["safe_delivery"] == arep["safe_delivery"]


# --- B2: mismatch degrades verification -------------------------------------
def test_mismatch_env_actually_perturbs_execution():
    cfg = sample_scene(EC1)
    a = Synthetic2DEnv(cfg, seed=1)
    b = MismatchedEnv(Synthetic2DEnv(cfg, seed=1), LEVELS["severe"], seed=1)
    a.reset(); b.reset()
    act = np.array([0.05, 0.02, 0.1])
    for _ in range(5):
        a.step(act); b.step(act)
    assert not np.allclose(a.state, b.state), "severe mismatch must change execution"


def test_conservative_verifier_rejects_more_than_nominal():
    from rekep_repair.policies.verified_repair import VerifiedRepairPolicy
    cfg = sample_scene(EC1)
    outs = {}
    for v in ("nominal", "conservative"):
        env = MismatchedEnv(Synthetic2DEnv(cfg, seed=3), LEVELS["moderate"], seed=3)
        pol = VerifiedRepairPolicy(v)
        pol.reset(env)
        act = instrument(pol)
        Executor(env).run(pol)
        outs[v] = sum(len(a.rejected) for a in act.activations)
    assert outs["conservative"] >= outs["nominal"], \
        "conservative margins must reject at least as many candidates"


def test_scene_sampling_is_stable_across_processes():
    """Regression: scene sampling once used Python's salted hash(), so scenes
    silently differed between processes and the benchmark was not reproducible.
    _stable_seed must be a pure function of the key."""
    import subprocess, sys as _s
    from rekep_repair.benchmark.scenes import _stable_seed
    key = "upright_transport|obstacle+slip|high|4"
    here = _stable_seed(key)
    out = subprocess.run(
        [_s.executable, "-c",
         "from rekep_repair.benchmark.scenes import _stable_seed;"
         f"print(_stable_seed({key!r}))"],
        capture_output=True, text=True, check=True)
    assert int(out.stdout.strip()) == here
