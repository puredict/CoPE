from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .interruptions import EventApplication, InterruptionEvent, InterruptionType, apply_interruption


def canonical_event_digest(events: Iterable[InterruptionEvent]) -> str:
    payload = [event.to_dict() for event in events]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_event_sequence(events: Iterable[InterruptionEvent]) -> None:
    ordered = tuple(events)
    event_ids: set[str] = set()
    active_zones: set[str] = set()
    unavailable_tools: set[str] = set()
    previous_step = -1
    for event in ordered:
        if event.event_id in event_ids:
            raise ValueError(f"duplicate event_id {event.event_id!r}")
        event_ids.add(event.event_id)
        if event.trigger_policy_step <= previous_step:
            raise ValueError("event trigger steps must be strictly increasing")
        previous_step = event.trigger_policy_step
        if event.event_type == InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS:
            zone = str(event.payload["zone_id"])
            if zone in active_zones:
                raise ValueError(f"zone {zone!r} appears twice without disappearing")
            active_zones.add(zone)
        elif event.event_type == InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS:
            zone = str(event.payload["zone_id"])
            if zone not in active_zones:
                raise ValueError(f"zone {zone!r} disappears before it appears")
            active_zones.remove(zone)
        elif event.event_type == InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE:
            tool = str(event.payload["tool_joint"])
            if tool in unavailable_tools:
                raise ValueError(f"tool {tool!r} becomes unavailable twice")
            unavailable_tools.add(tool)
        elif event.event_type == InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN:
            tool = str(event.payload["tool_joint"])
            if tool not in unavailable_tools:
                raise ValueError(f"tool {tool!r} becomes available without unavailability")
            unavailable_tools.remove(tool)


@dataclass
class InterruptionScheduler:
    events: tuple[InterruptionEvent, ...]
    applied_event_ids: set[str] = field(default_factory=set)
    applications: list[EventApplication] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_event_sequence(self.events)

    @property
    def schedule_digest(self) -> str:
        return canonical_event_digest(self.events)

    def _trigger_satisfied(
        self,
        event: InterruptionEvent,
        *,
        policy_step: int,
        progress: Mapping[str, bool] | None,
    ) -> bool:
        predicate = event.trigger_predicate
        kind = str(predicate.get("kind", "policy_step_gte"))
        if int(policy_step) < event.trigger_policy_step:
            return False
        if kind == "policy_step_gte":
            return True
        names = tuple(str(name) for name in predicate.get("predicates", ()))
        values = progress or {}
        if kind == "progress_all_or_step_gte":
            return all(bool(values.get(name, False)) for name in names) or int(policy_step) >= int(
                predicate.get("fallback_policy_step", event.trigger_policy_step)
            )
        if kind == "progress_any_or_step_gte":
            return any(bool(values.get(name, False)) for name in names) or int(policy_step) >= int(
                predicate.get("fallback_policy_step", event.trigger_policy_step)
            )
        raise ValueError(f"unknown trigger predicate kind {kind!r}")

    def due_events(
        self,
        *,
        policy_step: int,
        progress: Mapping[str, bool] | None = None,
    ) -> tuple[InterruptionEvent, ...]:
        return tuple(
            event
            for event in self.events
            if event.event_id not in self.applied_event_ids
            and self._trigger_satisfied(event, policy_step=policy_step, progress=progress)
        )

    def apply_due(
        self,
        context: Any,
        *,
        policy_step: int,
        progress: Mapping[str, bool] | None = None,
    ) -> tuple[list[EventApplication], dict[str, Any] | None]:
        applications: list[EventApplication] = []
        observation: dict[str, Any] | None = None
        for event in self.due_events(policy_step=policy_step, progress=progress):
            record, observation = apply_interruption(context, event, policy_step=policy_step)
            if record.policy_step_before != policy_step or record.policy_step_after != policy_step:
                raise RuntimeError("interruption application changed the policy-step counter")
            self.applied_event_ids.add(event.event_id)
            self.applications.append(record)
            applications.append(record)
        return applications, observation

    @property
    def complete(self) -> bool:
        return len(self.applied_event_ids) == len(self.events)


def schedules_are_paired_equal(
    first: Iterable[InterruptionEvent],
    second: Iterable[InterruptionEvent],
) -> bool:
    return canonical_event_digest(first) == canonical_event_digest(second)
