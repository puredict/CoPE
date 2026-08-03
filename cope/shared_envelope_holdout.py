from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from cope.shared_commit_envelope import (
    SharedEnvelopeCase,
    _event,
    _meta,
    _record,
    _state,
    apply_typed_operations,
    build_development_cases,
)
from cope.types import canonical_json


def _base_state() -> dict[str, Any]:
    return _state(
        [
            _record("c0", status="active", owner="owner", priority=3, requires_all=[], requires_any=[]),
            _record("c1", status="active", owner="owner", priority=2, requires_all=["c0"], requires_any=[]),
            _record("c2", status="pending", owner="owner", priority=1, requires_all=[], requires_any=["c0", "c1"]),
            _record("c3", status="suspended", owner="owner", priority=5, requires_all=[], requires_any=[], overridden_by="c0"),
        ],
        [
            _record("a0", commitment_id="c0", status="running", progress=0.4, reversible=True),
            _record("a1", commitment_id="c1", status="pending", progress=0.0, reversible=True),
            _record("a2", commitment_id="c3", status="paused", progress=0.6, reversible=False),
        ],
        [
            _record("p0", commitment_id="c0", value=0.4, valid=True),
            _record("p1", commitment_id="c1", value=0.0, valid=True),
        ],
        [_record("r0", target_id="c3", after_id="c0", status="pending")],
        {"clear": True, "evidence_ok": True, "retry_count": 0, "safe_stop": False},
    )


def _rule(index: int, operation: Mapping[str, Any]) -> dict[str, str]:
    name = operation["op"]
    if name == "SetCommitmentStatus":
        text = f"Set commitment {operation['target_id']} status exactly to {operation['status']}."
    elif name == "SetCommitmentField":
        text = f"Set commitment {operation['target_id']} field {operation['field']} to canonical JSON {canonical_json(operation['value'])}."
    elif name == "InsertCommitment":
        text = f"Insert this commitment record exactly: {canonical_json(operation['record'])}."
    elif name == "SetActionFields":
        text = f"For action {operation['target_id']}, set exactly these fields and preserve its other fields: {canonical_json(operation['fields'])}."
    elif name == "InsertAction":
        text = f"Insert this action record exactly: {canonical_json(operation['record'])}."
    elif name == "SetProgressFields":
        text = f"For progress record {operation['target_id']}, set exactly these fields and preserve its other fields: {canonical_json(operation['fields'])}."
    elif name == "InsertProgress":
        text = f"Insert this progress record exactly: {canonical_json(operation['record'])}."
    elif name == "AddRestoration":
        text = f"Append this restoration record exactly: {canonical_json(operation['record'])}."
    elif name == "RemoveRestoration":
        text = f"Remove exactly the restoration record with id {operation['target_id']}."
    elif name == "SetFact":
        text = f"Set fact {operation['key']} to canonical JSON {canonical_json(operation['value'])}."
    else:
        raise ValueError(name)
    return {"id": f"R{index}", "text": text}


