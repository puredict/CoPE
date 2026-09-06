import inspect
from pathlib import Path

import pytest

import cope.decomposed_validator as module
from cope.decomposed_validator import DecomposedValidationError, validate_decomposed
from cope.native_ntrack import derive_post_state, load_manifest, state_without_history


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"


def test_source_has_no_forbidden_oracle_symbols():
    source = inspect.getsource(module)
    forbidden = ("expected" + "_patch", "derive" + "_post_state", "validate" + "_and_compile")
    assert all(name not in source for name in forbidden)


def test_all_clean_states_pass_decomposed_validator():
    for case in load_manifest(CASES):
        candidate = state_without_history(derive_post_state(case.pre_state, case.event))
        assert validate_decomposed(candidate, case.pre_state, case.event)


def test_omitted_transition_is_rejected_by_named_groups():
    case = next(item for item in load_manifest(CASES) if item.case_id == "replace_pending_target")
    candidate = state_without_history(case.pre_state)
    with pytest.raises(DecomposedValidationError) as caught:
        validate_decomposed(candidate, case.pre_state, case.event)
    assert "version_evidence" in caught.value.violations
    assert "identity_lifecycle" in caught.value.violations
    assert "goal_consistency" in caught.value.violations


def test_unaffected_sibling_corruption_is_rejected():
    case = next(item for item in load_manifest(CASES) if item.case_id == "release_override")
    candidate = state_without_history(derive_post_state(case.pre_state, case.event))
    next(item for item in candidate["commitments"] if item["id"] == "deliver:a")["lifecycle_status"] = "cancelled"
    with pytest.raises(DecomposedValidationError) as caught:
        validate_decomposed(candidate, case.pre_state, case.event)
    assert "unaffected_scope" in caught.value.violations


def test_unknown_field_on_affected_target_is_rejected():
    case = next(item for item in load_manifest(CASES) if item.case_id == "cancel_sibling")
    candidate = state_without_history(derive_post_state(case.pre_state, case.event))
    next(item for item in candidate["commitments"] if item["id"] == "deliver:b")["__unknown_mutation__"] = "mutation"
    with pytest.raises(DecomposedValidationError) as caught:
        validate_decomposed(candidate, case.pre_state, case.event)
    assert caught.value.violations["identity_lifecycle"] == [
        "commitment_fields_noncanonical:deliver:b"
    ]
