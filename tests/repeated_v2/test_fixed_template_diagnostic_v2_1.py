"""Qualification tests for the separate hand-designed semantics diagnostic."""

import json

import pytest

from cope_benchmark.repeated_v2.adapters import (
    DEFAULT_FIXED_TEMPLATE_RULES, FixedEventTemplateEditor, leave_one_realization_out,
)
from cope_benchmark.repeated_v2.enums import NON_ORACLE_METHODS
from cope_benchmark.repeated_v2.oracle_fixtures import initial_fixture
from cope_benchmark.repeated_v2.schema import EvidenceRecord, EventEvidence


def event(index, hypothesis, *, user_message=None):
    return EventEvidence(event_id=f"visible-{index}", event_index=index,
        hypothesis=hypothesis, confidence=1.0, evidence_ids=(f"visible-e{index}",),
        timestamp=index, provenance="shared_public_observer", user_message=user_message,
        affected_entity_hypotheses=("mug",))


def evidence(item):
    return (EvidenceRecord(item.evidence_ids[0], item.hypothesis, item.confidence,
                           item.provenance, item.timestamp),)


def editor():
    ledger, context = initial_fixture()
    adapter = FixedEventTemplateEditor()
    adapter.start_episode(task={"episode_id": "fixed-diagnostic", "instruction": "Put the mug on the shelf."},
                          ledger=ledger, context=context)
    return adapter, context


def test_same_visible_symptom_can_require_different_transition_from_public_user_language():
    temporary, context = editor()
    occluded = event(1, "The mug is not visible.")
    result = temporary.on_event(evidence=occluded, context=context,
        public_history=[{"task_update": {"restore_guard": {
            "hypothesis": "mug is available again", "min_confidence": 0.9}}}],
        evidence_records=evidence(occluded))
    assert result.accepted and result.transition == "SUSPEND"
    assert temporary.ledger.slots[0].lifecycle.value == "suspended"

    cancelled, context = editor()
    explicit = event(1, "The mug is not visible.", user_message="Cancel placing the mug on the shelf.")
    result = cancelled.on_event(evidence=explicit, context=context, public_history=[],
                                evidence_records=evidence(explicit))
    assert result.accepted and result.transition == "EXPIRE"
    assert cancelled.ledger.slots[0].lifecycle.value == "expired"


@pytest.mark.parametrize("description", [
    "The mug is temporarily occluded.",
    "The mug is temporarily unavailable.",
    "A safety boundary blocks the mug.",
])
def test_different_visible_realizations_share_the_same_transition(description):
    adapter, context = editor()
    visible = event(1, description)
    outcome = adapter.on_event(evidence=visible, context=context,
        public_history=[{"task_update": {"restore_guard": {
            "hypothesis": "mug is available again", "min_confidence": 0.9}}}],
        evidence_records=evidence(visible))
    assert outcome.accepted and outcome.transition == "SUSPEND"


def test_leave_one_realization_out_exposes_fixed_lookup_failure():
    rules = leave_one_realization_out(DEFAULT_FIXED_TEMPLATE_RULES, "temporary-interference")
    ledger, context = initial_fixture()
    adapter = FixedEventTemplateEditor(rules=rules)
    adapter.start_episode(task={"episode_id": "held-out"}, ledger=ledger, context=context)
    visible = event(1, "The mug is temporarily occluded.")
    outcome = adapter.on_event(evidence=visible, context=context, public_history=[],
                               evidence_records=evidence(visible))
    assert not outcome.accepted
    assert outcome.rejection == "visible evidence matched no rule"
    assert adapter.ledger == ledger


def test_canonical_family_names_are_rejected_and_diagnostic_stays_outside_primary_methods():
    adapter, context = editor()
    with pytest.raises(ValueError, match="hidden family label"):
        event(1, "TEMPORARY_NO_GO_APPEARS")
    assert "fixed_event_template_editor" not in {method.value for method in NON_ORACLE_METHODS}


def test_restore_uses_fresh_bound_evidence_and_snapshot_round_trips():
    adapter, context = editor()
    blocked = event(1, "The mug is temporarily unavailable.")
    history = [{"task_update": {"restore_guard": {
        "hypothesis": "mug is available again", "min_confidence": 0.9}}}]
    assert adapter.on_event(evidence=blocked, context=context, public_history=history,
                            evidence_records=evidence(blocked)).accepted
    restored = event(2, "mug is available again")
    outcome = adapter.on_event(evidence=restored, context=context, public_history=history,
                               evidence_records=evidence(restored))
    assert outcome.accepted and outcome.transition == "RESTORE" and outcome.output_tokens == 0
    assert adapter.ledger.slots[0].lifecycle.value == "active"
    snapshot = json.loads(json.dumps(adapter.snapshot()))
    clone = FixedEventTemplateEditor()
    clone.restore(snapshot)
    assert clone.snapshot() == snapshot


def test_replacement_cancellation_and_reissue_use_public_commitment_records():
    adapter, context = editor()
    replacement = {
        "family_key": "goal:mug:cabinet", "role": "achievement_goal",
        "predicate": "inside", "arguments": ["mug", "cabinet"],
    }
    changed = event(1, "Put the mug in the cabinet instead.",
                    user_message="Put the mug in the cabinet instead.")
    outcome = adapter.on_event(evidence=changed, context=context,
        public_history=[{"task_update": {"replacement_commitment": replacement}}],
        evidence_records=evidence(changed))
    assert outcome.accepted and outcome.transition == "OVERRIDE"
    assert {slot.occurrence_id: slot.lifecycle.value for slot in adapter.ledger.slots}[
        "goal:mug:cabinet@1"] == "active"

    cancelled = event(2, "The mug is present.", user_message="Cancel the cabinet request.")
    assert adapter.on_event(evidence=cancelled, context=context, public_history=[],
                            evidence_records=evidence(cancelled)).accepted
    reissued = event(3, "The shelf request is needed.",
                     user_message="Please request again that the mug goes on the shelf.")
    original = {
        "family_key": "goal:mug:shelf", "role": "achievement_goal",
        "predicate": "inside", "arguments": ["mug", "shelf"],
    }
    outcome = adapter.on_event(evidence=reissued, context=context,
        public_history=[{"task_update": {"new_commitment": original}}],
        evidence_records=evidence(reissued))
    assert outcome.accepted and outcome.transition == "INSERT"
    assert any(slot.occurrence_id == "goal:mug:shelf@2" for slot in adapter.ledger.slots)
