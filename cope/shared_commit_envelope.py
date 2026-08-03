from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from cope.types import canonical_json, stable_hash


class SharedEnvelopeError(ValueError):
    pass


ARMS = ("cope_semantic", "neutral_typed", "compact_semantic", "fsr_semantic")
SEMANTIC_TO_NEUTRAL = {
    "SetCommitmentStatus": "N01",
    "SetCommitmentField": "N02",
    "InsertCommitment": "N03",
    "SetActionFields": "N04",
    "InsertAction": "N05",
    "SetProgressFields": "N06",
    "InsertProgress": "N07",
    "AddRestoration": "N08",
    "RemoveRestoration": "N09",
    "SetFact": "N10",
}
NEUTRAL_TO_SEMANTIC = {value: key for key, value in SEMANTIC_TO_NEUTRAL.items()}


def _record(identifier: str, **fields: Any) -> dict[str, Any]:
    return {"id": identifier, **fields}


def _state(
    commitments: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]] = (),
    progress: Sequence[Mapping[str, Any]] = (),
    restorations: Sequence[Mapping[str, Any]] = (),
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "shared-semantic-state-v1",
        "commitments": copy.deepcopy(list(commitments)),
        "actions": copy.deepcopy(list(actions)),
        "progress": copy.deepcopy(list(progress)),
        "restorations": copy.deepcopy(list(restorations)),
        "facts": copy.deepcopy(dict(facts or {})),
    }


