import json

import pytest

from cope.types import ProviderInvocation, TokenUsage
from experiments.provider_operational_smoke import (
    build_smoke_input, evaluate, execute_one_draw,
)


def test_operational_smoke_requires_exact_zero_retry_acknowledgement():
    good = ProviderInvocation(
        mode="compact", raw_request={}, raw_response={"response_sha256": "abc"},
        parsed_output={"status": "ready"}, usage=TokenUsage(10, 2),
        latency_seconds=0.1,
    )
    assert evaluate(good)["gate"] == "PASS"
    wrong = ProviderInvocation(
        mode="compact", raw_request={}, raw_response={"response_sha256": "abc"},
        parsed_output={"status": "ready", "extra": True},
    )
    assert evaluate(wrong)["gate"] == "FAIL"
    assert build_smoke_input().task_progress["experimental_case"] is False


class _Provider:
    def __init__(self, invocation=None, error=None):
        self.invocation = invocation
        self.error = error
        self.calls = 0

    def call_contract(self, *_args):
        self.calls += 1
        if self.error:
            raise self.error
        return self.invocation


def test_operational_smoke_persists_intent_before_call_and_refuses_recall(tmp_path):
    provider = _Provider(error=RuntimeError("injected interruption"))
    output = tmp_path / "smoke"
    with pytest.raises(RuntimeError, match="injected interruption"):
        execute_one_draw(
            output_dir=output, provider=provider, recovery=build_smoke_input(),
            runtime_commit="abc", endpoint="https://example.invalid/v1",
        )
    intent = json.loads((output / "00_CALL_INTENT.txt").read_text())
    assert intent["max_retries"] == 0
    assert intent["credential_logged"] is False
    assert not (output / "01_REDACTED_TRACE.txt").exists()
    assert not (output / "00_STATUS.txt").exists()
    with pytest.raises(FileExistsError):
        execute_one_draw(
            output_dir=output, provider=provider, recovery=build_smoke_input(),
            runtime_commit="abc", endpoint="https://example.invalid/v1",
        )
    assert provider.calls == 1


def test_operational_smoke_publishes_response_before_terminal_status(tmp_path):
    good = ProviderInvocation(
        mode="compact", raw_request={"redacted": True},
        raw_response={"response_sha256": "abc"},
        parsed_output={"status": "ready"}, usage=TokenUsage(10, 2),
        latency_seconds=0.1,
    )
    output = tmp_path / "smoke"
    assert execute_one_draw(
        output_dir=output, provider=_Provider(invocation=good),
        recovery=build_smoke_input(), runtime_commit="abc",
        endpoint="https://example.invalid/v1",
    ) == 0
    assert json.loads((output / "00_STATUS.txt").read_text())["gate"] == "PASS"
    assert (output / "00_CALL_INTENT.txt").exists()
    assert (output / "01_REDACTED_TRACE.txt").exists()
