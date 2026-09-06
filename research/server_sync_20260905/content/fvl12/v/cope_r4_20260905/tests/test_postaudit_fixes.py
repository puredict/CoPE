"""Tests for the post-audit revision (r2).

Each test maps to a numbered requirement from the post-audit brief. The v2 audit
found a controller failure silently deleting an experimental condition, so these
tests exist to make that class of defect impossible to reintroduce unnoticed.
"""
from __future__ import annotations

import pytest

from cope.benchmark import BasketTaskSpec
from cope.benchmark.basket_task import interruption
from cope.benchmark.failure_layers import classify
from cope.benchmark.backend_episode import _canonical_candidate_summary
from cope.benchmark.physical_episode import run_physical_episode
from cope.benchmark.scheduler import (
    NOT_DELIVERED_TERMINATED, InterruptionScheduler, SCHEDULES, SCHEDULES_CPU,
)
from cope.benchmark.verifier_probe import (
    VerifierProbeSpec, compare_verifier_arms, run_probe,
)
from cope.policies import FSRPC_VARIANTS, METHODS, VERIFIER_ARMS
from cope.policies.fsrpc_variants import assert_no_patch_application

CONDS = ("I1", "I2", "I3", "I4", "I5")
ADAPTERS = ("CoPE", "FSR-PC", "FSR-PC_stable_ids", "FSR-PC_provenance")


# ===================== §2 time-based restore scheduling =====================
def test_the_scheduler_never_consults_goal_completion():
    """The v2 defect in one assertion: no completion-dependent input exists."""
    import ast
    import inspect
    # scan EXECUTABLE source only: the module docstring describes the defect
    # being fixed, so a naive text scan would match its own explanation.
    tree = ast.parse(inspect.getsource(InterruptionScheduler))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            node.body = [n for n in node.body
                         if not (isinstance(n, ast.Expr)
                                 and isinstance(n.value, ast.Constant)
                                 and isinstance(n.value.value, str))]
    src = ast.unparse(tree)
    for banned in ("completed_goal", "completed_objects", "grasp_", "slot_id"):
        assert banned not in src, banned
    sig = inspect.signature(InterruptionScheduler.due)
    assert list(sig.parameters) == ["self", "sim_step"]


def test_schedule_is_a_pure_function_of_the_step():
    s = InterruptionScheduler.for_condition("I2", 0, 2, profile="cpu")
    assert s.due(0) == [] and s.due(4) == []
    assert s.due(5) == ["u1"]
    s.mark_delivered("u1", 5, "I2-u1")
    # u2 is anchored on the ACTUAL delivery of u1
    assert s.scheduled_step_for("u2") == 5 + SCHEDULES_CPU["I2"]["u2_delta"]
    assert s.due(10) == []
    assert s.due(5 + SCHEDULES_CPU["I2"]["u2_delta"]) == ["u2"]


def test_u2_anchors_on_actual_not_scheduled_delivery():
    s = InterruptionScheduler.for_condition("I2", 0, 2, profile="cpu")
    s.mark_delivered("u1", 9, "I2-u1")          # 4 steps late
    assert s.events[0].delivery_delay == 4
    assert s.scheduled_step_for("u2") == 9 + SCHEDULES_CPU["I2"]["u2_delta"]


@pytest.mark.parametrize("cond", ("I2", "I3", "I4", "I5"))
def test_every_scheduled_event_is_delivered_in_a_normal_episode(cond):
    for method in ADAPTERS:
        r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                                method=method))
        evs = r.schedule["events"]
        n_expected = interruption(cond, 0).n_updates
        assert len(evs) == n_expected, f"{cond}/{method}: {evs}"
        assert all(e["event_delivered"] for e in evs), f"{cond}/{method}: {evs}"
        assert r.schedule["all_delivered"]


