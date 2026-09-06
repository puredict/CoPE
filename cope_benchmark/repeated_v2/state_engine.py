"""Atomic deterministic v2 kernel. It never owns perception or executor state.

Both interfaces submit changes to the same invariant checker. A failed proposal
raises TransactionError and leaves the immutable input ledger and allocator
unchanged. The model cannot allocate IDs or issue its own validation evidence.
"""

from collections.abc import Mapping

from .canonical import canonical_sha256, to_primitive
from .occurrence import OccurrenceAllocator, validate_occurrences
from .parsers import parse_cope_proposal, ProposalError
from .schema import CommitmentOccurrence, PersistentLedger, RelationEdge


class TransactionError(ValueError):
    pass


AUTHORITY_RANK = {"planner": 0, "perception": 1, "task": 2, "user": 3, "safety": 4, "system": 5}
DAG_RELATIONS = {"depends_on", "precedes", "overrides", "derived_from"}
SYMMETRIC_RELATIONS = {"conflicts_with", "same_family"}


def default_protected_ids(ledger, affected_scope=()):
    return tuple(sorted(slot.occurrence_id for slot in ledger.slots
                        if slot.occurrence_id not in set(affected_scope)))


def protected_projection(ledger, protected_ids, context=None):
    protected = set(protected_ids)
    slots = {slot.occurrence_id: slot for slot in ledger.slots}
    if protected - slots.keys():
        raise TransactionError("protected IDs must exist")
    return {
        "slots": [to_primitive(slots[slot_id]) for slot_id in sorted(protected)],
        "relations": sorted([to_primitive(edge) for edge in ledger.relations
            if edge.source_id in protected or edge.target_id in protected],
            key=lambda edge: (edge["source_id"], edge["relation"], edge["target_id"])),
        "progress_certificates": to_primitive(context.progress) if context is not None else [],
    }


def protected_projection_sha256(ledger, protected_ids, context=None):
    return canonical_sha256(protected_projection(ledger, protected_ids, context))


protected_projection_hash = protected_projection_sha256


def semantic_history(ledger):
    """Public semantic audit projection shared by all persistent interfaces.

    Only carrier/logging metadata is removed. Invalidation timestamps, bound
    validation evidence, allocations and before/after semantics are retained.
    """
    metadata = {"carrier", "proposal_sha256", "protected_projection_sha256"}
    result = [{key: to_primitive(value) for key, value in record.items() if key not in metadata}
              for record in ledger.history_records if record.get("kind") != "full_state_regenerated"]
    from .evidence import assert_public_safe
    assert_public_safe(result)
    return result


def _authorize(slot, authority):
    if authority not in AUTHORITY_RANK:
        raise TransactionError("unknown caller authority")
    try:
        required = max(AUTHORITY_RANK[slot["authority"]], AUTHORITY_RANK[slot["source"]])
    except KeyError as exc:
        raise TransactionError("unknown commitment authority/source") from exc
    if slot["role"] == "safety_requirement":
        required = max(required, AUTHORITY_RANK["safety"])
    if AUTHORITY_RANK[authority] < required:
        raise TransactionError("authority restriction")


