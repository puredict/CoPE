from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cope.native_ntrack import (
    NativeOutputError,
    build_case,
    derive_post_state,
    expected_patch,
    materialize_patch,
    parse_full_state,
    parse_patch,
    state_without_history,
    validate_and_compile,
)


CASES = [
    "no_op", "cancel_sibling", "replace_pending_target", "activate_override",
    "release_override", "world_change_release", "wrong_source_revoke", "stale_version",
    "idempotence", "irrelevant_sibling_change", "continuity_valid", "continuity_invalid",
]


@pytest.mark.parametrize("case_id", CASES)
def test_oracle_patch_and_full_state_share_validator_and_compiler(case_id: str) -> None:
    case = build_case(case_id, "smoke", "test", "public_synthetic")
    patch = parse_patch(expected_patch(case.pre_state, case.event))
    materialized = materialize_patch(patch, case.pre_state, case.event)
    full_state = parse_full_state(state_without_history(derive_post_state(case.pre_state, case.event)))
    assert materialized == full_state
    assert validate_and_compile(materialized, case.pre_state, case.event) == validate_and_compile(
        full_state, case.pre_state, case.event
    )


@pytest.mark.parametrize("case_id", ["wrong_source_revoke", "stale_version", "idempotence"])
def test_unauthorized_stale_and_duplicate_events_require_empty_patch(case_id: str) -> None:
    case = build_case(case_id, "smoke", "test", "public_synthetic")
    assert expected_patch(case.pre_state, case.event)["operations"] == []
    bad = expected_patch(case.pre_state, case.event)
    bad["operations"] = [{"op": "cancel_commitment", "target_id": "deliver:b"}]
    with pytest.raises(NativeOutputError, match="authorized minimum"):
        materialize_patch(bad, case.pre_state, case.event)


def test_invalid_continuity_requires_explicit_action_cancellation() -> None:
    case = build_case("continuity_invalid", "smoke", "continuity", "public_synthetic")
    ops = expected_patch(case.pre_state, case.event)["operations"]
    assert [item["op"] for item in ops] == ["activate_override", "cancel_executing_action"]
    post = derive_post_state(case.pre_state, case.event)
    assert post["plan"][0]["status"] == "cancelled"
    assert post["plan"][0]["cancellation_reason"]


def test_world_change_release_revalidates_current_grounding() -> None:
    case = build_case("world_change_release", "smoke", "release", "public_synthetic")
    post = derive_post_state(case.pre_state, case.event)
    commitment = next(item for item in post["commitments"] if item["id"] == "deliver:b")
    assert commitment["grounding"] == ["package_b", "dock_2"]
    assert post["plan"][0]["arguments"] == ["package_b", "dock_2"]


def test_full_state_parser_rejects_controller_prompt() -> None:
    case = build_case("no_op", "smoke", "noop", "public_synthetic")
    state = state_without_history(derive_post_state(case.pre_state, case.event))
    state["controller_prompt"] = "execute stale task"
    with pytest.raises(NativeOutputError, match="fields"):
        parse_full_state(state)