def test_restore_is_delivered_even_when_a_grasp_fails():
    """THE regression test for the v2 defect.

    With `p_disturbance=1.0` every placement fails, so no goal ever completes.
    Under the v2 rule the restore event could never fire. Under the scheduler it
    still must, because the episode is still running.
    """
    for cond in ("I2", "I4"):
        r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                                method="CoPE"),
                                 p_disturbance=1.0)
        evs = r.schedule["events"]
        assert len(evs) == 2, evs
        assert all(e["event_delivered"] for e in evs), (
            f"{cond}: a placement failure suppressed an interruption again: {evs}")
        # and no goal actually completed, which is what makes the test meaningful
        assert not any(l["placed"] for l in r.legs)


def test_undelivered_events_are_recorded_never_omitted():
    s = InterruptionScheduler.for_condition("I2", 0, 2, profile="cpu")
    s.mark_delivered("u1", 5, "I2-u1")
    events = s.finalize(final_step=7)          # ended long before u2 was due
    assert len(events) == 2
    missing = [e for e in events if not e.event_delivered]
    assert len(missing) == 1
    assert missing[0].delivery_failure_reason == NOT_DELIVERED_TERMINATED
    assert not s.all_delivered


def test_schedule_fingerprint_is_method_independent():
    a = InterruptionScheduler.for_condition("I4", 3, 2, profile="cpu")
    b = InterruptionScheduler.for_condition("I4", 3, 2, profile="cpu")
    assert a.schedule_fingerprint() == b.schedule_fingerprint()
    assert (InterruptionScheduler.for_condition("I4", 4, 2, profile="cpu")
            .schedule_fingerprint() != a.schedule_fingerprint())


@pytest.mark.parametrize("cond", CONDS)
def test_paired_arms_get_the_identical_schedule(cond):
    fps = {}
    for m in ADAPTERS + ("no_adaptation",):
        r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond, method=m))
        fps[m] = (r.schedule["schedule_fingerprint"],
                  tuple(e["scheduled_step"] for e in r.schedule["events"]))
    assert len(set(fps.values())) == 1, fps


def test_both_step_profiles_are_pre_registered():
    for cond in CONDS:
        assert cond in SCHEDULES and cond in SCHEDULES_CPU


# ===================== §3 failure-layer classification ======================
def test_a_correct_state_update_with_a_failed_grasp_is_a_controller_failure():
    """The v2 mislabelling, asserted away."""
    L = classify(
        task_metrics={"revised_task_success": False, "collision": False,
                      "stale_goal_execution": False,
                      "cancelled_goal_violation": False,
                      "remaining_goal_correct": True},
        schedule={"schedule_fingerprint": "x", "all_delivered": True,
                  "events": [{"tag": "u1", "event_delivered": True}]},
        repair_outcomes=[{"markers": ["EVENT", "PATCH", "CONTINUATION_CAPTURED",
                                      "REPAIR_GOAL_COMPILED",
                                      "CANDIDATES_GENERATED", "ROLLOUT_RESULTS",
                                      "CANDIDATE_SELECTED", "GRAPH_SPLICED",
                                      "RESTORE_VALIDATED", "STAGE_RESUMED"],
                          "restore_validated": True}],
        legs=[{"obj": "milk", "reason": "grasp_not_acquired",
               "grasp_acquired": False}],
        infrastructure_errors=[], condition="I2")
    assert L.controller_failure is True
    assert L.adaptation_failure is False
    assert L.failure_layer == "controller"
    assert "grasp_not_acquired" in L.failure_detail
    assert L.state_update_valid is True


def test_a_stale_target_is_an_adaptation_failure():
    L = classify(
        task_metrics={"revised_task_success": False, "stale_goal_execution": True},
        schedule={"schedule_fingerprint": "x", "all_delivered": True, "events": []},
        repair_outcomes=[], legs=[], infrastructure_errors=[], condition="I1")
    assert L.adaptation_failure and L.failure_layer == "adaptation"
    assert "stale_target_retained" in L.failure_detail