def _acyclic(edges, relation):
    graph = {}
    for source, target in edges:
        graph.setdefault(source, []).append(target)
    visiting, complete = set(), set()

    def visit(node):
        if node in visiting:
            raise TransactionError(f"{relation} cycle")
        if node in complete:
            return
        visiting.add(node)
        for target in graph.get(node, ()):
            visit(target)
        visiting.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def validate_ledger(ledger):
    """Validate each edge type independently; symmetric relations allow cycles."""
    try:
        validate_occurrences(ledger.slots)
    except ValueError as exc:
        raise TransactionError(str(exc)) from exc
    slots = {slot.occurrence_id: to_primitive(slot) for slot in ledger.slots}
    graphs = {name: [] for name in DAG_RELATIONS}
    symmetric = set()
    for slot_id, slot in slots.items():
        _authorize(slot, "system")
        for dependency in slot["dependency_ids"]:
            if dependency not in slots or dependency == slot_id:
                raise TransactionError("invalid dependency endpoint")
            graphs["depends_on"].append((slot_id, dependency))
    for edge in ledger.relations:
        source, target, relation = edge.source_id, edge.target_id, edge.relation
        if source not in slots or target not in slots or source == target:
            raise TransactionError("invalid relation endpoint")
        if relation in graphs:
            graphs[relation].append((source, target))
        elif relation in SYMMETRIC_RELATIONS:
            key = (relation, *sorted((source, target)))
            if key in symmetric:
                raise TransactionError("duplicate undirected relation")
            symmetric.add(key)
        else:
            raise TransactionError("unsupported relation type")
        if relation == "overrides":
            if slots[target]["lifecycle"] not in {"overridden", "expired"}:
                raise TransactionError("override target must be retired")
            if AUTHORITY_RANK[slots[source]["authority"]] < AUTHORITY_RANK[slots[target]["authority"]]:
                raise TransactionError("override relation authority")
        elif relation == "conflicts_with":
            if slots[source]["lifecycle"] == slots[target]["lifecycle"] == "active":
                raise TransactionError("conflicting commitments cannot both be active")
        elif relation == "same_family":
            if slots[source]["family_key"] != slots[target]["family_key"]:
                raise TransactionError("same_family requires equal semantic families")
    for relation, edges in graphs.items():
        _acyclic(edges, relation)
    # Both relations impose ordering in the common compiler. A mixed cycle is
    # invalid even if each directed edge type is separately acyclic.
    _acyclic(graphs["depends_on"] + [(target, source) for source, target in graphs["precedes"]],
             "scheduling dependency")
    return ledger


def _fresh_checks(ledger, checks, records, *, evidence_ids, event_id, event_index,
                  event_timestamp, slots):
    evidence = {}
    for item in records:
        from .schema import EvidenceRecord
        try:
            record = EvidenceRecord.from_dict(to_primitive(item)).to_dict()
        except (TypeError, ValueError) as exc:
            raise TransactionError("expected trusted evidence record") from exc
        if not isinstance(record, dict) or not {"evidence_id", "hypothesis", "confidence", "timestamp", "provenance"} <= record.keys():
            raise TransactionError("expected trusted evidence record")
        if record["evidence_id"] in evidence:
            raise TransactionError("duplicate trusted evidence ID")
        if type(record["timestamp"]) is not int or type(record["confidence"]) not in (int, float) or not 0 <= record["confidence"] <= 1:
            raise TransactionError("invalid trusted evidence record")
        if record["timestamp"] > event_timestamp:
            raise TransactionError("future evidence is not available at this event")
        evidence[record["evidence_id"]] = record
    if set(evidence_ids) - evidence.keys():
        raise TransactionError("unknown proposal evidence reference")
    previous_check_ids = {record.get("check_id") for record in ledger.history_records
                          if record.get("kind") == "validation"}
    results = {}
    for check in checks:
        check_id, slot_id = check["check_id"], check["occurrence_id"]
        if check_id in previous_check_ids or check_id in results:
            raise TransactionError("duplicate validation ID")
        if slot_id not in slots:
            raise TransactionError("validation occurrence does not exist")
        if not check["evidence_ids"] or set(check["evidence_ids"]) - set(evidence_ids):
            raise TransactionError("validation evidence must be declared and trusted")
        guard = slots[slot_id]["restore_guard"]
        if check["guard"] != guard:
            raise TransactionError("validation is not bound to the current guard")
        last_invalidated = max((record.get("event_timestamp", -1) for record in ledger.history_records
            if slot_id in record.get("invalidated_ids", ())), default=-1)
        minimum = guard.get("min_confidence", 0.9)
        if type(minimum) not in (int, float) or not 0 <= minimum <= 1:
            raise TransactionError("invalid guard confidence")
        if set(guard) - {"hypothesis", "min_confidence"}:
            raise TransactionError("unsupported restore guard semantics")
        successful = bool(guard.get("hypothesis")) and any(
            evidence[ref]["hypothesis"] == guard["hypothesis"]
            and evidence[ref]["confidence"] >= minimum
            and evidence[ref]["timestamp"] >= event_timestamp
            and evidence[ref]["timestamp"] > last_invalidated
            and evidence[ref].get("result", True) is True
            for ref in check["evidence_ids"])
        if check["result"] != successful:
            raise TransactionError("claimed validation result disagrees with trusted evidence")
        results[check_id] = {
            "kind": "validation", "check_id": check_id, "occurrence_id": slot_id,
            "guard": guard, "restore_guard_sha256": canonical_sha256(guard),
            "result": successful, "evidence_ids": check["evidence_ids"],
            "event_id": event_id, "validated_at_event_index": event_index,
            "event_timestamp": event_timestamp, "state_revision": ledger.revision,
        }
    return results