def _specs() -> list[tuple[str, str, Sequence[dict[str, Any]]]]:
    new_c = lambda identifier, status="active", priority=4: _record(
        identifier, status=status, owner="owner", priority=priority,
        requires_all=[], requires_any=[]
    )
    new_a = lambda identifier, commitment: _record(
        identifier, commitment_id=commitment, status="pending", progress=0.0,
        reversible=True
    )
    new_p = lambda identifier, commitment, value=0.0: _record(
        identifier, commitment_id=commitment, value=value, valid=True
    )
    return [
        ("single_root_expiry", "expire", [{"op":"SetCommitmentStatus","target_id":"c0","status":"expired"}]),
        ("expiry_with_running_action", "expire", [{"op":"SetCommitmentStatus","target_id":"c0","status":"expired"},{"op":"SetActionFields","target_id":"a0","fields":{"status":"halted"}}]),
        ("conjunctive_dependency_block", "prerequisite_lost", [{"op":"SetCommitmentStatus","target_id":"c0","status":"failed"},{"op":"SetCommitmentStatus","target_id":"c1","status":"blocked"},{"op":"SetActionFields","target_id":"a1","fields":{"status":"blocked"}}]),
        ("disjunctive_dependency_survival", "alternative_lost", [{"op":"SetCommitmentStatus","target_id":"c0","status":"unavailable"},{"op":"SetCommitmentField","target_id":"c2","field":"requires_any","value":["c1"]}]),
        ("priority_raise_without_preemption", "priority_update", [{"op":"SetCommitmentField","target_id":"c1","field":"priority","value":4}]),
        ("priority_raise_with_preemption", "priority_update", [{"op":"SetCommitmentField","target_id":"c1","field":"priority","value":7},{"op":"SetActionFields","target_id":"a0","fields":{"status":"paused"}},{"op":"SetActionFields","target_id":"a1","fields":{"status":"running"}}]),
        ("replacement_insert_only", "replacement", [{"op":"SetCommitmentStatus","target_id":"c2","status":"superseded"},{"op":"InsertCommitment","record":new_c("n07",priority=1)}]),
        ("replacement_retarget_action", "replacement", [{"op":"SetCommitmentStatus","target_id":"c1","status":"superseded"},{"op":"InsertCommitment","record":new_c("n08",priority=2)},{"op":"SetActionFields","target_id":"a1","fields":{"commitment_id":"n08"}}]),
        ("replacement_retarget_progress", "replacement", [{"op":"SetCommitmentStatus","target_id":"c0","status":"superseded"},{"op":"InsertCommitment","record":new_c("n09",priority=3)},{"op":"SetProgressFields","target_id":"p0","fields":{"commitment_id":"n09","valid":True}}]),
        ("temporary_override_insert", "override", [{"op":"SetCommitmentStatus","target_id":"c0","status":"suspended"},{"op":"InsertCommitment","record":new_c("n10",priority=9)},{"op":"InsertAction","record":new_a("na10","n10")}]),
        ("temporary_override_with_restore", "override", [{"op":"SetCommitmentStatus","target_id":"c1","status":"suspended"},{"op":"SetActionFields","target_id":"a1","fields":{"status":"paused"}},{"op":"InsertCommitment","record":new_c("n11",priority=8)},{"op":"AddRestoration","record":_record("nr11",target_id="c1",after_id="n11",status="pending")}]),
        ("override_release_resume", "release", [{"op":"SetCommitmentStatus","target_id":"c3","status":"active"},{"op":"SetCommitmentField","target_id":"c3","field":"overridden_by","value":None},{"op":"SetActionFields","target_id":"a2","fields":{"status":"running"}},{"op":"RemoveRestoration","target_id":"r0"}]),
        ("override_release_complete", "release", [{"op":"SetCommitmentStatus","target_id":"c3","status":"completed"},{"op":"SetCommitmentField","target_id":"c3","field":"overridden_by","value":None},{"op":"SetActionFields","target_id":"a2","fields":{"status":"completed","progress":1.0}},{"op":"RemoveRestoration","target_id":"r0"}]),
        ("world_fact_blocks_pending", "world_change", [{"op":"SetFact","key":"clear","value":False},{"op":"SetCommitmentStatus","target_id":"c2","status":"blocked"}]),
        ("world_fact_halts_running", "world_change", [{"op":"SetFact","key":"clear","value":False},{"op":"SetActionFields","target_id":"a0","fields":{"status":"halted"}},{"op":"SetProgressFields","target_id":"p0","fields":{"valid":False}}]),
        ("evidence_invalidates_progress", "evidence_change", [{"op":"SetFact","key":"evidence_ok","value":False},{"op":"SetProgressFields","target_id":"p0","fields":{"valid":False}},{"op":"SetCommitmentStatus","target_id":"c0","status":"needs_revalidation"}]),
        ("evidence_revalidates_progress", "evidence_change", [{"op":"SetFact","key":"evidence_ok","value":True},{"op":"SetProgressFields","target_id":"p1","fields":{"valid":True,"value":0.25}},{"op":"SetCommitmentStatus","target_id":"c1","status":"active"}]),
        ("nonreversible_safe_stop", "cancel", [{"op":"SetCommitmentStatus","target_id":"c3","status":"cancelling"},{"op":"SetActionFields","target_id":"a2","fields":{"status":"stop_after_safe_point"}},{"op":"SetFact","key":"safe_stop","value":True}]),
        ("reversible_immediate_stop", "cancel", [{"op":"SetCommitmentStatus","target_id":"c0","status":"cancelled"},{"op":"SetActionFields","target_id":"a0","fields":{"status":"cancelled","progress":0.4}}]),
        ("progress_checkpoint_insert", "checkpoint", [{"op":"InsertProgress","record":new_p("np20","c2",0.1)},{"op":"SetCommitmentStatus","target_id":"c2","status":"active"}]),
        ("progress_checkpoint_advance", "checkpoint", [{"op":"SetProgressFields","target_id":"p0","fields":{"value":0.7}},{"op":"SetActionFields","target_id":"a0","fields":{"progress":0.7}}]),
        ("progress_reset_retry", "retry", [{"op":"SetProgressFields","target_id":"p0","fields":{"value":0.0,"valid":True}},{"op":"SetActionFields","target_id":"a0","fields":{"status":"pending","progress":0.0}},{"op":"SetFact","key":"retry_count","value":1}]),
        ("restoration_candidate_add", "restoration", [{"op":"AddRestoration","record":_record("nr23",target_id="c1",after_id="c0",status="pending")}]),
        ("restoration_candidate_replace", "restoration", [{"op":"RemoveRestoration","target_id":"r0"},{"op":"AddRestoration","record":_record("nr24",target_id="c2",after_id="c1",status="pending")}]),
        ("restoration_candidate_drop", "restoration", [{"op":"RemoveRestoration","target_id":"r0"},{"op":"SetCommitmentStatus","target_id":"c3","status":"blocked"}]),
        ("subgoal_insert_commitment", "decompose", [{"op":"InsertCommitment","record":new_c("n26",status="pending",priority=2)},{"op":"SetCommitmentField","target_id":"c1","field":"requires_all","value":["c0","n26"]}]),
        ("subgoal_insert_action", "decompose", [{"op":"InsertCommitment","record":new_c("n27",status="active",priority=2)},{"op":"InsertAction","record":new_a("na27","n27")},{"op":"SetCommitmentStatus","target_id":"c2","status":"blocked"}]),
        ("subgoal_insert_full_bundle", "decompose", [{"op":"InsertCommitment","record":new_c("n28",status="active",priority=4)},{"op":"InsertAction","record":new_a("na28","n28")},{"op":"InsertProgress","record":new_p("np28","n28",0.0)},{"op":"SetCommitmentField","target_id":"c2","field":"requires_all","value":["n28"]}]),
        ("deadline_expire_pending", "deadline", [{"op":"SetCommitmentStatus","target_id":"c2","status":"expired"},{"op":"SetActionFields","target_id":"a1","fields":{"status":"cancelled"}}]),
        ("deadline_grace_extension", "deadline", [{"op":"SetCommitmentField","target_id":"c1","field":"deadline","value":250},{"op":"SetCommitmentStatus","target_id":"c1","status":"active"}]),
        ("concurrent_commutative_fact", "concurrent_event", [{"op":"SetFact","key":"external_note","value":"accepted"}]),
        ("concurrent_conflict_hold", "concurrent_event", [{"op":"SetCommitmentStatus","target_id":"c0","status":"held"},{"op":"SetActionFields","target_id":"a0","fields":{"status":"paused"}},{"op":"SetFact","key":"conflict_pending","value":True}]),
        ("owner_scoped_status_change", "authority", [{"op":"SetCommitmentStatus","target_id":"c1","status":"cancelled"},{"op":"SetActionFields","target_id":"a1","fields":{"status":"cancelled"}}]),
        ("owner_scoped_field_change", "authority", [{"op":"SetCommitmentField","target_id":"c2","field":"owner","value":"delegate"},{"op":"SetCommitmentField","target_id":"c2","field":"priority","value":4}]),
        ("compound_resume_and_checkpoint", "compound", [{"op":"SetCommitmentStatus","target_id":"c3","status":"active"},{"op":"SetActionFields","target_id":"a2","fields":{"status":"running","progress":0.6}},{"op":"SetProgressFields","target_id":"p1","fields":{"value":0.2}},{"op":"SetFact","key":"safe_stop","value":False}]),
        ("compound_replace_and_restore", "compound", [{"op":"SetCommitmentStatus","target_id":"c0","status":"superseded"},{"op":"InsertCommitment","record":new_c("n36",priority=6)},{"op":"SetActionFields","target_id":"a0","fields":{"commitment_id":"n36","status":"running"}},{"op":"AddRestoration","record":_record("nr36",target_id="c1",after_id="n36",status="pending")}]),
    ]


