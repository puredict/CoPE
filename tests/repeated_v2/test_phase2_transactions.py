"""Executable contract negatives and deterministic transaction invariants."""

import copy
import json
from dataclasses import replace

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_sha256, to_primitive
from cope_benchmark.repeated_v2.generic_contract import GENERIC_VERSION
from cope_benchmark.repeated_v2.generic_engine import apply_generic
from cope_benchmark.repeated_v2.parsers import (ProposalError, parse_full_state, parse_generic_proposal,
    parse_planning_directive, parse_proposal)
from cope_benchmark.repeated_v2.patch_contract import (DIRECTIVE_VERSION, FULL_STATE_VERSION, PATCH_VERSION)
from cope_benchmark.repeated_v2.schema import (CommitmentOccurrence, ContinuationState, EvidenceRecord,
    ExecutionContext, PersistentLedger, ProgressCertificate, RelationEdge)
from cope_benchmark.repeated_v2.state_engine import (TransactionError, apply_cope, apply_full_state,
    default_protected_ids, protected_projection_sha256, semantic_history, validate_ledger)


def make_slot(name="goal:mug", **updates):
    value = dict(family_key=name, occurrence_id=name + "@1", role="achievement_goal",
        predicate="inside", arguments=["mug", "cabinet"], lifecycle="active", grounding_validity="valid",
        priority=10, hardness="hard", source="task", authority="user", restore_guard={},
        dependency_ids=[], provenance={"request": "public-request"}, evidence_ids=[],
        created_event_id="initial", retired_event_id=None)
    value.update(updates)
    return CommitmentOccurrence.from_dict(value)


def new_slot(name="goal:new"):
    value = make_slot(name).to_dict()
    for field in ("occurrence_id", "created_event_id", "retired_event_id"):
        del value[field]
    return value


def make_ledger():
    return PersistentLedger(0, (make_slot(), make_slot("goal:plate")))


def make_context():
    return ExecutionContext((), (ProgressCertificate("done", "inside", ("plate", "rack"),
        "satisfied", "verifier1", ("initial",), 0),),
        ContinuationState(None, None, None, None, (), None, 0))


def proposal(ledger, operations=(), *, checks=(), event_index=None, context=None, evidence_ids=()):
    scope = sorted({operation["occurrence_id"] for operation in operations if "occurrence_id" in operation})
    protected = default_protected_ids(ledger, scope)
    return dict(schema_version=PATCH_VERSION, episode_id="test", event_index=event_index or ledger.revision + 1,
        base_revision=ledger.revision, affected_scope=scope, protected_ids=list(protected),
        protected_projection_sha256=protected_projection_sha256(ledger, protected, context),
        evidence_ids=list(evidence_ids), checks=list(checks), operations=list(operations), confidence=1.0)


def generic(typed):
    tx = {key: value for key, value in typed.items() if key not in {"operations", "checks", "confidence"}}
    tx.update(schema_version=GENERIC_VERSION, assertions=[{**record, "kind": "validation"} for record in typed["checks"]],
        creates=[], writes=[], relation_additions=[], relation_removals=[], evidence_links=[])
    for operation in typed["operations"]:
        op, target = operation["op"], operation.get("occurrence_id")
        if op in {"INSERT", "OVERRIDE"}:
            tx["creates"].append({"request_id": operation["request_id"], "slot": operation["slot"]})
        if op in {"SUSPEND", "OVERRIDE", "EXPIRE", "RESTORE"}:
            tx["writes"].append({"occurrence_id": target, "path": "/lifecycle",
                "value": {"SUSPEND": "suspended", "OVERRIDE": "overridden", "EXPIRE": "expired", "RESTORE": "active"}[op],
                **({"assertion_id": operation["check_id"]} if op == "RESTORE" else {})})
        for field in ("priority", "restore_guard", "grounding_validity"):
            if field in operation:
                tx["writes"].append({"occurrence_id": target, "path": "/" + field, "value": operation[field]})
        if op == "OVERRIDE":
            tx["relation_additions"].append({"source_id": operation["request_id"], "relation": "overrides", "target_id": target})
        tx["relation_additions"].extend(operation.get("relation_additions", []))
        tx["relation_removals"].extend(operation.get("relation_removals", []))
    return tx


GUARD = {"hypothesis": "mug available", "min_confidence": 0.9}


