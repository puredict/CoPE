from dataclasses import replace

import pytest

from cope_benchmark.repeated_v2.enums import EventFamily
from cope_benchmark.repeated_v2.evidence import EventLeakageError, assert_public_safe, public_event_payload, validate_evidence_references
from cope_benchmark.repeated_v2.schema import BeliefFact, EvidenceRecord, HiddenCanonicalEffect, PublicEventPayload, SealedEvaluation


def payload(**changes):
    fields = dict(event_id="event-opaque", event_index=1, hypothesis="The mug position changed.", confidence=.8,
                  evidence_ids=("ev1",), timestamp=10, provenance="shared_detector", observation_refs=("obs1",))
    fields.update(changes)
    return PublicEventPayload(**fields)


@pytest.mark.parametrize("leak", [
    {"hidden_cause": "external"}, {"outer": [{"expected_operator": "insert"}]},
    {"nested": {"expected-target-occurrence-id": "goal@1"}},
    {"event": {"affected_occurrence_ids": ["goal@1"]}},
    {"hypothesis": '{"deep":{"canonical_state":{"goal":true}}}'},
    {"hypothesis": "expected_operator: insert"}, {"hypothesis": "Use EXPIRE on the old goal."},
    {"hypothesis": "TARGET_OBJECT_DISPLACED"}, {"metadata": {"FaultLabel": "shift"}},
])
def test_recursive_leakage_scan_rejects_hidden_labels_and_serialized_truth(leak):
    with pytest.raises(EventLeakageError):
        assert_public_safe(leak)


def test_public_record_constructor_scans_values_and_projection_rejects_merged_records():
    with pytest.raises(EventLeakageError):
        payload(hypothesis="The expected operation is RESTORE.")
    hidden = HiddenCanonicalEffect("event-opaque", EventFamily.TARGET_OBJECT_DISPLACED,
                                    ("goal@1",), {"expected_operator": "EXPIRE"}, {})
    for value in (hidden, {"public": payload().to_dict(), "hidden": hidden.to_dict()}, payload().to_dict()):
        with pytest.raises(EventLeakageError):
            public_event_payload(value)
    assert set(public_event_payload(payload())) == set(payload().to_dict())


def test_evidence_is_confident_timestamped_provenanced_and_references_resolve():
    record = EvidenceRecord("ev1", "The mug is visible.", .9, "shared_detector", 9, ("obs1",))
    validate_evidence_references(payload(), (record,))
    for records in ((), (record, record), (replace(record, timestamp=11),)):
        with pytest.raises(ValueError):
            validate_evidence_references(payload(), records)
    for changes in ({"confidence": 1.1}, {"provenance": ""}, {"timestamp": -1}, {"timestamp": True}, {"evidence_ids": ()}):
        with pytest.raises(ValueError):
            payload(**changes)


def test_nested_scoring_record_and_hidden_belief_value_are_rejected():
    evaluation = SealedEvaluation("eval1", "e1", {"success": True}, "truth-hash")
    for value in (evaluation, {"records": [evaluation]}, {"records": [evaluation.to_dict()]}):
        with pytest.raises(EventLeakageError):
            assert_public_safe(value)
    with pytest.raises(EventLeakageError):
        BeliefFact("pose", {"hidden_cause": "oracle"}, 1., ("evidence1",), 10)
