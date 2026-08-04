"""Generic governed-delta control for sequential commitment transitions.

This is a Tang-inspired operationalization, not code from arXiv:2606.31339.
It deliberately avoids CoPE operation names and uses affected scope plus
generic forest/blackboard deltas before the shared sequential validator.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from cope.sequential_semantics import (
    STATE_FIELDS,
    SequentialSemanticError,
    sequence_state_hash,
    validate_event_against_state,
    validate_sequence_transition,
)
from cope.types import canonical_json


SCHEMA = "governed-delta-v1"
PROPOSAL_FIELDS = {
    "schema_version",
    "event_id",
    "read_revision",
    "proposal_type",
    "affected_scope",
    "forest_delta",
    "blackboard_delta",
}
BLACKBOARD_FIELDS = {"current_goal", "plan", "pending_restorations"}


class GovernedDeltaError(ValueError):
    pass


def _commitment_map(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("commitments")
    if not isinstance(rows, list):
        raise GovernedDeltaError("commitments must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise GovernedDeltaError("commitment record is malformed")
        if row["id"] in mapped:
            raise GovernedDeltaError("commitment IDs are duplicated")
        mapped[row["id"]] = row
    return mapped


def governed_oracle_proposal(
    pre_state: Mapping[str, Any],
    expected_state: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct the oracle-correct control output for capability testing."""
    before = _commitment_map(pre_state)
    after = _commitment_map(expected_state)
    changed = [
        identifier
        for identifier, record in after.items()
        if identifier not in before
        or canonical_json(before[identifier]) != canonical_json(record)
    ]
    return {
        "schema_version": SCHEMA,
        "event_id": str(event["event_id"]),
        "read_revision": int(pre_state["state_version"]),
        "proposal_type": "repair",
        "affected_scope": sorted(changed),
        "forest_delta": [
            {"node_id": identifier, "after": copy.deepcopy(after[identifier])}
            for identifier in sorted(changed)
        ],
        "blackboard_delta": {
            field: copy.deepcopy(expected_state[field])
            for field in sorted(BLACKBOARD_FIELDS)
        },
    }


def materialize_governed_delta(
    proposal: Any,
    pre_state: Mapping[str, Any],
    event: Mapping[str, Any],
    physically_true_objects: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Stage a generic governed delta and publish only after shared validation."""
    try:
        validate_event_against_state(pre_state, event)
    except SequentialSemanticError as exc:
        raise GovernedDeltaError(str(exc)) from exc
    if not isinstance(proposal, Mapping) or set(proposal) != PROPOSAL_FIELDS:
        raise GovernedDeltaError("proposal fields are noncanonical")
    if proposal.get("schema_version") != SCHEMA:
        raise GovernedDeltaError("proposal schema is wrong")
    if proposal.get("event_id") != event.get("event_id"):
        raise GovernedDeltaError("proposal event is mismatched")
    if proposal.get("proposal_type") != "repair":
        raise GovernedDeltaError("proposal type is unsupported")
    if int(proposal.get("read_revision", -1)) != int(pre_state["state_version"]):
        raise GovernedDeltaError("proposal read revision is stale")

    scope = proposal.get("affected_scope")
    delta = proposal.get("forest_delta")
    blackboard = proposal.get("blackboard_delta")
    if (
        not isinstance(scope, list)
        or not scope
        or any(not isinstance(item, str) or not item for item in scope)
        or len(set(scope)) != len(scope)
    ):
        raise GovernedDeltaError("affected scope is malformed")
    if not isinstance(delta, list) or not delta:
        raise GovernedDeltaError("forest delta is malformed")
    records: dict[str, dict[str, Any]] = {}
    for item in delta:
        if not isinstance(item, Mapping) or set(item) != {"node_id", "after"}:
            raise GovernedDeltaError("forest delta record is malformed")
        identifier = item.get("node_id")
        record = item.get("after")
        if (
            not isinstance(identifier, str)
            or not isinstance(record, dict)
            or record.get("id") != identifier
            or identifier in records
        ):
            raise GovernedDeltaError("forest delta identity is malformed")
        records[identifier] = copy.deepcopy(record)
    if set(scope) != set(records):
        raise GovernedDeltaError("affected scope and forest delta disagree")
    if not isinstance(blackboard, Mapping) or set(blackboard) != BLACKBOARD_FIELDS:
        raise GovernedDeltaError("blackboard delta is malformed")

    before_hash = sequence_state_hash(pre_state)
    staged = copy.deepcopy(dict(pre_state))
    staged_rows = staged["commitments"]
    positions = {row["id"]: index for index, row in enumerate(staged_rows)}
    for identifier in scope:
        if identifier in positions:
            staged_rows[positions[identifier]] = records[identifier]
        else:
            staged_rows.append(records[identifier])
    for field in BLACKBOARD_FIELDS:
        staged[field] = copy.deepcopy(blackboard[field])
    staged["state_version"] = int(pre_state["state_version"]) + 1
    staged["evidence_versions"] = {
        "event_id": str(event["event_id"]),
        "world_version": int(event["world_version"]),
        "input_state_version": int(pre_state["state_version"]),
    }
    if set(staged) != STATE_FIELDS:
        raise GovernedDeltaError("staged state fields drifted")
    try:
        directive = validate_sequence_transition(
            pre_state, staged, event, physically_true_objects
        )
    except SequentialSemanticError as exc:
        raise GovernedDeltaError(f"shared verifier rejected proposal: {exc}") from exc
    receipt = {
        "accepted": True,
        "proposal_type": "repair",
        "affected_scope": list(scope),
        "read_revision": int(pre_state["state_version"]),
        "published_revision": int(staged["state_version"]),
        "before_hash": before_hash,
        "after_hash": sequence_state_hash(staged),
        "common_validator_calls": 1,
    }
    return staged, receipt, directive

