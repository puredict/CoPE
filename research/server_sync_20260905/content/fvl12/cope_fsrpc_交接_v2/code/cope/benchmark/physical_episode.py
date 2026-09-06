"""Physical episode runner --- the harness that exercises the WHOLE stack.

    for each leg (one object -> one basket):
        run it through the frozen controller/guards inside Synthetic2DEnv
        when a user update lands MID-LEG:
            policy.adapt(...)                  -> PATCH | REGENERATION
            RecoveryManager.enter_repair_pipeline(...)   [the shared entry point]
                Capture(kappa)                 -> CONTINUATION_CAPTURED
                ConstraintStateToRepairGoalCompiler -> REPAIR_GOAL_COMPILED
                SynthesisGenerator             -> CANDIDATES_GENERATED
                RolloutVerifier                -> ROLLOUT_RESULTS
                Legality/Feasibility/Rollout   -> hard rejection
                Scorer.select                  -> CANDIDATE_SELECTED
                TaskProgram.splice_*           -> GRAPH_SPLICED
                mark_restore_validated         -> RESTORE_VALIDATED
                advance -> RESUMED             -> STAGE_RESUMED
            then re-read the compiled state and continue or abandon the leg

The interruption is delivered mid-leg on purpose: an update that arrives between
legs has no active stage to interrupt, so nothing would be spliced and the
pipeline would be trivially incomplete.

Fairness controls F1-F5 from the v1 harness are unchanged and still asserted;
this runner adds F6: both arms share one `SharedRepairEngine` instance, so they
cannot diverge in the downstream stack even by accident.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..audit_trace import AuditTrace
from ..naming import canonical_id
from ..policies import METHODS
from ..repair_bridge import SharedRepairEngine, assert_complete
from ..state_store import StateStore
from .basket_task import (
    BasketTaskSpec, NOMINAL_ASSIGNMENT, audit_applicability, build_initial_state,
    interruption, make_adaptation_input,
)
from .basket_world import BasketLegEnv
from .metrics import EpisodeMetrics, evaluate_episode
from .physical_executor import LegResult, PhysicalLegExecutor

MAX_LEGS = 12
#: an update is delivered once its trigger is due AND the robot is at least this
#: many steps into a leg, so there is always an ACTIVE stage to interrupt. A
#: fixed fraction of the leg does not work: legs are short, and an update that
#: arrives after the leg has finished would have nothing to splice into.
MIN_STEPS_BEFORE_INTERRUPT = 3


@dataclass
class PhysicalEpisodeResult:
    spec: BasketTaskSpec
    metrics: EpisodeMetrics
    legs: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_markers: List[List[str]] = field(default_factory=list)
    pipeline_complete: List[bool] = field(default_factory=list)
    repair_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    adaptation_input_fingerprints: List[str] = field(default_factory=list)
    requirement_fingerprints: List[str] = field(default_factory=list)
    executor_request_fingerprints: List[str] = field(default_factory=list)
    expected_final: Dict[str, str] = field(default_factory=dict)
    cancelled_expected: List[str] = field(default_factory=list)
    store: Any = None
    policy: Any = None
    engine: Any = None
    executor: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {"episode_id": self.spec.episode_id(),
                "pairing_key": self.spec.key(),
                "condition": self.spec.condition, "seed": self.spec.seed,
                "method": self.spec.method,
                "expected_final": dict(self.expected_final),
                "cancelled_expected": list(self.cancelled_expected),
                "legs": list(self.legs),
                "pipeline_markers": [list(m) for m in self.pipeline_markers],
                "pipeline_complete": list(self.pipeline_complete),
                "repair_outcomes": list(self.repair_outcomes),
                "adaptation_input_fingerprints":
                    list(self.adaptation_input_fingerprints),
                "requirement_fingerprints": list(self.requirement_fingerprints),
                "executor_request_fingerprints":
                    list(self.executor_request_fingerprints),
                "metrics": self.metrics.to_dict()}


def _expected_outcome(condition: str) -> Tuple[Dict[str, str], Set[str]]:
    """Ground truth for the REVISED task, from the condition alone."""
    final = dict(NOMINAL_ASSIGNMENT)
    cancelled: Set[str] = set()
    if condition == "nominal":
        return final, cancelled
    if condition == "I1":
        cancelled.add("g_yogurt"); final.pop("yogurt")
        final["butter"] = "basket_A"
    elif condition == "I3":
        final["butter"] = "basket_C"
    return final, cancelled


def run_physical_episode(spec: BasketTaskSpec, *, p_disturbance: float = 0.0,
                         verbose: bool = False) -> PhysicalEpisodeResult:
    """One episode, whole stack. CPU-only; no GPU software is touched."""
    if spec.method not in METHODS:
        raise ValueError(f"unknown method {spec.method!r}; have {list(METHODS)}")

    cond = interruption(spec.condition, spec.seed)
    store = StateStore()
    initial = build_initial_state()
    if cond is not None and cond.execution_order:
        initial = [replace(s, payload={**s.payload,
                                       "order": cond.execution_order.get(
                                           s.payload.get("object"),
                                           s.payload.get("order", 99))})
                   if s.payload.get("object") else s for s in initial]
    store.seed(initial)

    world: Dict[str, Any] = {"unavailable_targets": [], "moved_targets": []}
    executor = PhysicalLegExecutor(seed=spec.seed, p_disturbance=p_disturbance)

    # ONE engine for the whole episode, shared by whichever policy runs (F6).
    bootstrap = BasketLegEnv("milk", "basket_A", seed=spec.seed)
    engine = SharedRepairEngine(bootstrap, store.trace)
    policy = METHODS[spec.method](store, horizon_steps=spec.horizon_steps,
                                  repair_engine=engine)

    completed_objects: Set[str] = set()
    completed_goal_ids: Set[str] = set()
    ids_before_first_adapt: Set[str] = set(store.state.ids())
    completed_before_first_adapt: Set[str] = set()
    task_history: List[Dict[str, Any]] = []
    event_history: List[Dict[str, Any]] = []
    exec_results: List[Dict[str, Any]] = []
    in_fps: List[str] = []
    req_fps: List[str] = []
    adaptation_seconds = 0.0
    fired: Set[str] = set()
    # permanent physical failures only. Cancellation and suspension are
    # expressed by the constraint state itself -- `compile_active()`
    # already omits them -- so putting them here would prevent a later
    # Restore from ever being executed.
    failed_objects: Set[str] = set()
    result = PhysicalEpisodeResult(spec=spec, metrics=EpisodeMetrics())

    def compiled_goals() -> List[Dict[str, Any]]:
        req = policy.mgr.compile(budget={"horizon_steps": spec.horizon_steps})
        req_fps.append(req.fingerprint())
        return [g for g in req.active_goals
                if g.get("object") and not g.get("completed")
                and g["object"] not in completed_objects
                and g["object"] not in failed_objects]

    def deliver(tag: str, upd: Dict[str, Any], step: int) -> None:
        nonlocal adaptation_seconds, ids_before_first_adapt
        nonlocal completed_before_first_adapt
        first = not fired
        fired.add(tag)
        if upd.get("world") is not None:
            world.update(upd["world"])
            if executor.env is not None:
                executor.env.set_blocked(
                    tuple(world.get("unavailable_targets", []) or ()))
        event_id = f"{spec.condition}-{tag}"
        ordinal = len(event_history) + 1
        event_history.append({"step": step, "ordinal": ordinal,
                              "event_id": event_id,
                              "update": {k: v for k, v in upd.items()
                                         if k != "world"},
                              "world": upd.get("world", {})})
        if first:
            ids_before_first_adapt = set(store.state.ids())
            completed_before_first_adapt = set(completed_goal_ids)

        inp = make_adaptation_input(
            spec, world,
            completed=tuple(sorted(completed_goal_ids)),
            pending=tuple(sorted({f"g_{o}" for o in NOMINAL_ASSIGNMENT}
                                 - completed_goal_ids)),
            cancelled=tuple(sorted({c for e in event_history
                                    for c in e["update"].get("cancel", [])})),
            task_history=tuple(dict(h) for h in task_history),
            event_history=tuple(dict(h) for h in event_history),
            update=upd, event_id=event_id, event_step=ordinal)
        in_fps.append(inp.fingerprint())

        t0 = time.perf_counter()
        policy.adapt(inp)                     # -> shared repair pipeline inside
        adaptation_seconds += time.perf_counter() - t0

        out = getattr(policy, "last_repair", None)
        if out is not None:
            ok, _ = assert_complete(out.markers)
            result.pipeline_markers.append(list(out.markers))
            result.pipeline_complete.append(bool(ok))
            result.repair_outcomes.append(out.to_dict())
            if out.requirements_fingerprint:
                result.requirement_fingerprints.append(
                    out.requirements_fingerprint)
            if verbose:
                print(f"[{spec.method}] {event_id}: {' -> '.join(out.markers)}")

    def pending_updates() -> List[Tuple[str, Dict[str, Any]]]:
        if cond is None:
            return []
        out = []
        trig = canonical_id(cond.trigger_after_goal or "")
        if "u1" not in fired and (trig == "" or trig in completed_goal_ids):
            out.append(("u1", cond.update))
        if (cond.second_update is not None and "u2" not in fired
                and ("u1" in fired or out)
                and canonical_id(cond.second_trigger_after_goal or "")
                in completed_goal_ids):
            out.append(("u2", cond.second_update))
        return out

    # ---------------------------------------------------------------- legs
    for leg_index in range(MAX_LEGS):
        goals = compiled_goals()
        if not goals:
            break
        goal = sorted(goals, key=lambda g: (g.get("order", 99),
                                            str(g.get("object")), g["id"]))[0]
        obj = goal["object"]
        env = executor.begin_leg(goal, engine, world)
        steps, min_clr, collision = 0, float("inf"), False
        leg_abandoned = False

        while steps < executor.max_leg_steps:
            # deliver a pending update MID-leg so there is a stage to interrupt
            if steps >= MIN_STEPS_BEFORE_INTERRUPT:
                due = pending_updates()
                if due:
                    for tag, upd in due:
                        deliver(tag, upd, steps)
                    # the adaptation may have retargeted, cancelled or suspended
                    # THIS object's goal; re-read the compiled state
                    live = {g["object"]: g for g in compiled_goals()}
                    if obj not in live:
                        # cancelled or suspended: the leg stops, but the object
                        # is NOT marked as permanently failed, so a later
                        # Restore can bring it back
                        executor.finish_leg(goal, "goal cancelled or suspended",
                                            steps, min_clr, collision,
                                            force_failed=True)
                        leg_abandoned = True
                        break
                    new_target = live[obj].get("target")
                    if new_target and new_target != env.target_name:
                        env.retarget(new_target)
                        task_history.append({"step": steps,
                                             "event": "retargeted",
                                             "object": obj,
                                             "target": new_target})

            done, reason = executor.leg_done(engine)
            if done:
                res = executor.finish_leg(goal, reason, steps, min_clr, collision)
                if res.placed:
                    completed_objects.add(obj)
                    completed_goal_ids.add(f"g_{obj}")
                    task_history.append({"step": steps, "event": "goal_completed",
                                         "object": obj, "target": res.target,
                                         "goal_id": canonical_id(goal["id"])})
                else:
                    failed_objects.add(obj)
                    task_history.append({"step": steps, "event": "goal_failed",
                                         "object": obj, "reason": res.reason})
                break

            info = executor.step(engine)
            min_clr = min(min_clr, info["clearance"])
            collision = collision or info["collision"]
            steps += 1
        else:
            executor.finish_leg(goal, "leg step budget exhausted", steps,
                                min_clr, collision)
            failed_objects.add(obj)

        exec_results.append({
            "placed": ([{"goal_id": goal["id"], "object": obj,
                         "target": executor.legs[-1].target}]
                       if executor.legs[-1].placed else []),
            "failed": ([] if executor.legs[-1].placed else [goal["id"]]),
            "invalid_actions": ([] if executor.legs[-1].placed
                                or executor.legs[-1].reason != "target unavailable at arrival"
                                else [goal["id"]]),
            "steps": steps, "collision": collision,
            "adaptations_before": len(fired)})
        result.legs.append(executor.legs[-1].to_dict())

        # an update may still be pending if its trigger only just became true
        if not pending_updates():
            continue

    expected_final, cancelled_expected = _expected_outcome(spec.condition)
    metrics = evaluate_episode(
        method=spec.method, condition=spec.condition, seed=spec.seed,
        store=store, policy=policy, exec_results=exec_results,
        expected_final=expected_final, cancelled_expected=cancelled_expected,
        completed_before=completed_before_first_adapt,
        adaptation_latency_s=adaptation_seconds,
        ids_before_first_adapt=ids_before_first_adapt,
        applicable=audit_applicability(spec.condition))

    # --- pipeline metrics: did the repair engine actually run? ------------
    outs = policy.mgr.repair_outcomes
    metrics.repairs_invoked = len(outs)
    metrics.pipelines_complete = sum(result.pipeline_complete)
    metrics.candidates_generated = sum(o.n_candidates for o in outs)
    metrics.candidates_rejected = sum(o.n_rejected for o in outs)
    metrics.rollouts_run = sum(len(o.rollouts) for o in outs)
    metrics.splices = sum(1 for o in outs if o.spliced_stage_ids)
    metrics.restores_validated = sum(1 for o in outs if o.restore_validated)
    metrics.stages_resumed = sum(1 for o in outs if o.stage_resumed)
    metrics.engine_safe_fallbacks = sum(1 for o in outs if o.safe_fallback)
    metrics.safe_fallback = metrics.engine_safe_fallbacks > 0

    result.metrics = metrics
    result.adaptation_input_fingerprints = in_fps
    result.executor_request_fingerprints = req_fps
    result.expected_final = expected_final
    result.cancelled_expected = sorted(cancelled_expected)
    result.store, result.policy = store, policy
    result.engine, result.executor = engine, executor
    return result