def _apply_neutral(ledger, proposal, *, creates, writes, checks, relation_additions,
                   relation_removals, evidence_links, evidence_records=(), context=None,
                   authority="user", event_id=None, event_timestamp=None, carrier="generic"):
    """Shared carrier-neutral materialization and validation boundary."""
    validate_ledger(ledger)
    if proposal["base_revision"] != ledger.revision:
        raise TransactionError("stale base revision")
    event_index = proposal["event_index"]
    event_id = event_id or f"{proposal['episode_id']}:event:{event_index}"
    event_timestamp = event_index if event_timestamp is None else event_timestamp
    if type(event_timestamp) is not int or event_timestamp < 0:
        raise TransactionError("event timestamp must be a nonnegative integer")
    previous_indices = [record["event_index"] for record in ledger.history_records
                        if record.get("kind") == "transaction" and "event_index" in record]
    if previous_indices and event_index <= max(previous_indices):
        raise TransactionError("event index must increase")
    before = {slot.occurrence_id: to_primitive(slot) for slot in ledger.slots}
    scope, protected = set(proposal["affected_scope"]), set(proposal["protected_ids"])
    if scope - before.keys():
        raise TransactionError("affected scope must contain existing occurrence IDs")
    if set(default_protected_ids(ledger, scope)) - protected:
        raise TransactionError("unmentioned occurrences must be protected")
    if protected_projection_sha256(ledger, protected, context) != proposal["protected_projection_sha256"]:
        raise TransactionError("protected projection hash mismatch")
    validations = _fresh_checks(ledger, checks, evidence_records, evidence_ids=proposal["evidence_ids"],
        event_id=event_id, event_index=event_index, event_timestamp=event_timestamp, slots=before)
    allocator = OccurrenceAllocator.from_ledger(ledger)
    slots = to_primitive(before)
    allocated = {}
    for request in creates:
        request_id = request["request_id"]
        if request_id in allocated or request_id in before:
            raise TransactionError("duplicate or shadowing allocation request")
        slot = to_primitive(request["slot"])
        _authorize(slot, authority)
        if set(slot["evidence_ids"]) - set(proposal["evidence_ids"]):
            raise TransactionError("new occurrence has undeclared evidence")
        allocated[request_id] = allocator.allocate(slot["family_key"])
        slots[allocated[request_id]] = {**slot, "occurrence_id": allocated[request_id],
                                       "created_event_id": event_id, "retired_event_id": None}

    def resolve(ref):
        return allocated.get(ref, ref)

    def mutable(ref):
        slot_id = resolve(ref)
        if slot_id not in slots:
            raise TransactionError("unknown occurrence ID")
        if slot_id in before and slot_id not in scope:
            raise TransactionError("write outside affected scope")
        _authorize(slots[slot_id], authority)
        return slot_id

    written, lifecycle_writes, invalidated, touched = set(), {}, set(), set()
    for write in writes:
        slot_id = mutable(write["occurrence_id"])
        if slot_id not in before:
            raise TransactionError("new occurrence must be fully specified in its create record")
        field = write["path"][1:]
        if field not in {"lifecycle", "priority", "grounding_validity", "restore_guard", "dependency_ids"}:
            raise TransactionError("immutable or owner-controlled path")
        if (slot_id, field) in written:
            raise TransactionError("multiple writes to the same path")
        written.add((slot_id, field))
        if before[slot_id]["lifecycle"] in {"overridden", "expired"}:
            raise TransactionError("retired occurrence is immutable; request a new occurrence")
        if field == "lifecycle":
            old, new = before[slot_id]["lifecycle"], write["value"]
            if new not in {"active", "suspended", "overridden", "expired"}:
                raise TransactionError("invalid lifecycle")
            if old == new:
                raise TransactionError("lifecycle mutation must change applicability")
            if new == "active":
                validation = validations.get(write.get("assertion_id"))
                if old != "suspended" or not validation or not validation["result"] or validation["occurrence_id"] != slot_id:
                    raise TransactionError("restore requires a fresh successful bound validation")
            elif new == "suspended" and old != "active":
                raise TransactionError("only active occurrences can be suspended")
            elif new == "overridden" and old not in {"active", "suspended"}:
                raise TransactionError("invalid replacement precondition")
            lifecycle_writes[slot_id] = new
            slots[slot_id]["retired_event_id"] = event_id if new in {"overridden", "expired"} else None
            if new == "suspended":
                invalidated.add(slot_id)
        if field in {"grounding_validity", "restore_guard"}:
            invalidated.add(slot_id)
        slots[slot_id][field] = to_primitive(write["value"])
        touched.add(slot_id)

    for slot_id, field in written:
        if field in {"grounding_validity", "restore_guard"}:
            transition = lifecycle_writes.get(slot_id)
            if transition not in {"suspended", "active"}:
                raise TransactionError("grounding and guard changes require a declared applicability transition")
            if field == "restore_guard" and transition == "active":
                raise TransactionError("restore cannot rewrite its certified guard")
    for slot_id in allocated.values():
        slots[slot_id]["dependency_ids"] = [resolve(ref) for ref in slots[slot_id]["dependency_ids"]]
    for link in evidence_links:
        slot_id = mutable(link["occurrence_id"])
        if slots[slot_id]["lifecycle"] in {"overridden", "expired"}:
            raise TransactionError("retired evidence references are immutable")
        if set(link["evidence_ids"]) - set(proposal["evidence_ids"]):
            raise TransactionError("unknown evidence link")
        slots[slot_id]["evidence_ids"] = list(dict.fromkeys(slots[slot_id]["evidence_ids"] + link["evidence_ids"]))
        touched.add(slot_id)
    edges = {(edge.source_id, edge.relation, edge.target_id) for edge in ledger.relations}
    for changes, adding in ((relation_removals, False), (relation_additions, True)):
        for edge in changes:
            source, target = mutable(edge["source_id"]), mutable(edge["target_id"])
            key = (source, edge["relation"], target)
            if adding:
                if key in edges:
                    raise TransactionError("relation already exists")
                edges.add(key)
            else:
                if key not in edges:
                    raise TransactionError("removed relation does not exist")
                edges.remove(key)
            touched.update((source, target))
    for slot_id, lifecycle in lifecycle_writes.items():
        if lifecycle == "overridden" and not any(target == slot_id and relation == "overrides"
                and source in allocated.values() for source, relation, target in edges):
            raise TransactionError("replacement requires a fresh occurrence and explicit relation")
    history = list(ledger.history_records) + list(validations.values()) + [{
        "kind": "transaction", "carrier": carrier, "revision": ledger.revision + 1,
        "base_revision": ledger.revision, "event_id": event_id, "event_index": event_index,
        "event_timestamp": event_timestamp, "affected_ids": sorted(touched | set(allocated.values())),
        "invalidated_ids": sorted(invalidated), "allocations": allocated,
        "before": {slot_id: before[slot_id] for slot_id in sorted(touched) if slot_id in before},
        "after": {slot_id: slots[slot_id] for slot_id in sorted(touched | set(allocated.values()))},
        "proposal_sha256": canonical_sha256(proposal), "authority": authority,
        "protected_projection_sha256": proposal["protected_projection_sha256"],
    }]
    try:
        result = PersistentLedger(revision=ledger.revision + 1,
            slots=tuple(CommitmentOccurrence.from_dict(value) for value in slots.values()),
            relations=tuple(RelationEdge(source_id=s, relation=r, target_id=t) for s, r, t in sorted(edges)),
            history_records=tuple(history))
        validate_ledger(result)
    except (ValueError, TypeError) as exc:
        raise TransactionError(str(exc)) from exc
    if protected_projection_sha256(result, protected, context) != proposal["protected_projection_sha256"]:
        raise TransactionError("protected projection changed")
    if tuple(result.history_records[:len(ledger.history_records)]) != ledger.history_records:
        raise TransactionError("audit history prefix changed")
    return result