def suspended():
    ledger = make_ledger()
    return apply_cope(ledger, proposal(ledger, [{"op": "SUSPEND", "occurrence_id": "goal:mug@1",
        "restore_guard": GUARD, "grounding_validity": "invalid"}]))


def restoration(ledger):
    check = dict(kind="REVALIDATE", check_id="v2", occurrence_id="goal:mug@1", evidence_ids=["e2"],
        guard=GUARD, result=True)
    patch = proposal(ledger, [{"op": "RESTORE", "occurrence_id": "goal:mug@1", "check_id": "v2",
        "grounding_validity": "valid"}], checks=[check], evidence_ids=["e2"])
    return patch, EvidenceRecord("e2", "mug available", 1, "verifier", 2)


def test_unmentioned_slots_remain_unchanged_and_history_strictly_extends():
    before = make_ledger()
    after = apply_cope(before, proposal(before, [{"op": "SET_PRIORITY", "occurrence_id": "goal:mug@1", "priority": 3}]))
    assert after.slots[1] == before.slots[1]
    assert after.slots[0].lifecycle.value == "active"
    assert after.revision == 1 and len(after.history_records) == 1
    assert before.revision == 0 and not before.history_records


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(extra=True), lambda p: p.update(base_revision=True),
    lambda p: p.update(confidence=float("nan")), lambda p: p.pop("protected_ids"),
    lambda p: p["operations"].append({"op": "REVALIDATE", "occurrence_id": "goal:mug@1"}),
    lambda p: p["operations"].append({"op": "DEMOTED", "occurrence_id": "goal:mug@1"}),
])
def test_parser_rejects_malformed_contract(mutation):
    value = proposal(make_ledger())
    mutation(value)
    with pytest.raises(ProposalError):
        parse_proposal("cope_typed_edit", value)


@pytest.mark.parametrize("raw", ['{"schema_version":"x","schema_version":"y"}',
    '```json\n{}\n```', '{"x":NaN}', '{"x":1e10000}', '[]', 'null', '{} trailing'])
def test_json_parser_does_not_extract_or_repair(raw):
    with pytest.raises(ProposalError):
        parse_proposal("cope_typed_edit", raw)


def test_parser_handles_immutable_public_mapping():
    from cope_benchmark.repeated_v2.canonical import freeze_json
    patch = proposal(make_ledger())
    assert parse_proposal("cope_typed_edit", freeze_json(patch)) == patch


@pytest.mark.parametrize("field", ["event_index", "base_revision"])
def test_mapping_parser_does_not_coerce_integral_float_to_integer(field):
    patch = proposal(make_ledger())
    patch[field] = float(patch[field])
    for raw in (patch, json.dumps(patch)):
        with pytest.raises(ProposalError):
            parse_proposal("cope_typed_edit", raw)


def test_new_occurrence_id_is_allocator_owned():
    before = make_ledger()
    patch = proposal(before, [{"op": "INSERT", "request_id": "request", "slot": new_slot()}])
    result = apply_cope(before, patch)
    assert result.slots[-1].occurrence_id == "goal:new@1"
    patch["operations"][0]["slot"]["occurrence_id"] = "model-selected@99"
    with pytest.raises(ProposalError):
        apply_cope(before, patch)


def test_transaction_failure_does_not_consume_ids_or_partially_apply():
    before = make_ledger()
    snapshot = canonical_sha256(before)
    patch = proposal(before, [{"op": "INSERT", "request_id": "request", "slot": new_slot()},
        {"op": "RESTORE", "occurrence_id": "goal:mug@1", "check_id": "missing"}])
    with pytest.raises(TransactionError):
        apply_cope(before, patch)
    assert canonical_sha256(before) == snapshot
    result = apply_cope(before, proposal(before, patch["operations"][:1]))
    assert result.slots[-1].occurrence_id == "goal:new@1"


@pytest.mark.parametrize("problem", ["stale", "hash", "outside_scope", "omitted_protection", "protected_write"])
def test_scope_revision_and_projection_protection(problem):
    before = make_ledger()
    patch = proposal(before, [{"op": "SET_PRIORITY", "occurrence_id": "goal:mug@1", "priority": 1}])
    if problem == "stale":
        patch["base_revision"] = 99
    elif problem == "hash":
        patch["protected_projection_sha256"] = "0" * 64
    elif problem == "outside_scope":
        patch["affected_scope"] = []
        patch["protected_ids"] = list(default_protected_ids(before))
        patch["protected_projection_sha256"] = protected_projection_sha256(before, patch["protected_ids"])
    elif problem == "omitted_protection":
        patch["protected_ids"] = []
        patch["protected_projection_sha256"] = protected_projection_sha256(before, [])
    else:
        patch["protected_ids"].append("goal:mug@1")
        patch["protected_projection_sha256"] = protected_projection_sha256(before, patch["protected_ids"])
    with pytest.raises(TransactionError):
        apply_cope(before, patch)


