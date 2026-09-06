from __future__ import annotations

import copy
from typing import Any, Mapping

from cope.types import canonical_json, stable_hash


NORMALIZATION_VERSION = "stable-record-order-v1"
COLLECTION_KEYS = {
    "commitments": "id",
    "entities": "id",
    "progress_ledger": "milestone_id",
}


class RecordNormalizationError(ValueError):
    pass


def normalize_record_order(state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise RecordNormalizationError("state must be a mapping")
    caller_before = canonical_json(state)
    normalized = copy.deepcopy(dict(state))
    for collection, stable_key in COLLECTION_KEYS.items():
        rows = normalized.get(collection)
        if not isinstance(rows, list):
            raise RecordNormalizationError(f"{collection} must be a list")
        values = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise RecordNormalizationError(f"{collection} record must be a mapping")
            value = row.get(stable_key)
            if not isinstance(value, str):
                raise RecordNormalizationError(f"{collection} record requires string {stable_key}")
            values.append(value)
        if len(values) != len(set(values)):
            raise RecordNormalizationError(f"{collection} contains duplicate stable keys")
        normalized[collection] = sorted(rows, key=lambda row: row[stable_key])
    if canonical_json(state) != caller_before:
        raise RuntimeError("record normalization mutated caller state")
    return normalized


def is_normalized_record_order(state: Mapping[str, Any]) -> bool:
    return canonical_json(state) == canonical_json(normalize_record_order(state))


def normalized_state_hash(state: Mapping[str, Any]) -> str:
    return stable_hash({
        "normalization_version": NORMALIZATION_VERSION,
        "state": normalize_record_order(state),
    })
