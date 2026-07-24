from __future__ import annotations

import importlib
import re
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any, Callable

from cope.types import (
    ProviderInvocation,
    ProviderMetadata,
    RecoveryInput,
)


SECRET_KEY_PATTERN = re.compile(
    r"(api[-_]?key|authorization|bearer|access[-_]?token|secret|password|cookie)",
    flags=re.IGNORECASE,
)


class HighLevelRecoveryProvider(ABC):
    """Provider-neutral interface shared by regeneration and patch modes.

    Implementations must return only externally visible request/response data.
    Private chain-of-thought must never be requested or included.
    """

    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    def regenerate(self, recovery_input: RecoveryInput) -> ProviderInvocation:
        raise NotImplementedError

    @abstractmethod
    def patch(
        self,
        recovery_input: RecoveryInput,
        constraint_state: dict[str, Any],
    ) -> ProviderInvocation:
        raise NotImplementedError


def assert_secret_free(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                raise ValueError(f"secret-like field is forbidden in provider logs: {path}.{key}")
            assert_secret_free(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_secret_free(item, f"{path}[{index}]")


def validate_provider_invocation(
    invocation: ProviderInvocation,
    *,
    expected_mode: str,
    recovery_input: RecoveryInput,
    metadata: ProviderMetadata,
) -> None:
    if invocation.mode != expected_mode:
        raise ValueError(f"provider returned mode {invocation.mode!r}; expected {expected_mode!r}")
    if invocation.retry_count > metadata.max_retries:
        raise ValueError("provider retry count exceeded configured maximum")
    if invocation.usage.prompt_tokens > metadata.max_prompt_tokens:
        raise ValueError("provider prompt token usage exceeded ceiling")
    if invocation.usage.completion_tokens > metadata.max_completion_tokens:
        raise ValueError("provider completion token usage exceeded ceiling")
    common_input = invocation.raw_request.get("recovery_input")
    if common_input != recovery_input.as_payload():
        raise ValueError("provider raw request does not contain the exact common recovery input")
    assert_secret_free(invocation.raw_request, "raw_request")
    assert_secret_free(invocation.raw_response, "raw_response")
    if invocation.timeout:
        raise TimeoutError("high-level provider timed out")
    if invocation.parse_failure:
        raise ValueError(f"high-level provider parse failure: {invocation.parse_failure}")
    if invocation.validation_failure:
        raise ValueError(f"high-level provider validation failure: {invocation.validation_failure}")
    if invocation.parsed_output is None:
        raise ValueError("high-level provider did not return parsed output")


def provider_call_record(invocation: ProviderInvocation, metadata: ProviderMetadata) -> dict[str, Any]:
    """Return the audit record; metadata never includes credentials."""

    assert_secret_free(invocation.raw_request, "raw_request")
    assert_secret_free(invocation.raw_response, "raw_response")
    return {
        "provider_metadata": asdict(metadata),
        "mode": invocation.mode,
        "raw_request": invocation.raw_request,
        "raw_response": invocation.raw_response,
        "parsed_output": invocation.parsed_output,
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "retry_count": invocation.retry_count,
        "timeout": invocation.timeout,
        "parse_failure": invocation.parse_failure,
        "validation_failure": invocation.validation_failure,
        "latency_seconds": invocation.latency_seconds,
    }


def load_object(spec: str) -> Any:
    if ":" not in spec:
        raise ValueError("factory spec must use module:attribute")
    module_name, attribute = spec.split(":", 1)
    if not module_name or not attribute:
        raise ValueError("factory spec must use module:attribute")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ValueError(f"{spec!r} does not resolve to an attribute") from exc


def load_provider_factory(spec: str) -> Callable[[dict[str, Any]], HighLevelRecoveryProvider]:
    factory = load_object(spec)
    if not callable(factory):
        raise TypeError(f"provider factory {spec!r} is not callable")
    return factory
