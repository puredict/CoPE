"""Legality and feasibility filter tests (props 5-8)."""

from __future__ import annotations

import numpy as np

from rekep_repair.repair.feasibility_filter import ControlLimits, FeasibilityFilter
from rekep_repair.repair.legality_filter import LegalityFilter
from rekep_repair.repair.operator import RepairParams
from .helpers import candidate, continuation, stage


def test_cyclic_patch_rejected():
    s1 = stage("u1", provides_restore=True)
    s2 = stage("u2")
    # explicit internal edges with a back-edge -> cycle
    cyc = {("u1", "u2"), ("u2", "u1")}
    cand = candidate([s1, s2], continuation(), internal_edges=cyc)
    LegalityFilter().check(cand)
    assert cand.legal is False
    assert "cyclic" in cand.legality_reason


def test_patch_without_restore_edge_rejected():
    cand = candidate([stage("suspend"), stage("retreat")], continuation())  # no restore, not terminal
    LegalityFilter().check(cand)
    assert cand.legal is False
    assert cand.legality_reason == "no-restore-edge"


def test_attachment_inconsistent_patch_rejected():
    # object released, but Realign requires grasp with no reacquire before it
    realign = stage("realign", behavior="to_handoff", requires_grasp=True)
    resume = stage("resume", behavior="to_handoff", requires_grasp=True, provides_restore=True)
    cand = candidate([realign, resume], continuation(released=True))
    LegalityFilter().check(cand)
    assert cand.legal is False
    assert "attachment" in cand.legality_reason


def test_attachment_consistent_with_reacquire():
    reacq = stage("reacquire", behavior="to_target", establishes_grasp=True)
    realign = stage("realign", behavior="to_handoff", requires_grasp=True, provides_restore=True)
    cand = candidate([reacq, realign], continuation(released=True))
    LegalityFilter().check(cand)
    assert cand.legal is True


def test_infeasible_handoff_rejected():
    # handoff orientation delta = |theta_pour - theta_hold| = 1.0, but budget tiny
    params = RepairParams(theta_pour=1.0, theta_hold=0.0, d_safe=0.15,
                          handoff_pose=np.array([0.1, 0.0]), handoff_theta=1.0)
    limits = ControlLimits(v_max=0.06, w_max=0.01,       # too slow to reorient
                           ws_lo=np.array([-1, -1]), ws_hi=np.array([2, 2]))
    realign = stage("realign", behavior="to_handoff", max_steps=2, requires_grasp=True)
    resume = stage("resume", behavior="to_handoff", max_steps=1,
                   requires_grasp=True, provides_restore=True)
    cand = candidate([realign, resume], continuation())
    FeasibilityFilter(limits, params).check(cand)
    assert cand.feasible is False
    assert "handoff-orientation-unreachable" in cand.feasibility_reason


def test_feasible_handoff_accepted():
    params = RepairParams(theta_pour=1.0, theta_hold=0.0, d_safe=0.15,
                          handoff_pose=np.array([0.1, 0.0]), handoff_theta=1.0)
    limits = ControlLimits(v_max=0.06, w_max=0.30,
                           ws_lo=np.array([-1, -1]), ws_hi=np.array([2, 2]))
    realign = stage("realign", behavior="to_handoff", max_steps=30, requires_grasp=True)
    resume = stage("resume", behavior="to_handoff", max_steps=5,
                   requires_grasp=True, provides_restore=True)
    cand = candidate([realign, resume], continuation())
    FeasibilityFilter(limits, params).check(cand)
    assert cand.feasible is True