def test_zero_event_and_envelope_leakage_are_rejected():
    patch = proposal(make_ledger())
    patch["event_index"] = 0
    with pytest.raises(ProposalError):
        apply_cope(make_ledger(), patch)
    patch["event_index"] = 1
    patch["episode_id"] = "TARGET_OBJECT_DISPLACED"
    with pytest.raises(ProposalError):
        apply_cope(make_ledger(), patch)


def test_progress_is_in_protected_projection():
    ledger, context = make_ledger(), make_context()
    patch = proposal(ledger, context=context)
    changed = replace(context, progress=())
    with pytest.raises(TransactionError, match="hash mismatch"):
        apply_cope(ledger, patch, context=changed)


def test_authority_and_safety_cannot_be_rewritten_by_user():
    safety = make_slot("safety:never_drop", role="safety_requirement", source="safety", authority="safety")
    ledger = PersistentLedger(0, (safety,))
    patch = proposal(ledger, [{"op": "EXPIRE", "occurrence_id": safety.occurrence_id}])
    with pytest.raises(TransactionError, match="authority"):
        apply_cope(ledger, patch, authority="user")


def test_revalidation_is_only_an_audit_record():
    ledger = suspended()
    patch, evidence = restoration(ledger)
    patch = proposal(ledger, checks=patch["checks"], evidence_ids=["e2"])
    result = apply_cope(ledger, patch, evidence_records=[evidence])
    assert result.slots == ledger.slots
    assert result.history_records[-2]["kind"] == "validation"
    assert result.history_records[-2]["result"] is True


def test_fresh_restore_preserves_identity_and_grounding_is_explicit():
    ledger = suspended()
    patch, evidence = restoration(ledger)
    result = apply_cope(ledger, patch, evidence_records=[evidence])
    assert result.slots[0].occurrence_id == "goal:mug@1"
    assert result.slots[0].grounding_validity.value == "valid"
    patch["operations"][0].pop("grounding_validity")
    omitted = apply_cope(ledger, patch, evidence_records=[evidence])
    assert omitted.slots[0].grounding_validity.value == "invalid"


@pytest.mark.parametrize("fault", ["stale", "future", "wrong_hypothesis", "low_confidence", "wrong_guard",
    "wrong_occurrence", "missing_record", "false_result", "forged_result_field"])
def test_restore_requires_trusted_bound_fresh_evidence(fault):
    ledger = suspended()
    patch, evidence = restoration(ledger)
    records = [evidence]
    if fault == "stale": records = [replace(evidence, timestamp=1)]
    elif fault == "future": records = [replace(evidence, timestamp=3)]
    elif fault == "wrong_hypothesis": records = [replace(evidence, hypothesis="mug unavailable")]
    elif fault == "low_confidence": records = [replace(evidence, confidence=0.1)]
    elif fault == "wrong_guard": patch["checks"][0]["guard"] = {"hypothesis": "something else"}
    elif fault == "wrong_occurrence": patch["checks"][0]["occurrence_id"] = "goal:plate@1"
    elif fault == "missing_record": records = []
    elif fault == "false_result": patch["checks"][0]["result"] = False
    else: records = [{**evidence.to_dict(), "result": True}]
    with pytest.raises(TransactionError):
        apply_cope(ledger, patch, evidence_records=records)


def test_revalidation_from_prior_event_cannot_authorize_current_restore():
    ledger = suspended()
    patch, evidence = restoration(ledger)
    checked = apply_cope(ledger, proposal(ledger, checks=patch["checks"], evidence_ids=["e2"]), evidence_records=[evidence])
    with pytest.raises(TransactionError):
        apply_cope(checked, proposal(checked, patch["operations"]))


