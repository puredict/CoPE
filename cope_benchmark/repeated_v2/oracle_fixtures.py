"""Explicit diagnostic answers; never import these into a formal reasoner.

These hand-authored examples exercise eight continuous events. They are oracle
fixtures for code qualification, not model outputs or experimental evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import canonical_json, to_primitive
from .enums import MethodName
from .schema import (CommitmentOccurrence, ContinuationState, EvidenceRecord,
                     EventEvidence, ExecutionContext, PersistentLedger,
                     ProgressCertificate)


def new_slot(family: str, predicate: str, arguments: tuple[str, ...], *,
             role: str = "achievement_goal", source: str = "task",
             authority: str = "user", hardness: str = "hard") -> dict[str, Any]:
    return {"family_key": family, "role": role, "predicate": predicate,
            "arguments": list(arguments), "lifecycle": "active",
            "grounding_validity": "valid", "priority": 10, "hardness": hardness,
            "source": source, "authority": authority, "restore_guard": {},
            "dependency_ids": [], "provenance": {"record": "initial-request"},
            "evidence_ids": []}


def initial_fixture() -> tuple[PersistentLedger, ExecutionContext]:
    specs = [new_slot("goal:mug:shelf", "inside", ("mug", "shelf")),
             new_slot("goal:plate:rack", "inside", ("plate", "rack")),
             new_slot("binding:mug", "at", ("mug", "table"),
                      role="grounding_binding", source="perception")]
    slots = tuple(CommitmentOccurrence.from_dict({**spec,
        "occurrence_id": spec["family_key"] + "@1", "created_event_id": "initial",
        "retired_event_id": None}) for spec in specs)
    context = ExecutionContext(beliefs=(), progress=(ProgressCertificate(
        milestone_id="plate_done", predicate="inside", arguments=("plate", "rack"),
        satisfaction="satisfied", verifier_record_id="v0", evidence_ids=("e0",),
        verified_at_step=0),), continuation=ContinuationState(
            active_stage="transport", active_skill="place", program_counter=1,
            held_object_hypothesis=None, resumable_suffix=("place",),
            controller_state_ref=None, captured_at_step=0))
    return PersistentLedger(0, slots), context


@dataclass(frozen=True)
class OracleFixtureStep:
    event: EventEvidence
    evidence: tuple[EvidenceRecord, ...]
    operations: tuple[dict[str, Any], ...]
    checks: tuple[dict[str, Any], ...] = ()


def fixture_steps() -> tuple[OracleFixtureStep, ...]:
    guard = {"hypothesis": "mug is available", "min_confidence": 0.9}
    descriptions = (
        "The mug is now at the side table.",
        "The mug cannot be accessed temporarily.",
        "Please handle the mug gently for the rest of this task.",
        "mug is available",
        "Put the mug in the cabinet instead of the shelf.",
        "Cancel the request to put the mug in the cabinet.",
        "Please put the mug on the shelf again as a new request.",
        "Give gentle handling of the mug priority twenty.",
    )
    operations = (
        ({"op": "OVERRIDE", "occurrence_id": "binding:mug@1", "request_id": "binding2",
          "slot": new_slot("binding:mug", "at", ("mug", "side_table"),
                           role="grounding_binding", source="perception")},),
        ({"op": "SUSPEND", "occurrence_id": "goal:mug:shelf@1", "restore_guard": guard,
          "grounding_validity": "invalid"},),
        ({"op": "INSERT", "request_id": "gentle1", "slot": new_slot(
            "preference:gentle:mug", "gentle", ("mug",), role="user_preference",
            source="user", hardness="soft")},),
        ({"op": "RESTORE", "occurrence_id": "goal:mug:shelf@1", "check_id": "available4",
          "grounding_validity": "valid"},),
        ({"op": "OVERRIDE", "occurrence_id": "goal:mug:shelf@1", "request_id": "cabinet1",
          "slot": new_slot("goal:mug:cabinet", "inside", ("mug", "cabinet"))},),
        ({"op": "EXPIRE", "occurrence_id": "goal:mug:cabinet@1"},),
        ({"op": "INSERT", "request_id": "shelf2", "slot": new_slot(
            "goal:mug:shelf", "inside", ("mug", "shelf"))},),
        ({"op": "SET_PRIORITY", "occurrence_id": "preference:gentle:mug@1", "priority": 20},),
    )
    result = []
    for index, (description, ops) in enumerate(zip(descriptions, operations), 1):
        event = EventEvidence(event_id=f"event-{index}", event_index=index,
            hypothesis=description, confidence=1.0, evidence_ids=(f"e{index}",),
            timestamp=index, provenance="shared_observer",
            user_message=description if index in (3, 5, 6, 7, 8) else None,
            affected_entity_hypotheses=("mug",))
        checks = ({"kind": "REVALIDATE", "check_id": "available4",
                   "occurrence_id": "goal:mug:shelf@1", "evidence_ids": ["e4"],
                   "guard": guard, "result": True},) if index == 4 else ()
        record = EvidenceRecord(f"e{index}", description, 1.0, "shared_observer", index)
        result.append(OracleFixtureStep(event, (record,), ops, checks))
    return tuple(result)


def typed_fixture(ledger, context, step: OracleFixtureStep) -> dict[str, Any]:
    from .patch_contract import PATCH_VERSION
    from .state_engine import protected_projection_sha256
    affected = sorted({op["occurrence_id"] for op in step.operations if "occurrence_id" in op})
    protected = sorted(slot.occurrence_id for slot in ledger.slots if slot.occurrence_id not in affected)
    return {"schema_version": PATCH_VERSION, "episode_id": "qualification",
            "event_index": step.event.event_index, "base_revision": ledger.revision,
            "affected_scope": affected, "protected_ids": protected,
            "protected_projection_sha256": protected_projection_sha256(ledger, protected, context=context),
            "evidence_ids": list(step.event.evidence_ids), "checks": to_primitive(step.checks),
            "operations": to_primitive(step.operations), "confidence": 1.0}


def generic_fixture(typed: dict[str, Any]) -> dict[str, Any]:
    """Mechanical fixture encoding only; the generic runtime does not call this."""
    from .generic_contract import GENERIC_VERSION
    tx = {key: to_primitive(value) for key, value in typed.items()
          if key not in {"checks", "operations", "confidence"}}
    tx.update(schema_version=GENERIC_VERSION,
              assertions=[{**check, "kind": "validation"} for check in typed["checks"]],
              creates=[], writes=[], relation_additions=[], relation_removals=[], evidence_links=[])
    for operation in typed["operations"]:
        op, target = operation["op"], operation.get("occurrence_id")
        if op in ("INSERT", "OVERRIDE"):
            tx["creates"].append({"request_id": operation["request_id"], "slot": operation["slot"]})
        if op in ("SUSPEND", "OVERRIDE", "EXPIRE", "RESTORE"):
            value = {"SUSPEND": "suspended", "OVERRIDE": "overridden", "EXPIRE": "expired",
                     "RESTORE": "active"}[op]
            write = {"occurrence_id": target, "path": "/lifecycle", "value": value}
            if op == "RESTORE":
                write["assertion_id"] = operation["check_id"]
            tx["writes"].append(write)
        for field in ("restore_guard", "grounding_validity", "priority"):
            if field in operation:
                tx["writes"].append({"occurrence_id": target, "path": "/" + field,
                                     "value": operation[field]})
        if op == "OVERRIDE":
            tx["relation_additions"].append({"source_id": operation["request_id"],
                                            "relation": "overrides", "target_id": target})
    return tx


def full_state_fixture(ledger, context) -> dict[str, Any]:
    from .patch_contract import FULL_STATE_VERSION
    from .state_engine import semantic_history
    return {"schema_version": FULL_STATE_VERSION, "base_revision": ledger.revision - 1,
            "semantic_history": semantic_history(ledger),
            "slots": [slot.to_dict() for slot in ledger.slots],
            "relations": [edge.to_dict() for edge in ledger.relations],
            "initial_facts": [fact.to_dict() for fact in context.beliefs],
            "progress_certificates": [cert.to_dict() for cert in context.progress],
            "continuation_assumptions": context.continuation.to_dict()}


def directive_fixture(ledger, context) -> dict[str, Any]:
    from .compiler import compile_ledger
    from .patch_contract import DIRECTIVE_VERSION
    problem = compile_ledger(ledger=ledger, context=context, source_method=MethodName.COPE_TYPED_EDIT)
    data = problem.to_dict()
    for field in ("problem_id", "source_method", "source_revision"):
        data.pop(field)
    data.update(schema_version=DIRECTIVE_VERSION, ordered_macro_plan=[])
    return data


def build_oracle_fixture_chain() -> tuple[dict[str, Any], ...]:
    """Validate fixture encodings and return before/after states for smoke only."""
    from .state_engine import apply_cope
    from .generic_engine import apply_generic
    ledger, context = initial_fixture()
    generic_ledger = ledger
    result = []
    for step in fixture_steps():
        patch = typed_fixture(ledger, context, step)
        generic = generic_fixture(typed_fixture(generic_ledger, context, step))
        after = apply_cope(ledger, patch, evidence_records=step.evidence, context=context,
                          authority="user", event_id=step.event.event_id,
                          event_timestamp=step.event.timestamp)
        generic_after = apply_generic(generic_ledger, generic, evidence_records=step.evidence,
                          context=context, authority="user", event_id=step.event.event_id,
                          event_timestamp=step.event.timestamp)
        if to_primitive(after.slots) != to_primitive(generic_after.slots):
            raise AssertionError("Fixture typed/generic semantic slots differ")
        if to_primitive(after.relations) != to_primitive(generic_after.relations):
            raise AssertionError("Fixture typed/generic relations differ")
        result.append({"step": step, "before": ledger, "after": after,
                       "typed": patch, "generic": generic,
                       "full_state": full_state_fixture(after, context),
                       "directive": directive_fixture(after, context)})
        ledger, generic_ledger = after, generic_after
    by_id = {slot.occurrence_id: slot for slot in ledger.slots}
    expected = {"goal:mug:shelf@1": "overridden", "goal:mug:cabinet@1": "expired",
                "goal:mug:shelf@2": "active", "binding:mug@1": "overridden",
                "binding:mug@2": "active", "preference:gentle:mug@1": "active"}
    for occurrence_id, lifecycle in expected.items():
        if by_id[occurrence_id].lifecycle.value != lifecycle:
            raise AssertionError(f"Wrong fixture lifecycle for {occurrence_id}")
    if by_id["preference:gentle:mug@1"].priority != 20:
        raise AssertionError("Priority fixture changed lifecycle or missed weight")
    return tuple(result)
