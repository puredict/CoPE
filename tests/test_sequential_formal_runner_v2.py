from __future__ import annotations

import pytest

from cope.governed_delta import governed_oracle_proposal
from cope.sequential_prompting import build_sequential_recovery_input
from cope.sequential_semantics import (
    build_expected_next_state,
    build_initial_sequence_state,
    build_sequence_event,
    fsr_oracle_proposal,
    full_replan_oracle_proposal,
    initialize_typed_sequence_state,
    neutral_json_oracle_proposal,
    sparse_oracle_proposal,
)
from cope.types import ProviderInvocation, TokenUsage
from experiments.sequential_formal_runner_v2 import FormalTransitionError, call_and_transition


class FixtureProvider:
    def __init__(self, proposal=None, failure=""):
        self.proposal = proposal
        self.failure = failure

    def call_contract(self, mode, recovery_input, contract):
        return ProviderInvocation(
            mode=mode,
            raw_request={"recovery_input": recovery_input.as_payload()},
            raw_response={"response_sha256": "abc"},
            parsed_output=self.proposal,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
            validation_failure=self.failure or None,
            latency_seconds=0.5,
        )


def fixture():
    state = build_initial_sequence_state(
        sequence_id="runner-unit",
        done_object="alphabet_soup_1",
        pending_object="tomato_sauce_1",
        available_objects=(
            "alphabet_soup_1", "tomato_sauce_1", "cream_cheese_1", "butter_1"
        ),
        world_version=100,
    )
    event = build_sequence_event(
        state,
        sequence_id="runner-unit",
        step_index=1,
        done_object="alphabet_soup_1",
        event_type="replace_pending_goal",
        replacement_object="cream_cheese_1",
        world_version=101,
    )
    recovery = build_sequential_recovery_input(
        sequence_id="runner-unit",
        task_id=0,
        state_id=0,
        event=event,
        pre_state=state,
        physically_true_objects=("alphabet_soup_1",),
        processed_event_ids=(),
        event_index=1,
    )
    return state, event, recovery


@pytest.mark.parametrize("arm", ["cope", "neutral_patch", "governed_delta", "fsr_pc", "full_replan"])
def test_formal_transition_bridge_accepts_oracle_correct_arm_output(arm):
    state, event, recovery = fixture()
    expected = build_expected_next_state(state, event)
    if arm == "cope":
        proposal = sparse_oracle_proposal(event, neutral=False)
        typed = initialize_typed_sequence_state(
            sequence_id="runner-unit",
            done_object="alphabet_soup_1",
            pending_object="tomato_sauce_1",
        )
    elif arm == "neutral_patch":
        proposal = neutral_json_oracle_proposal(state, expected, event)
        typed = None
    elif arm == "governed_delta":
        proposal = governed_oracle_proposal(state, expected, event)
        typed = None
    elif arm == "fsr_pc":
        proposal = fsr_oracle_proposal(expected)
        typed = None
    else:
        proposal = full_replan_oracle_proposal(expected, event)
        typed = None
    candidate, _, receipt, directive, diagnostics = call_and_transition(
        provider=FixtureProvider(proposal),
        arm=arm,
        recovery_input=recovery,
        event=event,
        logical_state=state,
        typed_state=typed,
        physically_true=("alphabet_soup_1",),
    )
    assert candidate == expected
    assert receipt.get("accepted", receipt.get("published")) is True
    assert directive == "place_in(cream_cheese_1, basket_1_contain_region)"
    assert diagnostics["provider_called"] is True
    assert diagnostics["prompt_tokens"] == 100


def test_provider_outage_retains_attempt_diagnostics_for_fail_closed_result():
    state, event, recovery = fixture()
    with pytest.raises(FormalTransitionError) as captured:
        call_and_transition(
            provider=FixtureProvider(failure="provider_http_503"),
            arm="cope",
            recovery_input=recovery,
            event=event,
            logical_state=state,
            typed_state=initialize_typed_sequence_state(
                sequence_id="runner-unit",
                done_object="alphabet_soup_1",
                pending_object="tomato_sauce_1",
            ),
            physically_true=("alphabet_soup_1",),
        )
    assert captured.value.diagnostics["provider_called"] is True
    assert captured.value.diagnostics["prompt_tokens"] == 100
