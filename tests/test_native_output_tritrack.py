from __future__ import annotations

import csv
import json

from cope.compact_tx import proposal_from_verbose_carrier
from cope.native_ntrack import (
    build_case,
    derive_post_state,
    expected_patch,
    state_without_history,
    validate_and_compile,
)
from cope.providers.openai_compatible import (
    OpenAICompatibleRecoveryProvider,
    normalized_wire_request_hash,
)
from cope.tx_exec import execute_transaction
from experiments.native_output_tritrack import (
    run_triplet,
    write_blocked_results,
    write_preflight_fairness,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def outputs(case):
    verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
    return {
        "cope": expected_patch(case.pre_state, case.event),
        "compact_tx": proposal_from_verbose_carrier(verbose.carrier),
        "fsr_pc": state_without_history(derive_post_state(case.pre_state, case.event)),
    }


def provider(monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    return OpenAICompatibleRecoveryProvider(
        {
            "provider": "test-real-adapter",
            "model": "frozen-model-version",
            "api_key_env": "TEST_PROVIDER_KEY",
            "max_retries": 0,
        }
    )


def test_provider_three_modes_have_identical_normalized_request(monkeypatch) -> None:
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")
    expected = outputs(case)
    queue = [expected["cope"], expected["compact_tx"], expected["fsr_pc"]]

    def fake_urlopen(req, timeout):
        return _Response(
            {
                "id": "request-id",
                "choices": [{"message": {"content": json.dumps(queue.pop(0))}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        )

    p = provider(monkeypatch)
    monkeypatch.setattr("cope.providers.openai_compatible.request.urlopen", fake_urlopen)
    calls = [
        p.patch(case.recovery_input, case.pre_state),
        p.compact(case.recovery_input),
        p.regenerate(case.recovery_input),
    ]
    assert {call.mode for call in calls} == {"patch", "compact", "regenerate"}
    assert len({call.raw_request["common_input_message_sha256"] for call in calls}) == 1
    assert len({normalized_wire_request_hash(call) for call in calls}) == 1
    assert all("secret-value" not in json.dumps(call.raw_request) for call in calls)


def test_oracle_transport_controls_pass_all_three_arms(monkeypatch) -> None:
    p = provider(monkeypatch)
    case_ids = [
        "no_op", "replace_pending_target", "wrong_source_revoke", "continuity_invalid",
        "cancel_sibling", "activate_override", "release_override", "world_change_release",
        "stale_version", "idempotence", "irrelevant_sibling_change", "continuity_valid",
    ]
    for index, case_id in enumerate(case_ids):
        case = build_case(case_id, "control", "oracle", "test_only")
        expected = outputs(case)
        arms = ["cope", "compact_tx", "fsr_pc"]
        offset = index % 3
        call_order = arms[offset:] + arms[:offset]
        queue = [expected[arm] for arm in call_order]

        def fake_urlopen(req, timeout):
            return _Response(
                {
                    "id": "request-id",
                    "choices": [{"message": {"content": json.dumps(queue.pop(0))}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                }
            )

        monkeypatch.setattr("cope.providers.openai_compatible.request.urlopen", fake_urlopen)
        rows = run_triplet(case, p, order_index=index)
        assert len(rows) == 3
        assert all(row["fairness_pass"] for row in rows)
        assert all(row["first_pass_valid"] for row in rows)
        assert all(row["semantic_correct"] for row in rows)
        assert {row["call_order_position"] for row in rows} == {0, 1, 2}


def test_credential_blocked_ledger_retains_36_cells_and_balanced_order(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("TEST_PROVIDER_KEY", raising=False)
    p = OpenAICompatibleRecoveryProvider(
        {
            "provider": "test-real-adapter",
            "model": "frozen-model-version",
            "api_key_env": "TEST_PROVIDER_KEY",
            "max_retries": 0,
        }
    )
    case_ids = [
        "no_op", "replace_pending_target", "wrong_source_revoke", "continuity_invalid",
        "cancel_sibling", "activate_override", "release_override", "world_change_release",
        "stale_version", "idempotence", "irrelevant_sibling_change", "continuity_valid",
    ]
    cases = [build_case(case_id, "control", "test", "public_synthetic") for case_id in case_ids]
    fairness_path = tmp_path / "fairness.csv"
    ledger_path = tmp_path / "ledger.csv"
    assert write_preflight_fairness(fairness_path, cases, p) is True
    write_blocked_results(ledger_path, cases, p)
    with ledger_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 36
    assert {row["arm"] for row in rows} == {"cope", "compact_tx", "fsr_pc"}
    for arm in ("cope", "compact_tx", "fsr_pc"):
        selected = [row for row in rows if row["arm"] == arm]
        assert sum(row["call_order_position"] == "0" for row in selected) == 4
    assert all(row["provider_status"] == "configuration_blocked" for row in rows)

