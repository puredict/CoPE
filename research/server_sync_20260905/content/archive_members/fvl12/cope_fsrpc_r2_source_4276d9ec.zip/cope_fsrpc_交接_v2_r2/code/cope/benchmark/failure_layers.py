"""Deterministic failure-layer classification.

The v2 audit's central confound: a single `revised_task_success` flag conflated
three independent layers. Four CoPE and four FSR-PC episodes were labelled
failures when the adaptation was demonstrably correct and a *grasp* had failed.

Layers, checked in a fixed order so classification is deterministic:

    1. infrastructure_failure   the experiment did not run properly
                                (simulator crash, missing artifact, video
                                failure, checkpoint failure, undelivered event)
    2. adaptation_failure       the task state was updated wrongly
                                (stale target retained, cancelled goal executed,
                                invalid restoration, missing repair stage,
                                wrong revised active-goal set)
    3. controller_failure       the state was right and the body failed
                                (grasp_not_acquired, controller timeout,
                                dropped object, collision)
    4. task_failure_reason      otherwise, a plain unmet placement

**A correct state update followed by a failed grasp is a controller failure,
never an adaptation failure.** That rule is the point of this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---- reason vocabularies (kept explicit so logs stay greppable) ------------
CONTROLLER_REASONS = ("grasp_not_acquired", "controller_timeout",
                      "dropped_object", "object_slipped", "place_failed",
                      "leg step budget exhausted", "horizon exhausted",
                      "collision")
INFRA_REASONS = ("simulator_crash", "missing_artifact", "video_failure",
                 "checkpoint_failure", "event_not_delivered",
                 "state_hash_mismatch")
ADAPTATION_REASONS = ("stale_target_retained", "cancelled_goal_executed",
                      "invalid_restoration", "missing_repair_stage",
                      "wrong_active_goal_set", "duplicate_goal_execution",
                      "restore_not_revalidated", "lineage_inconsistent")


@dataclass
class EpisodeLayers:
    """The per-episode fields the audit asked to be made explicit."""
    # --- experiment plumbing
    event_schedule_valid: bool = True
    all_required_events_delivered: bool = True
    adaptation_input_valid: bool = True
    # --- semantic layer
    state_update_valid: bool = True
    patch_or_regeneration_valid: bool = True
    # --- repair pipeline
    continuation_captured: bool = False
    repair_goal_compiled: bool = False
    candidate_generation_complete: bool = False
    rollout_verification_complete: bool = False
    graph_splice_complete: bool = False
    restore_event_delivered: Optional[bool] = None
    revalidation_performed: Optional[bool] = None
    restore_contract_valid: Optional[bool] = None
    stage_resumed: bool = False
    # --- physical layer
    controller_success: bool = False
    grasp_success: bool = False
    placement_success: bool = False
    # --- outcome
    revised_task_success: bool = False
    # --- classification
    infrastructure_failure: bool = False
    controller_failure: bool = False
    adaptation_failure: bool = False
    task_failure_reason: str = ""
    failure_layer: str = "none"
    failure_detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def classify(*, task_metrics: Dict[str, Any], schedule: Dict[str, Any],
             repair_outcomes: List[Dict[str, Any]],
             legs: List[Dict[str, Any]],
             infrastructure_errors: List[str],
             required_artifacts_present: bool = True,
             condition: str = "") -> EpisodeLayers:
    """Classify one episode. Order of checks is fixed and documented above."""
    L = EpisodeLayers()
    tm, ro = task_metrics or {}, repair_outcomes or []

    # ---------- plumbing -------------------------------------------------
    events = schedule.get("events", []) or []
    L.all_required_events_delivered = bool(schedule.get("all_delivered", False))
    L.event_schedule_valid = bool(schedule.get("schedule_fingerprint"))
    undelivered = [e for e in events if not e.get("event_delivered")]

    # ---------- repair-pipeline stages -----------------------------------
    def every(marker: str) -> bool:
        return bool(ro) and all(marker in (o.get("markers") or []) for o in ro)

    L.continuation_captured = every("CONTINUATION_CAPTURED")
    L.repair_goal_compiled = every("REPAIR_GOAL_COMPILED")
    L.candidate_generation_complete = every("CANDIDATES_GENERATED")
    L.rollout_verification_complete = every("ROLLOUT_RESULTS")
    L.graph_splice_complete = every("GRAPH_SPLICED")
    L.stage_resumed = every("STAGE_RESUMED")
    if condition in ("I2", "I4", "I5"):
        L.restore_event_delivered = any(
            e.get("event_delivered") and e.get("tag") in ("u2", "u3")
            for e in events)
        L.revalidation_performed = bool(
            tm.get("revalidation_performed", every("RESTORE_VALIDATED")))
        L.restore_contract_valid = all(
            o.get("restore_validated") is not False for o in ro) or None
    L.patch_or_regeneration_valid = bool(ro) and all(
        ("PATCH" in (o.get("markers") or []))
        or ("REGENERATION" in (o.get("markers") or []))
        or o.get("skipped") for o in ro)

    # ---------- physical layer -------------------------------------------
    grasp_failures = [l for l in legs
                      if str(l.get("reason", "")).startswith("grasp")
                      or l.get("grasp_acquired") is False]
    L.grasp_success = not grasp_failures
    L.placement_success = bool(tm.get("revised_task_success"))
    L.controller_success = (L.grasp_success and not tm.get("collision")
                            and not tm.get("unsafe_contact"))
    L.revised_task_success = bool(tm.get("revised_task_success"))

    # ---------- semantic correctness -------------------------------------
    adaptation_problems: List[str] = []
    if tm.get("stale_goal_execution"):
        adaptation_problems.append("stale_target_retained")
    if tm.get("cancelled_goal_violation") or tm.get("cancellation_violation"):
        adaptation_problems.append("cancelled_goal_executed")
    if tm.get("duplicate_goal_execution"):
        adaptation_problems.append("duplicate_goal_execution")
    if tm.get("invalid_restoration"):
        adaptation_problems.append("invalid_restoration")
    if tm.get("remaining_goal_correct") is False:
        adaptation_problems.append("wrong_active_goal_set")
    if ro and not (L.continuation_captured and L.repair_goal_compiled
                   and L.graph_splice_complete and L.stage_resumed):
        adaptation_problems.append("missing_repair_stage")
    L.state_update_valid = not adaptation_problems

    # ---------- deterministic hierarchy ----------------------------------
    if infrastructure_errors or not required_artifacts_present or undelivered:
        L.infrastructure_failure = True
        L.failure_layer = "infrastructure"
        why = list(infrastructure_errors)
        if not required_artifacts_present:
            why.append("missing_artifact")
        why += [f"event_not_delivered:{e.get('tag')}"
                f"({e.get('delivery_failure_reason')})" for e in undelivered]
        L.failure_detail = ";".join(why)
    elif adaptation_problems:
        L.adaptation_failure = True
        L.failure_layer = "adaptation"
        L.failure_detail = ";".join(adaptation_problems)
    elif not L.revised_task_success and not L.controller_success:
        L.controller_failure = True
        L.failure_layer = "controller"
        reasons = sorted({str(l.get("reason", "")) for l in grasp_failures
                          if l.get("reason")})
        if tm.get("collision"):
            reasons.append("collision")
        L.failure_detail = ";".join(reasons) or "controller_failure"
    elif not L.revised_task_success:
        L.failure_layer = "task"
        L.failure_detail = "placement_not_achieved"
    else:
        L.failure_layer = "none"

    L.task_failure_reason = L.failure_detail if L.failure_layer != "none" else ""
    return L