def test_an_undelivered_event_is_an_infrastructure_failure():
    L = classify(
        task_metrics={"revised_task_success": True},
        schedule={"schedule_fingerprint": "x", "all_delivered": False,
                  "events": [{"tag": "u2", "event_delivered": False,
                              "delivery_failure_reason": NOT_DELIVERED_TERMINATED}]},
        repair_outcomes=[], legs=[], infrastructure_errors=[], condition="I2")
    assert L.infrastructure_failure and L.failure_layer == "infrastructure"
    assert "event_not_delivered" in L.failure_detail
    assert L.all_required_events_delivered is False


def test_the_layer_hierarchy_is_deterministic():
    """Infrastructure outranks adaptation, which outranks controller."""
    both = classify(
        task_metrics={"revised_task_success": False, "stale_goal_execution": True},
        schedule={"schedule_fingerprint": "x", "all_delivered": False,
                  "events": [{"tag": "u2", "event_delivered": False,
                              "delivery_failure_reason": "x"}]},
        repair_outcomes=[],
        legs=[{"reason": "grasp_not_acquired", "grasp_acquired": False}],
        infrastructure_errors=[], condition="I2")
    assert both.failure_layer == "infrastructure"


@pytest.mark.parametrize("cond", CONDS)
def test_every_episode_reports_a_layer(cond):
    for m in ADAPTERS + ("no_adaptation",):
        r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond, method=m))
        assert r.layers["failure_layer"] in ("none", "task", "controller",
                                             "adaptation", "infrastructure")
        assert set(r.layers) >= {
            "event_schedule_valid", "all_required_events_delivered",
            "adaptation_input_valid", "state_update_valid",
            "patch_or_regeneration_valid", "continuation_captured",
            "repair_goal_compiled", "candidate_generation_complete",
            "rollout_verification_complete", "graph_splice_complete",
            "stage_resumed", "controller_success", "grasp_success",
            "placement_success", "revised_task_success",
            "infrastructure_failure", "controller_failure",
            "adaptation_failure", "task_failure_reason"}


# ===================== §4 interruption-level records ========================
@pytest.mark.parametrize("cond", CONDS)
def test_every_interruption_produces_an_event_level_record(cond):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond, method="CoPE"))
    assert len(r.interruptions) == interruption(cond, 0).n_updates
    for rec in r.interruptions:
        assert set(rec) >= {
            "episode_id", "method", "condition", "seed", "event_index",
            "event_type", "scheduled_step", "delivered_step",
            "task_state_before", "task_state_after", "physical_world_change",
            "affected_goal_ids", "old_target", "new_target",
            "patch_operations", "regenerated_state_hash", "continuation_id",
            "repair_invocation_id", "restoration_required",
            "revalidation_result", "restoration_result"}


def test_records_distinguish_undelivered_from_failed_adaptation():
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I2",
                                            method="CoPE"))
    assert all(rec["event_delivered"] for rec in r.interruptions)
    s = InterruptionScheduler.for_condition("I2", 0, 2, profile="cpu")
    s.finalize(final_step=0)
    assert not any(e.event_delivered for e in s.events)


# ===================== §5 I2 / I4 required sequences ========================
@pytest.mark.parametrize("cond", ("I2", "I4"))
def test_suspension_and_restore_both_occur(cond):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition=cond, method="CoPE"))
    tags = [e["tag"] for e in r.schedule["events"] if e["event_delivered"]]
    assert tags == ["u1", "u2"]
    ops = [o.op.value for p in r.policy.patches for o in p.ops]
    assert "Suspend" in ops and "Revalidate" in ops and "Restore" in ops
    assert ops.index("Revalidate") < ops.index("Restore")


def test_i4_moves_the_target_before_restoration():
    c = interruption("I4", 0)
    assert "basket_B" in c.second_update["world"]["moved_targets"]
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I4", method="CoPE"))
    assert r.metrics.restore_preceded_by_revalidation is True


