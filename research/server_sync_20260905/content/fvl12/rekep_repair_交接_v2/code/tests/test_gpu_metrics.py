"""Tests for the GPU P0 fixes (P0-1 .. P0-4). All CPU / mocked -- no GPU imports.

Covers the 12 required cases:
 1 nominal insertion -> success            7 collision candidate rejected
 2 pen beside holder -> failure            8 invalid-handoff candidate rejected
 3 horizontal pen on table -> failure      9 valid candidate accepted
 4 insufficient depth -> failure          10 restore failure leaves state unchanged
 5 unstable pen -> failure                11 paired methods get identical disturbance
 6 rollout state isolation                12 missing metrics -> UNAVAILABLE
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from rekep_repair.gpu_metrics import (
    ContinuationRestoreContract,
    GPUCandidateVerifier,
    HolderGeometry,
    PenGeometry,
    PenInHolderEvaluator,
    PenInHolderThresholds,
    RestoreTolerances,
    RigidBodyState,
    RolloutLimits,
    StateIsolationError,
    select_best,
)

# --- scene constants used by the tests (a plausible pencil holder) -----------
PEN = PenGeometry(length=0.16, radius=0.006, long_axis=2)
HOLDER = HolderGeometry(inner_radius=0.035, rim_height=0.045, bore_depth=0.085, axis=2)
HOLDER_POS = np.array([-0.30, 0.075, 0.741])
UP = np.array([0.0, 0.0, 0.0, 1.0])          # identity quat, body z = world z


def _steady(pen_pos, n=12, quat=UP, speed=0.0):
    """A stability history of n samples with a given per-step speed."""
    return [RigidBodyState.of(pen_pos, quat, lin=[speed, 0, 0], ang=[0, 0, 0])
            for _ in range(n)]


def _ev(thr=None):
    return PenInHolderEvaluator(PEN, HOLDER, thr)


# =====================================================================
# P0-1 -- success evaluator
# =====================================================================
def test_1_nominal_insertion_is_success():
    """Pen upright, concentric, tip well down the bore."""
    tip_z = HOLDER_POS[2] + HOLDER.rim_height - 0.05      # 50 mm below the rim
    pen_pos = np.array([HOLDER_POS[0], HOLDER_POS[1], tip_z + PEN.length / 2])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="released",
                       history=_steady(pen_pos))
    assert r.inside_holder is True
    assert r.task_success is True, r.success_failure_reasons
    assert r.xy_error < 1e-6 and r.insertion_depth > 0.04
    assert r.tilt_error_deg < 1e-6


def test_1b_success_does_not_require_release():
    """Official semantics: completing while still grasping must NOT be failed
    by default (require_release is off)."""
    tip_z = HOLDER_POS[2] + HOLDER.rim_height - 0.05
    pen_pos = np.array([HOLDER_POS[0], HOLDER_POS[1], tip_z + PEN.length / 2])
    kw = dict(holder_state=RigidBodyState.of(HOLDER_POS, UP),
              history=_steady(pen_pos))
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       attachment_state="grasped", **kw)
    assert r.task_success is True
    strict = PenInHolderThresholds(require_release=True)
    r2 = _ev(strict).evaluate(RigidBodyState.of(pen_pos, UP),
                              attachment_state="grasped", **kw)
    assert r2.task_success is False
    assert any("require_release" in s for s in r2.success_failure_reasons)


def test_2_pen_beside_holder_is_failure():
    """Seed-0/3/5 pattern: pen held ~0.095 m from the holder axis."""
    pen_pos = HOLDER_POS + np.array([0.095, 0.0, 0.055])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="grasped", history=_steady(pen_pos))
    assert r.inside_holder is False
    assert r.task_success is False
    assert any("outside bore radius" in s or "xy_error" in s
               for s in r.success_failure_reasons)


def test_3_horizontal_pen_on_table_is_failure():
    """Seed-7 retry pattern: pen lying flat, below the holder centre."""
    lying = np.array([0.7071, 0.0, 0.0, 0.7071])          # body z -> world y
    pen_pos = HOLDER_POS + np.array([0.11, 0.0, -0.041])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, lying),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="released", history=_steady(pen_pos))
    assert r.task_success is False
    assert r.tilt_error_deg > 60.0
    assert any("tilt" in s for s in r.success_failure_reasons)


def test_4_insufficient_insertion_depth_is_failure():
    """Concentric and upright, but the tip only dips 5 mm below the rim."""
    tip_z = HOLDER_POS[2] + HOLDER.rim_height - 0.005
    pen_pos = np.array([HOLDER_POS[0], HOLDER_POS[1], tip_z + PEN.length / 2])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="released", history=_steady(pen_pos))
    assert r.inside_holder is True          # geometrically inside...
    assert r.task_success is False          # ...but not inserted enough
    assert any("insertion_depth" in s for s in r.success_failure_reasons)


def test_5_unstable_pen_is_failure():
    tip_z = HOLDER_POS[2] + HOLDER.rim_height - 0.05
    pen_pos = np.array([HOLDER_POS[0], HOLDER_POS[1], tip_z + PEN.length / 2])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="released",
                       history=_steady(pen_pos, speed=0.5))
    assert r.task_success is False
    assert any("unstable" in s for s in r.success_failure_reasons)


def test_12_missing_state_is_unavailable_not_guessed():
    """No stability history -> success WITHHELD (None), never assumed True."""
    tip_z = HOLDER_POS[2] + HOLDER.rim_height - 0.05
    pen_pos = np.array([HOLDER_POS[0], HOLDER_POS[1], tip_z + PEN.length / 2])
    r = _ev().evaluate(RigidBodyState.of(pen_pos, UP),
                       RigidBodyState.of(HOLDER_POS, UP),
                       attachment_state="released", history=None)
    assert r.task_success is None
    assert "stability_history" in r.unavailable
    assert r.inside_holder is True          # what IS measurable is still reported


# =====================================================================
# P0-2 -- rollout verifier
# =====================================================================
class _Stage:
    def __init__(self, op): self.metadata = {"operator": op}


class _Cand:
    def __init__(self, ops): self.stages = [_Stage(o) for o in ops]


class FakeHost:
    """Deterministic fake ReKep/OmniGibson host.

    Mutates its own state during a rollout so that a verifier which forgets to
    restore the checkpoint is detectable.
    """

    def __init__(self, outcomes, leak=False):
        self.outcomes = outcomes          # first-operator -> result dict
        self.state = 0
        self.leak = leak                  # if True, restore_checkpoint is a no-op
        self.restores = 0

    def save_checkpoint(self):
        return {"state": self.state}

    def restore_checkpoint(self, ck):
        self.restores += 1
        if not self.leak:
            self.state = ck["state"]

    def state_hash(self):
        return f"h{self.state}"

    def simulate_operator_sequence(self, operators, budget_steps):
        self.state += 1                   # rollout perturbs the world
        out = dict(self.outcomes[operators[1]])
        out.setdefault("steps_simulated", 10)
        return out


GOOD = dict(solver_success=True, collision=False, timeout=False,
            osc_warning_count=2, workspace_clip_count=0, attachment_valid=True,
            event_residual=[], handoff_error=0.01, predicted_xy_error=0.012,
            predicted_insertion_depth=0.05, predicted_tilt_error=4.0,
            predicted_success=True)
COLLIDE = {**GOOD, "collision": True, "predicted_success": False}
BADHAND = {**GOOD, "handoff_error": 0.42, "predicted_success": False}


def test_6_rollout_state_isolation_enforced():
    """Every candidate must start from the same checkpoint hash."""
    host = FakeHost({"Retreat": GOOD, "Stabilize": COLLIDE, "Realign": BADHAND})
    v = GPUCandidateVerifier(host)
    res = v.verify_all([_Cand(["Suspend", "Retreat"]),
                        _Cand(["Suspend", "Stabilize"]),
                        _Cand(["Suspend", "Realign"])])
    assert all(r.isolation_ok for r in res)
    assert len({r.pre_rollout_hash for r in res}) == 1, "all must start identically"
    assert res[0].checkpoint_hash == res[0].pre_rollout_hash
    assert host.state == 0, "live simulator must be left as found"


def test_6b_leaking_host_is_detected_not_silently_accepted():
    host = FakeHost({"Retreat": GOOD, "Stabilize": GOOD}, leak=True)
    v = GPUCandidateVerifier(host)
    with pytest.raises(StateIsolationError):
        v.verify_all([_Cand(["Suspend", "Retreat"]), _Cand(["Suspend", "Stabilize"])])


def test_7_collision_candidate_rejected():
    host = FakeHost({"Stabilize": COLLIDE})
    r = GPUCandidateVerifier(host).verify_all([_Cand(["Suspend", "Stabilize"])])[0]
    assert r.accepted is False
    assert "collision" in r.rejection_reason


def test_8_invalid_handoff_candidate_rejected():
    host = FakeHost({"Realign": BADHAND})
    r = GPUCandidateVerifier(host).verify_all([_Cand(["Suspend", "Realign"])])[0]
    assert r.accepted is False
    assert "handoff" in r.rejection_reason


def test_9_valid_candidate_accepted_and_selected():
    host = FakeHost({"Retreat": GOOD, "Stabilize": COLLIDE, "Realign": BADHAND})
    res = GPUCandidateVerifier(host).verify_all(
        [_Cand(["Suspend", "Stabilize"]), _Cand(["Suspend", "Realign"]),
         _Cand(["Suspend", "Retreat"])])
    assert [r.accepted for r in res] == [False, False, True]
    best = select_best(res)
    assert best is not None and best.operator_sequence == ["Suspend", "Retreat"]
    # the trace must be meaningful, not "0 rejected"
    assert sum(1 for r in res if not r.accepted) == 2


def test_9b_solver_failure_and_timeout_rejected():
    host = FakeHost({"A": {**GOOD, "solver_success": False},
                     "B": {**GOOD, "timeout": True},
                     "C": {**GOOD, "attachment_valid": False},
                     "D": {**GOOD, "event_residual": ["aligned_to_current_target"]},
                     "E": {**GOOD, "osc_warning_count": 500}})
    res = GPUCandidateVerifier(host).verify_all(
        [_Cand(["S", k]) for k in "ABCDE"])
    assert all(not r.accepted for r in res)
    reasons = " | ".join(r.rejection_reason for r in res)
    for frag in ("solver", "timeout", "attachment", "not resolved", "converging"):
        assert frag in reasons
    assert select_best(res) is None


# =====================================================================
# P0-3 -- restore contract
# =====================================================================
def _contract(tol=None):
    return ContinuationRestoreContract(
        handoff_ee_position=np.array([-0.395, -0.032, 0.923]),
        handoff_ee_orientation=np.array([0.472, 0.878, -0.080, 0.001]),
        required_attachment="grasped",
        relocated_target_position=np.array([-0.300, 0.075, 0.741]),
        reference_pen_position=np.array([-0.395, -0.032, 0.900]),
        tolerances=tol)


def test_restore_contract_accepts_valid_state():
    ev = _contract().evaluate(
        ee_position=np.array([-0.395, -0.032, 0.923]),
        ee_orientation=np.array([0.472, 0.878, -0.080, 0.001]),
        active_target_position=np.array([-0.300, 0.075, 0.741]),
        attachment_state="grasped",
        pen_state=RigidBodyState.of([-0.395, -0.032, 0.900], UP),
        collision_free=True, stage_entry_satisfied=True)
    assert ev.restore_valid is True and ev.failure_reasons == []
    assert ev.ee_position_error < 1e-6


@pytest.mark.parametrize("perturb,frag", [
    (dict(ee_position=np.array([-0.20, 0.20, 0.90])), "ee position"),
    (dict(attachment_state="released"), "attachment"),
    (dict(active_target_position=np.array([-0.30, 0.150, 0.741])), "target contract"),
    (dict(collision_free=False), "collision"),
    (dict(stage_entry_satisfied=False), "entry constraints"),
])
def test_restore_contract_rejects_each_perturbation(perturb, frag):
    kw = dict(ee_position=np.array([-0.395, -0.032, 0.923]),
              ee_orientation=np.array([0.472, 0.878, -0.080, 0.001]),
              active_target_position=np.array([-0.300, 0.075, 0.741]),
              attachment_state="grasped",
              pen_state=RigidBodyState.of([-0.395, -0.032, 0.900], UP),
              collision_free=True, stage_entry_satisfied=True)
    kw.update(perturb)
    ev = _contract().evaluate(**kw)
    assert ev.restore_valid is False
    assert any(frag in r for r in ev.failure_reasons), ev.failure_reasons


def test_restore_contract_is_not_tautological():
    """The v1 gate returned a latched flag. This one must depend on its inputs."""
    c = _contract()
    good = c.evaluate(ee_position=np.array([-0.395, -0.032, 0.923]),
                      ee_orientation=np.array([0.472, 0.878, -0.080, 0.001]),
                      active_target_position=np.array([-0.300, 0.075, 0.741]),
                      attachment_state="grasped",
                      pen_state=RigidBodyState.of([-0.395, -0.032, 0.900], UP),
                      collision_free=True, stage_entry_satisfied=True)
    bad = c.evaluate(ee_position=np.array([0.5, 0.5, 0.5]),
                     ee_orientation=np.array([0, 0, 0, 1.0]),
                     active_target_position=np.array([0.9, 0.9, 0.9]),
                     attachment_state="released",
                     pen_state=RigidBodyState.of([0.9, 0.9, 0.9], UP),
                     collision_free=False, stage_entry_satisfied=False)
    assert good.restore_valid and not bad.restore_valid
    assert len(bad.failure_reasons) >= 5


def test_10_restore_failure_leaves_task_program_unchanged():
    """A failing gate must not complete the repair node or enter RESUMED."""
    from dataclasses import replace as dcreplace
    from rekep_repair.program.stage import Mode, StageSpec, StageState
    from rekep_repair.program.task_program import RestorationBlocked, TaskProgram
    from rekep_repair.program.continuation import Continuation

    pour = StageSpec("stage3", Mode.POUR, kind="nominal",
                     metadata={"behavior": "progress", "exit_kind": "nominal"})
    tp = TaskProgram([pour])
    c = _contract()
    contract = c.as_task_program_contract(lambda: dict(
        ee_position=np.array([0.5, 0.5, 0.5]),          # far from handoff
        ee_orientation=np.array([0, 0, 0, 1.0]),
        active_target_position=np.array([0.9, 0.9, 0.9]),
        attachment_state="released",
        pen_state=RigidBodyState.of([0.9, 0.9, 0.9], UP),
        collision_free=False, stage_entry_satisfied=False))
    cont = Continuation(interrupted_stage_id="stage3", stage_mode=Mode.POUR,
                        state=np.zeros(3), ee_pose=np.zeros(3),
                        resume_contract=contract, timestamp=1, event_id="E1")
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    rep = StageSpec("resume", Mode.RESTORE, kind="repair",
                    metadata={"operator": "Resume", "provides_restore": True,
                              "behavior": "hold", "exit_kind": "restore_contract"})
    tp.splice_repair_before_successor([rep], cont)

    before_active = tp.active_id()
    before_states = dict(tp.state)
    assert tp.mark_restore_validated(np.zeros(3)) is False
    with pytest.raises(RestorationBlocked):
        tp.advance()
    assert tp.active_id() == before_active
    assert dict(tp.state) == before_states, "blocked gate must not mutate state"
    assert tp.state[tp._resumed_id] == StageState.PENDING


# =====================================================================
# P0-4 -- paired baseline
# =====================================================================
def test_11_paired_methods_receive_identical_disturbance():
    from rekep_repair.gpu_metrics.pilot_spec import PilotSpec, disturbance_for

    a = disturbance_for(PilotSpec(seed=3, severity_m=0.15,
                                  method="nominal_with_disturbance"))
    b = disturbance_for(PilotSpec(seed=3, severity_m=0.15, method="online_repair"))
    assert a.trigger_step == b.trigger_step
    assert np.allclose(a.relocation_vector, b.relocation_vector)
    assert a.n_interpolation_steps == b.n_interpolation_steps
    assert a.detection_threshold_m == b.detection_threshold_m
    assert a.horizon_steps == b.horizon_steps
    # different seeds must actually differ somewhere
    c = disturbance_for(PilotSpec(seed=4, severity_m=0.15, method="online_repair"))
    assert (c.trigger_step != a.trigger_step) or \
           (not np.allclose(c.relocation_vector, a.relocation_vector))


def test_11b_severity_is_not_a_constant_by_construction():
    """v1 defect: linspace(num=5)+threshold 0.05 forced displacement=0.075 always.
    The pilot spec must decouple the detection crossing from the severity."""
    from rekep_repair.gpu_metrics.pilot_spec import PilotSpec, disturbance_for
    lo = disturbance_for(PilotSpec(seed=0, severity_m=0.075, method="online_repair"))
    hi = disturbance_for(PilotSpec(seed=0, severity_m=0.150, method="online_repair"))
    assert not np.allclose(lo.relocation_vector, hi.relocation_vector)
    assert np.isclose(np.linalg.norm(lo.relocation_vector), 0.075)
    assert np.isclose(np.linalg.norm(hi.relocation_vector), 0.150)
    # and the first threshold crossing must be finer than v1's 0.0375 quantum
    assert lo.step_quantum < 0.0375 and hi.step_quantum < 0.0375
