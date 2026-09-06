"""One-call reasoner boundary with immutable, exact request/response audit logs.

There is deliberately no provider SDK or retry loop here. A production provider
implements ``Reasoner``; the included fixture is explicitly not a model result.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ReasonerConfig:
    provider: str
    model: str
    temperature: float = 0.0
    seed: int = 0
    seed_policy: str = "fixed"
    max_input_tokens: int = 32768
    max_output_tokens: int = 8192
    setting: str = "evidence_matched"
    truncation_policy: str = "public-history-prefix-v1"
    semantic_retries: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("Provider must be a nonempty string")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Model must be a nonempty string")
        if type(self.seed) is not int:
            raise ValueError("Seed must be an integer")
        if (type(self.temperature) not in (int, float) or self.temperature != 0
                or type(self.semantic_retries) is not int or self.semantic_retries != 0):
            raise ValueError("Event reasoning requires temperature zero and zero semantic retries")
        if self.setting not in {"evidence_matched", "token_matched"}:
            raise ValueError("Unknown fairness setting")
        if self.seed_policy != "fixed" or self.truncation_policy != "public-history-prefix-v1":
            raise ValueError("Unsupported unfrozen seed/truncation policy")
        if any(type(value) is not int or value <= 0
               for value in (self.max_input_tokens, self.max_output_tokens)):
            raise ValueError("Token ceilings must be positive integers")


@dataclass(frozen=True)
class ReasonerResponse:
    text: str
    input_tokens: int
    output_tokens: int
    token_count_kind: str = "provider"
    fixture: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("Response text must be a string")
        if any(type(value) is not int or value < 0 for value in (self.input_tokens, self.output_tokens)):
            raise ValueError("Token usage must be nonnegative integers")
        if not isinstance(self.token_count_kind, str) or not self.token_count_kind.strip():
            raise ValueError("Token count kind must be a nonempty string")
        if type(self.fixture) is not bool:
            raise ValueError("Fixture status must be Boolean")


class Reasoner(Protocol):
    def count_tokens(self, messages: Sequence[Mapping[str, str]]) -> int: ...

    def complete(self, *, messages: Sequence[Mapping[str, str]], config: ReasonerConfig) -> ReasonerResponse: ...


@dataclass(frozen=True)
class PromptLog:
    episode_id: str
    event_index: int
    messages_json: str
    config_json: str
    response: str | None
    input_tokens: int
    output_tokens: int | None
    token_count_kind: str
    fixture: bool
    error: str | None = None

    @property
    def messages(self) -> list[dict[str, str]]:
        return json.loads(self.messages_json)


class ReasonerGateway:
    """Consume at most one provider call for each episode/event, even on failure."""

    def __init__(self, reasoner: Reasoner, config: ReasonerConfig, *, log_path: str | Path | None = None):
        self.reasoner = reasoner
        self.config = config
        self.logs: list[PromptLog] = []
        self._events: set[tuple[str, int]] = set()
        self.log_path = Path(log_path) if log_path is not None else None
        # Exclusive creation prevents accidental overwrite or audit-log mixing.
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("x", encoding="utf-8"):
                pass

    def _record(self, log: PromptLog) -> None:
        self.logs.append(log)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(log), ensure_ascii=False) + "\n")

    def snapshot(self) -> dict:
        return {"config": self.config.to_dict(), "events": [list(key) for key in sorted(self._events)],
                "logs": [asdict(log) for log in self.logs]}

    def restore(self, snapshot: Mapping) -> None:
        if snapshot["config"] != self.config.to_dict():
            raise ValueError("Cannot change frozen reasoner configuration on resume")
        self._events = {(str(episode), int(event)) for episode, event in snapshot["events"]}
        self.logs = [PromptLog(**log) for log in snapshot["logs"]]

    def count_tokens(self, messages: Sequence[Mapping[str, str]]) -> int:
        count = self.reasoner.count_tokens(messages)
        if type(count) is not int or count < 0:
            raise ValueError("Preflight token count must be a nonnegative integer")
        return count

    def call(self, *, episode_id: str, event_index: int, messages: Sequence[Mapping[str, str]]) -> str:
        from .prompts import scan_public_input

        scan_public_input(messages)
        key = (episode_id, event_index)
        if key in self._events:
            raise ValueError("A high-level adaptation call was already consumed for this event")
        exact_messages = copy.deepcopy(list(messages))
        input_tokens = self.count_tokens(exact_messages)
        if input_tokens > self.config.max_input_tokens:
            raise ValueError("Input exceeds the common token ceiling; no provider call made")
        messages_json = json.dumps(exact_messages, ensure_ascii=False, separators=(",", ":"))
        config_json = json.dumps(asdict(self.config), sort_keys=True, separators=(",", ":"))
        self._events.add(key)
        try:
            response = self.reasoner.complete(messages=exact_messages, config=self.config)
            if not isinstance(response, ReasonerResponse):
                raise ValueError("Provider must return a validated ReasonerResponse")
        except Exception as exc:
            self._record(PromptLog(episode_id, event_index, messages_json, config_json, None,
                                  input_tokens, None, "preflight", False, type(exc).__name__))
            raise
        self._record(PromptLog(episode_id, event_index, messages_json, config_json, response.text,
                              response.input_tokens, response.output_tokens,
                              response.token_count_kind, response.fixture))
        if response.input_tokens > self.config.max_input_tokens or response.output_tokens > self.config.max_output_tokens:
            raise ValueError("Provider exceeded the frozen token ceiling")
        return response.text


def assert_same_backbone(gateways: Sequence[ReasonerGateway]) -> None:
    """Fail before a comparison if any generation or budget configuration differs."""
    if gateways and any(item.config != gateways[0].config for item in gateways[1:]):
        raise ValueError("Generative arms do not have identical reasoner configuration")


class FixtureReasoner:
    """Deterministic offline test double; its token counts are UTF-8 byte counts.

    This never sends network traffic and must not be reported as provider/model
    performance. UTF-8 bytes deliberately form a conservative fixture budget.
    """

    def __init__(self, responses: Sequence[str | Mapping] | Callable):
        self.responses = responses
        self.calls = 0

    def count_tokens(self, messages: Sequence[Mapping[str, str]]) -> int:
        return len(json.dumps(list(messages), ensure_ascii=False).encode("utf-8"))

    def complete(self, *, messages: Sequence[Mapping[str, str]], config: ReasonerConfig) -> ReasonerResponse:
        index = self.calls
        self.calls += 1
        value = self.responses(messages, config, index) if callable(self.responses) else self.responses[index]
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return ReasonerResponse(text, self.count_tokens(messages), len(text.encode("utf-8")),
                                "fixture_utf8_bytes", True)
