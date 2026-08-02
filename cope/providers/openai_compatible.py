from __future__ import annotations

import json
import hashlib
import os
import socket
import time
from pathlib import Path
from typing import Any, Mapping
from urllib import error, request

from cope.providers.base import HighLevelRecoveryProvider
from cope.types import ProviderInvocation, ProviderMetadata, RecoveryInput, TokenUsage, canonical_json, stable_hash


class ProviderConfigurationError(RuntimeError):
    pass


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("provider response contains no JSON object")
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("provider response JSON must be an object")
    return value


class OpenAICompatibleRecoveryProvider(HighLevelRecoveryProvider):
    """Single-draw, credential-redacting adapter for OpenAI-compatible chat APIs."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.endpoint = str(config.get("endpoint", "https://openrouter.ai/api/v1/chat/completions"))
        self.api_key_env = str(config.get("api_key_env", "OPENROUTER_API_KEY"))
        self.seed = int(config.get("seed", 20260802))
        self._metadata = ProviderMetadata(
            provider=str(config.get("provider", "openai_compatible")),
            model=str(config["model"]),
            temperature=float(config.get("temperature", 0.0)),
            max_prompt_tokens=int(config.get("max_prompt_tokens", 12000)),
            max_completion_tokens=int(config.get("max_completion_tokens", 4096)),
            max_retries=int(config.get("max_retries", 0)),
            timeout_seconds=float(config.get("timeout_seconds", 90.0)),
            is_fake=False,
        )
        if self._metadata.max_retries != 0:
            raise ProviderConfigurationError("native N-track freezes retries at zero")
        prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
        self.patch_contract = (prompt_dir / "cope_typed_patch_v1.txt").read_text(encoding="utf-8")
        self.full_contract = (prompt_dir / "fsr_pc_full_state_v2.txt").read_text(encoding="utf-8")

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def _common_message(self, recovery_input: RecoveryInput) -> str:
        return "RECOVERY_INPUT_CANONICAL_JSON\n" + canonical_json(recovery_input.as_payload())

    def _call(self, mode: str, recovery_input: RecoveryInput, output_contract: str) -> ProviderInvocation:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderConfigurationError(f"credential environment variable {self.api_key_env} is not set")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a deterministic semantic state-transition generator. "
                    "Use only the supplied recovery input and return one JSON object."
                ),
            },
            {"role": "user", "content": self._common_message(recovery_input)},
            {"role": "user", "content": output_contract},
        ]
        wire_payload = {
            "model": self._metadata.model,
            "messages": messages,
            "temperature": self._metadata.temperature,
            "seed": self.seed,
            "max_tokens": self._metadata.max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        audited_request = {
            "mode": mode,
            "recovery_input": recovery_input.as_payload(),
            "common_input_message_sha256": stable_hash(messages[1]["content"]),
            "output_contract_sha256": stable_hash(output_contract),
            "wire_payload": wire_payload,
        }
        req = request.Request(
            self.endpoint,
            data=canonical_json(wire_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with request.urlopen(req, timeout=self._metadata.timeout_seconds) as response:
                raw_bytes = response.read()
            latency = time.monotonic() - started
            envelope = json.loads(raw_bytes.decode("utf-8"))
            message = envelope["choices"][0]["message"]
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("provider response has no textual message content")
            usage = envelope.get("usage") or {}
            parsed = _json_object(content)
            return ProviderInvocation(
                mode=mode,
                raw_request=audited_request,
                raw_response={
                    "response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    "content": content,
                    "provider_request_id": envelope.get("id"),
                },
                parsed_output=parsed,
                usage=TokenUsage(
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                ),
                latency_seconds=latency,
            )
        except (TimeoutError, socket.timeout) as exc:
            latency = time.monotonic() - started
            return ProviderInvocation(
                mode=mode,
                raw_request=audited_request,
                raw_response={"error_class": type(exc).__name__},
                parsed_output=None,
                timeout=True,
                validation_failure="provider_timeout",
                latency_seconds=latency,
            )
        except error.HTTPError as exc:
            latency = time.monotonic() - started
            return ProviderInvocation(
                mode=mode,
                raw_request=audited_request,
                raw_response={"error_class": "HTTPError", "http_status": int(exc.code)},
                parsed_output=None,
                validation_failure=f"provider_http_{int(exc.code)}",
                latency_seconds=latency,
            )
        except (error.URLError, OSError) as exc:
            latency = time.monotonic() - started
            return ProviderInvocation(
                mode=mode,
                raw_request=audited_request,
                raw_response={"error_class": type(exc).__name__},
                parsed_output=None,
                validation_failure="provider_transport_outage",
                latency_seconds=latency,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            latency = time.monotonic() - started
            return ProviderInvocation(
                mode=mode,
                raw_request=audited_request,
                raw_response={"error_class": type(exc).__name__},
                parsed_output=None,
                parse_failure=str(exc),
                latency_seconds=latency,
            )

    def regenerate(self, recovery_input: RecoveryInput) -> ProviderInvocation:
        return self._call("regenerate", recovery_input, self.full_contract)

    def patch(self, recovery_input: RecoveryInput, constraint_state: dict[str, Any]) -> ProviderInvocation:
        embedded = recovery_input.task_progress.get("pre_state")
        if canonical_json(constraint_state) != canonical_json(embedded):
            raise ValueError("patch-side state must equal the state embedded in common RecoveryInput")
        return self._call("patch", recovery_input, self.patch_contract)


def normalized_wire_request_hash(invocation: ProviderInvocation) -> str:
    payload = json.loads(canonical_json(invocation.raw_request["wire_payload"]))
    payload["messages"][2]["content"] = "<ARM_OUTPUT_CONTRACT>"
    return stable_hash(payload)


def create_openai_compatible_provider(config: dict[str, Any]) -> OpenAICompatibleRecoveryProvider:
    return OpenAICompatibleRecoveryProvider(config)
