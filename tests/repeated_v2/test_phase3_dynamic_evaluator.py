import pytest
from cope_benchmark.repeated_v2.dynamic_evaluator import SealedDynamicEvaluator, EvaluationError


def goal(oid="old", *, lifecycle="active", predicate="placed", role="achievement_goal"):
    return dict(occurrence_id=oid, lifecycle=lifecycle, predicate=predicate,
                arguments=["cup", "tray"], role=role, hardness="hard")


def truth(predicate, arguments):
    return True


def test_cancel_and_reissue_same_predicate_scores_identity_not_static_success():
    evaluator = SealedDynamicEvaluator({"slots": [goal()]}, required_events=2)
    evaluator.update_canonical({"slots": [goal(lifecycle="expired")]}, event_id="cancel")
    evaluator.update_canonical({"slots": [goal(lifecycle="expired"), goal("new")]}, event_id="reissue")
    evaluator.monitor(truth, step=3, action={"macro_id": "m", "target_occurrence_id": "old"})
    result = evaluator.evaluate(truth)
    assert result.active_goals_satisfied and not result.success
    assert result.wrong_occurrence_execution == ("old",)
    assert result.active_goal_ids == ("new",)


def test_omitted_canonical_goal_is_still_required_and_empty_cancellation_is_valid():
    evaluator = SealedDynamicEvaluator({"slots": [goal()]}, required_events=1)
    assert not evaluator.evaluate(lambda *_: False).success
    evaluator.update_canonical({"slots": [goal(lifecycle="expired")]}, event_id="cancel")
    assert evaluator.evaluate(lambda *_: False).success


def test_hard_violation_latches_even_after_recovery():
    evaluator = SealedDynamicEvaluator({"slots": [goal(role="safety_requirement")]}, required_events=0)
    evaluator.monitor(lambda *_: False, step=0)
    assert evaluator.evaluate(truth).hard_constraint_violations == ("old",)
    assert not evaluator.evaluate(truth).success


def test_progress_exemption_is_only_from_explicit_hidden_invalidation():
    evaluator = SealedDynamicEvaluator({"slots": []}, required_events=1)
    evaluator.certify_progress({"milestone_id": "m", "predicate": "placed", "arguments": [], "verifier_record_id": "sealed1"})
    evaluator.update_canonical({"slots": []}, event_id="event", legitimately_invalidated_milestones=["m"])
    assert evaluator.evaluate(lambda *_: False).success
    evaluator.certify_progress({"milestone_id": "m2", "predicate": "placed", "arguments": [], "verifier_record_id": "sealed2"})
    assert evaluator.evaluate(lambda *_: False).completed_step_regression == ("m2",)


def test_redundant_new_macro_is_regression_but_continuing_same_macro_is_not():
    evaluator = SealedDynamicEvaluator({"slots": [goal()]}, required_events=0)
    action = {"macro_id": "m", "target_occurrence_id": "old"}
    evaluator.monitor(truth, step=0, action=action)
    evaluator.monitor(truth, step=1, action=action)
    assert evaluator.evaluate(truth).success
    evaluator.monitor(truth, step=2, action={**action, "macro_id": "m2"})
    assert not evaluator.evaluate(truth).success


def test_resume_roundtrip_and_required_events_timeout_manual_failure():
    evaluator = SealedDynamicEvaluator({"slots": [goal()]}, required_events=1)
    evaluator.monitor(truth, step=0)
    copy = SealedDynamicEvaluator({"slots": []}, required_events=1)
    copy.restore(evaluator.snapshot())
    assert copy.snapshot() == evaluator.snapshot()
    assert not copy.evaluate(truth).success
    copy.update_canonical({"slots": [goal()]}, event_id="e")
    assert copy.evaluate(truth).success
    assert not copy.evaluate(truth, timeout=True).success
    assert not copy.evaluate(truth, manual_intervention=True).success


def test_unknown_truth_fails_closed_and_runtime_verifier_cannot_supply_score():
    evaluator = SealedDynamicEvaluator({"slots": [goal()]}, required_events=0)
    with pytest.raises(EvaluationError):
        evaluator.evaluate(lambda *_: None)
    with pytest.raises(EvaluationError):
        evaluator.monitor(truth, step=0, action={"target_occurrence_id": "old"})


def test_planning_fidelity_tracks_omission_without_repair_and_ignores_metadata():
    from cope_benchmark.repeated_v2.dynamic_evaluator import FIDELITY_FIELDS, compare_planning_problems
    canonical = {name: [] for name in FIDELITY_FIELDS}
    canonical.update(continuation_assumptions={}, active_goal_occurrence_ids=["old", "new"], source_method="oracle")
    proposed = {**canonical, "active_goal_occurrence_ids": ["new"], "source_method": "baseline"}
    result = compare_planning_problems(proposed, canonical)
    assert not result["planning_fidelity_exact"]
    assert result["planning_fidelity_fields"]["active_goal_occurrence_ids"]["f1"] == pytest.approx(2/3)
    assert proposed["active_goal_occurrence_ids"] == ["new"]
    assert compare_planning_problems({**canonical, "source_method": "baseline"}, canonical)["planning_fidelity_exact"]


def test_history_corruption_does_not_award_ledgerless_representation_a_pass():
    from cope_benchmark.repeated_v2.dynamic_evaluator import protected_history_corruption
    before = {"ledger": {"slots": [goal(), goal("unaffected")]}}
    after = {"ledger": {"slots": [goal(lifecycle="expired"), goal("unaffected")]}}
    assert protected_history_corruption(before, after, allowed_occurrence_ids=["old"]) is False
    assert protected_history_corruption(before, after, allowed_occurrence_ids=[]) is True
    assert protected_history_corruption({}, {}, allowed_occurrence_ids=[]) is None


def test_representation_neutral_protection_audit_catches_missing_obligation():
    from cope_benchmark.repeated_v2.dynamic_evaluator import compare_protected_planning_projection
    before = goal("protected")
    projection = [{"field": "remaining_goals", "selector": "occurrence_id",
                   "ids": ["protected"], "expected": [before]}]
    assert compare_protected_planning_projection({"remaining_goals": [before, goal("changed")]}, projection)["history_corruption"] is False
    directive = {"remaining_goals": [goal("changed")]}
    assert compare_protected_planning_projection(directive, projection)["history_corruption"] is True
    assert directive == {"remaining_goals": [goal("changed")]}
