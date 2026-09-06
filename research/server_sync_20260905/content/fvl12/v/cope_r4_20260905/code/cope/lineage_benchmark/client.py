"""Fixed-model clients: OpenAI-compatible vLLM and deterministic local oracle."""

from __future__ import annotations

from abc import ABC, abstractmethod
import http.client
import json
import math
import socket
import threading
import time
import uuid
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit

from .models import GenerationResult, ModelPacket, canonical_json
from .prompts import system_prompt, user_prompt
from .schemas import output_schema, validate_output_document
from .reference import reference_transition
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
    start = 0
    if not cleaned.startswith("{"):
        raise ValueError("response must start with a JSON object")
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
    """One streamed vLLM call, static grammar, and an absolute client deadline.

    Parameters are verified against vLLM v0.8.5's public protocol:
    https://github.com/vllm-project/vllm/blob/v0.8.5/vllm/entrypoints/openai/protocol.py
    https://docs.vllm.ai/en/v0.8.5/features/structured_outputs.html

    Socket closure requests cancellation by disconnecting. It does not prove
    the server stopped generating: the runner must check server-side evidence.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        seed: int = 0,
        guided_decoding_backend: str = "xgrammar",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.seed = int(seed)
        if guided_decoding_backend not in {"xgrammar", "guidance"}:
            raise ValueError("use an explicitly configured supported V1 backend")
        self.guided_decoding_backend = guided_decoding_backend

    def generate(
        self,
        *,
        method: str,
        packet: ModelPacket,
        max_output_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        packet_tokens = int(packet.compute_budget.get("max_output_tokens", max_output_tokens))
        packet_timeout = float(packet.compute_budget.get("timeout_s", timeout_s))
        if packet_tokens != int(max_output_tokens) or packet_timeout != float(timeout_s):
            raise ValueError("generation arguments disagree with packet compute_budget")
        if packet_tokens < 1 or not math.isfinite(packet_timeout) or packet_timeout <= 0:
            raise ValueError("max_output_tokens and timeout_s must be positive and finite")
        request_id = str(uuid.uuid4())
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt(method)},
                {"role": "user", "content": user_prompt(packet)},
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": self.seed,
            "max_tokens": packet_tokens,
            "guided_json": output_schema(method),
            # vLLM V1 requires exact equality with the engine-level setting.
            # Explicit xgrammar disables fallback in V1; its constructor does
            # not accept V0's additional no-fallback option.
            "guided_decoding_backend": self.guided_decoding_backend,
            "stream": True,
            "stream_options": {"include_usage": True, "continuous_usage_stats": True},
            "request_id": request_id,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        endpoint = urlsplit(f"{self.base_url}/v1/chat/completions")
        if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
            raise ValueError("base_url must be an http(s) URL")
        connection_type = (http.client.HTTPSConnection if endpoint.scheme == "https"
                           else http.client.HTTPConnection)
        connection = connection_type(endpoint.hostname, endpoint.port, timeout=packet_timeout)
        content_parts = []
        usage: Dict[str, Any] = {}
        response_id = ""
        finish = ""
        ttft = None
        status = "transport_or_response_error"
        error = ""
        parsed = None
        http_status = None
        server_error = ""
        stream_chunks = 0
        content_chunks = 0
        got_done = False
        response = None
        timed_out = threading.Event()
        network_finished = threading.Event()
        active_socket = [None]
        cancellation_status = "not_requested"
        telemetry: Dict[str, Any] = {
            "protocol": "vllm-0.8.5-streaming-guided-json",
            "guided_decoding_backend": body["guided_decoding_backend"],
            "model_calls": 1,
            "max_output_tokens": packet_tokens,
            "timeout_s": packet_timeout,
            "json_valid": False,
            "schema_valid": False,
            "observed_token_note": "Only server-reported usage; SSE chunks are not tokens.",
        }
        started = time.monotonic()

        def expire_request():
            if network_finished.is_set():
                return
            timed_out.set()
            sock = active_socket[0] or connection.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        def check_deadline(update_socket=True):
            remaining = packet_timeout - (time.monotonic() - started)
            if timed_out.is_set() or remaining <= 0:
                timed_out.set()
                raise TimeoutError("absolute client request deadline exceeded")
            sock = active_socket[0] or connection.sock
            if update_socket and sock is not None:
                sock.settimeout(remaining)

        timer = threading.Timer(packet_timeout, expire_request)
        timer.daemon = True
        timer.start()
        try:
            connection.connect()
            active_socket[0] = connection.sock
            check_deadline()
            connection.request(
                "POST", endpoint.path + (f"?{endpoint.query}" if endpoint.query else ""),
                body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Accept": "text/event-stream",
                         "Authorization": f"Bearer {self.api_key}",
                         "X-Request-Id": request_id},
            )
            check_deadline()
            response = connection.getresponse()
            http_status = response.status
            if http_status >= 400:
                detail = response.read(2000).decode("utf-8", errors="replace")
                status = "http_error"
                server_error = detail
                error = f"HTTP {http_status}: {detail}"
                network_finished.set()
            else:
                content_type = response.getheader("Content-Type", "")
                if "text/event-stream" not in content_type:
                    raise ValueError(f"server did not return SSE: {content_type!r}")
                data_lines = []
                while not got_done:
                    check_deadline()
                    line = response.readline()
                    check_deadline(update_socket=False)
                    if not line:
                        break
                    if line.strip():
                        if line.startswith(b"data:"):
                            data_lines.append(line[5:].strip())
                        continue
                    if not data_lines:
                        continue
                    data = b"\n".join(data_lines).decode("utf-8")
                    data_lines = []
                    if data == "[DONE]":
                        got_done = True
                        network_finished.set()
                        break
                    chunk = json.loads(data)
                    if not isinstance(chunk, dict):
                        raise ValueError("SSE data must be a JSON object")
                    stream_chunks += 1
                    if "error" in chunk:
                        server_error = canonical_json(chunk["error"])
                        status = "server_error"
                        error = server_error
                        network_finished.set()
                        break
                    response_id = str(chunk.get("id") or response_id)
                    current_usage = chunk.get("usage")
                    if current_usage:
                        if not isinstance(current_usage, dict):
                            raise ValueError("stream usage must be an object")
                        usage.update(current_usage)
                        telemetry["last_usage_at_s"] = time.monotonic() - started
                    for choice in chunk.get("choices", []):
                        if not isinstance(choice, dict):
                            raise ValueError("stream choices must contain objects")
                        if choice.get("index", 0) != 0:
                            raise ValueError("unexpected multiple completion choices")
                        delta = choice.get("delta") or {}
                        content = delta.get("content") or ""
                        if not isinstance(content, str):
                            raise ValueError("stream delta.content must be text")
                        if content:
                            if ttft is None:
                                ttft = time.monotonic() - started
                            content_parts.append(content)
                            content_chunks += 1
                        if choice.get("finish_reason") is not None:
                            finish = str(choice["finish_reason"])
                if not server_error:
                    if not got_done or not finish:
                        status = "incomplete_stream"
                        error = "stream ended without both finish_reason and [DONE]"
                    elif finish == "length":
                        status = "truncated"
                    elif finish != "stop":
                        status = "unexpected_finish_reason"
                        error = f"unexpected finish_reason {finish!r}"
                    else:
                        try:
                            parsed = parse_json_object("".join(content_parts))
                            telemetry["json_valid"] = True
                        except (ValueError, json.JSONDecodeError) as exc:
                            status, error = "json_parse_error", str(exc)
                        else:
                            try:
                                validate_output_document(method, parsed)
                                telemetry["schema_valid"] = True
                                status = "ok"
                            except ValueError as exc:
                                status, error = "schema_validation_failure", str(exc)
        except (TimeoutError, socket.timeout) as exc:
            timed_out.set()
            status, error = "client_timeout", str(exc)
        except (OSError, http.client.HTTPException, KeyError, TypeError, ValueError) as exc:
            status = "client_timeout" if timed_out.is_set() else "transport_or_response_error"
            error = str(exc)
        finally:
            timer.cancel()
            if timed_out.is_set():
                status = "client_timeout"
                error = error or "absolute client request deadline exceeded"
                cancellation_status = "connection_closed_server_status_unknown"
            elif not network_finished.is_set():
                cancellation_status = "connection_closed_server_status_unknown"
            if response is not None:
                response.close()
            connection.close()
        content = "".join(content_parts)
        observed_tokens = _maybe_int(usage.get("completion_tokens"))
        telemetry["content_chunks"] = content_chunks
        telemetry["received_done"] = got_done
        telemetry["client_connection_closed"] = True
        telemetry["server_cancellation_confirmed"] = None
        telemetry["generation_completed_before_client_deadline"] = (
            got_done and bool(finish) and not timed_out.is_set()
        )
        return GenerationResult(
            ok=status == "ok", status=status, text=content, parsed=parsed,
            latency_s=time.monotonic() - started, finish_reason=finish,
            prompt_tokens=_maybe_int(usage.get("prompt_tokens")),
            completion_tokens=observed_tokens, error=error, response_id=response_id,
            request_id=request_id, ttft_s=ttft, streamed_chunks=stream_chunks,
            observed_output_chars=len(content), observed_completion_tokens=observed_tokens,
            observed_token_count_kind=("server_usage_cumulative" if observed_tokens is not None
                                       else "unavailable"),
            request_completed=got_done and bool(finish) and not timed_out.is_set(),
            http_status=http_status, server_error=server_error,
            cancellation_status=cancellation_status, telemetry=telemetry,
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
            document = reference_transition(
                packet.current_state,
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
                request_completed=True,
                observed_output_chars=len(clipped),
                observed_completion_tokens=max_output_tokens,
                observed_token_count_kind="oracle_character_estimate_not_tokenizer",
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
            request_completed=True,
            observed_output_chars=len(text),
            observed_completion_tokens=estimated_tokens,
            observed_token_count_kind="oracle_character_estimate_not_tokenizer",
        )
