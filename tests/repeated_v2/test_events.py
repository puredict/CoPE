from dataclasses import replace
import inspect

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_sha256
from cope_benchmark.repeated_v2.enums import EventFamily, MethodName
from cope_benchmark.repeated_v2.events import (
    EventWorldSnapshot, FreshObservation, complete_event_injection,
    inject_event, phase1_contract_self_check,
)
from cope_benchmark.repeated_v2.schema import HiddenCanonicalEffect, PublicEventPayload


def public(event_id="opaque-e1", event_index=1):
    return PublicEventPayload(event_id, event_index, "A shared observation or instruction arrived.", 1.,
                              ("evidence-1",), 10, "test_fixture", user_message="Please put the mug away.")


def effect(family, intervention, event_id="opaque-e1"):
    return HiddenCanonicalEffect(event_id, family, ("goal:one@1",), {"lifecycle": "expired"}, intervention)


def movement(position=(1, 2, 3)):
    return {"entity_id": "mug", "position": position, "safe_positions": [position]}


def ready_world(**changes):
    fields = dict(object_positions={"mug": [0, 0, 0]}, policy_step=10, environment_step=10)
    fields.update(changes)
    return EventWorldSnapshot(**fields)


def observation(**changes):
    fields = dict(observation_id="obs1", after_event_id="opaque-e1", version=1, policy_step=10,
                  environment_step=10, data={"image_ref": "post-event-image"})
    fields.update(changes)
    return FreshObservation(**fields)


@pytest.mark.parametrize("family", tuple(EventFamily))
def test_all_event_families_prepare_environment_change_and_leave_all_arm_states_untouched(family):
    # An input object can be aliased to every arm; schema construction detaches
    # it before the environment boundary operates on its own typed snapshot.
    source = {"mug": [0, 0, 0]}
    arms = {m.value: {"corrupted_prior_state": [m.value], "poses": source} for m in MethodName}
    hashes = {m: canonical_sha256(state) for m, state in arms.items()}
    world = ready_world(object_positions=source)
    intervention = {}
    if family in (EventFamily.TARGET_OBJECT_DISPLACED, EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED):
        intervention = movement()
    elif family is EventFamily.TEMPORARY_NO_GO_APPEARS:
        intervention = {"zone_id": "zone1", "minimum": [0, 0, 0], "maximum": [1, 1, 1]}
    elif family is EventFamily.TEMPORARY_NO_GO_CLEARS:
        world = replace(world, active_no_go_zones={"zone1": {"minimum": [0, 0, 0], "maximum": [1, 1, 1]}})
        intervention = {"zone_id": "zone1"}
    elif family in (EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE, EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN):
        available = family is EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN
        if available:
            world = replace(world, unavailable_entities=("mug",))
        intervention = {**movement((0, 0, 0) if available else (1, 2, 3)),
                        "accessible_bounds": {"minimum": [-.5, -.5, -.5], "maximum": [.5, .5, .5]}}
    before = world.sha256
    pending = inject_event(world=world, public_payload=public(), hidden_effect=effect(family, intervention))
    assert world.sha256 == before
    completed = complete_event_injection(pending, observation())
    assert set(completed.method_input()) == {"event_evidence", "observation"}
    assert {m: canonical_sha256(state) for m, state in arms.items()} == hashes
    assert completed.environment_after.policy_step == world.policy_step
    assert completed.environment_after.environment_step == world.environment_step


def test_injector_capability_has_no_arm_state_or_callback_and_rejects_wrong_world_types():
    assert set(inspect.signature(inject_event).parameters) == {"world", "public_payload", "hidden_effect"}
    hidden = effect(EventFamily.USER_CANCELS_ACTIVE_GOAL, {})
    with pytest.raises(TypeError):
        inject_event(world=ready_world(), public_payload=public(), hidden_effect=hidden, arm_state={})
    with pytest.raises(TypeError, match="environment-only"):
        inject_event(world={"arm_state": {}}, public_payload=public(), hidden_effect=hidden)
    with pytest.raises(ValueError, match="unknown"):
        EventWorldSnapshot.from_dict({"arm_state": {"goals": []}})
    with pytest.raises(ValueError, match="unknown"):
        inject_event(world=ready_world(), public_payload=public(),
                     hidden_effect=effect(EventFamily.USER_CANCELS_ACTIVE_GOAL, {"arm_state": {}}))


def test_physical_injection_cannot_teleport_grasped_entity_without_explicit_event_model():
    world = ready_world(held_object="mug")
    hidden = effect(EventFamily.TARGET_OBJECT_DISPLACED, movement())
    with pytest.raises(ValueError, match="grasped"):
        inject_event(world=world, public_payload=public(), hidden_effect=hidden)
    forced = replace(hidden, simulator_intervention={**movement(), "forced_external_displacement": True})
    pending = inject_event(world=world, public_payload=public(), hidden_effect=forced)
    assert pending.environment_after.held_object is None
    assert world.held_object == "mug"


@pytest.mark.parametrize("changes", [{"position": [99, 0, 0]}, {"safe_positions": []}, {"entity_id": "unknown"},
    {"forced_external_displacement": "yes"}, {"position": [float("nan"), 0, 0]}])
def test_physical_intervention_fails_closed_on_missing_safe_pose_or_entity(changes):
    with pytest.raises(ValueError):
        inject_event(world=ready_world(), public_payload=public(),
                     hidden_effect=effect(EventFamily.TARGET_OBJECT_DISPLACED, {**movement(), **changes}))


@pytest.mark.parametrize("changes", [{"version": 0}, {"version": 2}, {"after_event_id": "wrong"},
    {"policy_step": 11}, {"environment_step": 11}])
def test_observation_must_be_fresh_and_event_injection_must_consume_no_steps(changes):
    pending = inject_event(world=ready_world(), public_payload=public(),
                           hidden_effect=effect(EventFamily.USER_CANCELS_ACTIVE_GOAL, {}))
    assert not hasattr(pending, "method_input")
    with pytest.raises(ValueError):
        complete_event_injection(pending, observation(**changes))


def test_public_observation_rejects_hidden_truth_and_detaches_input():
    with pytest.raises(ValueError):
        observation(data={"camera": {"canonical_state": {"goal": "correct"}}})
    data = {"features": [1, 2, 3]}
    result = observation(data=data)
    data["features"][0] = 100
    assert result.data["features"] == (1, 2, 3)


def test_restoration_pair_and_duplicate_event_guards():
    for family, intervention in [
        (EventFamily.TEMPORARY_NO_GO_CLEARS, {"zone_id": "zone1"}),
        (EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN, {**movement((0, 0, 0)),
            "accessible_bounds": {"minimum": [-1, -1, -1], "maximum": [1, 1, 1]}}),
    ]:
        with pytest.raises(ValueError):
            inject_event(world=ready_world(), public_payload=public(), hidden_effect=effect(family, intervention))
    pending = inject_event(world=ready_world(), public_payload=public(),
                           hidden_effect=effect(EventFamily.USER_CANCELS_ACTIVE_GOAL, {}))
    with pytest.raises(ValueError, match="already injected"):
        inject_event(world=pending.environment_after, public_payload=public(),
                     hidden_effect=effect(EventFamily.USER_CANCELS_ACTIVE_GOAL, {}))


def test_zero_provider_contract_self_check_is_deterministic():
    assert phase1_contract_self_check() == phase1_contract_self_check()
    assert all(phase1_contract_self_check().values())
