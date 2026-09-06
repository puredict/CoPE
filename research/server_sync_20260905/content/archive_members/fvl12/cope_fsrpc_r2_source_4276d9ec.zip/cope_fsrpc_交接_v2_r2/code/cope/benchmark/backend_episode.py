"""Backend-neutral episode harness with audit-grade per-episode artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Set, Tuple

from ..backends import make_backend
from ..backends.rollout_verifier import BackendRolloutVerifier
from ..naming import canonical_id
from ..policies import METHODS
from ..repair_bridge import SharedRepairEngine, assert_complete
from ..state_store import StateStore
from .basket_task import (
    NOMINAL_ASSIGNMENT,
    BasketTaskSpec,
    audit_applicability,
    build_initial_state,
    interruption,
    make_adaptation_input,
)
from .failure_layers import classify
from .scheduler import InterruptionScheduler, NOT_DELIVERED_TERMINATED
from .metrics import evaluate_episode
from .physical_episode import _expected_outcome


MAX_LEGS = 12


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: List[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def run_backend_episode(
    spec: BasketTaskSpec,
    *,
    backend_name: str,
    backend_config: str | Path,
    episode_dir: str | Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run one method/condition/seed in the requested simulator backend."""

    if spec.method not in METHODS:
        raise ValueError(f"unknown method {spec.method!r}; have {sorted(METHODS)}")
    out_dir = Path(episode_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    backend = make_backend(backend_name)
    backend_meta = backend.initialize(backend_config)
    reset_meta = backend.reset(spec.seed)

    cond = interruption(spec.condition, spec.seed)
    store = StateStore()
    initial = build_initial_state()
    if cond is not None and cond.execution_order:
        from dataclasses import replace

        initial = [
            replace(
                slot,
                payload={
                    **slot.payload,
                    "order": cond.execution_order.get(
                        slot.payload.get("object"), slot.payload.get("order", 99)
                    ),
                },
            )
            if slot.payload.get("object")
            else slot
            for slot in initial
        ]
    store.seed(initial)
    engine = SharedRepairEngine(
        backend,
        store.trace,
        horizon_budget=int(
            getattr(backend, "config", {})
            .get("limits", {})
            .get("candidate_horizon_steps", 200)
        ),
        target_move_threshold=1e-6,
        verifier_factory=BackendRolloutVerifier,
    )
    policy = METHODS[spec.method](
        store, horizon_steps=spec.horizon_steps, repair_engine=engine
    )

    # Pre-registered, method-independent schedule (see benchmark/scheduler.py).
    # Built from (condition, seed) only; `spec.method` is never passed in.
    scheduler = InterruptionScheduler.for_condition(
        spec.condition, spec.seed,
        cond.n_updates if cond is not None else 0, profile="libero")
    interruption_rows: List[Dict[str, Any]] = []

    world: Dict[str, Any] = {"unavailable_targets": [], "moved_targets": []}
    completed_objects: Set[str] = set()
    completed_goal_ids: Set[str] = set()
    failed_objects: Set[str] = set()
    fired: Set[str] = set()
    events: List[Dict[str, Any]] = []
    state_snapshots: List[Dict[str, Any]] = [
        {
            "label": "initial",
            "constraint_state": store.state.to_dict(),
            "simulator_state_hash": backend.state_hash(),
        }
    ]
    exec_results: List[Dict[str, Any]] = []
    legs: List[Dict[str, Any]] = []
    repair_rows: List[Dict[str, Any]] = []
    completed_before_first_adapt: Set[str] = set()
    ids_before_first_adapt = set(store.state.ids())
    adaptation_seconds = 0.0
    task_history: List[Dict[str, Any]] = []
    event_history: List[Dict[str, Any]] = []
    infrastructure_errors: List[str] = []

    def compiled_goals() -> List[Dict[str, Any]]:
        request = policy.mgr.compile(budget={"horizon_steps": spec.horizon_steps})
        return [
            goal
            for goal in request.active_goals
            if goal.get("object")
            and goal["object"] not in completed_objects
            and goal["object"] not in failed_objects
        ]

    def update_for(tag: str) -> Optional[Dict[str, Any]]:
        if cond is None:
            return None
        return {"u1": cond.update, "u2": cond.second_update,
                "u3": getattr(cond, "third_update", None)}.get(tag)

    def pending_updates() -> List[Tuple[str, Dict[str, Any]]]:
        """Elapsed-step delivery, method- and outcome-independent.

        v2 keyed the restore event on `g_milk` completing. When the milk grasp
        failed the event was never delivered and the episode silently stopped
        testing restoration. The scheduler cannot be suppressed by a controller
        failure; only the episode ending can prevent delivery, and that is
        recorded explicitly.
        """
        out: List[Tuple[str, Dict[str, Any]]] = []
        for tag in scheduler.due(backend.current_step()):
            upd = update_for(tag)
            if upd is not None:
                out.append((tag, upd))
        return out

    def apply_world_change(tag: str, update: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal world
        requested = dict(update.get("world", {}) or {})
        records: List[Dict[str, Any]] = []
        before_unavailable = set(world.get("unavailable_targets", []) or [])
        after_unavailable = set(
            requested.get("unavailable_targets", before_unavailable) or []
        )
        for target in sorted(before_unavailable | after_unavailable):
            if (target in before_unavailable) != (target in after_unavailable):
                records.append(
                    backend.set_target_availability(
                        target, available=target not in after_unavailable
                    )
                )
        world.update(requested)
        # I4: after the removed basket returns, restore it to a deliberately
        # changed on-table pose so revalidation is against changed geometry.
        if spec.condition == "I4" and tag == "u2":
            delta = (
                getattr(backend, "config", {})
                .get("world_events", {})
                .get("changed_world_basket_B_delta_xyz", [0.0, -0.12, 0.0])
            )
            records.append(backend.move_target("basket_B", delta))
        return {
            "requested_world": requested,
            "simulator_changes": records,
            "world_changed": any(r.get("world_changed", True) for r in records),
        }

    def deliver(tag: str, update: Dict[str, Any]) -> None:
        nonlocal adaptation_seconds, ids_before_first_adapt
        nonlocal completed_before_first_adapt
        first = not fired
        fired.add(tag)
        if first:
            ids_before_first_adapt = set(store.state.ids())
            completed_before_first_adapt = set(completed_goal_ids)
        world_record = apply_world_change(tag, update)
        event_id = f"{spec.condition}-{tag}"
        ordinal = len(event_history) + 1
        event_record = {
            "event_id": event_id,
            "ordinal": ordinal,
            "condition": spec.condition,
            "update": {k: v for k, v in update.items() if k != "world"},
            "world": dict(world),
            "world_application": world_record,
            "simulator_step": backend.step_count,
            "simulator_state_hash_before_adaptation": backend.state_hash(),
        }
        sched_ev = scheduler.mark_delivered(
            tag, backend.current_step(), event_id,
            hash_before=event_record["simulator_state_hash_before_adaptation"])
        event_record["scheduled_step"] = sched_ev.scheduled_step
        event_record["delivery_delay"] = sched_ev.delivery_delay
        event_history.append(event_record)
        inp = make_adaptation_input(
            spec,
            world,
            completed=tuple(sorted(completed_goal_ids)),
            pending=tuple(
                sorted({f"g_{obj}" for obj in NOMINAL_ASSIGNMENT} - completed_goal_ids)
            ),
            cancelled=tuple(
                sorted(
                    goal
                    for prior in event_history
                    for goal in prior["update"].get("cancel", [])
                )
            ),
            task_history=tuple(dict(row) for row in task_history),
            event_history=tuple(dict(row) for row in event_history),
            update=update,
            event_id=event_id,
            event_step=ordinal,
        )
        before_state = store.state.to_dict()
        started = time.perf_counter()
        policy.adapt(inp)
        adaptation_seconds += time.perf_counter() - started
        after_state = store.state.to_dict()
        outcome = getattr(policy, "last_repair", None)
        if outcome is not None:
            complete, problems = assert_complete(outcome.markers)
            row = outcome.to_dict()
            row["pipeline_complete"] = complete
            row["pipeline_problems"] = problems
            repair_rows.append(row)
        event_record["simulator_state_hash_after_adaptation"] = backend.state_hash()
        event_record["pipeline_markers"] = (
            list(outcome.markers) if outcome is not None else []
        )
        event_record["pipeline_complete"] = (
            assert_complete(outcome.markers)[0] if outcome is not None else False
        )
        sched_ev.world_state_hash_after = event_record[
            "simulator_state_hash_after_adaptation"]
        events.append(event_record)
        interruption_rows.append({
            "episode_id": spec.episode_id(), "method": spec.method,
            "condition": spec.condition, "seed": spec.seed,
            "event_index": len(interruption_rows) + 1, "event_type": tag,
            "event_id": event_id,
            "scheduled_step": sched_ev.scheduled_step,
            "delivered_step": sched_ev.actual_delivery_step,
            "delivery_delay": sched_ev.delivery_delay,
            "event_delivered": True,
            "task_state_before": before_state,
            "task_state_after": after_state,
            "physical_world_change": world_record,
            "affected_goal_ids": sorted(
                set(update.get("cancel", []) or [])
                | set(update.get("suspend", []) or [])
                | set(update.get("restore", []) or [])
                | set((update.get("redirect", {}) or {}).keys())
                | set(update.get("cancel_redirect", []) or [])),
            "old_target": {k: (store.state.get(k).payload.get("target")
                               if store.state.get(k) else None)
                           for k in (update.get("redirect", {}) or {})},
            "new_target": dict(update.get("redirect", {}) or {}),
            "patch_operations": [o.op.value for p_ in
                                 getattr(policy, "patches", [])[-1:]
                                 for o in p_.ops],
            "regenerated_state_hash": (
                getattr(policy, "regenerations", [])[-1].regen_id
                if getattr(policy, "regenerations", []) else None),
            "continuation_id": (outcome.event_id if outcome else None),
            "repair_invocation_id": len(policy.mgr.repair_outcomes),
            "restoration_required": bool(update.get("restore")),
            "revalidation_result": (
                "OK" if outcome and outcome.restore_validated else
                ("FAILED" if outcome and outcome.restore_validated is False
                 else None)),
            "restoration_result": (
                "restored" if outcome and outcome.stage_resumed else
                ("not_required" if not update.get("restore") else "unresolved")),
            "simulator_state_hash_before": sched_ev.world_state_hash_before,
            "simulator_state_hash_after": sched_ev.world_state_hash_after,
        })
        state_snapshots.append(
            {
                "label": event_id,
                "before": before_state,
                "after": after_state,
                "simulator_state_hash": backend.state_hash(),
            }
        )
        if verbose:
            try:
                print(
                    f"[{spec.method}] {event_id}: "
                    + " -> ".join(event_record["pipeline_markers"]),
                    flush=True,
                )
            except BrokenPipeError:
                # Logging transport must never enter the experimental control
                # path (e.g. a detached SSH client during a long run).
                pass

    try:
        for leg_index in range(MAX_LEGS):
            goals = compiled_goals()
            if not goals:
                break
            goal = sorted(
                goals,
                key=lambda row: (
                    row.get("order", 99),
                    str(row.get("object")),
                    str(row["id"]),
                ),
            )[0]
            obj = str(goal["object"])
            backend.begin_leg(goal)
            engine.begin_leg(backend)
            leg: Dict[str, Any] = {
                "leg_index": leg_index,
                "goal_id": goal["id"],
                "object": obj,
                "target_before": goal["target"],
                "step_start": backend.step_count,
            }
            # deliver anything already due BEFORE the pick, so a pick failure
            # cannot defer a scheduled event (the v2 defect)
            for tag, update in pending_updates():
                deliver(tag, update)

            pick = backend.pick_current_object()
            leg["pick"] = pick
            if not pick.get("success"):
                failed_objects.add(obj)
                leg["placed"] = False
                leg["failure_reason"] = pick.get("failure_reason", "pick_failed")
                # A GRASP FAILURE MUST NOT SUPPRESS AN INTERRUPTION. In v2 this
                # path returned immediately and the restore event keyed on
                # `g_milk` was lost in 8 of 30 I2/I4 episodes.
                for tag, update in pending_updates():
                    deliver(tag, update)
                legs.append(leg)
                exec_results.append(
                    {
                        "placed": [],
                        "failed": [goal["id"]],
                        "invalid_actions": [goal["id"]],
                        "steps": backend.step_count - leg["step_start"],
                        "collision": backend.collision_status()["collision"],
                        "adaptations_before": len(fired),
                    }
                )
                continue

            for tag, update in pending_updates():
                deliver(tag, update)

            live = {row["object"]: row for row in compiled_goals()}
            if obj not in live:
                # Expired current goals are physically cancelled; suspended
                # goals are safely returned but remain eligible for restore.
                cancelled = store.state.find_canonical(f"g_{obj}")
                if cancelled is not None and cancelled.mode.value == "expired":
                    stop = backend.cancel_goal(goal["id"])
                else:
                    stop = backend.return_current_object()
                leg.update(
                    {
                        "placed": False,
                        "abandoned_after_update": True,
                        "stop": stop,
                        "failure_reason": "goal_cancelled_or_suspended",
                        "step_end": backend.step_count,
                    }
                )
                legs.append(leg)
                exec_results.append(
                    {
                        "placed": [],
                        "failed": [],
                        "invalid_actions": [],
                        "steps": backend.step_count - leg["step_start"],
                        "collision": backend.collision_status()["collision"],
                        "adaptations_before": len(fired),
                    }
                )
                continue

            active_goal = live[obj]
            if active_goal.get("target") != backend.current_target:
                leg["retarget"] = backend.retarget(str(active_goal["target"]))
            if backend.current_target in backend.unavailable_targets:
                stop = backend.return_current_object()
                failed_objects.add(obj)
                leg.update(
                    {
                        "placed": False,
                        "stop": stop,
                        "failure_reason": "target_unavailable_without_suspension",
                        "step_end": backend.step_count,
                    }
                )
                legs.append(leg)
                exec_results.append(
                    {
                        "placed": [],
                        "failed": [goal["id"]],
                        "invalid_actions": [goal["id"]],
                        "steps": backend.step_count - leg["step_start"],
                        "collision": backend.collision_status()["collision"],
                        "adaptations_before": len(fired),
                    }
                )
                continue

            placement = backend.place_current_object()
            placed = bool(placement.get("success"))
            if placed:
                completed_objects.add(obj)
                completed_goal_ids.add(f"g_{obj}")
                task_history.append(
                    {
                        "event": "goal_completed",
                        "goal_id": canonical_id(goal["id"]),
                        "object": obj,
                        "target": backend.current_target,
                        "step": backend.step_count,
                    }
                )
            else:
                failed_objects.add(obj)
            leg.update(
                {
                    "target_after": backend.current_target,
                    "placement": placement,
                    "placed": placed,
                    "step_end": backend.step_count,
                    "collision": backend.collision_status()["collision"],
                }
            )
            legs.append(leg)
            exec_results.append(
                {
                    "placed": (
                        [
                            {
                                "goal_id": goal["id"],
                                "object": obj,
                                "target": backend.current_target,
                            }
                        ]
                        if placed
                        else []
                    ),
                    "failed": [] if placed else [goal["id"]],
                    "invalid_actions": [],
                    "steps": backend.step_count - leg["step_start"],
                    "collision": backend.collision_status()["collision"],
                    "adaptations_before": len(fired),
                }
            )
    except Exception as exc:
        infrastructure_errors.append(f"{type(exc).__name__}: {exc}")

    try:
        final_settle = backend.settle_world()
    except Exception as exc:
        infrastructure_errors.append(f"final_settle: {type(exc).__name__}: {exc}")
        final_settle = {"stable": False, "steps": 0, "reason": str(exc)}
    expected_final, cancelled_goal_ids = _expected_outcome(spec.condition)
    # Final drain: the episode is still active, so any event whose scheduled
    # step has already elapsed is delivered rather than dropped. Only events
    # scheduled beyond the end of the episode remain undelivered, and those are
    # recorded with an explicit reason.
    for tag, update in pending_updates():
        deliver(tag, update)

    cancelled_objects = sorted(goal.replace("g_", "") for goal in cancelled_goal_ids)
    task_metrics = backend.task_success(expected_final, cancelled_objects)
    task_metrics["stability_gate_passed"] = bool(final_settle.get("stable"))
    task_metrics["revised_task_success"] = bool(
        task_metrics.get("revised_task_success")
        and task_metrics["stability_gate_passed"]
    )
    metrics = evaluate_episode(
        method=spec.method,
        condition=spec.condition,
        seed=spec.seed,
        store=store,
        policy=policy,
        exec_results=exec_results,
        expected_final=expected_final,
        cancelled_expected=set(cancelled_goal_ids),
        completed_before=completed_before_first_adapt,
        adaptation_latency_s=adaptation_seconds,
        ids_before_first_adapt=ids_before_first_adapt,
        applicable=audit_applicability(spec.condition),
    )
    metrics.revised_task_success = bool(task_metrics["revised_task_success"])
    metrics.collision = bool(task_metrics["collision"])
    metrics.completion_steps = backend.step_count
    outcomes = policy.mgr.repair_outcomes
    metrics.repairs_invoked = len(outcomes)
    metrics.pipelines_complete = sum(
        int(assert_complete(outcome.markers)[0]) for outcome in outcomes
    )
    metrics.candidates_generated = sum(outcome.n_candidates for outcome in outcomes)
    metrics.candidates_rejected = sum(outcome.n_rejected for outcome in outcomes)
    metrics.rollouts_run = sum(len(outcome.rollouts) for outcome in outcomes)
    metrics.splices = sum(int(bool(outcome.spliced_stage_ids)) for outcome in outcomes)
    metrics.restores_validated = sum(
        int(bool(outcome.restore_validated)) for outcome in outcomes
    )
    metrics.stages_resumed = sum(int(bool(outcome.stage_resumed)) for outcome in outcomes)
    metrics.engine_safe_fallbacks = sum(int(outcome.safe_fallback) for outcome in outcomes)
    metrics.safe_fallback = metrics.engine_safe_fallbacks > 0
    physically_preserved = all(
        bool(task_metrics["expected_predicates"].get(goal.replace("g_", ""), {})
             .get("predicate", False))
        for goal in completed_before_first_adapt
    )
    metrics.completed_progress_preserved = bool(
        metrics.completed_progress_preserved and physically_preserved
    )
    task_metrics["completed_progress_preserved"] = physically_preserved
    task_metrics["cancelled_goal_violation"] = bool(
        task_metrics.get("cancellation_violation", False)
    )
    task_metrics["safe_fallback"] = bool(metrics.safe_fallback)

    try:
        video_meta = backend.write_video(out_dir / "video.mp4")
    except Exception as exc:
        infrastructure_errors.append(f"video_write: {type(exc).__name__}: {exc}")
        video_meta = {
            "written": False,
            "path": str(out_dir / "video.mp4"),
            "reason": str(exc),
        }
    (out_dir / "simulator.log").write_text(
        "\n".join(backend.simulator_log) + "\n", encoding="utf-8"
    )
    _write_jsonl(out_dir / "events.jsonl", events)
    _write_jsonl(out_dir / "adaptation_trace.jsonl", store.trace.entries)
    _write_jsonl(out_dir / "repair_trace.jsonl", repair_rows)
    _write_json(out_dir / "state_snapshots.json", state_snapshots)
    candidate_summaries: List[Dict[str, Any]] = []
    for repair in repair_rows:
        for candidate_name, summary in repair.get("rollouts", []):
            try:
                parsed = json.loads(summary)
            except (TypeError, json.JSONDecodeError):
                parsed = {"restore_exact": False, "parse_error": True}
            candidate_summaries.append(
                {"candidate": candidate_name, **dict(parsed)}
            )
    candidate_isolation_valid = all(
        bool(row.get("restore_exact")) for row in candidate_summaries
    )
    if not candidate_isolation_valid:
        infrastructure_errors.append(
            "candidate_isolation: at least one rollout did not restore its checkpoint"
        )
    denominators = {
        "attempted_episodes": 1,
        "valid_episodes": int(not infrastructure_errors),
        "attempted_candidates": sum(row.get("n_candidates", 0) for row in repair_rows),
        "evaluated_candidates": len(candidate_summaries),
        # A collision or invalid-handoff rejection is a scientifically valid
        # candidate evaluation. Validity means its rollout completed far
        # enough to restore the isolated checkpoint, not that it was accepted.
        "valid_candidates": sum(
            int(bool(row.get("restore_exact"))) for row in candidate_summaries
        ),
        "accepted_candidates": sum(
            int(bool(row.get("ok"))) for row in candidate_summaries
        ),
        "rejected_candidates": sum(row.get("n_rejected", 0) for row in repair_rows),
        "candidate_isolation_valid": bool(candidate_isolation_valid),
    }
    layers = classify(
        task_metrics=task_metrics, schedule=scheduler.to_dict(),
        repair_outcomes=repair_rows, legs=legs,
        infrastructure_errors=infrastructure_errors,
        required_artifacts_present=True, condition=spec.condition)
    # separate denominators, per the audit
    denominators.update({
        "all_events_delivered_episodes": int(scheduler.all_delivered),
        "adaptation_valid_episodes": int(not layers.adaptation_failure),
        "controller_valid_episodes": int(layers.controller_success),
        "final_task_successes": int(bool(task_metrics.get(
            "revised_task_success"))),
        "events_scheduled": len(scheduler.events),
        "events_delivered": scheduler.n_delivered,
    })
    # Any scheduled event that never ran is recorded explicitly.
    for ev in scheduler.finalize(backend.current_step()):
        if ev.event_delivered:
            continue
        interruption_rows.append({
            "episode_id": spec.episode_id(), "method": spec.method,
            "condition": spec.condition, "seed": spec.seed,
            "event_index": len(interruption_rows) + 1, "event_type": ev.tag,
            "event_id": ev.event_id, "scheduled_step": ev.scheduled_step,
            "delivered_step": None, "event_delivered": False,
            "delivery_failure_reason": ev.delivery_failure_reason})

    # the two artifacts the revised protocol requires per episode
    _write_jsonl(out_dir / "interruptions.jsonl", interruption_rows)
    _write_jsonl(out_dir / "candidate_rollouts.jsonl", candidate_summaries)

    result = {
        "episode_id": spec.episode_id(),
        "pairing_key": spec.key(),
        "backend": backend_name,
        "backend_meta": backend_meta,
        "reset_meta": reset_meta,
        "condition": spec.condition,
        "seed": spec.seed,
        "method": spec.method,
        "expected_final": expected_final,
        "cancelled_expected": cancelled_objects,
        "legs": legs,
        "events": events,
        "repair_outcomes": repair_rows,
        "schedule": scheduler.to_dict(),
        "interruptions": interruption_rows,
        "layers": layers.to_dict(),
        "metrics": metrics.to_dict(),
        "task_metrics": task_metrics,
        "final_settle": final_settle,
        "denominators": denominators,
        "infrastructure_errors": infrastructure_errors,
        "video": video_meta,
        "final_state": store.state.to_dict(),
        "final_simulator_state_hash": backend.state_hash(),
    }
    result["backend_finish"] = backend.finish_episode()
    _write_json(out_dir / "result.json", result)
    return _json_safe(result)
