from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_json, canonical_sha256, freeze_json, strict_loads
from cope_benchmark.repeated_v2.enums import CommitmentRole, GroundingValidity, Lifecycle, Satisfaction
from cope_benchmark.repeated_v2.schema import (
    BeliefFact, CommitmentOccurrence, ContinuationState, ExecutionContext,
    PersistentLedger, ProgressCertificate, PublicEventPayload,
    EventEvidence, HiddenCanonicalEffect, PlanningProblem, record_json_schema,
)


def slot(**changes):
    fields = dict(family_key="goal:mug", occurrence_id="goal:mug@1", role=CommitmentRole.ACHIEVEMENT_GOAL,
                  predicate="inside", arguments=("mug", "cabinet"), lifecycle=Lifecycle.ACTIVE,
                  grounding_validity=GroundingValidity.VALID, priority=1, hardness="hard",
                  source="task", authority="user", restore_guard={"reachable": True})
    fields.update(changes)
    return CommitmentOccurrence(**fields)


def test_canonical_order_unicode_numeric_and_sequence_contract():
    assert canonical_json({"中": [1.0, -0.0], "a": True}) == '{"a":true,"中":[1,0]}'
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    assert canonical_sha256(["a", "b"]) != canonical_sha256(["b", "a"])
    assert canonical_sha256({"n": 1.0}) == canonical_sha256({"n": 1})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {1: "bad"}, {"bad": {False: 1}}, {1, 2}, object(), "\ud800"])
def test_canonical_rejects_non_json_and_nonfinite(value):
    with pytest.raises((ValueError, UnicodeError)):
        canonical_json(value)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":{"b":1,"b":2}}', 'NaN', '1e999'])
def test_strict_json_rejects_ambiguous_numbers_and_keys(text):
    with pytest.raises(ValueError):
        strict_loads(text)


def test_canonical_rejects_cycles_but_allows_shared_immutable_values():
    array = []
    array.append(array)
    with pytest.raises(ValueError, match="cyclic"):
        canonical_json(array)
    leaf = {"x": 1}
    assert canonical_json([leaf, leaf]) == '[{"x":1},{"x":1}]'


def test_schema_recursively_snapshots_input_and_to_dict_is_detached():
    source = {"nested": [{"x": 1}]}
    original = slot(provenance=source)
    before = original.sha256
    source["nested"][0]["x"] = 9
    assert original.sha256 == before
    exported = original.to_dict()
    exported["provenance"]["nested"][0]["x"] = 10
    assert original.sha256 == before
    with pytest.raises(TypeError):
        original.provenance["nested"][0]["x"] = 20
    with pytest.raises(FrozenInstanceError):
        original.priority = 3
    assert CommitmentOccurrence.from_dict(original.to_dict()) == original


@pytest.mark.parametrize("change", [{"lifecycle": "demoted"}, {"priority": math.nan}, {"arguments": "mug"},
    {"priority": True}, {"family_key": ""}, {"lifecycle": "expired"}, {"retired_event_id": "e1"},
    {"dependency_ids": ("goal:mug@1",)}, {"grounding_validity": "satisfied"}])
def test_occurrence_schema_fails_closed(change):
    with pytest.raises(ValueError):
        slot(**change)


def test_no_lifecycle_progress_grounding_conflation_and_unknown_fields_rejected():
    occurrence = slot(lifecycle=Lifecycle.SUSPENDED, grounding_validity=GroundingValidity.INVALID)
    assert occurrence.lifecycle is Lifecycle.SUSPENDED
    assert occurrence.grounding_validity is GroundingValidity.INVALID
    assert "satisfaction" not in occurrence.to_dict()
    with pytest.raises(ValueError, match="unknown"):
        CommitmentOccurrence.from_dict({**occurrence.to_dict(), "status": "active"})
    with pytest.raises(ValueError, match="incomplete"):
        PublicEventPayload.from_dict({"event_id": "e1"})


def test_ledger_rejects_duplicate_ids_and_dangling_references():
    with pytest.raises(ValueError, match="duplicate"):
        PersistentLedger(0, (slot(), slot()))
    with pytest.raises(ValueError, match="dangling"):
        PersistentLedger(0, (slot(dependency_ids=("unknown@1",)),))


def test_progress_has_verifier_backing_and_legitimate_invalidation_fields():
    progress = ProgressCertificate("m1", "inside", ("mug", "cabinet"), Satisfaction.SATISFIED,
                                   "v1", ("e1",), 10)
    invalidated = replace(progress, affected_by_event_ids=("event-2",), currently_preserved=False)
    context = ExecutionContext((BeliefFact("visible", True, .9, ("e1",), 10),), (invalidated,),
                               ContinuationState("transport", "place", 2, "mug", ("place",), None, 10))
    assert ExecutionContext.from_dict(context.to_dict()) == context
    assert context.progress[0].affected_by_event_ids == ("event-2",)
    with pytest.raises(ValueError, match="evidence"):
        replace(progress, evidence_ids=())
    with pytest.raises(ValueError, match="preserved"):
        replace(progress, satisfaction=Satisfaction.UNRESOLVED)


@pytest.mark.parametrize("name,record_type", [
    ("public_event_payload", PublicEventPayload), ("event_evidence", EventEvidence),
    ("commitment_occurrence", CommitmentOccurrence), ("persistent_ledger", PersistentLedger),
    ("execution_context", ExecutionContext), ("hidden_canonical_effect", HiddenCanonicalEffect),
    ("planning_problem", PlanningProblem),
])
def test_checked_in_json_schemas_match_runtime_contracts(name, record_type):
    import jsonschema
    path = Path(__file__).resolve().parents[2] / "schemas" / "repeated_v2" / (name + ".schema.json")
    schema = strict_loads(path.read_text())
    assert schema == record_json_schema(record_type)
    jsonschema.Draft202012Validator.check_schema(schema)


def test_json_schema_rejects_additional_hidden_fields_and_demoted_lifecycle():
    import jsonschema
    validator = jsonschema.Draft202012Validator(record_json_schema(CommitmentOccurrence))
    validator.validate(slot().to_dict())
    for changed in ({"lifecycle": "demoted"}, {"expected_operator": "INSERT"}):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({**slot().to_dict(), **changed})