def _find(rows: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise SharedEnvelopeError(f"expected one record {identifier}, got {len(matches)}")
    return matches[0]


def apply_typed_operations(
    pre_state: Mapping[str, Any], operations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    out = copy.deepcopy(dict(pre_state))
    for operation in operations:
        if not isinstance(operation, Mapping):
            raise SharedEnvelopeError("typed operation must be an object")
        name = operation.get("op")
        if name == "SetCommitmentStatus":
            _find(out["commitments"], str(operation["target_id"]))["status"] = operation["status"]
        elif name == "SetCommitmentField":
            _find(out["commitments"], str(operation["target_id"]))[str(operation["field"])] = copy.deepcopy(operation["value"])
        elif name == "InsertCommitment":
            record = copy.deepcopy(operation["record"])
            if any(row.get("id") == record.get("id") for row in out["commitments"]):
                raise SharedEnvelopeError("duplicate commitment")
            out["commitments"].append(record)
        elif name == "SetActionFields":
            row = _find(out["actions"], str(operation["target_id"]))
            for key, value in dict(operation["fields"]).items():
                row[str(key)] = copy.deepcopy(value)
        elif name == "InsertAction":
            record = copy.deepcopy(operation["record"])
            if any(row.get("id") == record.get("id") for row in out["actions"]):
                raise SharedEnvelopeError("duplicate action")
            out["actions"].append(record)
        elif name == "SetProgressFields":
            row = _find(out["progress"], str(operation["target_id"]))
            for key, value in dict(operation["fields"]).items():
                row[str(key)] = copy.deepcopy(value)
        elif name == "InsertProgress":
            record = copy.deepcopy(operation["record"])
            if any(row.get("id") == record.get("id") for row in out["progress"]):
                raise SharedEnvelopeError("duplicate progress")
            out["progress"].append(record)
        elif name == "AddRestoration":
            out["restorations"].append(copy.deepcopy(operation["record"]))
        elif name == "RemoveRestoration":
            target = str(operation["target_id"])
            before = len(out["restorations"])
            out["restorations"] = [row for row in out["restorations"] if row.get("id") != target]
            if len(out["restorations"]) != before - 1:
                raise SharedEnvelopeError("restoration removal mismatch")
        elif name == "SetFact":
            out["facts"][str(operation["key"])] = copy.deepcopy(operation["value"])
        else:
            raise SharedEnvelopeError(f"unknown typed operation {name!r}")
    return out


def _split_path(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise SharedEnvelopeError("compact path must start with /")
    parts = path[1:].split("/")
    if any(not part for part in parts):
        raise SharedEnvelopeError("compact path contains an empty component")
    return parts


def apply_compact_writes(
    pre_state: Mapping[str, Any], writes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    out = copy.deepcopy(dict(pre_state))
    for write in writes:
        if set(write) != {"op", "path", "value"} or write["op"] not in {"add", "replace", "remove"}:
            raise SharedEnvelopeError("compact write schema mismatch")
        parts = _split_path(str(write["path"]))
        root = parts[0]
        value = copy.deepcopy(write["value"])
        if root in {"commitments", "actions", "progress"}:
            if len(parts) == 2:
                matches = [index for index, row in enumerate(out[root]) if row.get("id") == parts[1]]
                if write["op"] in {"add", "replace"} and isinstance(value, dict) and value.get("id") == parts[1]:
                    if write["op"] == "replace" and not matches:
                        raise SharedEnvelopeError("replace targets absent record")
                    if matches:
                        out[root][matches[0]] = value
                    else:
                        out[root].append(value)
                elif write["op"] == "remove" and value is None:
                    before = len(out[root])
                    out[root] = [row for row in out[root] if row.get("id") != parts[1]]
                    if len(out[root]) != before - 1:
                        raise SharedEnvelopeError("compact record removal mismatch")
                else:
                    raise SharedEnvelopeError("compact record write mismatch")
            elif len(parts) == 3:
                row = _find(out[root], parts[1])
                if write["op"] == "remove":
                    if value is not None or parts[2] not in row:
                        raise SharedEnvelopeError("compact field removal mismatch")
                    del row[parts[2]]
                    continue
                if write["op"] == "replace" and parts[2] not in row:
                    raise SharedEnvelopeError("replace targets absent field")
                row[parts[2]] = value
            else:
                raise SharedEnvelopeError("compact record path mismatch")
        elif root == "restorations" and len(parts) == 1:
            if write["op"] != "replace" or not isinstance(value, list):
                raise SharedEnvelopeError("restoration replacement mismatch")
            out["restorations"] = value
        elif root == "restorations" and len(parts) == 2:
            matches = [index for index, row in enumerate(out["restorations"]) if row.get("id") == parts[1]]
            if write["op"] in {"add", "replace"} and isinstance(value, dict) and value.get("id") == parts[1]:
                if write["op"] == "replace" and not matches:
                    raise SharedEnvelopeError("replace targets absent restoration")
                if matches:
                    out["restorations"][matches[0]] = value
                else:
                    out["restorations"].append(value)
            elif write["op"] == "remove" and value is None:
                before = len(out["restorations"])
                out["restorations"] = [row for row in out["restorations"] if row.get("id") != parts[1]]
                if len(out["restorations"]) != before - 1:
                    raise SharedEnvelopeError("restoration removal mismatch")
            else:
                raise SharedEnvelopeError("restoration record write mismatch")
        elif root == "restorations" and len(parts) == 3:
            row = _find(out["restorations"], parts[1])
            if write["op"] == "remove":
                if value is not None or parts[2] not in row:
                    raise SharedEnvelopeError("restoration field removal mismatch")
                del row[parts[2]]
                continue
            if write["op"] == "replace" and parts[2] not in row:
                raise SharedEnvelopeError("replace targets absent restoration field")
            row[parts[2]] = value
        elif root == "facts" and len(parts) == 2:
            if write["op"] == "remove":
                if value is not None or parts[1] not in out["facts"]:
                    raise SharedEnvelopeError("compact fact removal mismatch")
                del out["facts"][parts[1]]
                continue
            if write["op"] == "replace" and parts[1] not in out["facts"]:
                raise SharedEnvelopeError("replace targets absent fact")
            out["facts"][parts[1]] = value
        else:
            raise SharedEnvelopeError("transaction metadata and unknown paths are forbidden")
    return out


def compact_diff(pre_state: Mapping[str, Any], post_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    for root in ("commitments", "actions", "progress"):
        before = {row["id"]: row for row in pre_state[root]}
        after = {row["id"]: row for row in post_state[root]}
        if set(before) - set(after):
            raise SharedEnvelopeError("compact semantic contract forbids record deletion")
        for identifier, row in after.items():
            if identifier not in before:
                writes.append({"op": "add", "path": f"/{root}/{identifier}", "value": copy.deepcopy(row)})
                continue
            for field, value in row.items():
                if before[identifier].get(field) != value:
                    writes.append({
                        "op": "replace" if field in before[identifier] else "add",
                        "path": f"/{root}/{identifier}/{field}",
                        "value": copy.deepcopy(value),
                    })
        for identifier, row in before.items():
            if identifier in after and set(row) - set(after[identifier]):
                raise SharedEnvelopeError("compact semantic contract forbids field deletion")
    before_rest = {row["id"]: row for row in pre_state["restorations"]}
    after_rest = {row["id"]: row for row in post_state["restorations"]}
    for identifier in sorted(set(before_rest) - set(after_rest)):
        writes.append({"op": "remove", "path": f"/restorations/{identifier}", "value": None})
    for identifier, row in after_rest.items():
        if identifier not in before_rest:
            writes.append({"op": "add", "path": f"/restorations/{identifier}", "value": copy.deepcopy(row)})
            continue
        for field, value in row.items():
            if before_rest[identifier].get(field) != value:
                writes.append({
                    "op": "replace" if field in before_rest[identifier] else "add",
                    "path": f"/restorations/{identifier}/{field}",
                    "value": copy.deepcopy(value),
                })
    before_facts, after_facts = pre_state["facts"], post_state["facts"]
    if set(before_facts) - set(after_facts):
        raise SharedEnvelopeError("compact semantic contract forbids fact deletion")
    for key, value in after_facts.items():
        if before_facts.get(key) != value:
            writes.append({
                "op": "replace" if key in before_facts else "add",
                "path": f"/facts/{key}", "value": copy.deepcopy(value),
            })
    return writes


def commit_envelope(
    transaction_meta: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    if int(event["base_version"]) != int(transaction_meta["state_version"]):
        raise SharedEnvelopeError("event base version mismatch")
    event_id = str(event["event_id"])
    if any(row.get("event_id") == event_id for row in transaction_meta["processed_events"]):
        raise SharedEnvelopeError("event already processed")
    out = copy.deepcopy(dict(transaction_meta))
    out["state_version"] = int(out["state_version"]) + 1
    out["evidence_version"] = int(event["world_version"])
    out["processed_events"].append({
        "event_id": event_id,
        "payload_sha256": hashlib.sha256(canonical_json(event).encode("utf-8")).hexdigest(),
    })
    return out


@dataclass(frozen=True)
class SharedEnvelopeCase:
    case_id: str
    family: str
    original_task: str
    pre_state: dict[str, Any]
    event: dict[str, Any]
    transaction_meta: dict[str, Any]
    rule_clauses: tuple[dict[str, str], ...]
    oracle_operations: tuple[dict[str, Any], ...]
    post_state: dict[str, Any]

    @property
    def common_input(self) -> dict[str, Any]:
        return {
            "schema_version": "shared-envelope-input-v1",
            "case_id": self.case_id,
            "original_task": self.original_task,
            "pre_semantic_state": copy.deepcopy(self.pre_state),
            "event": copy.deepcopy(self.event),
            "transaction_meta": copy.deepcopy(self.transaction_meta),
            "rule_clauses": copy.deepcopy(list(self.rule_clauses)),
            "common_contract": {
                "disposition": "APPLY",
                "reason_code": "AUTHORIZED_TRANSITION",
                "semantic_only": True,
                "transaction_metadata_generated_by_shared_trusted_envelope": True,
                "preserve_every_field_not_explicitly_changed_by_a_rule_clause": True,
            },
        }


def _event(case_id: str, kind: str, base: int, world: int, **payload: Any) -> dict[str, Any]:
    return {"event_id": f"sce:{case_id.lower()}", "event_type": kind, "base_version": base, "world_version": world, **payload}


def _meta(version: int, evidence: int) -> dict[str, Any]:
    return {"schema_version": "transaction-meta-v1", "state_version": version, "evidence_version": evidence, "processed_events": []}


def build_development_cases() -> list[SharedEnvelopeCase]:
    cases: list[SharedEnvelopeCase] = []

    pre = _state(
        [_record("source_a", status="active", owner="owner", requires_all=[], requires_any=[]),
         _record("source_b", status="active", owner="owner", requires_all=[], requires_any=[]),
         _record("assemble", status="active", owner="owner", requires_all=[], requires_any=["source_a", "source_b"])],
        [_record("act_a", commitment_id="source_a", status="running", progress=0.2),
         _record("act_assemble", commitment_id="assemble", status="pending", progress=0.0)],
    )
    ops = (
        {"op": "SetCommitmentStatus", "target_id": "source_a", "status": "cancelled"},
        {"op": "SetActionFields", "target_id": "act_a", "fields": {"status": "cancelled"}},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D01", "or_dependency_cancellation", "assemble using either available source", pre,
        _event("D01", "cancel", 3, 31, target_id="source_a", issuer="owner"), _meta(3, 30),
        (
            {"id": "R1", "text": "For an authorized cancel event, set the target commitment status to cancelled."},
            {"id": "R2", "text": "Set every action owned by the cancelled target commitment to cancelled; preserve its numeric progress."},
            {"id": "R3", "text": "A requires_any descendant remains unchanged while at least one listed prerequisite remains active."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    pre = _state(
        [_record("old_part", status="active", owner="owner", priority=2, requires_all=[], requires_any=[])],
        [_record("fit_part", commitment_id="old_part", status="running", progress=0.4)],
        [_record("fit_progress", commitment_id="old_part", value=0.4, valid=True)],
    )
    replacement = _record("new_part", status="active", owner="owner", priority=2, requires_all=[], requires_any=[])
    ops = (
        {"op": "SetCommitmentStatus", "target_id": "old_part", "status": "superseded"},
        {"op": "InsertCommitment", "record": replacement},
        {"op": "SetActionFields", "target_id": "fit_part", "fields": {"commitment_id": "new_part"}},
        {"op": "SetProgressFields", "target_id": "fit_progress", "fields": {"commitment_id": "new_part"}},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D02", "replacement_progress_transfer", "fit the approved part", pre,
        _event("D02", "replace", 8, 84, target_id="old_part", replacement=replacement, preserve_progress=True), _meta(8, 80),
        (
            {"id": "R1", "text": "For an authorized replacement, set the target commitment to superseded and insert the event replacement record exactly."},
            {"id": "R2", "text": "When preserve_progress is true, retarget every target-owned action and progress record to the replacement ID without changing status, progress, value, or validity."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    pre = _state(
        [_record("base_goal", status="active", owner="owner", priority=2, requires_all=[], requires_any=[])],
        [_record("base_action", commitment_id="base_goal", status="running", progress=0.3)],
    )
    urgent = _record("urgent_goal", status="active", owner="owner", priority=9, requires_all=[], requires_any=[])
    urgent_action = _record("urgent_action", commitment_id="urgent_goal", status="pending", progress=0.0)
    restoration = _record("restore_base", target_id="base_goal", after_id="urgent_goal", status="pending")
    ops = (
        {"op": "SetCommitmentStatus", "target_id": "base_goal", "status": "suspended"},
        {"op": "SetCommitmentField", "target_id": "base_goal", "field": "overridden_by", "value": "urgent_goal"},
        {"op": "SetActionFields", "target_id": "base_action", "fields": {"status": "paused"}},
        {"op": "InsertCommitment", "record": urgent},
        {"op": "InsertAction", "record": urgent_action},
        {"op": "AddRestoration", "record": restoration},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D03", "temporary_override", "finish the base goal after an urgent inspection", pre,
        _event("D03", "override", 5, 56, target_id="base_goal", override=urgent, override_action=urgent_action, restoration=restoration), _meta(5, 52),
        (
            {"id": "R1", "text": "For an authorized temporary override, set the target to suspended, set overridden_by to the override ID, and pause every running target-owned action."},
            {"id": "R2", "text": "Insert the event override commitment and override_action records exactly."},
            {"id": "R3", "text": "Append the event restoration record exactly."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    pre = _state(
        [_record("base_goal", status="suspended", owner="owner", priority=2, requires_all=[], requires_any=[], overridden_by="urgent_goal"),
         _record("urgent_goal", status="active", owner="owner", priority=9, requires_all=[], requires_any=[])],
        [_record("base_action", commitment_id="base_goal", status="paused", progress=0.3),
         _record("urgent_action", commitment_id="urgent_goal", status="completed", progress=1.0)],
        restorations=[_record("restore_base", target_id="base_goal", after_id="urgent_goal", status="pending")],
        facts={"base_goal_satisfied": False},
    )
    ops = (
        {"op": "SetCommitmentStatus", "target_id": "urgent_goal", "status": "released"},
        {"op": "SetCommitmentStatus", "target_id": "base_goal", "status": "active"},
        {"op": "SetCommitmentField", "target_id": "base_goal", "field": "overridden_by", "value": None},
        {"op": "SetActionFields", "target_id": "base_action", "fields": {"status": "running"}},
        {"op": "RemoveRestoration", "target_id": "restore_base"},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D04", "override_release", "resume the base goal after urgent inspection", pre,
        _event("D04", "release", 6, 64, override_id="urgent_goal", target_id="base_goal", restoration_id="restore_base"), _meta(6, 60),
        (
            {"id": "R1", "text": "On authorized release, set the override to released."},
            {"id": "R2", "text": "Because facts.base_goal_satisfied is false, set the target to active, clear overridden_by to null, and resume each paused target-owned action by setting it to running."},
            {"id": "R3", "text": "Remove the restoration record named by restoration_id."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    pre = _state(
        [_record("base_goal", status="suspended", owner="owner", requires_all=[], requires_any=[], overridden_by="urgent_goal"),
         _record("urgent_goal", status="active", owner="owner", requires_all=[], requires_any=[])],
        [_record("base_action", commitment_id="base_goal", status="paused", progress=0.5)],
        restorations=[_record("restore_base", target_id="base_goal", after_id="urgent_goal", status="pending")],
        facts={"workspace_clear": True},
    )
    ops = (
        {"op": "SetFact", "key": "workspace_clear", "value": False},
        {"op": "SetCommitmentStatus", "target_id": "urgent_goal", "status": "expired"},
        {"op": "SetCommitmentStatus", "target_id": "base_goal", "status": "blocked"},
        {"op": "SetActionFields", "target_id": "base_action", "fields": {"status": "halted"}},
        {"op": "RemoveRestoration", "target_id": "restore_base"},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D05", "world_invalidated_restoration", "restore only when the workspace remains clear", pre,
        _event("D05", "world_change", 10, 103, fact_key="workspace_clear", fact_value=False, override_id="urgent_goal", target_id="base_goal", restoration_id="restore_base"), _meta(10, 100),
        (
            {"id": "R1", "text": "Set the event fact_key to event fact_value."},
            {"id": "R2", "text": "When workspace_clear becomes false, set the override to expired and the restoration target to blocked."},
            {"id": "R3", "text": "Set each paused action owned by the blocked target to halted and remove the named restoration record."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    pre = _state(
        [_record("heat_part", status="active", owner="owner", requires_all=[], requires_any=[])],
        [_record("heat_action", commitment_id="heat_part", status="running", progress=0.8, reversible=False)],
        [_record("heat_progress", commitment_id="heat_part", value=0.8, valid=True)],
        facts={"safe_stop_required": False},
    )
    ops = (
        {"op": "SetCommitmentStatus", "target_id": "heat_part", "status": "cancelling"},
        {"op": "SetActionFields", "target_id": "heat_action", "fields": {"status": "stop_after_safe_point"}},
        {"op": "SetFact", "key": "safe_stop_required", "value": True},
    )
    cases.append(SharedEnvelopeCase(
        "SCE-D06", "nonreversible_continuity", "stop heating without unsafe reversal", pre,
        _event("D06", "cancel", 12, 125, target_id="heat_part", issuer="owner"), _meta(12, 120),
        (
            {"id": "R1", "text": "For an authorized cancel targeting a commitment with a running non-reversible action, set the commitment to cancelling rather than cancelled."},
            {"id": "R2", "text": "Set that running action to stop_after_safe_point; preserve action progress and every progress record unchanged."},
            {"id": "R3", "text": "Set facts.safe_stop_required to true."},
        ), ops, apply_typed_operations(pre, ops),
    ))

    if len({case.family for case in cases}) != 6:
        raise AssertionError("development families must be distinct")
    return cases


def oracle_proposal(case: SharedEnvelopeCase, arm: str) -> dict[str, Any]:
    common = {
        "disposition": "APPLY",
        "reason_code": "AUTHORIZED_TRANSITION",
        "base_version": case.transaction_meta["state_version"],
        "event_id": case.event["event_id"],
    }
    if arm == "cope_semantic":
        return {"schema_version": "cope-semantic-delta-v1", **common, "operations": copy.deepcopy(list(case.oracle_operations))}
    if arm == "neutral_typed":
        operations = copy.deepcopy(list(case.oracle_operations))
        for operation in operations:
            operation["op"] = SEMANTIC_TO_NEUTRAL[operation["op"]]
        return {"schema_version": "neutral-semantic-delta-v1", **common, "operations": operations}
    if arm == "compact_semantic":
        return {"schema_version": "compact-semantic-delta-v1", **common, "writes": compact_diff(case.pre_state, case.post_state)}
    if arm == "fsr_semantic":
        return {"schema_version": "fsr-semantic-state-v1", **common, "state": copy.deepcopy(case.post_state)}
    raise SharedEnvelopeError(f"unknown arm {arm}")


def materialize_proposal(case: SharedEnvelopeCase, arm: str, proposal: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_keys = {
        "cope_semantic": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "operations"},
        "neutral_typed": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "operations"},
        "compact_semantic": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "writes"},
        "fsr_semantic": {"schema_version", "disposition", "reason_code", "base_version", "event_id", "state"},
    }[arm]
    versions = {
        "cope_semantic": "cope-semantic-delta-v1",
        "neutral_typed": "neutral-semantic-delta-v1",
        "compact_semantic": "compact-semantic-delta-v1",
        "fsr_semantic": "fsr-semantic-state-v1",
    }
    if set(proposal) != expected_keys or proposal.get("schema_version") != versions[arm]:
        raise SharedEnvelopeError("proposal schema mismatch")
    if proposal.get("disposition") != "APPLY" or proposal.get("reason_code") != "AUTHORIZED_TRANSITION":
        raise SharedEnvelopeError("disposition or reason mismatch")
    if proposal.get("base_version") != case.transaction_meta["state_version"] or proposal.get("event_id") != case.event["event_id"]:
        raise SharedEnvelopeError("event binding mismatch")
    if arm == "cope_semantic":
        semantic = apply_typed_operations(case.pre_state, proposal["operations"])
    elif arm == "neutral_typed":
        operations = copy.deepcopy(proposal["operations"])
        for operation in operations:
            if operation.get("op") not in NEUTRAL_TO_SEMANTIC:
                raise SharedEnvelopeError("unknown neutral operation")
            operation["op"] = NEUTRAL_TO_SEMANTIC[operation["op"]]
        semantic = apply_typed_operations(case.pre_state, operations)
    elif arm == "compact_semantic":
        semantic = apply_compact_writes(case.pre_state, proposal["writes"])
    else:
        semantic = copy.deepcopy(proposal["state"])
    if semantic != case.post_state:
        raise SharedEnvelopeError("semantic state differs from oracle")
    meta = commit_envelope(case.transaction_meta, case.event)
    return semantic, meta


def qualification_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in build_development_cases():
        results = {}
        for arm in ARMS:
            proposal = oracle_proposal(case, arm)
            semantic, meta = materialize_proposal(case, arm, proposal)
            results[arm] = (semantic, meta)
            rows.append({
                "case_id": case.case_id,
                "family": case.family,
                "arm": arm,
                "oracle_accepted": True,
                "semantic_state_sha256": stable_hash(semantic),
                "transaction_meta_sha256": stable_hash(meta),
                "common_input_sha256": stable_hash(case.common_input),
                "rule_clause_count": len(case.rule_clauses),
            })
        if len({stable_hash(value) for value in results.values()}) != 1:
            raise AssertionError(f"cross-arm envelope mismatch: {case.case_id}")
    return rows
