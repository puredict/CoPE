"""Deterministic master schedules and read-only semantic trigger decisions.

A schedule is private experiment metadata, never an agent input. The scheduler
owns only event delivery bookkeeping: it cannot receive or replace an arm's
accepted state. Availability events create *obligations* for post-event
revalidation; they do not certify restoration themselves.
"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any

from .canonical import canonical_sha256, freeze_json, to_primitive
from .enums import EventFamily, ProtocolName

CHECKPOINTS = (0, 1, 2, 4, 8)
MASTER_EVENT_COUNT = 8
MIN_STEPS_BETWEEN_EVENTS = 10
_GROUNDING = (EventFamily.TARGET_OBJECT_DISPLACED, EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED)
_RETIREMENT = (EventFamily.USER_REPLACES_ACTIVE_GOAL, EventFamily.USER_CANCELS_ACTIVE_GOAL)
_PAIR_PREDECESSORS = {
    EventFamily.TEMPORARY_NO_GO_CLEARS: EventFamily.TEMPORARY_NO_GO_APPEARS,
    EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN: EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE,
}


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class SemanticTrigger:
    """References facts supplied by the task monitor and feasibility verifier.

    The names must be present in their frozen task catalog. Missing facts at
    runtime block delivery rather than falling back to elapsed policy steps.
    """
    predicate: str
    earliest_policy_step: int
    latest_policy_step: int
    physical_feasibility_guard: str
    min_steps_since_previous_event: int = MIN_STEPS_BETWEEN_EVENTS
    moves_object: bool = False
    intervention_entity: str | None = None
    forced_external_displacement: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.predicate, str) or not self.predicate.strip():
            raise ValueError("BLOCKED_TASK_CATALOG_GAP: semantic predicate required")
        if self.predicate in {"always", "policy_step_gte", "progress_all_or_step_gte", "progress_any_or_step_gte"}:
            raise ValueError("fixed-step or fallback-only triggers are forbidden in v2")
        if not isinstance(self.physical_feasibility_guard, str) or not self.physical_feasibility_guard.strip():
            raise ValueError("BLOCKED_TASK_CATALOG_GAP: physical feasibility guard required")
        _integer(self.earliest_policy_step, "earliest_policy_step")
        _integer(self.latest_policy_step, "latest_policy_step", self.earliest_policy_step)
        _integer(self.min_steps_since_previous_event, "min_steps_since_previous_event", MIN_STEPS_BETWEEN_EVENTS)
        if type(self.moves_object) is not bool or type(self.forced_external_displacement) is not bool:
            raise ValueError("physical intervention flags must be booleans")
        if self.moves_object and (not isinstance(self.intervention_entity, str) or not self.intervention_entity):
            raise ValueError("BLOCKED_TASK_CATALOG_GAP: moving interventions require an entity")
        if self.forced_external_displacement and not self.moves_object:
            raise ValueError("forced displacement must explicitly move an object")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticTrigger":
        required = {"predicate", "earliest_policy_step", "latest_policy_step", "physical_feasibility_guard", "min_steps_since_previous_event"}
        if required - value.keys():
            raise ValueError(f"BLOCKED_TASK_CATALOG_GAP: missing trigger fields {sorted(required - value.keys())}")
        return cls(**dict(value))


@dataclass(frozen=True)
class ScheduledEvent:
    event_id: str
    event_index: int
    family: EventFamily
    trigger: SemanticTrigger
    dependency_event_ids: tuple[str, ...] = ()
    requires_fresh_revalidation: bool = False

    def __post_init__(self) -> None:
        _integer(self.event_index, "event_index", 1)
        if not self.event_id or not isinstance(self.family, EventFamily):
            raise ValueError("event identity and known EventFamily required")
        object.__setattr__(self, "dependency_event_ids", tuple(self.dependency_event_ids))
        if type(self.requires_fresh_revalidation) is not bool:
            raise ValueError("revalidation requirement must be boolean")

    def public_reference(self) -> dict[str, Any]:
        """The only schedule projection suitable for an agent-visible envelope."""
        return {"event_id": self.event_id, "event_index": self.event_index}


@dataclass(frozen=True)
class MasterSchedule:
    master_episode_id: str
    seed: int
    events: tuple[ScheduledEvent, ...]
    schema_version: str = "cope-repeated-v2/schedule-1"

    def __post_init__(self) -> None:
        if not isinstance(self.master_episode_id, str) or not self.master_episode_id:
            raise ValueError("master_episode_id required")
        _integer(self.seed, "seed")
        object.__setattr__(self, "events", tuple(self.events))
        validate_schedule(self)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self)

    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MasterSchedule":
        raw = dict(value)
        raw["events"] = tuple(ScheduledEvent(
            **{**dict(e), "family": EventFamily(e["family"]), "trigger": SemanticTrigger.from_dict(e["trigger"])}
        ) for e in raw["events"])
        return cls(**raw)

    def prefix(self, checkpoint: int, *, protocol: ProtocolName | str = ProtocolName.CONTROLLED) -> tuple[ScheduledEvent, ...]:
        protocol = ProtocolName(protocol)
        allowed = CHECKPOINTS if protocol is ProtocolName.CONTROLLED else CHECKPOINTS[:-1]
        if type(checkpoint) is not int or checkpoint not in allowed:
            raise ValueError(f"unsupported {protocol.value} checkpoint {checkpoint}")
        result = self.events[:checkpoint]
        validate_prefix(result)
        return result


def validate_prefix(events: Sequence[ScheduledEvent]) -> None:
    """Open pairs are legal; closing or reissuing without predecessors is not."""
    prior: dict[EventFamily, ScheduledEvent] = {}
    ids: set[str] = set()
    earliest_reachable = 0
    for index, event in enumerate(events, 1):
        if event.event_index != index or event.event_id in ids:
            raise ValueError("event indices must be contiguous and IDs unique")
        if event.family in prior:
            raise ValueError("each selected family must occur once per master schedule")
        if len(set(event.dependency_event_ids)) != len(event.dependency_event_ids):
            raise ValueError("duplicate event dependency")
        if not set(event.dependency_event_ids) <= ids:
            raise ValueError("event dependency must precede its dependent")
        predecessor = _PAIR_PREDECESSORS.get(event.family)
        if event.family is EventFamily.USER_REISSUES_RETIRED_GOAL:
            retired = [prior[f] for f in _RETIREMENT if f in prior]
            if not retired or not any(e.event_id in event.dependency_event_ids for e in retired):
                raise ValueError("reissue requires a preceding retirement dependency")
        if predecessor:
            if predecessor not in prior or prior[predecessor].event_id not in event.dependency_event_ids:
                raise ValueError(f"{event.family.value} requires its paired predecessor")
            if not event.requires_fresh_revalidation:
                raise ValueError("availability/clearance must require fresh post-event revalidation")
        elif event.requires_fresh_revalidation:
            raise ValueError("only restoration endpoints carry this revalidation requirement")
        earliest_reachable = max(event.trigger.earliest_policy_step,
                                 earliest_reachable + event.trigger.min_steps_since_previous_event if index > 1 else 0)
        if earliest_reachable > event.trigger.latest_policy_step:
            raise ValueError("infeasible trigger windows under minimum event spacing")
        ids.add(event.event_id)
        prior[event.family] = event


def validate_schedule(schedule: MasterSchedule | Sequence[ScheduledEvent]) -> None:
    events = schedule.events if isinstance(schedule, MasterSchedule) else tuple(schedule)
    if len(events) != MASTER_EVENT_COUNT:
        raise ValueError("master schedule must contain exactly eight events")
    validate_prefix(events)
    families = {e.family for e in events}
    required = set(_PAIR_PREDECESSORS) | set(_PAIR_PREDECESSORS.values()) | {
        EventFamily.USER_ADDS_PERSISTENT_PREFERENCE, EventFamily.USER_REISSUES_RETIRED_GOAL,
    }
    if not required <= families or not families.intersection(_GROUNDING) or not families.intersection(_RETIREMENT):
        raise ValueError("master schedule lacks required grounding/lifecycle/preference/retirement/reissue coverage")
    for checkpoint in CHECKPOINTS:
        validate_prefix(events[:checkpoint])


@lru_cache(maxsize=4)
def _topological_shuffles(grounding: EventFamily, retirement: EventFamily) -> tuple[tuple[EventFamily, ...], ...]:
    dependencies = {**_PAIR_PREDECESSORS, EventFamily.USER_REISSUES_RETIRED_GOAL: retirement}
    nodes = sorted({grounding, retirement, EventFamily.USER_REISSUES_RETIRED_GOAL,
                    EventFamily.USER_ADDS_PERSISTENT_PREFERENCE, *_PAIR_PREDECESSORS,
                    *_PAIR_PREDECESSORS.values()}, key=lambda f: f.value)
    result: list[tuple[EventFamily, ...]] = []
    def visit(prefix: tuple[EventFamily, ...]) -> None:
        if len(prefix) == MASTER_EVENT_COUNT:
            result.append(prefix)
            return
        for node in nodes:
            if node not in prefix and (node not in dependencies or dependencies[node] in prefix):
                visit((*prefix, node))
    visit(())
    return tuple(result)


def build_master_schedule(
    master_episode_id: str,
    *,
    semantic_triggers: Mapping[str, Mapping[str, Any] | SemanticTrigger],
    seed: int = 20260906,
    supported_event_families: Sequence[EventFamily | str] | None = None,
    schedule_index: int = 0,
    position_counts: Mapping[tuple[str, int], int] | None = None,
) -> MasterSchedule:
    """Seeded constrained shuffle, optionally minimizing family-position reuse.

    Alternating grounding and retirement variants balances their frequency.
    Both temporary pairs are present, giving eight events without counting an
    observation or revalidation as an additional interruption.
    """
    _integer(seed, "seed")
    _integer(schedule_index, "schedule_index")
    declared = tuple(supported_event_families if supported_event_families is not None else semantic_triggers)
    try:
        normalized = tuple(EventFamily(f) for f in declared)
    except (TypeError, ValueError) as exc:
        raise ValueError("BLOCKED_TASK_CATALOG_GAP: unknown supported event family") from exc
    supported = set(normalized)
    if not supported or len(supported) != len(normalized):
        raise ValueError("BLOCKED_TASK_CATALOG_GAP: nonempty unique supported event families required")
    # Preserve the existing eight-distinct-event template, including both
    # temporary pairs. Only its grounding/retirement alternatives vary by task.
    required = set(_PAIR_PREDECESSORS) | set(_PAIR_PREDECESSORS.values()) | {
        EventFamily.USER_ADDS_PERSISTENT_PREFERENCE, EventFamily.USER_REISSUES_RETIRED_GOAL,
    }
    missing = required - supported
    if missing:
        raise ValueError(f"BLOCKED_TASK_CATALOG_GAP: unsupported eight-event template families {sorted(f.value for f in missing)}")
    grounding_options = tuple(family for family in _GROUNDING if family in supported)
    retirement_options = tuple(family for family in _RETIREMENT if family in supported)
    if not grounding_options or not retirement_options:
        raise ValueError("BLOCKED_TASK_CATALOG_GAP: supported grounding and retirement required")
    triggers = {}
    for family in EventFamily:
        if family not in supported:
            continue
        if family.value not in semantic_triggers:
            raise ValueError(f"BLOCKED_TASK_CATALOG_GAP: missing trigger for {family.value}")
        raw = semantic_triggers[family.value]
        triggers[family] = raw if isinstance(raw, SemanticTrigger) else SemanticTrigger.from_dict(raw)
    grounding = grounding_options[(schedule_index + seed) % len(grounding_options)]
    retirement = retirement_options[(schedule_index // 2 + seed) % len(retirement_options)]
    candidates = _topological_shuffles(grounding, retirement)
    rng = random.Random(int(canonical_sha256({"seed": seed, "master_episode_id": master_episode_id, "schedule_index": schedule_index}), 16))
    counts = position_counts or {}
    # Linear incremental squared-count cost favors least-used positions;
    # dependencies define which positions each family can legally occupy.
    best_cost: int | None = None
    best: list[tuple[EventFamily, ...]] = []
    for order in candidates:
        step = 0
        legal = True
        for index, family in enumerate(order):
            trigger = triggers[family]
            step = max(trigger.earliest_policy_step, step + trigger.min_steps_since_previous_event if index else 0)
            if step > trigger.latest_policy_step:
                legal = False
                break
        if not legal:
            continue
        cost = sum(2 * counts.get((family.value, index), 0) + 1 for index, family in enumerate(order, 1))
        if best_cost is None or cost < best_cost:
            best_cost, best = cost, [order]
        elif cost == best_cost:
            best.append(order)
    if not best:
        raise ValueError("BLOCKED_TASK_CATALOG_GAP: no feasible semantic trigger ordering")
    order = rng.choice(best)
    event_ids = {family: "ev_" + canonical_sha256({"master_episode_id": master_episode_id, "event_index": index})[:24]
                 for index, family in enumerate(order, 1)}
    events = []
    for index, family in enumerate(order, 1):
        predecessor = retirement if family is EventFamily.USER_REISSUES_RETIRED_GOAL else _PAIR_PREDECESSORS.get(family)
        events.append(ScheduledEvent(event_ids[family], index, family, triggers[family],
                                     (event_ids[predecessor],) if predecessor else (),
                                     family in _PAIR_PREDECESSORS))
    return MasterSchedule(master_episode_id, seed, tuple(events))


def build_balanced_master_schedules(session_specs: Sequence[Mapping[str, Any]], *, seed: int = 20260906) -> tuple[MasterSchedule, ...]:
    """Build in canonical session-ID order so caller ordering cannot change pairing."""
    ordered = sorted(session_specs, key=lambda item: item["master_episode_id"])
    ids = [item["master_episode_id"] for item in ordered]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate master session")
    counts: Counter[tuple[str, int]] = Counter()
    schedules = []
    for index, spec in enumerate(ordered):
        schedule = build_master_schedule(spec["master_episode_id"], seed=seed, schedule_index=index,
                                         semantic_triggers=spec["semantic_triggers"],
                                         supported_event_families=spec.get("supported_event_families"),
                                         position_counts=counts)
        counts.update((event.family.value, event.event_index) for event in schedule.events)
        schedules.append(schedule)
    return tuple(schedules)


class TriggerStatus(str, Enum):
    READY = "READY"
    WAITING_EARLIEST_STEP = "WAITING_EARLIEST_STEP"
    WAITING_MINIMUM_SPACING = "WAITING_MINIMUM_SPACING"
    WAITING_SEMANTIC_TRIGGER = "WAITING_SEMANTIC_TRIGGER"
    WAITING_PHYSICAL_FEASIBILITY = "WAITING_PHYSICAL_FEASIBILITY"
    WAITING_UNGRASPED_OBJECT = "WAITING_UNGRASPED_OBJECT"
    BLOCKED_SEMANTIC_TRIGGER_UNAVAILABLE = "BLOCKED_SEMANTIC_TRIGGER_UNAVAILABLE"
    BLOCKED_FEASIBILITY_GUARD_UNAVAILABLE = "BLOCKED_FEASIBILITY_GUARD_UNAVAILABLE"
    EVENT_TRIGGER_WINDOW_MISSED = "EVENT_TRIGGER_WINDOW_MISSED"
    EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE = "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE"


@dataclass(frozen=True)
class TriggerContext:
    policy_step: int
    semantic_facts: Mapping[str, bool]
    feasibility_facts: Mapping[str, bool]
    previous_event_step: int | None = None
    prior_failure: bool = False
    grasped_entities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _integer(self.policy_step, "policy_step")
        if self.previous_event_step is not None:
            _integer(self.previous_event_step, "previous_event_step")
            if self.previous_event_step > self.policy_step:
                raise ValueError("previous event cannot occur in the future")
        for name in ("semantic_facts", "feasibility_facts"):
            values = getattr(self, name)
            if any(type(v) is not bool for v in values.values()):
                raise ValueError("trusted trigger facts must be booleans")
            object.__setattr__(self, name, freeze_json(values))
        if type(self.prior_failure) is not bool:
            raise ValueError("prior_failure must be boolean")
        object.__setattr__(self, "grasped_entities", tuple(self.grasped_entities))


@dataclass(frozen=True)
class TriggerDecision:
    event_id: str
    status: TriggerStatus
    include_in_denominator: bool = True

    @property
    def ready(self) -> bool:
        return self.status is TriggerStatus.READY

    @property
    def terminal_failure(self) -> bool:
        return self.status in {TriggerStatus.EVENT_TRIGGER_WINDOW_MISSED, TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE}


def evaluate_trigger(event: ScheduledEvent, context: TriggerContext) -> TriggerDecision:
    """Read-only decision: neither consumes policy steps nor changes arm state."""
    trigger = event.trigger
    status = TriggerStatus.READY
    if context.prior_failure:
        status = TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE
    elif context.policy_step > trigger.latest_policy_step:
        status = TriggerStatus.EVENT_TRIGGER_WINDOW_MISSED
    elif context.policy_step < trigger.earliest_policy_step:
        status = TriggerStatus.WAITING_EARLIEST_STEP
    elif event.event_index > 1 and context.previous_event_step is None:
        raise ValueError("noninitial event requires previous event delivery step")
    elif context.previous_event_step is not None and context.policy_step - context.previous_event_step < trigger.min_steps_since_previous_event:
        status = TriggerStatus.WAITING_MINIMUM_SPACING
    elif trigger.predicate not in context.semantic_facts:
        status = TriggerStatus.BLOCKED_SEMANTIC_TRIGGER_UNAVAILABLE
    elif not context.semantic_facts[trigger.predicate]:
        status = TriggerStatus.WAITING_SEMANTIC_TRIGGER
    elif trigger.physical_feasibility_guard not in context.feasibility_facts:
        status = TriggerStatus.BLOCKED_FEASIBILITY_GUARD_UNAVAILABLE
    elif not context.feasibility_facts[trigger.physical_feasibility_guard]:
        status = TriggerStatus.WAITING_PHYSICAL_FEASIBILITY
    elif trigger.moves_object and trigger.intervention_entity in context.grasped_entities and not trigger.forced_external_displacement:
        status = TriggerStatus.WAITING_UNGRASPED_OBJECT
    return TriggerDecision(event.event_id, status)


@dataclass(frozen=True)
class FreshRevalidation:
    """Verifier output, never synthesized by a clear/available event."""
    event_id: str
    evidence_id: str
    observation_version: int
    successful: bool
    provenance: str

    def __post_init__(self) -> None:
        if not self.event_id or not self.evidence_id or not self.provenance:
            raise ValueError("revalidation requires event, evidence identity and provenance")
        _integer(self.observation_version, "observation_version")
        if type(self.successful) is not bool:
            raise ValueError("successful must be boolean")


def has_fresh_revalidation(event: ScheduledEvent, evidence: FreshRevalidation | None, *, injected_observation_version: int) -> bool:
    """Check an explicit successful observation newer than the pre-injection one.

    This records schedule legality only; future state kernels must additionally
    validate the occurrence-specific restore guard, lifecycle and authority.
    """
    _integer(injected_observation_version, "injected_observation_version")
    return bool(event.requires_fresh_revalidation and evidence is not None
                and evidence.event_id == event.event_id and evidence.successful
                and evidence.observation_version > injected_observation_version)


@dataclass
class SemanticScheduler:
    """Per-trajectory event cursor; contains no ledger or execution owner state."""
    schedule: MasterSchedule
    protocol: ProtocolName | str = ProtocolName.CONTROLLED
    _delivered: list[tuple[str, int]] = field(default_factory=list, init=False, repr=False)
    _failed: bool = field(default=False, init=False, repr=False)
    _last_observed_step: int | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.protocol = ProtocolName(self.protocol)

    @property
    def events(self) -> tuple[ScheduledEvent, ...]:
        return self.schedule.events if self.protocol is ProtocolName.CONTROLLED else self.schedule.events[:4]

    @property
    def complete(self) -> bool:
        return len(self._delivered) == len(self.events)

    def decision(self, context: TriggerContext) -> TriggerDecision | None:
        if self.complete:
            return None
        if self._last_observed_step is not None and context.policy_step < self._last_observed_step:
            raise ValueError("policy steps cannot rewind within a continuous trajectory")
        self._last_observed_step = context.policy_step
        previous = self._delivered[-1][1] if self._delivered else None
        if context.previous_event_step != previous:
            raise ValueError("trigger context disagrees with recorded prior event")
        if self._failed:
            context = TriggerContext(context.policy_step, context.semantic_facts, context.feasibility_facts,
                                     previous, True, context.grasped_entities)
        decision = evaluate_trigger(self.events[len(self._delivered)], context)
        if decision.terminal_failure:
            self._failed = True
        return decision

    def record_delivery(self, context: TriggerContext) -> ScheduledEvent:
        decision = self.decision(context)
        if decision is None or not decision.ready:
            raise ValueError("only a ready next event can be recorded as delivered")
        event = self.events[len(self._delivered)]
        self._delivered.append((event.event_id, context.policy_step))
        return event

    def remaining_after_failure(self) -> tuple[TriggerDecision, ...]:
        """Keep every remaining event in the denominator; no reset entry point."""
        self._failed = True
        return tuple(TriggerDecision(event.event_id, TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE)
                     for event in self.events[len(self._delivered):])
