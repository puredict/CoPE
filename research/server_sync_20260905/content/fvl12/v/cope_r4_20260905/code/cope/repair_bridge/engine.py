"""SharedRepairEngine --- the one downstream stack BOTH policies enter.

Implements the unified architecture end to end:

    C_t      = (S_t, G_t, H_t)                        persistent constraint state
    P_t      = epsilon(e_t, C_t, x_t)                 semantic update (CoPE or FSR-PC)
    C_t+     = Apply(C_t, P_t)
    kappa_t  = Capture(TaskProgram, active_stage, x_t)
    Omega_t  = Generate(C_t+, x_t, kappa_t)           runtime operator synthesis
    Delta_t* = argmin J(Delta)  s.t. Legal, RolloutFeasible, RestoreValid
    TP+      = Splice(TaskProgram, Delta_t*, kappa_t)
    Execute -> Revalidate -> Restore -> Resume

Everything from `Capture` onwards is the **frozen** `rekep_repair` engine,
imported and called, not re-implemented:

    rekep_repair.program.task_program.TaskProgram      splice / advance / restore gate
    rekep_repair.program.continuation.Continuation     kappa_t
    rekep_repair.repair.repair_manager.RepairManager   generate -> filter -> verify -> select
    rekep_repair.repair.synthesis_generator            runtime operator synthesis
    rekep_repair.repair.rollout_verifier.RolloutVerifier  sequential verification
    rekep_repair.execution.controller.control          the same controllers
    rekep_repair.execution.guard_monitor.stage_exit    the same guards
    rekep_repair.synthetic.env.Synthetic2DEnv          the same kinematics

The engine is **policy-blind**: `repair()` takes states and an adaptation
record, never a policy handle. Both arms call the identical method with the
identical signature, which is what makes requirement 10 checkable rather than
asserted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from rekep_repair.execution.controller import control
from rekep_repair.policies.common import build_params, nominal_pour_stage
from rekep_repair.program.continuation import Continuation
from rekep_repair.program.stage import StageState
from rekep_repair.program.task_program import RestorationBlocked, TaskProgram
from rekep_repair.repair.feasibility_filter import ControlLimits
from rekep_repair.repair.repair_manager import RepairManager
from rekep_repair.repair.synthesis_generator import SynthesisGenerator

from ..constraint_state import ConstraintState
from .continuation_capture import capture_continuation
from .goal_compiler import ConstraintStateToRepairGoalCompiler, RepairRequirements
from .stages import PipelineStage


@dataclass
class RepairOutcome:
    """What one physical adaptation actually did. Read by the metrics layer."""
    event_id: str
    markers: List[str] = field(default_factory=list)
    requirements: Optional[Dict[str, Any]] = None
    requirements_fingerprint: str = ""
    n_candidates: int = 0
    candidate_names: List[str] = field(default_factory=list)
    abstract_plans: List[Any] = field(default_factory=list)
    planner_expanded: int = 0
    n_rejected: int = 0
    rejections: List[Tuple[str, str]] = field(default_factory=list)
    rollouts: List[Tuple[str, str]] = field(default_factory=list)
    selected: Optional[str] = None
    selected_score: Optional[float] = None
    spliced_stage_ids: List[str] = field(default_factory=list)
    program_size_before: int = 0
    program_size_after: int = 0
    restore_validated: Optional[bool] = None
    restore_handoff_error: Optional[float] = None
    stage_resumed: bool = False
    repair_steps: int = 0
    safe_fallback: bool = False
    fallback_reason: str = ""
    rollout_verification_enabled: bool = True
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["rejections"] = [list(x) for x in self.rejections]
        d["rollouts"] = [list(x) for x in self.rollouts]
        return d


class SharedRepairEngine:
    """Owns the TaskProgram and drives the frozen repair pipeline.

    One instance per episode, shared by whichever policy is running. It holds no
    method-specific state.
    """

    def __init__(self, env, trace, *, horizon_budget: int = 200,
                 target_move_threshold: float = 0.15,
                 verifier_factory=None):
        self.env = env
        self.cfg = env.cfg
        self.trace = trace
        self.horizon_budget = horizon_budget
        # Optional backend adapter (added for the LIBERO integration).
        # Synthetic2D keeps the frozen verifier; a real simulator supplies an
        # interface-compatible verifier that performs checkpoint-isolated
        # rollouts in that simulator.
        self.verifier_factory = verifier_factory
        self.compiler = ConstraintStateToRepairGoalCompiler(
            target_move_threshold=target_move_threshold)
        self.limits = ControlLimits(v_max=self.cfg.v_max, w_max=self.cfg.w_max,
                                    ws_lo=self.cfg.ws_lo, ws_hi=self.cfg.ws_hi)
        # the task program for the leg currently being executed
        self.program = TaskProgram([nominal_pour_stage(behavior="progress")])
        self.continuation: Optional[Continuation] = None
        self.outcomes: List[RepairOutcome] = []
        # Set by CoPE_no_rollout_verification. Legality and feasibility filters
        # stay ON: the ablation removes sequential rollout verification only.
        self.disable_rollout_verification = False

    # ------------------------------------------------------------------
    def reset_program(self) -> None:
        """Start a fresh leg (one object -> one basket)."""
        self.program = TaskProgram([nominal_pour_stage(behavior="progress")])
        self.continuation = None

    def begin_leg(self, env) -> None:
        """Point the engine at the leg currently being executed.

        One engine instance lives for the whole episode and is shared by
        whichever policy is running, so `RecoveryManager.repair_engine` never
        has to be rebound and the two arms cannot end up holding different
        engines.
        """
        self.env = env
        self.cfg = env.cfg
        self.limits = ControlLimits(v_max=self.cfg.v_max, w_max=self.cfg.w_max,
                                    ws_lo=self.cfg.ws_lo, ws_hi=self.cfg.ws_hi)
        self.reset_program()

    # ------------------------------------------------------------------
    def repair(self, *, before: ConstraintState, after: ConstraintState,
               adaptation: Any, adaptation_kind: str, world: Dict[str, Any],
               ctx: Any, event_id: str, step: int) -> RepairOutcome:
        """Run the complete pipeline for one interruption.

        `adaptation_kind` is only used to emit PATCH vs REGENERATION in the
        trace; no branch in this method reads it.
        """
        out = RepairOutcome(event_id=event_id)
        self._mark(out, PipelineStage.EVENT, event_id=event_id, step=step)
        if adaptation_kind == "patch":
            self._mark(out, PipelineStage.PATCH, event_id=event_id)
        elif adaptation_kind == "regeneration":
            self._mark(out, PipelineStage.REGENERATION, event_id=event_id)
        else:
            # the control arm produces no state update at all. No slot-1 marker
            # is emitted, so `assert_complete` reports it as incomplete -- which
            # is the truth about that arm, not a bug.
            self.trace.record("no_state_update", event_id=event_id,
                              adaptation_kind=adaptation_kind)

        # --- kappa_t: BEFORE any physical adaptation ----------------------
        cont = capture_continuation(self.program, ctx, event_id,
                                    theta_pour=self.cfg.theta_pour,
                                    p_init=self.cfg.p_init)
        self._mark(out, PipelineStage.CONTINUATION_CAPTURED,
                   interrupted_stage=cont.interrupted_stage_id,
                   handoff_pose=[round(float(v), 4) for v in cont.handoff_pose],
                   progress_marker=round(cont.progress_marker, 4),
                   timestamp=cont.timestamp)

        # --- constraint-state semantics -> repair goal --------------------
        req: RepairRequirements = self.compiler.compile(
            before=before, after=after, adaptation=adaptation, world=world,
            ctx=ctx, event_id=event_id, step=step)
        out.requirements = req.to_dict()
        out.requirements_fingerprint = req.fingerprint()
        self._mark(out, PipelineStage.REPAIR_GOAL_COMPILED, **req.to_dict())

        if not req.needs_physical_repair:
            out.skipped = True
            out.skip_reason = req.note
            self.trace.record("repair_skipped", event_id=event_id,
                              reason=req.note)
            self.outcomes.append(out)
            return out

        # --- Omega_t -> filters -> sequential rollout -> argmin J ----------
        params = build_params(self.cfg, handoff_pose=cont.handoff_pose,
                              target_pos=(None if ctx.object_grasped
                                          else ctx.reacquire_pos),
                              task_goal=ctx.task_goal)
        generator = SynthesisGenerator(params)
        manager = RepairManager(
            params=params, limits=self.limits,
            anchor_id=self.program.active_id(),
            successor_id=self.program.next_id() or "__succ__",
            generator=generator,
            # RepairManager builds a verifier only when cfg is not None; the
            # ablation withholds cfg, which disables rollout verification
            # without touching the legality or feasibility filters.
            cfg=(None if self.disable_rollout_verification else self.cfg),
            horizon_budget=self.horizon_budget)
        if self.verifier_factory is not None:
            # A real backend supplies a checkpoint-isolated verifier. The
            # ablation must suppress it too, or CoPE_no_rollout_verification
            # would still be verified on the LIBERO path and the mechanism
            # test would be meaningless.
            manager.verifier = (
                None if self.disable_rollout_verification
                else self.verifier_factory(backend=self.env, params=params,
                                           horizon_budget=self.horizon_budget))
        result = manager.plan(req.event, cont, req.abstract_init, req.goal,
                              ctx=ctx, env=self.env)

        out.n_candidates = len(result.generated)
        out.candidate_names = list(result.generated)
        plan_res = getattr(generator, "last_plan", None)
        # the k best abstract operator sequences the planner found; each becomes
        # one concrete candidate repair program
        out.abstract_plans = ([[list(seq), round(float(cost), 4)]
                               for seq, cost in plan_res.plans]
                              if plan_res is not None else [])
        out.planner_expanded = (int(plan_res.n_expanded)
                                if plan_res is not None else 0)
        self._mark(out, PipelineStage.CANDIDATES_GENERATED,
                   n=len(result.generated), names=list(result.generated),
                   abstract_plans=out.abstract_plans,
                   planner_nodes_expanded=out.planner_expanded,
                   goal_reached=(bool(plan_res.goal_reached)
                                 if plan_res is not None else None))

        out.rollouts = [(n, s) for n, s in result.rollouts]
        out.rollout_verification_enabled = not self.disable_rollout_verification
        self._mark(out, PipelineStage.ROLLOUT_RESULTS,
                   verification_enabled=not self.disable_rollout_verification,
                   n_verified=len(result.rollouts),
                   reports=[{"candidate": n, "report": s}
                            for n, s in result.rollouts])

        out.rejections = [(n, r) for n, r in result.rejected]
        out.n_rejected = len(out.rejections)
        if out.rejections:
            # hard rejection, never a score penalty
            self.trace.record("candidates_rejected", event_id=event_id,
                              rejected=[{"candidate": n, "reason": r}
                                        for n, r in out.rejections])

        if result.selected is None:
            out.safe_fallback = True
            out.fallback_reason = ("no candidate survived legality / feasibility "
                                   "/ rollout verification")
            self.program.activate_safe_fallback(reason="no-candidate")
            self._mark(out, PipelineStage.SAFE_FALLBACK,
                       reason=out.fallback_reason,
                       rejected=[list(x) for x in out.rejections])
            self.outcomes.append(out)
            return out

        out.selected = result.selected.template_name
        out.selected_score = float(result.selected.score)
        self._mark(out, PipelineStage.CANDIDATE_SELECTED,
                   candidate=out.selected, score=round(out.selected_score, 5),
                   terms=result.selected.score_terms,
                   n_rejected=out.n_rejected)

        # --- Splice ---------------------------------------------------------
        out.program_size_before = self.program.num_stages()
        self.continuation = cont
        self.program.set_pending_continuation(cont)
        self.program.interrupt_active_stage(cont)
        self.program.splice_repair_before_successor(result.selected.stages, cont)
        out.program_size_after = self.program.num_stages()
        out.spliced_stage_ids = [s.stage_id for s in result.selected.stages]
        self._mark(out, PipelineStage.GRAPH_SPLICED,
                   spliced=out.spliced_stage_ids,
                   n_stages_before=out.program_size_before,
                   n_stages_after=out.program_size_after,
                   wellformed=self.program.is_wellformed(),
                   order_consistent=self.program.order_graph_consistent())

        self.outcomes.append(out)
        return out

    # ------------------------------------------------------------------
    def drive_repair(self, out: RepairOutcome, max_steps: int = 400) -> RepairOutcome:
        """Execute the spliced repair stages, validate the restore contract,
        and resume the interrupted stage.

        Uses the frozen controllers, the frozen guards and the frozen restore
        gate. The gate is non-tautological: `mark_restore_validated` compares
        the *current* physical state against the resume contract captured
        BEFORE the adaptation, so a repair cannot certify itself.
        """
        from rekep_repair.execution.guard_monitor import stage_exit

        if out.safe_fallback or out.skipped or self.continuation is None:
            return out

        cont = self.continuation
        params = build_params(self.cfg, handoff_pose=cont.handoff_pose,
                              task_goal=self.env.observe().task_goal)
        cur_steps = 0
        for _ in range(max_steps):
            if self.program.finished:
                break
            state = self.program.active_state()
            if state not in (StageState.REPAIR_ACTIVE, StageState.SUSPENDED,
                             StageState.RESUMED):
                break

            stage = self.program.active_stage()
            ctx = self.env.observe()
            exit_kind = stage.metadata.get("exit_kind", "nominal")
            satisfied = stage_exit(stage, ctx, cur_steps, cont, params,
                                   ctx.task_goal)

            if satisfied:
                if exit_kind == "restore_contract":
                    ok = self.program.mark_restore_validated(ctx.state,
                                                             ctx.keypoints)
                    err = cont.handoff_error(ctx.state)
                    out.restore_validated = bool(ok)
                    out.restore_handoff_error = round(float(err), 5)
                    self._mark(out, PipelineStage.RESTORE_VALIDATED,
                               validated=bool(ok),
                               handoff_error=out.restore_handoff_error,
                               contract=("resume contract captured at "
                                         f"t={cont.timestamp}, before adaptation"),
                               tautological=False)
                    if not ok:
                        if cur_steps > stage.max_steps:
                            self.program.activate_safe_fallback(
                                reason="restore-unvalidated")
                            out.safe_fallback = True
                            out.fallback_reason = "restore contract never satisfied"
                        cur_steps += 1
                        self._step(stage, ctx, cont, params)
                        continue
                try:
                    alive = self.program.advance()
                except RestorationBlocked:
                    self.program.activate_safe_fallback(reason="restoration-blocked")
                    out.safe_fallback = True
                    out.fallback_reason = "restoration blocked by the program graph"
                    return out
                cur_steps = 0
                if self.program.active_state() is StageState.RESUMED \
                        and not out.stage_resumed:
                    out.stage_resumed = True
                    self._mark(out, PipelineStage.STAGE_RESUMED,
                               resumed_stage=self.program.active_id(),
                               under_continuation=cont.event_id)
                    # The repair is over. The RESUMED stage is nominal work on
                    # the interrupted stage, so control returns to the harness.
                    # Driving on from here would let the repair loop finish the
                    # whole leg -- including, in the cancellation case, a goal
                    # the user had just cancelled.
                    break
                if not alive:
                    break
                continue

            if stage.kind == "repair" and cur_steps > stage.max_steps:
                self.program.activate_safe_fallback(
                    reason=f"{stage.stage_id}-timeout")
                out.safe_fallback = True
                out.fallback_reason = f"{stage.stage_id} exceeded its step bound"
                return out

            self._step(stage, ctx, cont, params)
            cur_steps += 1
            out.repair_steps += 1
        return out

    # ------------------------------------------------------------------
    def _step(self, stage, ctx, cont, params) -> None:
        behavior = stage.metadata.get("behavior", "hold")
        a = control(behavior, ctx, stage, cont, params, ctx.task_goal)
        self.env.step(a)

    def _mark(self, out: RepairOutcome, _marker: PipelineStage, **fields) -> None:
        # positional-by-convention: any keyword may be a trace field, so the
        # marker parameter is underscored to keep the namespace clear
        out.markers.append(_marker.value)
        self.trace.record("pipeline", marker=_marker.value, **fields)
