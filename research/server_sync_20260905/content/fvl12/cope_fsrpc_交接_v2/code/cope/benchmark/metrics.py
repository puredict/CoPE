"""Method-neutral metrics. Every field is computed identically for every policy."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class EpisodeMetrics:
    method: str = ""
    condition: str = ""
    seed: int = 0
    # --- final behaviour
    revised_task_success: Optional[bool] = None
    collision: Optional[bool] = None
    safe_fallback: bool = False
    invalid_action_count: int = 0
    completion_steps: Optional[int] = None
    # --- progress & continuity
    completed_progress_preserved: Optional[bool] = None
    completed_goals_repeated: int = 0
    cancelled_goal_violations: int = 0
    stale_goal_executions: int = 0
    remaining_goal_correct: Optional[bool] = None
    recovery_after_repeat: Optional[bool] = None
    # --- state representation
    identity_preserved: Optional[bool] = None
    lifecycle_transitions_legal: Optional[bool] = None
    restore_preceded_by_revalidation: Optional[bool] = None
    invalid_restore_count: int = 0
    lineage_correct: Optional[bool] = None
    history_monotonic: Optional[bool] = None
    # --- editing / regeneration
    slots_edited: int = 0            # total slots touched across the episode
    slots_regenerated: int = 0        # total slots re-emitted across the episode
    slots_touched_per_event: Optional[float] = None
    ops_per_event: Optional[float] = None
    normalized_edit_distance: Optional[float] = None   # mean fraction of the
                                                       # state touched per event
    state_churn: Optional[float] = None
    planner_calls: int = 0
    adaptation_latency_s: Optional[float] = None
    token_usage: Optional[int] = None          # None: no LLM used
    # --- repair pipeline (physical stack actually exercised?)
    repairs_invoked: int = 0
    pipelines_complete: int = 0
    candidates_generated: int = 0
    candidates_rejected: int = 0
    rollouts_run: int = 0
    splices: int = 0
    restores_validated: int = 0
    stages_resumed: int = 0
    engine_safe_fallbacks: int = 0
    # --- audit
    audit_coverage: Optional[float] = None
    audit_answerable: Dict[str, Optional[bool]] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_episode(*, method: str, condition: str, seed: int, store,
                     policy, exec_results: List[Dict[str, Any]],
                     expected_final: Dict[str, str],
                     cancelled_expected: Set[str],
                     completed_before: Set[str],
                     adaptation_latency_s: float,
                     ids_before_first_adapt: Set[str],
                     applicable: Optional[Dict[str, bool]] = None
                     ) -> EpisodeMetrics:
    """Compute all metrics from the store, the trace and the executor results."""
    m = EpisodeMetrics(method=method, condition=condition, seed=seed)
    state = store.state
    trace = store.trace

    placed = [p for r in exec_results for p in r.get("placed", [])]
    m.invalid_action_count = sum(len(r.get("invalid_actions", []))
                                 for r in exec_results)
    m.collision = any(r.get("collision") for r in exec_results)
    m.completion_steps = sum(r.get("steps", 0) for r in exec_results)

    # --- revised-task success: every expected object in its expected basket
    final_placement: Dict[str, str] = {}
    for p in placed:
        if p.get("object"):
            final_placement[p["object"]] = p["target"]
    m.revised_task_success = all(
        final_placement.get(o) == b for o, b in expected_final.items()) and \
        not any(o in final_placement for o in
                {c.replace("g_", "") for c in cancelled_expected})

    # --- progress & continuity
    obj_of = lambda gid: gid.split("@")[0].split("#")[0].replace("g_", "")
    # only placements that happen AFTER an adaptation can count as repeated work
    post = [p for r in exec_results if r.get("adaptations_before", 0) > 0
            for p in r.get("placed", [])]
    m.completed_goals_repeated = sum(
        1 for p in post if f"g_{p['object']}" in completed_before)
    m.completed_progress_preserved = (m.completed_goals_repeated == 0)
    cancelled_objs = {obj_of(c) for c in cancelled_expected}
    m.cancelled_goal_violations = sum(1 for p in placed
                                      if p.get("object") in cancelled_objs)
    # stale = executed against a target that is no longer the expected one
    m.stale_goal_executions = sum(
        1 for p in placed
        if p.get("object") in expected_final
        and p["target"] != expected_final[p["object"]])
    # the state the policy leaves behind must ask for exactly the right work
    compiled = {g["id"]: g for g in
                [{"id": s.id, **s.payload} for s in store.compile_active()]}
    wanted = {o: b for o, b in expected_final.items()}
    got = {g.get("object"): g.get("target") for g in compiled.values()
           if g.get("object") in wanted and not g.get("completed")}
    still_needed = {o: b for o, b in wanted.items()
                    if o not in {p["object"] for p in placed}}
    m.remaining_goal_correct = (m.stale_goal_executions == 0
                                and all(got.get(o) == b
                                        for o, b in still_needed.items())
                                and not any(o in cancelled_objs for o in got))

    # --- state representation
    ids_now = set(state.ids())
    m.identity_preserved = ids_before_first_adapt.issubset(ids_now)
    m.lifecycle_transitions_legal = all(
        e.get("ok", True) for e in trace.entries
        if e.get("kind") in ("state_validate", "regen_validate"))
    revalidated: Set[str] = set()
    restores_ok, restores_bad = 0, 0
    for e in trace.entries:
        if e.get("kind") != "op":
            continue
        if e.get("op") == "Revalidate":
            revalidated.add(e.get("target_id"))
        if e.get("op") == "Restore":
            if e.get("target_id") in revalidated:
                restores_ok += 1
            else:
                restores_bad += 1
    total_restores = restores_ok + restores_bad
    m.restore_preceded_by_revalidation = (
        None if total_restores == 0 else restores_bad == 0)
    m.invalid_restore_count = restores_bad
    m.lineage_correct = state.graph_consistent()
    m.history_monotonic = store.history_monotonic()

    # --- editing / regeneration
    m.slots_edited = getattr(policy, "n_slots_edited", 0)
    m.slots_regenerated = getattr(policy, "n_slots_emitted", 0)
    events = [h for h in store.history if "n_slots_after" in h]
    if events:
        # normalise per adaptation event so the figure stays in [0, 1] and is
        # comparable across conditions with different numbers of interruptions
        m.slots_touched_per_event = round(
            sum(len(h["touched"]) for h in events) / len(events), 4)
        m.ops_per_event = round(
            sum(h.get("n_ops", 0) for h in events) / len(events), 4)
        m.normalized_edit_distance = round(
            sum(len(h["touched"]) / max(1, h["n_slots_after"])
                for h in events) / len(events), 4)
        m.state_churn = round(
            sum(1 for h in events if h["before_fp"] != h["after_fp"])
            / len(events), 4)
    m.planner_calls = getattr(policy, "n_model_calls", 0)
    m.adaptation_latency_s = round(adaptation_latency_s, 6)
    m.token_usage = None

    # --- audit
    m.audit_answerable = trace.answerable(applicable)
    cov = trace.coverage(applicable)
    m.audit_coverage = None if cov is None else round(cov, 3)
    return m