# ===================== §6 verifier discrimination ===========================
def test_the_verifier_rejects_candidates_in_the_probe():
    s = run_probe(VerifierProbeSpec(obstacle_radius=0.20, obstacle_frac=0.40))
    assert s["n_candidates"] >= 3
    assert s["n_rejected"] > 0, "the probe failed to make the verifier reject"
    assert any(k in s["rejected_by_reason"]
               for k in ("collision_or_unsafe_contact", "invalid_handoff"))
    assert any(l.startswith("CANDIDATE_REJECTED") for l in s["lines"])


def test_disabling_the_verifier_changes_the_decision():
    """The mechanism test. If this ever returns False the verifier is inert."""
    r = compare_verifier_arms(VerifierProbeSpec(obstacle_radius=0.20,
                                                obstacle_frac=0.40))
    assert r["verifier_changed_the_decision"] is True
    assert r["n_rejected_full"] > 0
    assert r["n_rejected_ablated"] == 0


def test_the_ablation_keeps_legality_and_feasibility_on():
    import inspect
    from cope.repair_bridge.engine import SharedRepairEngine
    src = inspect.getsource(SharedRepairEngine.repair)
    assert "disable_rollout_verification" in src
    # the flag withholds cfg (the verifier), never the filters
    assert "LegalityFilter" not in src and "FeasibilityFilter" not in src


def test_verifier_arms_are_registered():
    assert set(VERIFIER_ARMS) <= set(METHODS)


# ===================== §7 FSR-PC variants ===================================
def test_all_fsrpc_variants_are_registered_and_regenerate():
    assert set(FSRPC_VARIANTS) <= set(METHODS)
    for name in FSRPC_VARIANTS:
        r = run_physical_episode(BasketTaskSpec(seed=0, condition="I1",
                                                method=name))
        assert r.metrics.slots_regenerated > 0, name
        assert r.metrics.slots_edited == r.metrics.slots_regenerated, name


def test_no_fsrpc_variant_applies_a_cope_patch():
    from cope.policies.fsrpc_variants import (
        FSRPCProvenancePolicy, FSRPCStableIdsPolicy)
    for cls in (FSRPCStableIdsPolicy, FSRPCProvenancePolicy):
        assert_no_patch_application(cls)


def test_stable_ids_variant_preserves_identity_but_still_regenerates():
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I1",
                                            method="FSR-PC_stable_ids"))
    assert r.metrics.identity_preserved is True
    assert r.metrics.slots_regenerated > 0


def test_provenance_variant_emits_the_five_required_fields():
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I2",
                                            method="FSR-PC_provenance"))
    provs = [(s.get("payload") or {}).get("provenance")
             for e in r.store.trace.entries
             if e.get("kind") == "state_regenerated"
             for s in (e.get("slots") or [])]
    provs = [p for p in provs if p]
    assert provs
    for p in provs:
        assert set(p) >= {"reason", "source_event", "predecessor_slot",
                          "replacement_relation", "restoration_condition"}


def test_no_variant_is_weakened_by_hiding_history_or_progress():
    for name in FSRPC_VARIANTS:
        r = run_physical_episode(BasketTaskSpec(seed=0, condition="I3",
                                                method=name))
        assert r.metrics.completed_progress_preserved is True, name


def test_audit_scoring_is_not_defined_by_cope_operator_names():
    """Provenance must be a real evidence path, or the audit metric is circular."""
    plain = run_physical_episode(BasketTaskSpec(seed=0, condition="I2",
                                                method="FSR-PC"))
    prov = run_physical_episode(BasketTaskSpec(seed=0, condition="I2",
                                               method="FSR-PC_provenance"))
    assert prov.metrics.audit_coverage > plain.metrics.audit_coverage