@pytest.mark.parametrize("retired", ["expired", "overridden"])
def test_retired_occurrence_cannot_restore_or_mutate(retired):
    slot = make_slot(lifecycle=retired, retired_event_id="prior", restore_guard=GUARD)
    ledger = PersistentLedger(0, (slot,))
    with pytest.raises(TransactionError):
        apply_cope(ledger, proposal(ledger, [{"op": "SET_PRIORITY", "occurrence_id": slot.occurrence_id, "priority": 9}]))
    with pytest.raises(TransactionError):
        apply_cope(ledger, proposal(ledger, [{"op": "RESTORE", "occurrence_id": slot.occurrence_id, "check_id": "v"}]))


def test_reissue_allocates_next_occurrence_without_reviving_old():
    ledger = PersistentLedger(0, (make_slot(lifecycle="expired", retired_event_id="prior"),))
    result = apply_cope(ledger, proposal(ledger, [{"op": "INSERT", "request_id": "new", "slot": new_slot("goal:mug")}]))
    assert result.slots[0] == ledger.slots[0]
    assert result.slots[1].occurrence_id == "goal:mug@2"


def test_exclusive_family_cannot_have_two_active_occurrences():
    ledger = make_ledger()
    with pytest.raises(TransactionError, match="exclusive"):
        apply_cope(ledger, proposal(ledger, [{"op": "INSERT", "request_id": "new", "slot": new_slot("goal:mug")}]))


@pytest.mark.parametrize("relation", ["depends_on", "precedes", "derived_from"])
def test_edge_specific_directed_cycles_rejected(relation):
    slots = make_ledger().slots
    ledger = PersistentLedger(0, slots, (RelationEdge(slots[0].occurrence_id, relation, slots[1].occurrence_id),
                                        RelationEdge(slots[1].occurrence_id, relation, slots[0].occurrence_id)))
    with pytest.raises(TransactionError, match="cycle"):
        validate_ledger(ledger)


def test_distinct_edge_types_are_not_collapsed_to_one_cycle_graph():
    slots = make_ledger().slots
    ledger = PersistentLedger(0, slots, (RelationEdge(slots[0].occurrence_id, "depends_on", slots[1].occurrence_id),
                                        RelationEdge(slots[1].occurrence_id, "derived_from", slots[0].occurrence_id)))
    assert validate_ledger(ledger) is ledger


def test_mixed_scheduling_cycle_is_rejected_before_compilation():
    slots = make_ledger().slots
    ledger = PersistentLedger(0, slots, (RelationEdge(slots[0].occurrence_id, "depends_on", slots[1].occurrence_id),
        RelationEdge(slots[0].occurrence_id, "precedes", slots[1].occurrence_id)))
    with pytest.raises(TransactionError, match="scheduling"):
        validate_ledger(ledger)


def test_symmetric_relations_allow_triangle_but_require_correct_families():
    slots = tuple(make_slot("family", occurrence_id=f"family@{index}", role="user_preference") for index in (1, 2, 3))
    edges = tuple(RelationEdge(f"family@{a}", "same_family", f"family@{b}") for a, b in ((1, 2), (2, 3), (3, 1)))
    assert validate_ledger(PersistentLedger(0, slots, edges))
    other = replace(slots[2], family_key="other", occurrence_id="other@1")
    with pytest.raises(TransactionError, match="same_family"):
        validate_ledger(PersistentLedger(0, (slots[0], other), (RelationEdge("family@1", "same_family", "other@1"),)))


def test_override_target_must_be_retired_and_conflicts_cannot_coactivate():
    slots = make_ledger().slots
    for relation in ("overrides", "conflicts_with"):
        with pytest.raises(TransactionError):
            validate_ledger(PersistentLedger(0, slots, (RelationEdge(slots[0].occurrence_id, relation, slots[1].occurrence_id),)))


@pytest.mark.parametrize("op", [
    {"op": "SET_PRIORITY", "occurrence_id": "goal:mug@1", "priority": 8},
    {"op": "SUSPEND", "occurrence_id": "goal:mug@1", "restore_guard": GUARD},
    {"op": "EXPIRE", "occurrence_id": "goal:mug@1"},
    {"op": "OVERRIDE", "occurrence_id": "goal:mug@1", "request_id": "new", "slot": new_slot()},
])
def test_generic_typed_materialization_semantic_parity(op):
    before = make_ledger()
    patch = proposal(before, [op])
    typed, neutral = apply_cope(before, patch), apply_generic(before, generic(patch))
    assert typed.slots == neutral.slots and typed.relations == neutral.relations
    assert semantic_history(typed) == semantic_history(neutral)


