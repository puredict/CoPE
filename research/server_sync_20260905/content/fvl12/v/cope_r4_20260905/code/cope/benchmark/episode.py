"""Episode runner --- the single harness both arms share.

Fairness controls implemented here (and nowhere else, so they cannot drift):

  F1  Same task, same seed, same object layout, same interruption timing.
      `BasketTaskSpec.key()` deliberately excludes the method.
  F2  Same information packet. The `AdaptationInput` is built from
      *method-independent* facts (canonical goal ids, completed objects, world
      state, full task and event history) and its fingerprint is recorded so the
      identity can be asserted in a test rather than argued about.
  F3  Same executor interface. Both policies return an `ExecutorRequest`
      compiled by `StateStore.compile_active()`; the executor object and its
      random stream are shared and keyed on the physical action.
  F4  Same compute budget, same horizon, same evaluation code.
  F5  Neither arm sees the other's output, and no metric is computed from
      policy-private structures --- everything is read off the shared store,
      the shared trace and the shared executor log.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..naming import canonical_id
from ..policies import METHODS
from ..policies.adaptation_input import AdaptationInput
from ..state_store import StateStore
from .basket_task import (
    BasketTaskSpec, NOMINAL_ASSIGNMENT, SAFETY, audit_applicability,
    build_initial_state, interruption, make_adaptation_input,
)
from .metrics import EpisodeMetrics, evaluate_episode
from .mock_executor import MockPickPlaceExecutor

MAX_EXECUTOR_CALLS = 24          # generous; the nominal task needs 3


@dataclass
class EpisodeResult:
    spec: BasketTaskSpec
    metrics: EpisodeMetrics
    adaptation_input_fingerprints: List[str] = field(default_factory=list)
    executor_request_fingerprints: List[str] = field(default_factory=list)
    expected_final: Dict[str, str] = field(default_factory=dict)
    cancelled_expected: List[str] = field(default_factory=list)
    store: Any = None
    policy: Any = None
    executor: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {"episode_id": self.spec.episode_id(),
                "pairing_key": self.spec.key(),
                "condition": self.spec.condition, "seed": self.spec.seed,
                "method": self.spec.method,
                "expected_final": dict(self.expected_final),
                "cancelled_expected": list(self.cancelled_expected),
                "adaptation_input_fingerprints":
                    list(self.adaptation_input_fingerprints),
                "executor_request_fingerprints":
                    list(self.executor_request_fingerprints),
                "metrics": self.metrics.to_dict()}


def _expected_outcome(condition: str) -> Tuple[Dict[str, str], Set[str]]:
    """Ground truth for the REVISED task, derived from the condition alone.

    Method-independent by construction: this is the grader, and it never looks
    at what either policy did.
    """
    final = dict(NOMINAL_ASSIGNMENT)
    cancelled: Set[str] = set()
    if condition == "nominal":
        return final, cancelled
    if condition == "I1":
        cancelled.add("g_yogurt"); final.pop("yogurt")
        final["butter"] = "basket_A"
    elif condition == "I2":
        pass                       # butter is suspended then restored to B
    elif condition == "I3":
        final["butter"] = "basket_C"   # redirected B->A, then A->C
    elif condition == "I4":
        pass                       # B moves but is the same basket when restored
    return final, cancelled


def run_episode(spec: BasketTaskSpec, *, p_success: float = 0.97,
                verbose: bool = False) -> EpisodeResult:
    """Run one episode of one method. CPU-only; no GPU software is touched."""
    if spec.method not in METHODS:
        raise ValueError(f"unknown method {spec.method!r}; have {list(METHODS)}")

    cond = interruption(spec.condition, spec.seed)

    store = StateStore()
    initial = build_initial_state()
    if cond is not None and cond.execution_order:
        # part of the shared initial state, applied before any policy exists
        initial = [replace(s, payload={**s.payload,
                                       "order": cond.execution_order.get(
                                           s.payload.get("object"),
                                           s.payload.get("order", 99))})
                   if s.payload.get("object") else s
                   for s in initial]
    store.seed(initial)
    policy = METHODS[spec.method](store, horizon_steps=spec.horizon_steps)

    world: Dict[str, Any] = {"unavailable_targets": [], "moved_targets": []}
    executor = MockPickPlaceExecutor(seed=spec.seed, p_success=p_success,
                                     world=world)

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

    request = policy.mgr.compile(budget={"horizon_steps": spec.horizon_steps})
    req_fps.append(request.fingerprint())

    def deliver(tag: str, upd: Dict[str, Any], step: int):
        """Hand one user update to the policy. Identical for every method."""
        nonlocal request, adaptation_seconds, ids_before_first_adapt
        nonlocal completed_before_first_adapt
        first = not fired
        fired.add(tag)
        if upd.get("world") is not None:
            world.update(upd["world"])
        event_id = f"{spec.condition}-{tag}"
        # `event_step` is the 1-based interruption ordinal, not the executor
        # step: it is method-independent and keeps generated ids readable.
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
        request = policy.adapt(inp)
        adaptation_seconds += time.perf_counter() - t0
        req_fps.append(request.fingerprint())
        if verbose:
            print(f"[{spec.method}] {event_id} -> active="
                  f"{[g['id'] for g in request.active_goals]}")

    def pending_updates(step: int):
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

    # an update whose trigger is "" arrives before any goal is attempted
    for tag, upd in pending_updates(-1):
        deliver(tag, upd, -1)
    request = policy.mgr.compile(budget={"horizon_steps": spec.horizon_steps})
    req_fps.append(request.fingerprint())

    for step in range(MAX_EXECUTOR_CALLS):
        # ---- mark already-satisfied goals; harness-side, method-neutral ----
        for g in request.active_goals:
            if g.get("object") in completed_objects:
                g["completed"] = True

        r = executor.run_one(request)
        r["adaptations_before"] = len(fired)
        exec_results.append(r)
        if r["done"]:
            break
        for p in r["placed"]:
            completed_objects.add(p["object"])
            completed_goal_ids.add(f"g_{p['object']}")
            task_history.append({"step": step, "event": "goal_completed",
                                 "object": p["object"], "target": p["target"],
                                 "goal_id": canonical_id(p["goal_id"])})
        for gid in r["failed"]:
            task_history.append({"step": step, "event": "goal_failed",
                                 "goal_id": canonical_id(gid)})
            # a failed primitive is retried by re-compiling; guarded by the loop
        for gid in r["invalid_actions"]:
            task_history.append({"step": step, "event": "invalid_action",
                                 "goal_id": canonical_id(gid)})

        # ---- interruption delivery: identical trigger for every method ----
        for tag, upd in pending_updates(step):
            deliver(tag, upd, step)
        # recompile so newly restored / redirected goals become executable
        request = policy.mgr.compile(budget={"horizon_steps": spec.horizon_steps})
        req_fps.append(request.fingerprint())

    expected_final, cancelled_expected = _expected_outcome(spec.condition)
    metrics = evaluate_episode(
        method=spec.method, condition=spec.condition, seed=spec.seed,
        store=store, policy=policy, exec_results=exec_results,
        expected_final=expected_final, cancelled_expected=cancelled_expected,
        completed_before=completed_before_first_adapt,
        adaptation_latency_s=adaptation_seconds,
        ids_before_first_adapt=ids_before_first_adapt,
        applicable=audit_applicability(spec.condition))
    metrics.safe_fallback = bool(getattr(policy, "last_validation", None)
                                 and not policy.last_validation.ok)
    metrics.recovery_after_repeat = (
        metrics.revised_task_success if spec.condition == "I3" else None)

    return EpisodeResult(spec=spec, metrics=metrics,
                         adaptation_input_fingerprints=in_fps,
                         executor_request_fingerprints=req_fps,
                         expected_final=expected_final,
                         cancelled_expected=sorted(cancelled_expected),
                         store=store, policy=policy, executor=executor)


def run_paired(condition: str, seed: int, methods: Tuple[str, ...] = (
        "CoPE", "FSR-PC"), **kw) -> Dict[str, EpisodeResult]:
    """Run the same (condition, seed) through every method. Paired by design."""
    return {m: run_episode(BasketTaskSpec(seed=seed, condition=condition,
                                          method=m), **kw)
            for m in methods}