# ===================== §8 I5 nested lineage =================================
def test_i5_is_registered_with_three_updates():
    c = interruption("I5", 0)
    assert c.n_updates == 3 and c.third_update is not None


@pytest.mark.parametrize("method", ADAPTERS)
def test_i5_leaves_exactly_one_active_butter_goal(method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I5",
                                            method=method))
    active = [s for s in r.store.state.ids()
              if "butter" in s and r.store.state.get(s).mode.value == "active"]
    assert len(active) == 1, f"{method}: {active}"


@pytest.mark.parametrize("method", ADAPTERS)
def test_i5_validity_checks(method):
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I5",
                                            method=method))
    m = r.metrics
    assert m.stale_goal_executions == 0, method
    assert m.cancelled_goal_violations == 0, method
    assert m.completed_progress_preserved is True, method
    assert m.lineage_correct is True, method
    assert m.invalid_restore_count == 0, method
    # the withdrawn detour must not have been executed
    assert not any(l["obj"] == "butter" and l["target"] == "basket_C"
                   and l["placed"] for l in r.legs), method
    # butter must be placed once, not twice
    assert sum(1 for l in r.legs if l["obj"] == "butter" and l["placed"]) <= 1


def test_i5_restores_the_original_grounding_not_the_detour():
    r = run_physical_episode(BasketTaskSpec(seed=0, condition="I5",
                                            method="CoPE"))
    ops = [(o.op.value, o.target_id or o.new_slot_id)
           for p in r.policy.patches for o in p.ops]
    assert ("Suspend", "g_butter") in ops
    assert any(op == "Override" for op, _ in ops)
    assert any(op == "Expire" and t and "basket_C" in t for op, t in ops)
    assert ("Restore", "g_butter") in ops
    assert r.store.state.get("g_butter").mode.value == "active"


def test_i5_is_not_rigged_for_cope():
    """Every adaptation arm must be able to pass I5."""
    for m in ADAPTERS:
        r = run_physical_episode(BasketTaskSpec(seed=0, condition="I5",
                                                method=m))
        assert r.metrics.revised_task_success is True, m


# ===================== §11 fairness =========================================
@pytest.mark.parametrize("cond", CONDS)
def test_paired_arms_receive_identical_adaptation_inputs(cond):
    fps = {m: run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                                  method=m)
                                   ).adaptation_input_fingerprints
           for m in ADAPTERS}
    assert len(set(map(tuple, fps.values()))) == 1, fps


@pytest.mark.parametrize("cond", CONDS)
def test_paired_arms_compile_identical_repair_goals(cond):
    fps = {m: run_physical_episode(BasketTaskSpec(seed=0, condition=cond,
                                                  method=m)
                                   ).requirement_fingerprints
           for m in ADAPTERS}
    assert len(set(map(tuple, fps.values()))) == 1, fps


# ===================== server path (backend_episode) wiring =================
# `backend_episode.run_backend_episode` can only be executed end to end on the
# LIBERO/MuJoCo host. These tests verify its WIRING here, so that the defect
# class the v2 audit found cannot silently return on the path that actually
# produces the published results.
def _backend_src() -> str:
    from cope.benchmark import backend_episode
    return open(backend_episode.__file__).read()


def test_server_path_uses_the_scheduler_not_goal_completion():
    src = _backend_src()
    assert "InterruptionScheduler" in src
    assert "scheduler.due(backend.current_step())" in src
    # the v2 trigger must be gone
    assert "trigger2 in completed_goal_ids" not in src
    assert "second_trigger_after_goal" not in src


def test_server_path_delivers_events_even_when_a_pick_fails():
    """The pick-failure branch previously `continue`d past every delivery check."""
    src = _backend_src()
    fail_branch = src[src.index('if not pick.get("success"):'):]
    fail_branch = fail_branch[:fail_branch.index("legs.append(leg)")]
    assert "pending_updates()" in fail_branch, (
        "a grasp failure can still suppress a scheduled interruption")


