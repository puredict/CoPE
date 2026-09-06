"""Typed records for the r3 lineage benchmark.

These are intentionally independent of the r2 ``ConstraintSlot`` serializer.
The model-facing schema is small, explicit, and stable so malformed model
output can be classified without guessing what the model intended.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


STATE_SCHEMA = "cope-lineage-state-v1"
PATCH_SCHEMA = "cope-lineage-patch-v1"
VALID_MODES = frozenset({"active", "suspended", "overridden", "expired", "completed"})
VALID_KINDS = frozenset({"workflow", "order_archive", "safety"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkflowSlot:
    slot_id: str
    logical_id: str
    kind: str
    mode: str
    priority: str
    grounding: str
    payload: Dict[str, Any] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)
    history: Tuple[Dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WorkflowSlot":
        required = {
            "slot_id", "logical_id", "kind", "mode", "priority",
            "grounding", "payload", "lineage", "history",
        }
        missing = sorted(required - set(raw))
        extra = sorted(set(raw) - required)
        if missing or extra:
            raise ValueError(f"slot fields missing={missing} extra={extra}")
        if not isinstance(raw["payload"], Mapping):
            raise ValueError("slot.payload must be an object")
        if not isinstance(raw["lineage"], Mapping):
            raise ValueError("slot.lineage must be an object")
        if not isinstance(raw["history"], list):
            raise ValueError("slot.history must be an array")
        return cls(
            slot_id=str(raw["slot_id"]), logical_id=str(raw["logical_id"]),
            kind=str(raw["kind"]), mode=str(raw["mode"]),
            priority=str(raw["priority"]), grounding=str(raw["grounding"]),
            payload=dict(raw["payload"]), lineage=dict(raw["lineage"]),
            history=tuple(dict(item) for item in raw["history"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "logical_id": self.logical_id,
            "kind": self.kind,
            "mode": self.mode,
            "priority": self.priority,
            "grounding": self.grounding,
            "payload": dict(self.payload),
            "lineage": dict(self.lineage),
            "history": [dict(item) for item in self.history],
        }


@dataclass(frozen=True)
class WorkflowState:
    revision: int
    slots: Dict[str, WorkflowSlot]
    schema_version: str = STATE_SCHEMA

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WorkflowState":
        required = {"schema_version", "revision", "slots"}
        missing = sorted(required - set(raw))
        extra = sorted(set(raw) - required)
        if missing or extra:
            raise ValueError(f"state fields missing={missing} extra={extra}")
        if raw["schema_version"] != STATE_SCHEMA:
            raise ValueError(f"unsupported state schema {raw['schema_version']!r}")
        if not isinstance(raw["revision"], int):
            raise ValueError("state.revision must be an integer")
        if not isinstance(raw["slots"], list):
            raise ValueError("state.slots must be an array")
        slots: Dict[str, WorkflowSlot] = {}
        for item in raw["slots"]:
            if not isinstance(item, Mapping):
                raise ValueError("every state slot must be an object")
            slot = WorkflowSlot.from_dict(item)
            if slot.slot_id in slots:
                raise ValueError(f"duplicate slot_id {slot.slot_id!r}")
            slots[slot.slot_id] = slot
        return cls(revision=raw["revision"], slots=slots)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "slots": [self.slots[key].to_dict() for key in sorted(self.slots)],
        }

    def fingerprint(self) -> str:
        return sha256_json(self.to_dict())

    def with_slots(self, slots: Iterable[WorkflowSlot]) -> "WorkflowState":
        return WorkflowState(
            revision=self.revision + 1,
            slots={slot.slot_id: slot for slot in slots},
        )


@dataclass(frozen=True)
class LineageEvent:
    event_id: str
    ordinal: int
    kind: str
    current_slot_id: str
    user_request: str
    reason: str
    new_slot: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "event_id": self.event_id,
            "ordinal": self.ordinal,
            "kind": self.kind,
            "current_slot_id": self.current_slot_id,
            "user_request": self.user_request,
            "reason": self.reason,
        }
        if self.new_slot is not None:
            out["new_slot"] = dict(self.new_slot)
        return out


@dataclass(frozen=True)
class ModelPacket:
    task_contract: Dict[str, Any]
    current_state: WorkflowState
    event: LineageEvent
    event_history: Tuple[Dict[str, Any], ...]
    completed_actions: Tuple[Dict[str, Any], ...]
    world_state: Dict[str, Any]
    compute_budget: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_contract": dict(self.task_contract),
            "current_state": self.current_state.to_dict(),
            "event": self.event.to_dict(),
            "event_history": [dict(item) for item in self.event_history],
            "completed_actions": [dict(item) for item in self.completed_actions],
            "world_state": dict(self.world_state),
            "compute_budget": dict(self.compute_budget),
        }

    def fingerprint(self) -> str:
        return sha256_json(self.to_dict())

    def exogenous_fingerprint(self) -> str:
        return sha256_json({
            "task_contract": self.task_contract,
            "event": self.event.to_dict(),
            "event_history": self.event_history,
            "completed_actions": self.completed_actions,
            "world_state": self.world_state,
            "compute_budget": self.compute_budget,
        })


@dataclass
class GenerationResult:
    ok: bool
    status: str
    text: str
    parsed: Optional[Dict[str, Any]]
    latency_s: float
    finish_reason: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    error: str = ""
    response_id: str = ""
    request_id: str = ""
    ttft_s: Optional[float] = None
    streamed_chunks: int = 0
    observed_output_chars: int = 0
    observed_completion_tokens: Optional[int] = None
    observed_token_count_kind: str = "unavailable"
    request_completed: bool = False
    http_status: Optional[int] = None
    server_error: str = ""
    cancellation_status: str = "not_requested"
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_text: bool = False) -> Dict[str, Any]:
        out = {
            "ok": self.ok,
            "status": self.status,
            "latency_s": self.latency_s,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error": self.error,
            "response_id": self.response_id,
            "output_chars": len(self.text),
            "output_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
            "request_id": self.request_id,
            "ttft_s": self.ttft_s,
            "streamed_chunks": self.streamed_chunks,
            "observed_output_chars": self.observed_output_chars,
            "observed_completion_tokens": self.observed_completion_tokens,
            "observed_token_count_kind": self.observed_token_count_kind,
            "request_completed": self.request_completed,
            "http_status": self.http_status,
            "server_error": self.server_error,
            "cancellation_status": self.cancellation_status,
            "telemetry": dict(self.telemetry),
        }
        if include_text:
            out["text"] = self.text
        return out


@dataclass
class AdaptationResult:
    ok: bool
    status: str
    state: WorkflowState
    generation: GenerationResult
    validation_errors: List[str] = field(default_factory=list)
    semantic_match: bool = False
    output_document: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ScenarioSpec:
    seed: int
    profile: str
    initial_slots: int
    lineage_depth: int
    max_output_tokens: int
    model_timeout_s: float


@dataclass(frozen=True)
class LineageScenario:
    spec: ScenarioSpec
    initial_state: WorkflowState
    events: Tuple[LineageEvent, ...]
    critical_logical_id: str
    expected_plan: Tuple[Dict[str, str], ...]
    task_contract: Dict[str, Any]
