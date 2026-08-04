from __future__ import annotations

import json
from pathlib import Path

from cope.native_ntrack import build_case, derive_post_state, expected_patch, state_without_history
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider, normalized_wire_request_hash
from experiments.sequential_formal_runner_v2 import invocation_failure
from experiments.native_output_ntrack import run_pair


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_nonfake_adapter_has_matched_common_input_and_redacts_credential(monkeypatch) -> None:
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")
    outputs = [expected_patch(case.pre_state, case.event), {k: v for k, v in case.pre_state.items() if k != "action_history"}]
    captured = []
    def fake_urlopen(req, timeout):
        captured.append(req)
        output = outputs.pop(0)
        return _Response({
            "id": "request-id", "choices": [{"message": {"content": json.dumps(output)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        })
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    monkeypatch.setattr("cope.providers.openai_compatible.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
    })
    patch_call = provider.patch(case.recovery_input, case.pre_state)
    full_call = provider.regenerate(case.recovery_input)
    assert provider.metadata.is_fake is False
    assert patch_call.raw_request["recovery_input"] == full_call.raw_request["recovery_input"]
    assert patch_call.raw_request["common_input_message_sha256"] == full_call.raw_request["common_input_message_sha256"]
    assert normalized_wire_request_hash(patch_call) == normalized_wire_request_hash(full_call)
    assert "secret-value" not in json.dumps(patch_call.raw_request)
    assert "secret-value" not in json.dumps(patch_call.raw_response)
    assert len(captured) == 2


def test_oracle_transport_controls_pass_fairness_and_shared_validator(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
    })
    case_ids = [
        "no_op", "cancel_sibling", "replace_pending_target", "activate_override",
        "release_override", "world_change_release", "wrong_source_revoke", "stale_version",
        "idempotence", "irrelevant_sibling_change", "continuity_valid", "continuity_invalid",
    ]
    for case_id in case_ids:
        case = build_case(case_id, "control", "oracle", "test_only")
        outputs = [
            expected_patch(case.pre_state, case.event),
            state_without_history(derive_post_state(case.pre_state, case.event)),
        ]
        def fake_urlopen(req, timeout):
            return _Response({
                "id": "request-id", "choices": [{"message": {"content": json.dumps(outputs.pop(0))}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            })
        monkeypatch.setattr("cope.providers.openai_compatible.request.urlopen", fake_urlopen)
        rows = run_pair(case, provider)
        assert len(rows) == 2
        assert all(row["fairness_pass"] for row in rows)
        assert all(row["first_pass_valid"] for row in rows)
        assert all(row["semantic_correct"] for row in rows)


def test_reasoning_effort_is_identical_and_auditable_across_arms() -> None:
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
        "reasoning_effort": "none",
    })
    requests = [
        provider.build_audited_request("patch", case.recovery_input, provider.patch_contract),
        provider.build_audited_request("compact", case.recovery_input, provider.compact_contract),
        provider.build_audited_request("regenerate", case.recovery_input, provider.full_contract),
    ]
    assert all(item["wire_payload"]["reasoning"] == {"effort": "none"} for item in requests)
    assert provider.reasoning_effort == "none"


def test_adapter_separates_malformed_envelope_from_model_json_failure(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
    })
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")

    monkeypatch.setattr(
        "cope.providers.openai_compatible.request.urlopen",
        lambda req, timeout: _Response({"id": "missing-choices"}),
    )
    malformed = provider.patch(case.recovery_input, case.pre_state)
    assert malformed.validation_failure == "provider_malformed_envelope"
    assert invocation_failure(malformed) == "provider_malformed_envelope"
    assert malformed.raw_response["response_sha256"]

    monkeypatch.setattr(
        "cope.providers.openai_compatible.request.urlopen",
        lambda req, timeout: _Response({
            "id": "valid-envelope", "choices": [{"message": {"content": "not-json"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }),
    )
    bad_content = provider.patch(case.recovery_input, case.pre_state)
    assert bad_content.validation_failure is None
    assert bad_content.parse_failure
    assert invocation_failure(bad_content) == "response_parse_failure"
    assert bad_content.raw_response["response_sha256"]


def test_adapter_rejects_prose_or_markdown_wrapped_json(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
    })
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")
    for content in (
        'Here is the result: {"status":"ready"}',
        '```json\n{"status":"ready"}\n```',
        '[{"status":"ready"}]',
        '{"status":NaN}',
        '{"status":Infinity}',
    ):
        monkeypatch.setattr(
            "cope.providers.openai_compatible.request.urlopen",
            lambda req, timeout, content=content: _Response({
                "id": "wrapped", "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }),
        )
        invocation = provider.patch(case.recovery_input, case.pre_state)
        assert invocation.parsed_output is None
        assert invocation.parse_failure
        assert invocation_failure(invocation) == "response_parse_failure"


def test_adapter_classifies_wrong_envelope_types_as_infrastructure(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "test-real-adapter", "model": "frozen-model-version",
        "api_key_env": "TEST_PROVIDER_KEY", "max_retries": 0,
    })
    case = build_case("cancel_sibling", "smoke", "cancel", "public_synthetic")
    for payload in (
        {"id": "bad-message", "choices": [{"message": "not-an-object"}]},
        {
            "id": "bad-usage", "choices": [{"message": {"content": "{}"}}],
            "usage": [],
        },
    ):
        monkeypatch.setattr(
            "cope.providers.openai_compatible.request.urlopen",
            lambda req, timeout, payload=payload: _Response(payload),
        )
        invocation = provider.patch(case.recovery_input, case.pre_state)
        assert invocation.validation_failure == "provider_malformed_envelope"
        assert invocation.raw_response["response_sha256"]
