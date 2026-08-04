from __future__ import annotations

import csv

import pytest

from cope.formal_recovery import AMBIGUOUS_FAILURE, FormalRecoveryLedger
from cope.occurrence_prompting import build_recovery_input
from cope.occurrence_sequence import build_recurrence_case, cope_oracle, expected_next_state
from cope.types import ProviderInvocation, TokenUsage
from experiments.occurrence_formal_runner import (
    FormalTransitionError, history_is_valid, obtain_proposal,
)


class FixtureProvider:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = 0

    def call_contract(self, mode, recovery, contract):
        self.calls += 1
        return ProviderInvocation(
            mode=mode, raw_request={},
            raw_response={"response_sha256": "response"},
            parsed_output=self.proposal, usage=TokenUsage(10, 5),
            latency_seconds=0.1,
        )


def fixture():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    with (root / "manifests" / "occurrence_learned_formal_40x5_v1.csv").open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    pre, event, _ = build_recurrence_case(
        case_id=row["case_id"], done_object=row["done_object"],
        recurring_object=row["recurring_object"],
        intermediate_object=row["intermediate_object"],
        recurrence_depth=int(row["recurrence_depth"]),
    )
    return row, pre, event, build_recovery_input(
        case_id=row["case_id"], pre_state=pre, event=event
    )


def test_occurrence_response_recovery_never_calls_provider_twice(tmp_path):
    row, pre, event, recovery = fixture()
    provider = FixtureProvider(cope_oracle(event))
    ledger = FormalRecoveryLedger(tmp_path / "run", {"run": "test"}, resume=False)
    first, _ = obtain_proposal(
        ledger=ledger, row=row, arm="cope", provider=provider, recovery=recovery
    )
    second, _ = obtain_proposal(
        ledger=ledger, row=row, arm="cope", provider=provider, recovery=recovery
    )
    assert first == second
    assert provider.calls == 1
    assert history_is_valid(expected_next_state(pre, event), row)


def test_occurrence_intent_without_response_is_ambiguous_and_not_recalled(tmp_path):
    row, _, event, recovery = fixture()
    provider = FixtureProvider(cope_oracle(event))
    ledger = FormalRecoveryLedger(tmp_path / "run", {"run": "test"}, resume=False)
    ledger.record_intent({
        "sequence_id": row["case_id"], "arm": "cope", "event_index": 1,
        "input_sha256": recovery.input_hash,
    })
    with pytest.raises(FormalTransitionError, match=AMBIGUOUS_FAILURE):
        obtain_proposal(
            ledger=ledger, row=row, arm="cope", provider=provider,
            recovery=recovery,
        )
    assert provider.calls == 0
