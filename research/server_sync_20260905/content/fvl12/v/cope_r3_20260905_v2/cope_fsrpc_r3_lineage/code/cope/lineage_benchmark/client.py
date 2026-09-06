"""Fixed-model clients: OpenAI-compatible vLLM and deterministic local oracle."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import math
import socket
import time
from typing import Any, Dict, Mapping, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from .models import GenerationResult, ModelPacket, canonical_json
from .prompts import system_prompt, user_prompt
from .state import apply_patch_document
from .task import oracle_patch


def parse_json_object(text: str) -> Dict[str, Any]:
    """Extract one JSON object while tolerating a Qwen thinking wrapper.

    Markdown fences are tolerated only as transport decoration. Any substantive
    trailing text is rejected so an apparently parseable prefix cannot hide a
    truncated or multi-answer generation.
    """

    cleaned = text.strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(cleaned[start:])
    tail = cleaned[start + end :].strip()
    if tail:
        raise ValueError("non-whitespace content follows JSON object")
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


class ModelClient(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        method: str,
        packet: ModelPacket,
        max_output_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        raise NotImplementedError


class OpenAICompatibleClient(ModelClient):
    """Minimal dependency-free client for a local vLLM chat-completions server."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        seed: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.seed = int(seed)

    def generate(
        self,
        *,
        method: str,
        packet: ModelPacket,
        max_output_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt(method)},
                {"role": "user", "content": user_prompt(packet)},
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": self.seed,
            "max_tokens": int(max_output_tokens),
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urlrequest.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlrequest.urlopen(req, timeout=float(timeout_s)) as response:
                raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            choice = payload["choices"][0]
            content = choice["message"].get("content") or ""
            finish = str(choice.get("finish_reason") or "")
            usage = payload.get("usage", {}) or {}
            parsed = None
            status = "ok"
            error = ""
            if finish == "length":
                status = "truncated"
            else:
                try:
                    parsed = parse_json_object(str(content))
                except (ValueError, json.JSONDecodeError) as exc:
                    status, error = "json_parse_error", str(exc)
            return GenerationResult(
                ok=status == "ok",
                status=status,
                text=str(content),
                parsed=parsed,
                latency_s=time.monotonic() - started,
                finish_reason=finish,
                prompt_tokens=_maybe_int(usage.get("prompt_tokens")),
                completion_tokens=_maybe_int(usage.get("completion_tokens")),
                error=error,
                response_id=str(payload.get("id") or ""),
            )
        except (TimeoutError, socket.timeout) as exc:
            return GenerationResult(
                False, "timeout", "", None, time.monotonic() - started,
                error=str(exc),
            )
        except urlerror.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                detail = str(exc)
            return GenerationResult(
                False, "http_error", "", None, time.monotonic() - started,
                error=f"HTTP {exc.code}: {detail}",
            )
        except (urlerror.URLError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return GenerationResult(
                False, "transport_or_response_error", "", None,
                time.monotonic() - started, error=str(exc),
            )


def _maybe_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class OracleModelClient(ModelClient):
    """Deterministic local client for code verification, never a paper result.

    With ``enforce_budget`` it serializes the exact correct response and then
    applies a conservative four-characters-per-token cap. This is useful for
    testing failure accounting, not for estimating a real tokenizer.
    """

    def __init__(self, *, enforce_budget: bool = False) -> None:
        self.enforce_budget = bool(enforce_budget)

    def generate(
        self,
        *,
        method: str,
        packet: ModelPacket,
        max_output_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        del timeout_s
        started = time.monotonic()
        patch = oracle_patch(packet.current_state, packet.event)
        if method == "CoPE":
            document = patch
        elif method == "FSR-PC":
            document = apply_patch_document(
                packet.current_state,
                patch,
                packet.event,
                str(packet.task_contract["critical_logical_id"]),
            ).to_dict()
        else:
            raise ValueError(f"unknown method {method!r}")
        text = canonical_json(document)
        estimated_tokens = max(1, math.ceil(len(text) / 4))
        if self.enforce_budget and estimated_tokens > max_output_tokens:
            clipped = text[: max_output_tokens * 4]
            return GenerationResult(
                False,
                "truncated",
                clipped,
                None,
                time.monotonic() - started,
                finish_reason="length",
                prompt_tokens=max(1, math.ceil(len(user_prompt(packet)) / 4)),
                completion_tokens=max_output_tokens,
                error=(
                    f"oracle serialization estimate {estimated_tokens} exceeds "
                    f"budget {max_output_tokens}"
                ),
                response_id="local-oracle",
            )
        return GenerationResult(
            True,
            "ok",
            text,
            document,
            time.monotonic() - started,
            finish_reason="stop",
            prompt_tokens=max(1, math.ceil(len(user_prompt(packet)) / 4)),
            completion_tokens=estimated_tokens,
            response_id="local-oracle",
        )

