"""v2 GPU pilot runner --- one episode, one method, with P0-1..P0-4 active.

STATUS:
  --dry-run : locally dry-run validated (fake host, no GPU imports)
  full mode : NOT EXECUTED -- REMOTE GPU SERVER ONLY

Differences from the v1 runner (`rekep_gpu_execution/code/run_repaired_rekep_headless.py`):

  P0-1  task success is computed from simulator geometry by
        `gpu_metrics.pen_in_holder`, and ALL state it needs (holder bore
        geometry, pen dimensions, velocities, a K-step history) is recorded.
  P0-2  every candidate is rolled out from an identical restored checkpoint via
        `GPUCandidateVerifier`; candidates are hard-rejected; selection uses
        measured rollout quantities. (v1: no rollout, score 0.3*5=1.5, 0 rejects.)
  P0-3  the resume contract is `ContinuationRestoreContract`, evaluated on live
        observed state with numeric margins. (v1: `lambda: flag_just_set_True`.)
  P0-4  three method arms share one paired `DisturbanceSpec`; the method cannot
        influence the disturbance.
  LOG   live JSONL structured events, so a killed episode still leaves evidence.

ReKep is still only SUBCLASSED; its subgoal/path/IK/OSC/constraint code is
untouched.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from rekep_repair.gpu_metrics import (
    ContinuationRestoreContract, GPUCandidateVerifier, HolderGeometry,
    PenGeometry, PenInHolderEvaluator, PenInHolderThresholds, PilotSpec,
    RestoreTolerances, RigidBodyState, RolloutLimits, StructuredLogger,
    disturbance_for, select_best,
)

# Scene geometry. MUST be confirmed on the GPU host against the real USD assets
# (see docs/GPU_SUCCESS_METRIC.md "calibration"); these are the declared defaults.
DEFAULT_PEN = PenGeometry(length=0.16, radius=0.006, long_axis=2)
DEFAULT_HOLDER = HolderGeometry(inner_radius=0.035, rim_height=0.045,
                                bore_depth=0.085, axis=2)


# ---------------------------------------------------------------------------
# Dry-run fake host: exercises the whole control flow with no simulator.
# ---------------------------------------------------------------------------
class _FakeShadowHost:
    """Deterministic stand-in used ONLY by --dry-run to prove the wiring."""

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)
        self.state = 0
        self._calls = 0

    def save_checkpoint(self):
        return {"state": self.state}

    def restore_checkpoint(self, ck):
        self.state = ck["state"]

    def state_hash(self):
        return f"fake-h{self.state}"

    def simulate_operator_sequence(self, operators, budget_steps):
        self.state += 1
        self._calls += 1
        # candidate 0 collides, candidate 1 has a bad handoff, candidate 2 is fine
        idx = (self._calls - 1) % 3
        base = dict(solver_success=True, collision=False, timeout=False,
                    osc_warning_count=int(self.rng.integers(0, 6)),
                    workspace_clip_count=0, attachment_valid=True,
                    event_residual=[], handoff_error=0.012,
                    predicted_xy_error=0.018, predicted_insertion_depth=0.052,
                    predicted_tilt_error=6.0, predicted_success=True,
                    steps_simulated=int(self.rng.integers(40, 90)))
        if idx == 0:
            base.update(collision=True, predicted_success=False)
        elif idx == 1:
            base.update(handoff_error=0.31, predicted_success=False)
        return base


def _dry_run(spec: PilotSpec, out_dir: Path, log: StructuredLogger) -> dict:
    """Full control flow on a fake host: synthesis -> rollout -> select ->
    restore-check -> success evaluation."""
    from rekep_repair.program.continuation import Continuation
    from rekep_repair.program.stage import Mode, StageSpec
    from rekep_repair.program.task_program import TaskProgram
    from rekep_repair.repair.abstract_state import (
        WorldPredicates, goal_from_predicates, state_from_predicates)
    from rekep_repair.repair.operator import RepairParams
    from rekep_repair.repair.synthesis_generator import SynthesisGenerator

    dist = disturbance_for(spec)
    log.emit("EPISODE_START", method=spec.method, severity_m=spec.severity_m,
             disturbance=dist.to_dict())

    tp = TaskProgram([StageSpec(f"rekep_stage_{i}", Mode.ALIGN, kind="nominal",
                                metadata={"behavior": "progress",
                                          "exit_kind": "nominal"})
                      for i in (1, 2, 3)])
    tp.advance(); tp.advance()                      # -> stage 3 active

    holder0 = np.array([-0.300, 0.150, 0.741])
    holder1 = holder0 + dist.relocation_vector
    ee = np.array([-0.396, -0.032, 0.923])
    ee_q = np.array([0.472, 0.878, -0.080, 0.001])

    if not dist.apply_disturbance:
        log.emit("EPISODE_END", note="no-disturbance control arm; nothing to repair")
        return {"mode": spec.method, "seed": spec.seed, "repair": None}

    if spec.method == "nominal_with_disturbance":
        # P0-4: the disturbance IS applied, but the program structure is NOT
        # modified -- no detection, no repair, no splice. ReKep keeps aiming at
        # the stale target, which is exactly the comparison we want.
        log.emit("EVENT_DETECTED", event_type="TARGET_RELOCATION",
                 displacement_m=round(float(np.linalg.norm(
                     holder1[:2] - holder0[:2])), 5),
                 note="observed for logging only; this arm does not repair")
        stale_pen = np.array([holder0[0], holder0[1],
                              holder0[2] + DEFAULT_HOLDER.rim_height + 0.03])
        hist0 = [RigidBodyState.of(stale_pen, [0, 0, 0, 1], lin=[0, 0, 0],
                                   ang=[0, 0, 0]) for _ in range(12)]
        ev0 = PenInHolderEvaluator(DEFAULT_PEN, DEFAULT_HOLDER,
                                   PenInHolderThresholds()).evaluate(
            RigidBodyState.of(stale_pen, [0, 0, 0, 1]),
            RigidBodyState.of(holder1, [0, 0, 0, 1]),
            attachment_state="released", history=hist0)
        log.emit("TASK_SUCCESS_EVALUATION", task_success=ev0.task_success,
                 inside_holder=ev0.inside_holder, xy_error=ev0.xy_error,
                 insertion_depth=ev0.insertion_depth,
                 tilt_error_deg=ev0.tilt_error_deg,
                 reasons=ev0.success_failure_reasons)
        log.emit("EPISODE_END", task_success=ev0.task_success)
        return {"mode": spec.method, "seed": spec.seed,
                "severity_m": spec.severity_m, "dry_run": True,
                "disturbance": dist.to_dict(), "repair": None,
                "task_success_evaluation": ev0.to_dict(),
                "task_program_order": list(tp._order)}

    detected_disp = float(np.linalg.norm(holder1[:2] - holder0[:2]))
    log.emit("EVENT_DETECTED", event_type="TARGET_RELOCATION",
             displacement_m=round(detected_disp, 5),
             threshold_m=dist.detection_threshold_m,
             trigger_step=dist.trigger_step)

    cont = Continuation(interrupted_stage_id=tp.active_id(),
                        stage_mode=tp.active_stage().mode,
                        state=np.array([ee[0], ee[1], 0.0]), ee_pose=ee,
                        attachment_state={"object": "grasped"},
                        nominal_target=holder0, handoff_pose=ee,
                        timestamp=dist.trigger_step,
                        event_id=f"target-relocation-{dist.trigger_step}")
    log.emit("CONTINUATION_CAPTURED", handoff_pose=[float(v) for v in ee],
             attachment="grasped", interrupted_stage=cont.interrupted_stage_id)

    preds = WorldPredicates(target_relocated=True)
    goal = goal_from_predicates(preds)
    log.emit("REPAIR_GOAL", label=goal.label,
             required_true=sorted(goal.required_true),
             required_false=sorted(goal.required_false))

    params = RepairParams(theta_pour=0.0, theta_hold=0.0, d_safe=0.10,
                          d_react=0.25, handoff_pose=ee[:2].copy(),
                          handoff_theta=0.0, task_goal=holder1[:2].copy())
    gen = SynthesisGenerator(params=params, k=4)
    cands = gen.generate(None, cont, state_from_predicates(preds), goal)
    log.emit("SEARCH_EXPANDED", n_expanded=getattr(gen.last_plan, "n_expanded", None),
             n_plans=len(cands))
    for i, c in enumerate(cands):
        log.emit("CANDIDATE_GENERATED", candidate_id=f"cand{i}",
                 operators=[s.metadata.get("operator") for s in c.stages])

    verifier = GPUCandidateVerifier(_FakeShadowHost(spec.seed),
                                    RolloutLimits(), logger=log)
    results = verifier.verify_all(cands)
    best = select_best(results)
    if best is None:
        log.emit("SAFE_FALLBACK", reason="no candidate survived verification")
        return {"mode": spec.method, "seed": spec.seed,
                "repair": {"selected": None,
                           "rollouts": [r.to_dict() for r in results]}}
    log.emit("CANDIDATE_SELECTED", candidate_id=best.candidate_id,
             operators=best.operator_sequence,
             predicted_xy_error=best.predicted_xy_error,
             handoff_error=best.handoff_error)

    chosen = cands[int(best.candidate_id.replace("cand", ""))]
    tp.set_pending_continuation(cont)
    tp.interrupt_active_stage(cont)
    tp.splice_repair_before_successor(chosen.stages, cont)
    log.emit("GRAPH_SPLICED", order=list(tp._order),
             interrupted_state=tp.state[cont.interrupted_stage_id].value)

    contract = ContinuationRestoreContract(
        handoff_ee_position=ee, handoff_ee_orientation=ee_q,
        required_attachment="grasped", relocated_target_position=holder1,
        reference_pen_position=ee, tolerances=RestoreTolerances())
    rest = contract.evaluate(ee_position=ee, ee_orientation=ee_q,
                             active_target_position=holder1,
                             attachment_state="grasped",
                             pen_state=RigidBodyState.of(ee, ee_q),
                             collision_free=True, stage_entry_satisfied=True)
    log.emit("RESTORE_CHECK", restore_valid=rest.restore_valid,
             **{k: v for k, v in rest.to_dict().items()
                if k not in ("failure_reasons", "unavailable", "restore_valid")})
    if not rest.restore_valid:
        log.emit("SAFE_FALLBACK", reason="restore contract rejected",
                 failure_reasons=rest.failure_reasons)
        return {"mode": spec.method, "seed": spec.seed, "restore": rest.to_dict()}

    tp.mark_restore_validated(np.array([ee[0], ee[1], 0.0]))
    while not tp.finished:
        tp.advance()
    log.emit("STAGE_RESUMED", resumed_node=tp._order[-1])

    # P0-1 success evaluation (fake terminal state: pen inserted)
    tip_z = holder1[2] + DEFAULT_HOLDER.rim_height - 0.05
    pen_pos = np.array([holder1[0], holder1[1], tip_z + DEFAULT_PEN.length / 2])
    hist = [RigidBodyState.of(pen_pos, [0, 0, 0, 1], lin=[0, 0, 0], ang=[0, 0, 0])
            for _ in range(12)]
    ev = PenInHolderEvaluator(DEFAULT_PEN, DEFAULT_HOLDER,
                              PenInHolderThresholds()).evaluate(
        RigidBodyState.of(pen_pos, [0, 0, 0, 1]),
        RigidBodyState.of(holder1, [0, 0, 0, 1]),
        attachment_state="released", history=hist)
    log.emit("TASK_SUCCESS_EVALUATION", task_success=ev.task_success,
             inside_holder=ev.inside_holder, xy_error=ev.xy_error,
             insertion_depth=ev.insertion_depth, tilt_error_deg=ev.tilt_error_deg,
             reasons=ev.success_failure_reasons)
    log.emit("EPISODE_END", task_success=ev.task_success)

    return {
        "mode": spec.method, "seed": spec.seed, "severity_m": spec.severity_m,
        "dry_run": True, "disturbance": dist.to_dict(),
        "repair": {
            "selected": best.operator_sequence,
            "selected_candidate_id": best.candidate_id,
            "n_candidates": len(cands),
            "n_rejected": sum(1 for r in results if not r.accepted),
            "rollouts": [r.to_dict() for r in results],
        },
        "restore": rest.to_dict(),
        "task_success_evaluation": ev.to_dict(),
        "task_program_order": list(tp._order),
    }


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--severity", type=float, required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rekep-root", default="../ReKep")
    args = ap.parse_args()

    spec = PilotSpec(seed=args.seed, severity_m=args.severity, method=args.method)
    out_dir = Path(args.out or f"runs/pilot/{spec.episode_id().replace('|','_')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    log = StructuredLogger(path=out_dir / "events.jsonl", seed=args.seed, echo=True)

    if args.dry_run:
        t0 = time.perf_counter()
        result = _dry_run(spec, out_dir, log)
        result["wall_seconds"] = round(time.perf_counter() - t0, 3)
        (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
        print(f"\nDRY-RUN complete -> {out_dir}/result.json")
        print("Status: wiring only. GPU behaviour NOT EXECUTED; requires remote GPU.")
        return

    if platform.system() == "Darwin":
        print("REFUSING: full mode is REMOTE GPU SERVER ONLY. Use --dry-run.",
              file=sys.stderr)
        sys.exit(2)

    # ---------------- REMOTE GPU SERVER ONLY ------------------------------
    # Implemented on the GPU host: subclass ReKep's Main exactly as v1 did, but
    #   * build the ShadowRolloutHost from the live env (save/restore via
    #     og.sim state dump; state_hash over robot joints + object poses),
    #   * call GPUCandidateVerifier before Scorer,
    #   * install ContinuationRestoreContract.as_task_program_contract(...),
    #   * record holder bore geometry, pen dims, velocities and a K-step history,
    #   * evaluate PenInHolderEvaluator at episode end.
    raise NotImplementedError(
        "GPU path must be completed on the remote host; see "
        "docs/GPU_V2_INTEGRATION.md for the exact call sites.")


if __name__ == "__main__":
    main()
