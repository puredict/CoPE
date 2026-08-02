from __future__ import annotations

import json
from pathlib import Path

from cope.native_ntrack import build_case, expected_patch
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider, normalized_wire_request_hash


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