def apply_cope(ledger, proposal, *, evidence_records=(), context=None, authority="user",
               event_id=None, event_timestamp=None):
    proposal = parse_cope_proposal(proposal)
    creates, writes, additions, removals = [], [], [], []
    for operation in proposal["operations"]:
        op, slot_id = operation["op"], operation.get("occurrence_id")
        if op in {"INSERT", "OVERRIDE"}:
            creates.append({"request_id": operation["request_id"], "slot": operation["slot"]})
        if op == "OVERRIDE":
            additions.append({"source_id": operation["request_id"], "relation": "overrides", "target_id": slot_id})
        if op in {"SUSPEND", "OVERRIDE", "EXPIRE", "RESTORE"}:
            writes.append({"occurrence_id": slot_id, "path": "/lifecycle",
                "value": {"SUSPEND": "suspended", "OVERRIDE": "overridden", "EXPIRE": "expired", "RESTORE": "active"}[op],
                **({"assertion_id": operation["check_id"]} if op == "RESTORE" else {})})
        for field in ("priority", "grounding_validity", "restore_guard"):
            if field in operation:
                writes.append({"occurrence_id": slot_id, "path": f"/{field}", "value": operation[field]})
        additions.extend(operation.get("relation_additions", ()))
        removals.extend(operation.get("relation_removals", ()))
    return _apply_neutral(ledger, proposal, creates=creates, writes=writes, checks=proposal["checks"],
        relation_additions=additions, relation_removals=removals, evidence_links=[],
        evidence_records=evidence_records, context=context, authority=authority,
        event_id=event_id, event_timestamp=event_timestamp, carrier="typed")


