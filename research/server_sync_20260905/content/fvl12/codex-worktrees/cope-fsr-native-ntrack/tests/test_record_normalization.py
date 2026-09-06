import copy
from pathlib import Path

import pytest

from cope.native_ntrack import derive_post_state, load_manifest, state_without_history
from cope.record_normalization import (
    RecordNormalizationError,
    is_normalized_record_order,
    normalize_record_order,
    normalized_state_hash,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"


def test_normalization_is_idempotent_and_order_invariant():
    for case in load_manifest(CASES):
        state = state_without_history(derive_post_state(case.pre_state, case.event))
        normalized = normalize_record_order(state)
        assert normalize_record_order(normalized) == normalized
        assert is_normalized_record_order(normalized)
        reversed_state = copy.deepcopy(state)
        reversed_state["entities"].reverse()
        assert normalized_state_hash(reversed_state) == normalized_state_hash(state)


def test_duplicate_and_missing_keys_fail_closed():
    case = next(item for item in load_manifest(CASES) if item.case_id == "replace_pending_target")
    state = state_without_history(derive_post_state(case.pre_state, case.event))
    duplicate = copy.deepcopy(state)
    duplicate["commitments"].append(copy.deepcopy(duplicate["commitments"][0]))
    with pytest.raises(RecordNormalizationError):
        normalize_record_order(duplicate)
    missing = copy.deepcopy(state)
    del missing["entities"][0]["id"]
    with pytest.raises(RecordNormalizationError):
        normalize_record_order(missing)