def test_server_path_drains_and_records_undelivered_events():
    src = _backend_src()
    assert "scheduler.finalize(backend.current_step())" in src
    assert "delivery_failure_reason" in src


def test_server_path_writes_the_new_required_artifacts():
    src = _backend_src()
    for artifact in ("interruptions.jsonl", "candidate_rollouts.jsonl",
                     "events.jsonl", "repair_trace.jsonl",
                     "adaptation_trace.jsonl", "state_snapshots.json",
                     "simulator.log", "video.mp4"):
        assert artifact in src, artifact


def test_event_hash_boundary_starts_before_the_physical_world_change():
    src = _backend_src()
    before = src.index(
        "simulator_state_hash_before_interruption = backend.state_hash()")
    world = src.index("world_record = apply_world_change(tag, update)")
    after_world = src.index(
        "simulator_state_hash_after_world_application = backend.state_hash()")
    assert before < world < after_world
    assert "hash_before=simulator_state_hash_before_interruption" in src
    assert '"simulator_state_hash_after_world_application"' in src


def test_candidate_rollout_uses_the_explicit_r2_audit_contract():
    row = _canonical_candidate_summary(
        event_id="I4-u2",
        candidate_index=2,
        candidate_name="repair-b",
        raw_summary={
            "checkpoint_hash": "same-state",
            "checks": [
                {"state_hash": "same-state", "new_unsafe_contact": False},
                {"state_hash": "later-state", "new_unsafe_contact": True},
            ],
            "collision": False,
            "handoff_error": 0.31,
            "restore_contract_ok": False,
            "ok": False,
            "reason": "invalid handoff",
            "restore_exact": True,
        },
    )
    assert row["event_id"] == "I4-u2"
    assert row["candidate_id"] == "I4-u2:candidate_02"
    assert row["checkpoint_hash"] == row["rollout_start_hash"] == "same-state"
    assert row["unsafe_contact"] is True
    assert row["handoff_error"] == 0.31
    assert row["restore_valid"] is False
    assert row["accepted"] is False and row["rejected"] is True
    assert row["rejection_reason"] == "invalid handoff"


def test_server_path_reports_separate_denominators():
    src = _backend_src()
    for k in ("all_events_delivered_episodes", "adaptation_valid_episodes",
              "controller_valid_episodes", "final_task_successes",
              "attempted_episodes", "valid_episodes"):
        assert k in src, k


def test_server_path_classifies_failure_layers():
    src = _backend_src()
    assert "from .failure_layers import classify" in src
    assert "layers.to_dict()" in src


def test_the_ablation_also_suppresses_a_backend_verifier():
    """Otherwise CoPE_no_rollout_verification would still be verified on LIBERO."""
    import inspect
    from cope.repair_bridge.engine import SharedRepairEngine
    src = inspect.getsource(SharedRepairEngine.repair)
    i = src.index("verifier_factory is not None")
    assert "disable_rollout_verification" in src[i:i + 400]


def test_real_libero_grasp_failure_uses_the_controller_layer():
    """The real harness nests grasp evidence under ``leg['pick']``."""
    layers = classify(
        task_metrics={"revised_task_success": False, "collision": False,
                      "unsafe_contact": False},
        schedule={"events": [], "schedule_fingerprint": "nominal",
                  "all_delivered": True},
        repair_outcomes=[],
        legs=[{"pick": {"success": False, "grasp_acquired": False,
                         "failure_reason": "grasp_not_acquired"},
               "failure_reason": "grasp_not_acquired"}],
        infrastructure_errors=[], required_artifacts_present=True,
        condition="nominal")
    assert layers.controller_failure is True
    assert layers.adaptation_failure is False
    assert layers.failure_layer == "controller"
    assert "grasp_not_acquired" in layers.failure_detail


def test_real_i5_moves_the_basket_in_mujoco_not_only_in_json():
    src = _backend_src()
    assert '(spec.condition == "I5" and tag == "u3")' in src
    assert 'backend.move_target("basket_B", delta)' in src