@pytest.mark.parametrize("poison", [{"note": "SET_PRIORITY"}, {"ground_truth": "x"},
    {"note": '{"canonical_state":{"x":1}}'}, {"RESTORE": "x"},
    {"TARGET_OBJECT_DISPLACED": "x"}, {"note": '{"SET_PRIORITY":"x"}'},
    {"method_name": "untrusted"}, {"note": "/home/user/condition.json"}])
def test_recursive_parser_leakage_scan(poison):
    before = make_ledger()
    patch = proposal(before, [{"op": "INSERT", "request_id": "new", "slot": new_slot()}])
    patch["operations"][0]["slot"]["provenance"] = poison
    with pytest.raises(ProposalError):
        parse_proposal("cope_typed_edit", patch)
    with pytest.raises(ProposalError):
        parse_generic_proposal(generic(patch))


def test_generic_rejects_immutable_owner_paths_and_legacy_lifecycle():
    ledger = make_ledger()
    tx = generic(proposal(ledger, [{"op": "SET_PRIORITY", "occurrence_id": "goal:mug@1", "priority": 9}]))
    for path, value in (("/source", "user"), ("/occurrence_id", "wrong@1"), ("/lifecycle", "demoted"), ("/priority", True)):
        invalid = copy.deepcopy(tx)
        invalid["writes"][0].update(path=path, value=value)
        with pytest.raises(ProposalError):
            apply_generic(ledger, invalid)


def test_full_regeneration_omissions_are_never_recovered_by_logger():
    before = suspended()
    state = dict(schema_version=FULL_STATE_VERSION, base_revision=before.revision, slots=[], relations=[],
        semantic_history=[], initial_facts=[], progress_certificates=[], continuation_assumptions={})
    accepted = apply_full_state(before, state, event_id="event2", event_index=2)
    assert accepted.slots == () and len(accepted.history_records) == 1
    assert accepted.history_records[0]["kind"] == "full_state_regenerated"
    state.pop("semantic_history")
    with pytest.raises(ProposalError):
        parse_full_state(state)


def test_full_regeneration_cannot_forge_or_recycle_allocator_ids():
    before = PersistentLedger(0, ())
    state = dict(schema_version=FULL_STATE_VERSION, base_revision=0, slots=[make_slot().to_dict()], relations=[],
        semantic_history=[], initial_facts=[], progress_certificates=[], continuation_assumptions={})
    state["slots"][0]["occurrence_id"] = "goal:mug@999"
    with pytest.raises(TransactionError, match="allocator"):
        apply_full_state(before, state)
    state["slots"][0]["occurrence_id"] = "goal:mug@2"
    with pytest.raises(TransactionError, match="allocator"):
        apply_full_state(before, state)
    accepted = apply_full_state(before, state, identity_registry={"goal:mug@1": "goal:mug"})
    assert accepted.slots[0].occurrence_id == "goal:mug@2"


def test_full_regeneration_retains_only_reproduced_semantic_history():
    before = suspended()
    state = dict(schema_version=FULL_STATE_VERSION, base_revision=before.revision,
        slots=to_primitive(before.slots), relations=to_primitive(before.relations),
        semantic_history=semantic_history(before), initial_facts=[], progress_certificates=[],
        continuation_assumptions={})
    accepted = apply_full_state(before, state, event_id="event2", event_index=2)
    assert semantic_history(accepted) == semantic_history(before)
    assert accepted.history_records[-1]["kind"] == "full_state_regenerated"
    state["semantic_history"] = []
    omitted = apply_full_state(before, state, event_id="event2", event_index=2)
    assert semantic_history(omitted) == []


def test_directive_missing_semantics_rejected_without_defaults():
    directive = dict(schema_version=DIRECTIVE_VERSION, initial_facts=[], active_goal_occurrence_ids=[],
        remaining_goals=[], hard_constraints=[], soft_preferences=[], forbidden_regressions=[],
        grounding_bindings=[], restore_eligibility=[], progress_certificates=[],
        continuation_assumptions={}, ordered_macro_plan=[])
    assert parse_planning_directive(directive) == directive
    for field in list(directive):
        incomplete = copy.deepcopy(directive)
        del incomplete[field]
        with pytest.raises(ProposalError):
            parse_planning_directive(incomplete)
    directive["remaining_goals"] = [{"predicate": "inside", "arguments": ["mug", "cabinet"]}]
    with pytest.raises(ProposalError):
        parse_planning_directive(directive)
