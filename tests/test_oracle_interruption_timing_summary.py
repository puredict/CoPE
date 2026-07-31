from __future__ import annotations

import copy

import pytest

from tools.summarize_oracle_interruption_timing import validate_rows


def row(mode: str) -> dict[str, str]:
    return {
        "state_id": "0",
        "timing": "post_lift",
        "mode": mode,
        "event_step": "280",
        "action_prefix_sha256": "a" * 64,
        "sim_state_before_patch_sha256": "b" * 64,
        "sim_state_after_patch_sha256": "b" * 64,
        "eef_at_event": "[0.1,0.2,0.3]",
        "held_position_at_event": "[0.1,0.2,0.29]",
        "patch_preserved_sim_state": "True",
        "patch_emitted_no_action": "True",
        "oracle_execution": "True",
        "oracle_operation_selection": "True",
        "learned_policy_used": "False",
        "physical_truth_before_first_patch": "True",
        "physical_truth_before_second_patch": "True",
        "held_at_event": "True",
        "held_in_region_at_event": "False",
        "second_patch_accepted": "True",
        "hash_chain_valid": "True",
        "within_horizon": "True",
        "expected_outcome_observed": "True",
        "force_contact_collision_safety_measured": "False",
    }


def test_strict_pair_validation_accepts_matching_prefixes():
    rows = [row("stale_continue"), row("safe_return_switch")]
    assert len(validate_rows(rows)) == 2


@pytest.mark.parametrize(
    "field",
    [
        "event_step",
        "action_prefix_sha256",
        "sim_state_before_patch_sha256",
        "eef_at_event",
        "held_position_at_event",
    ],
    )
def test_strict_pair_validation_rejects_prefix_mismatch(field: str):
    stale = row("stale_continue")
    safe = copy.deepcopy(row("safe_return_switch"))
    if field == "action_prefix_sha256":
        safe[field] = "c" * 64
    elif field == "sim_state_before_patch_sha256":
        safe[field] = "c" * 64
        safe["sim_state_after_patch_sha256"] = "c" * 64
    else:
        safe[field] += "-different"
    with pytest.raises(ValueError, match="paired-prefix mismatch"):
        validate_rows([stale, safe])