apply_cope_transaction = apply_cope


def apply_full_state(ledger, proposal, *, event_id=None, event_index=None, identity_registry=None):
    """Accept a complete regeneration without recovering any omitted semantics.

    Historical bytes belong to the external prompt/result journal. Only the
    semantic history reproduced by this arm enters its new accepted state.
    """
    from .parsers import parse_full_state
    proposal = parse_full_state(proposal)
    if proposal["base_revision"] != ledger.revision:
        raise TransactionError("stale base revision")
    # An out-of-band registry keeps only issued IDs and family identity; it
    # cannot supply any omitted planning semantics. Reproducing a known ID is
    # allowed, but inventing an arbitrary occurrence suffix is not.
    from .occurrence import occurrence_number
    registry = dict(identity_registry or {})
    for slot in ledger.slots:
        if slot.occurrence_id in registry and registry[slot.occurrence_id] != slot.family_key:
            raise TransactionError("inconsistent trusted identity registry")
        registry[slot.occurrence_id] = slot.family_key
    maxima = {}
    for occurrence_id, family in registry.items():
        maxima[family] = max(maxima.get(family, 0), occurrence_number(family, occurrence_id))
    for slot in proposal["slots"]:
        occurrence_id, family = slot["occurrence_id"], slot["family_key"]
        if occurrence_id in registry:
            if registry[occurrence_id] != family:
                raise TransactionError("existing occurrence changed semantic family identity")
        else:
            expected = f"{family}@{maxima.get(family, 0) + 1}"
            if occurrence_id != expected:
                raise TransactionError("new occurrence ID must match trusted allocator sequence")
            maxima[family] = maxima.get(family, 0) + 1
            registry[occurrence_id] = family
    try:
        result = PersistentLedger(revision=ledger.revision + 1,
            slots=tuple(CommitmentOccurrence.from_dict(slot) for slot in proposal["slots"]),
            relations=tuple(RelationEdge.from_dict(edge) for edge in proposal["relations"]),
            history_records=tuple(proposal["semantic_history"]) + ({
                "kind": "full_state_regenerated", "revision": ledger.revision + 1,
                "event_id": event_id, "event_index": event_index,
                "proposal_sha256": canonical_sha256(proposal),
            },))
        return validate_ledger(result)
    except ValueError as exc:
        raise TransactionError(str(exc)) from exc
