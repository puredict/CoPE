from __future__ import annotations

import io
import json

import pytest

from cope_benchmark.repeated_v2.provider import (
    OpenAICompatibleReasoner,
    ReasonerConfig,
    ReasonerModelUnavailable,
    ReasonerUnavailable,
    reasoner_from_environment,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_missing_production_reasoner_configuration_fails_without_a_call() -> None:
    with pytest.raises(ReasonerModelUnavailable, match="COPE_REASONER_MODEL") as exc:
        reasoner_from_environment({})
    assert exc.value.status == "BLOCKED_REASONER_MODEL_UNAVAILABLE"

    with pytest.raises(ReasonerUnavailable, match="COPE_REASONER_FACTORY") as exc:
        reasoner_from_environment({"COPE_REASONER_MODEL": "m"})
    assert type(exc.value) is ReasonerUnavailable


def test_openai_compatible_adapter_preserves_request_and_provider_usage() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["request"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response(json.dumps({
            "choices": [{"message": {"content": "{\"operations\":[]}"}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 5},
        }).encode())

    reasoner = OpenAICompatibleReasoner(
        endpoint="http://127.0.0.1:8000/v1", model="production-model",
        api_key="test-only-secret", timeout_seconds=12, opener=opener,
    )
    config = ReasonerConfig(provider=reasoner.provider_id, model="production-model",
                            max_input_tokens=1000, max_output_tokens=100)
    messages = [{"role": "user", "content": "public evidence"}]
    response = reasoner.complete(messages=messages, config=config)
    assert captured["request"] == {
        "model": "production-model", "messages": messages, "temperature": 0.0,
        "top_p": 1.0, "max_tokens": 100, "seed": 0,
    }
    assert captured["timeout"] == 12
    assert (response.input_tokens, response.output_tokens, response.fixture) == (17, 5, False)
    assert response.token_count_kind == "provider_usage"
    assert "test-only-secret" not in json.dumps(reasoner.identity)


def test_production_adapter_rejects_missing_exact_usage() -> None:
    def opener(request, *, timeout):
        return Response(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())

    reasoner = OpenAICompatibleReasoner(
        endpoint="http://127.0.0.1:8000/v1", model="production-model",
        api_key=None, opener=opener,
    )
    with pytest.raises(ReasonerUnavailable, match="exact usage"):
        reasoner.complete(messages=[], config=ReasonerConfig(
            provider=reasoner.provider_id, model="production-model"))
    assert reasoner.calls == 1


def test_production_adapter_rejects_provider_identity_mismatch_before_call() -> None:
    reasoner = OpenAICompatibleReasoner(
        endpoint="http://127.0.0.1:8000/v1", model="production-model",
        api_key=None, opener=lambda *args, **kwargs: None,
    )
    with pytest.raises(ValueError, match="decoding contract"):
        reasoner.complete(messages=[], config=ReasonerConfig(
            provider="different-provider", model="production-model"))
    assert reasoner.calls == 0