def test_real_schedule_is_finalized_before_failure_classification():
    src = _backend_src()
    assert src.index("scheduler.finalize(backend.current_step())") < src.index(
        "layers = classify(")


def test_real_results_carry_pairwise_fairness_evidence():
    src = _backend_src()
    for field in ("initial_simulator_state_hash", "backend_config_sha256",
                  "fairness_fingerprint", "adaptation_input_fingerprints",
                  "exogenous_adaptation_fingerprints",
                  "requirement_fingerprints"):
        assert field in src


def test_real_event_history_cannot_leak_prior_method_markers():
    src = _backend_src()
    assert "event_history.append(event_record)" not in src
    assert "method_independent_event_fact" in src
    history_block = src[src.index("method_independent_event_fact"):
                        src.index("before_state = store.state.to_dict()")]
    assert "pipeline_markers" not in history_block
    assert "adaptation_kind" not in history_block
    # The backend hash includes active_goal_id / cancelled_goal_ids.  Those are
    # intentionally representation-dependent for the regeneration baseline,
    # so the hash is audit evidence, not policy-visible task information.
    assert "simulator_state_hash" not in history_block


def test_real_simulator_hashes_remain_in_external_audit_artifacts():
    """Fair inputs must not come at the cost of losing replay evidence."""
    src = _backend_src()
    for field in ("simulator_state_hash_before_adaptation",
                  "simulator_state_hash_after_adaptation"):
        assert field in src
    for artifact in ("events.jsonl", "interruptions.jsonl",
                     "state_snapshots.json", "result.json"):
        assert artifact in src


def test_real_runner_routes_every_r2_stage_before_the_legacy_runner():
    from pathlib import Path
    runner = (Path(__file__).resolve().parents[1]
              / "scripts" / "run_cope_pilot.py").read_text()
    for stage in ("controller_gate", "regression_pilot",
                  "diagnostic_pilot", "verifier_probe"):
        assert stage in runner
    assert "return _run_real_r2_stage(args)" in runner
    assert "stage_a_controller_gate.json" in runner
    assert "stage_b_regression_pilot.json" in runner
    assert "stage_c_diagnostic_pilot.json" in runner
    assert "stage_d_verifier_ablation.json" in runner


def test_real_runner_resume_is_complete_bundle_only_and_non_destructive():
    from pathlib import Path
    runner = (Path(__file__).resolve().parents[1]
              / "scripts" / "run_cope_pilot.py").read_text()
    assert "--resume" in runner
    assert "_load_complete_real_result" in runner
    assert "REAL_EPISODE_ARTIFACTS" in runner
    assert "_preserve_incomplete_episode" in runner
    assert ".rename(archived)" in runner
    assert "resumed_completed_episodes" in runner
    assert "preserved_incomplete_episode_dirs" in runner


def test_safe_fallback_reopens_a_stage_for_later_scheduled_interruptions():
    src = _backend_src()
    reset = src[src.index("if outcome.safe_fallback"):
                src.index('event_record["simulator_state_hash_after_adaptation"]')]
    assert "engine.begin_leg(backend)" in reset
    assert "repair_program_reset_after_safe_fallback" in reset


def test_real_comparisons_use_exogenous_and_pre_treatment_causal_fairness():
    from pathlib import Path
    runner = (Path(__file__).resolve().parents[1]
              / "scripts" / "run_cope_pilot.py").read_text()
    for field in ("same_exogenous_adaptation_inputs",
                  "same_pre_treatment_adaptation_input",
                  "same_pre_treatment_compiled_repair_goal",
                  "same_pre_treatment_candidate_set",
                  "same_candidate_budget",
                  "post_treatment_adaptation_inputs_equal"):
        assert field in runner
    assert "all_event_exogenous_plus_pre_treatment_causal_pairing" in runner
