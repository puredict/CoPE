"""Pure event injection over environment-only snapshots.

Phase 1 prepares and verifies interventions without a simulator callback.
A later simulator bridge must apply the prepared environment change and supply
a fresh observation. No arm state, method, ledger, context, or callback is an
argument or stored capability. Thus this boundary cannot repair an arm's state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .canonical import canonical_sha256, freeze_json, to_primitive
from .enums import EventFamily
from .evidence import assert_public_safe, public_event_payload
from .schema import EventEvidence, HiddenCanonicalEffect, PublicEventPayload, Record


@dataclass(frozen=True)
class EventWorldSnapshot(Record):
    object_positions: Mapping[str, tuple[float, float, float]] = field(default_factory=dict)
    held_object: str | None = None
    active_no_go_zones: Mapping[str, Any] = field(default_factory=dict)
    unavailable_entities: tuple[str, ...] = ()
    user_messages: tuple[str, ...] = ()
    policy_step: int = 0
    environment_step: int = 0
    observation_version: int = 0
    applied_event_ids: tuple[str, ...] = ()

    def _validate(self) -> None:
        if len(set(self.applied_event_ids)) != len(self.applied_event_ids):
            raise ValueError("duplicate event injection")
        if self.held_object is not None and self.held_object not in self.object_positions:
            raise ValueError("held object is absent from environment snapshot")
        if set(self.unavailable_entities) - set(self.object_positions):
            raise ValueError("unavailable entity is absent from environment snapshot")


@dataclass(frozen=True)
class FreshObservation(Record):
    observation_id: str
    after_event_id: str
    version: int
    policy_step: int
    environment_step: int
    data: Mapping[str, Any]

    def _validate(self) -> None:
        if not self.data:
            raise ValueError("fresh observation cannot be empty")
        assert_public_safe(self.data)


@dataclass(frozen=True)
class HiddenEventApplication(Record):
    event_id: str
    effect: HiddenCanonicalEffect
    environment_before_sha256: str
    environment_after_sha256: str
    policy_step_before: int
    policy_step_after: int
    environment_step_before: int
    environment_step_after: int


@dataclass(frozen=True)
class PendingEventInjection(Record):
    public_payload: PublicEventPayload | EventEvidence
    environment_after: EventWorldSnapshot
    hidden_application: HiddenEventApplication
    required_observation_version: int


@dataclass(frozen=True)
class CompletedEventInjection(Record):
    public_payload: PublicEventPayload | EventEvidence
    observation: FreshObservation
    environment_after: EventWorldSnapshot
    hidden_application: HiddenEventApplication

    def method_input(self) -> Mapping[str, Any]:
        """Explicit allowlist: environmental intervention/audit never crosses."""
        value = {"event_evidence": public_event_payload(self.public_payload), "observation": self.observation.to_dict()}
        assert_public_safe(value)
        return freeze_json(value)


def _keys(value: Mapping[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    if required - set(value) or set(value) - required - optional:
        raise ValueError("incomplete or unknown simulator intervention fields")


def _position(value: Any) -> tuple[float, float, float]:
    # Reuse the strict positional schema, including finite-number checks.
    return EventWorldSnapshot(object_positions={"entity": value}).object_positions["entity"]


def _bounds(value: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if not isinstance(value, Mapping) or set(value) != {"minimum", "maximum"}:
        raise ValueError("bounds require minimum and maximum")
    minimum, maximum = _position(value["minimum"]), _position(value["maximum"])
    if any(lo >= hi for lo, hi in zip(minimum, maximum)):
        raise ValueError("invalid bounds")
    return minimum, maximum


def inject_event(*, world: EventWorldSnapshot, public_payload: PublicEventPayload | EventEvidence,
                 hidden_effect: HiddenCanonicalEffect) -> PendingEventInjection:
    """Prepare one event without mutating input objects or taking any steps."""
    if type(world) is not EventWorldSnapshot or type(hidden_effect) is not HiddenCanonicalEffect:
        raise TypeError("injection requires an environment-only snapshot and hidden effect")
    public_event_payload(public_payload)
    if hidden_effect.event_id != public_payload.event_id:
        raise ValueError("public/hidden event IDs differ")
    if hidden_effect.event_id in world.applied_event_ids:
        raise ValueError("event already injected")
    intervention = hidden_effect.simulator_intervention
    family = hidden_effect.true_family
    positions = to_primitive(world.object_positions)
    zones = to_primitive(world.active_no_go_zones)
    unavailable = set(world.unavailable_entities)
    messages = world.user_messages
    held_object = world.held_object
    moving = {
        EventFamily.TARGET_OBJECT_DISPLACED,
        EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED,
        EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE,
        EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN,
    }
    if family in moving:
        required = {"entity_id", "position", "safe_positions"}
        if family in (EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE, EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN):
            required.add("accessible_bounds")
        _keys(intervention, required, {"forced_external_displacement"})
        entity = intervention["entity_id"]
        if type(entity) is not str or entity not in positions:
            raise ValueError("unknown intervention entity")
        forced = intervention.get("forced_external_displacement", False)
        if type(forced) is not bool:
            raise ValueError("forced displacement declaration must be boolean")
        if entity == world.held_object and not forced:
            raise ValueError("cannot teleport a grasped object without explicit forced displacement")
        position = _position(intervention["position"])
        safe = intervention["safe_positions"]
        if not isinstance(safe, tuple) or not safe or position not in tuple(_position(p) for p in safe):
            raise ValueError("intervention pose is absent from catalog safe positions")
        if family in (EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE, EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN):
            minimum, maximum = _bounds(intervention["accessible_bounds"])
            inside = all(lo <= p <= hi for lo, p, hi in zip(minimum, position, maximum))
            becoming_available = family is EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN
            if becoming_available and entity not in unavailable:
                raise ValueError("availability restoration requires preceding unavailability")
            if not becoming_available and entity in unavailable:
                raise ValueError("entity already unavailable")
            if inside != becoming_available:
                raise ValueError("availability intervention fails accessibility guard")
            if becoming_available:
                unavailable.remove(entity)
            else:
                unavailable.add(entity)
        positions[entity] = position
        if forced and held_object == entity:
            held_object = None
    elif family is EventFamily.TEMPORARY_NO_GO_APPEARS:
        _keys(intervention, {"zone_id", "minimum", "maximum"})
        zone = intervention["zone_id"]
        if type(zone) is not str or not zone or zone in zones:
            raise ValueError("invalid or already active no-go zone")
        geometry = {"minimum": intervention["minimum"], "maximum": intervention["maximum"]}
        _bounds(geometry)
        zones[zone] = geometry
    elif family is EventFamily.TEMPORARY_NO_GO_CLEARS:
        _keys(intervention, {"zone_id"})
        zone = intervention["zone_id"]
        if type(zone) is not str or zone not in zones:
            raise ValueError("cannot clear a no-go zone that is not active")
        del zones[zone]
    else:
        # Preference, replacement, cancellation and reissue inject an utterance.
        # Their responsibility/lifecycle effect is decided later by each arm.
        _keys(intervention, set())
        if public_payload.user_message is None:
            raise ValueError("user event requires a public utterance")
        messages += (public_payload.user_message,)
    updated = replace(world, object_positions=positions, held_object=held_object,
                      active_no_go_zones=zones, unavailable_entities=tuple(sorted(unavailable)),
                      user_messages=messages, applied_event_ids=world.applied_event_ids + (hidden_effect.event_id,))
    audit = HiddenEventApplication(
        hidden_effect.event_id, hidden_effect, world.sha256, updated.sha256,
        world.policy_step, updated.policy_step, world.environment_step, updated.environment_step,
    )
    return PendingEventInjection(public_payload, updated, audit, world.observation_version + 1)


def complete_event_injection(pending: PendingEventInjection, observation: FreshObservation) -> CompletedEventInjection:
    """Reject stale observations and any policy or simulator step during injection."""
    if type(pending) is not PendingEventInjection or type(observation) is not FreshObservation:
        raise TypeError("completion requires typed injection and observation records")
    if observation.after_event_id != pending.public_payload.event_id:
        raise ValueError("observation does not follow this event")
    if observation.version != pending.required_observation_version:
        raise ValueError("fresh post-event observation is required")
    if (observation.policy_step, observation.environment_step) != (
        pending.environment_after.policy_step, pending.environment_after.environment_step,
    ):
        raise ValueError("event injection cannot consume a policy or environment step")
    updated = replace(pending.environment_after, observation_version=observation.version)
    return CompletedEventInjection(pending.public_payload, observation, updated, pending.hidden_application)


def phase1_contract_self_check() -> dict[str, bool]:
    """Deterministic synthetic boundary checks; this is not a simulator result."""
    public = PublicEventPayload("e-opaque", 1, "A new instruction was received.", 1.0,
                                ("evidence-1",), 10, "synthetic_preflight", user_message="Please move gently.")
    hidden = HiddenCanonicalEffect("e-opaque", EventFamily.USER_ADDS_PERSISTENT_PREFERENCE,
                                   ("goal:one@1",), {"expected_operator": "INSERT"}, {})
    world = EventWorldSnapshot(policy_step=10, environment_step=10)
    before = canonical_sha256(world)
    pending = inject_event(world=world, public_payload=public, hidden_effect=hidden)
    complete = complete_event_injection(pending, FreshObservation("obs-1", public.event_id, 1, 10, 10, {"image_ref": "image-1"}))
    leaked = False
    try:
        public_event_payload(hidden)
        leaked = True
    except ValueError:
        pass
    stepped = False
    try:
        complete_event_injection(pending, FreshObservation("obs-2", public.event_id, 1, 11, 10, {"image_ref": "image-2"}))
        stepped = True
    except ValueError:
        pass
    from .enums import CommitmentRole, GroundingValidity, Lifecycle
    from .occurrence import OccurrenceAllocator, RevalidationRecord, restore_occurrence_id
    from .schema import CommitmentOccurrence, PersistentLedger, record_json_schema
    slot = CommitmentOccurrence("goal:one", "goal:one@1", CommitmentRole.ACHIEVEMENT_GOAL,
        "inside", ("mug", "cabinet"), Lifecycle.SUSPENDED, GroundingValidity.VALID, 1.,
        "hard", "task", "user", restore_guard={"reachable": True})
    retired = replace(slot, lifecycle=Lifecycle.EXPIRED, retired_event_id="e-retire")
    allocator = OccurrenceAllocator((retired,))
    repeat = allocator.reissue(retired)
    validation = RevalidationRecord("verify-1", slot.occurrence_id, "e-restore", 2, 21, 1,
                                    True, canonical_sha256(slot.restore_guard), ("fresh-evidence",))
    restore_args = dict(event_id="e-restore", event_index=2, source_revision=1, latest_invalidation_timestamp=20)
    restored_id = restore_occurrence_id(slot, validation, **restore_args)
    stale_rejected = False
    try:
        restore_occurrence_id(slot, replace(validation, timestamp=20), **restore_args)
    except ValueError:
        stale_rejected = True
    json_schema_valid = False
    try:
        import jsonschema
        jsonschema.Draft202012Validator(record_json_schema(PublicEventPayload)).validate(public.to_dict())
        json_schema_valid = True
    except ImportError:
        pass  # The preflight reports a failed dependency check; no calls occur.
    ledger = PersistentLedger(0, (slot,))
    return {
        "canonical_roundtrip": canonical_sha256(public) == canonical_sha256(public.to_dict()),
        "event_input_immutable": before == canonical_sha256(world),
        "hidden_event_rejected": not leaked,
        "fresh_observation_without_step": not stepped,
        "public_projection_isolated": "canonical_effect" not in str(complete.method_input()),
        "injector_has_no_arm_state_argument": set(__import__("inspect").signature(inject_event).parameters) == {"world", "public_payload", "hidden_effect"},
        "schema_roundtrip": PersistentLedger.from_dict(ledger.to_dict()).sha256 == ledger.sha256,
        "json_schema_public_fixture_valid": json_schema_valid,
        "occurrence_allocation_deterministic": repeat == OccurrenceAllocator((retired,)).reissue(retired),
        "occurrence_reissue_fresh": repeat == "goal:one@2" and retired.occurrence_id == "goal:one@1",
        "restore_preserves_occurrence_id": restored_id == slot.occurrence_id,
        "restore_rejects_stale_evidence": stale_rejected,
    }