def build_holdout_cases() -> list[SharedEnvelopeCase]:
    cases: list[SharedEnvelopeCase] = []
    for index, (family, event_type, operations) in enumerate(_specs(), start=1):
        pre = _base_state()
        operations = copy.deepcopy(list(operations))
        post = apply_typed_operations(pre, operations)
        case_id = f"SCE-H{index:02d}"
        rules = tuple(_rule(rule_index, operation) for rule_index, operation in enumerate(operations, start=1))
        cases.append(SharedEnvelopeCase(
            case_id=case_id,
            family=family,
            original_task=f"execute the authorized {family.replace('_', ' ')} transition",
            pre_state=pre,
            event=_event(f"H{index:02d}", event_type, 100 + index, 500 + index, transition_family=family),
            transaction_meta=_meta(100 + index, 400 + index),
            rule_clauses=rules,
            oracle_operations=tuple(operations),
            post_state=post,
        ))
    if len(cases) != 36 or len({case.family for case in cases}) != 36:
        raise AssertionError("holdout must contain 36 unique families")
    signatures = {canonical_json([operation["op"] for operation in case.oracle_operations]) + ":" + case.family for case in cases}
    if len(signatures) != 36:
        raise AssertionError("holdout logic signatures are not unique")
    development_ids = {case.case_id for case in build_development_cases()}
    if development_ids & {case.case_id for case in cases}:
        raise AssertionError("holdout overlaps development IDs")
    return cases
