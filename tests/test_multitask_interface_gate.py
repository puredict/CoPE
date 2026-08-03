from __future__ import annotations

from cope.semantic_live_runner import build_expected_live_post_state, build_live_pre_state
from cope.semantic_replacement import FullStateValidationError, validate_event_sibling_objects
from experiments import multitask_interface_gate as gate


CASES = (
    {"case_id":"task0_replace","event_type":"replace_pending_goal","done_object":"alphabet_soup_1","pending_object":"tomato_sauce_1","replacement_object":"cream_cheese_1","previous_state_version":"0","policy_step":"200"},
    {"case_id":"task7_cancel","event_type":"cancel_pending_goal","done_object":"alphabet_soup_1","pending_object":"cream_cheese_1","replacement_object":"","previous_state_version":"0","policy_step":"200"},
)


def test_every_arm_accepts_oracle_correct_output() -> None:
    for case in CASES:
        event = gate.build_event(case)
        expected = build_expected_live_post_state(event)
        for arm in gate.ARMS:
            candidate, directive, proposal_hash = gate.run_arm(arm, event)
            assert candidate == expected
            assert directive
            assert proposal_hash


def test_compact_diff_is_allowlisted_and_metadata_free() -> None:
    event = gate.build_event(CASES[0])
    proposal = gate.compact_oracle_proposal(
        build_live_pre_state(event), build_expected_live_post_state(event), event
    )
    assert proposal["writes"]
    assert all(not write["path"].startswith("/state_version") for write in proposal["writes"])
    assert all(not write["path"].startswith("/evidence_versions") for write in proposal["writes"])


def test_event_siblings_fail_closed_when_identical_or_unknown() -> None:
    for done, pending in (("butter_1", "butter_1"), ("unknown", "butter_1")):
        try:
            validate_event_sibling_objects(done, pending)
        except FullStateValidationError:
            pass
        else:
            raise AssertionError("invalid event siblings must fail closed")
