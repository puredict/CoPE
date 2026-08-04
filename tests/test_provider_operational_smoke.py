from cope.types import ProviderInvocation, TokenUsage
from experiments.provider_operational_smoke import build_smoke_input, evaluate


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
