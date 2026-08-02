import inspect
from pathlib import Path

import pytest

from cope.generic_typed_interpreter import (
    GenericTypedInterpreterError,
    apply_generic_typed_patch,
)
from cope.native_ntrack import (
    derive_post_state,
    expected_patch,
    load_manifest,
    state_without_history,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"


def test_all_frozen_clean_cases_match_oracle_without_oracle_dependency():
    for case in load_manifest(MANIFEST):
        result = apply_generic_typed_patch(
            expected_patch(case.pre_state, case.event), case.pre_state, case.event
        )
        assert result == state_without_history(derive_post_state(case.pre_state, case.event))


def test_interpreter_source_has_no_forbidden_oracle_symbols():
    source = inspect.getsource(__import__("cope.generic_typed_interpreter", fromlist=["*"]))
    forbidden = ("expected" + "_patch", "derive" + "_post_state", "validate" + "_and_compile")
    assert all(name not in source for name in forbidden)


def test_generic_interpreter_allows_omission_for_common_validator_to_detect():
    case = next(item for item in load_manifest(MANIFEST) if item.case_id == "cancel_sibling")
    patch = expected_patch(case.pre_state, case.event)
    patch["operations"] = []
    result = apply_generic_typed_patch(patch, case.pre_state, case.event)
    assert result == state_without_history(case.pre_state)
    assert result != state_without_history(derive_post_state(case.pre_state, case.event))


def test_generic_interpreter_rejects_wrong_target_and_unauthorized_effect():
    cases = {item.case_id: item for item in load_manifest(MANIFEST)}
    cancel = cases["cancel_sibling"]
    wrong = expected_patch(cancel.pre_state, cancel.event)
    wrong["operations"][0]["target_id"] = "unknown:id"
    with pytest.raises(GenericTypedInterpreterError):
        apply_generic_typed_patch(wrong, cancel.pre_state, cancel.event)

    unauthorized = cases["wrong_source_revoke"]
    wrong = expected_patch(cancel.pre_state, cancel.event)
    wrong["event_id"] = unauthorized.event["event_id"]
    with pytest.raises(GenericTypedInterpreterError):
        apply_generic_typed_patch(wrong, unauthorized.pre_state, unauthorized.event)
