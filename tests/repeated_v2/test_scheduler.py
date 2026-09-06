from collections import Counter
from dataclasses import replace

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_json
from cope_benchmark.repeated_v2.enums import EventFamily, ProtocolName
from cope_benchmark.repeated_v2.scheduler import (
    CHECKPOINTS, FreshRevalidation, MasterSchedule, SemanticScheduler,
    SemanticTrigger, TriggerContext, TriggerStatus, build_balanced_master_schedules,
    build_master_schedule, evaluate_trigger, has_fresh_revalidation,
    validate_prefix, validate_schedule,
)


def trigger_map():
    return {family.value: {
        "predicate": "verified:before_final_goal_completed",
        "earliest_policy_step": 10,
        "latest_policy_step": 250,
        "physical_feasibility_guard": "safe:catalog_region",
        "min_steps_since_previous_event": 10,
    } for family in EventFamily}


def schedule(**kwargs):
    return build_master_schedule("synthetic-master", semantic_triggers=trigger_map(), **kwargs)


def context(event, *, step=30, previous=None, semantic=True, physical=True, **kwargs):
    return TriggerContext(step, {event.trigger.predicate: semantic},
                          {event.trigger.physical_feasibility_guard: physical}, previous, **kwargs)


def test_schedule_determinism_roundtrip_and_protocol_prefix_identity():
    first, second = schedule(), schedule()
    assert canonical_json(first) == canonical_json(second)
    assert first.sha256 == MasterSchedule.from_dict(first.to_dict()).sha256
    assert first.sha256 != schedule(seed=20260907).sha256
    for checkpoint in CHECKPOINTS:
        prefix = first.prefix(checkpoint)
        validate_prefix(prefix)
        assert prefix == first.events[:checkpoint]
    for checkpoint in (0, 1, 2, 4):
        assert first.prefix(checkpoint) == first.prefix(checkpoint, protocol=ProtocolName.END_TO_END)
    with pytest.raises(ValueError, match="checkpoint"):
        first.prefix(8, protocol=ProtocolName.END_TO_END)
    with pytest.raises(ValueError, match="checkpoint"):
        first.prefix(True)


def test_full_library_and_family_position_balance_subject_to_dependencies():
    specs = [{"master_episode_id": f"test-{i:03d}", "semantic_triggers": trigger_map()} for i in range(32)]
    schedules = build_balanced_master_schedules(specs)
    assert schedules == build_balanced_master_schedules(list(reversed(specs)))
    counts = Counter((event.family, event.event_index) for item in schedules for event in item.events)
    totals = Counter(event.family for item in schedules for event in item.events)
    assert set(totals) == set(EventFamily)
    assert totals[EventFamily.USER_REPLACES_ACTIVE_GOAL] == totals[EventFamily.USER_CANCELS_ACTIVE_GOAL] == 16
    assert totals[EventFamily.TARGET_OBJECT_DISPLACED] == totals[EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED] == 16
    for item in schedules:
        validate_schedule(item)
        assert len(item.events) == 8
    # Independent preference can occupy any position; pair endpoints cannot
    # legally occupy both extremes. No unconstrained family is pinned in place.
    assert {position for (family, position), n in counts.items() if family is EventFamily.USER_ADDS_PERSISTENT_PREFERENCE and n} == set(range(1, 9))
    assert max(counts[(EventFamily.USER_ADDS_PERSISTENT_PREFERENCE, p)] for p in range(1, 9)) <= 7
    assert counts[(EventFamily.TEMPORARY_NO_GO_CLEARS, 1)] == 0
    assert counts[(EventFamily.USER_REISSUES_RETIRED_GOAL, 1)] == 0
    assert counts[(EventFamily.TEMPORARY_NO_GO_APPEARS, 8)] == 0


def test_missing_and_unsupported_catalog_semantics_fail_closed():
    values = trigger_map()
    values.pop(EventFamily.TARGET_OBJECT_DISPLACED.value)
    with pytest.raises(ValueError, match="BLOCKED_TASK_CATALOG_GAP"):
        build_master_schedule("test", semantic_triggers=values)
    values = trigger_map()
    del values[EventFamily.TARGET_OBJECT_DISPLACED.value]["physical_feasibility_guard"]
    with pytest.raises(ValueError, match="BLOCKED_TASK_CATALOG_GAP"):
        build_master_schedule("test", semantic_triggers=values)
    values = trigger_map()
    values[EventFamily.TARGET_OBJECT_DISPLACED.value]["predicate"] = "policy_step_gte"
    with pytest.raises(ValueError, match="fixed-step"):
        build_master_schedule("test", semantic_triggers=values)
    with pytest.raises(ValueError, match="duplicate master"):
        build_balanced_master_schedules([{"master_episode_id": "x"}, {"master_episode_id": "x"}])


def test_dependencies_and_restoration_obligations_cannot_be_removed():
    original = schedule()
    terminal = next(e for e in original.events if e.family is EventFamily.TEMPORARY_NO_GO_CLEARS)
    events = list(original.events)
    events[terminal.event_index - 1] = replace(terminal, dependency_event_ids=())
    with pytest.raises(ValueError, match="paired predecessor"):
        validate_prefix(events)
    events[terminal.event_index - 1] = replace(terminal, requires_fresh_revalidation=False)
    with pytest.raises(ValueError, match="fresh post-event"):
        validate_schedule(events)
    reissue = next(e for e in original.events if e.family is EventFamily.USER_REISSUES_RETIRED_GOAL)
    events = list(original.events)
    events[reissue.event_index - 1] = replace(reissue, dependency_event_ids=())
    with pytest.raises(ValueError, match="retirement dependency"):
        validate_prefix(events)
    # Truncating a prefix may leave an open pair; reversing cannot close first.
    with pytest.raises(ValueError):
        validate_prefix(tuple(replace(e, event_index=i) for i, e in enumerate(reversed(original.events), 1)))


def test_impossible_windows_fail_before_execution():
    values = trigger_map()
    for item in values.values():
        item["latest_policy_step"] = 30
    with pytest.raises(ValueError, match="no feasible"):
        build_master_schedule("test", semantic_triggers=values)
    with pytest.raises(ValueError, match=">= 10"):
        SemanticTrigger("milestone", 0, 100, "safe", min_steps_since_previous_event=9)
    with pytest.raises(ValueError):
        SemanticTrigger("milestone", True, 100, "safe")


def test_trigger_semantics_windows_spacing_and_missing_facts():
    event = schedule().events[0]
    assert evaluate_trigger(event, context(event, step=9)).status is TriggerStatus.WAITING_EARLIEST_STEP
    assert evaluate_trigger(event, context(event, step=10)).ready
    assert evaluate_trigger(event, context(event, step=250, semantic=False)).status is TriggerStatus.WAITING_SEMANTIC_TRIGGER
    assert evaluate_trigger(event, context(event, step=251)).status is TriggerStatus.EVENT_TRIGGER_WINDOW_MISSED
    assert evaluate_trigger(event, context(event, physical=False)).status is TriggerStatus.WAITING_PHYSICAL_FEASIBILITY
    assert evaluate_trigger(event, TriggerContext(30, {}, {})).status is TriggerStatus.BLOCKED_SEMANTIC_TRIGGER_UNAVAILABLE
    assert evaluate_trigger(event, TriggerContext(30, {event.trigger.predicate: True}, {})).status is TriggerStatus.BLOCKED_FEASIBILITY_GUARD_UNAVAILABLE
    second = schedule().events[1]
    assert evaluate_trigger(second, context(second, step=30, previous=21)).status is TriggerStatus.WAITING_MINIMUM_SPACING
    assert evaluate_trigger(second, context(second, step=30, previous=20)).ready
    with pytest.raises(ValueError, match="previous event"):
        evaluate_trigger(second, context(second))


def test_grasp_guard_and_explicit_forced_displacement_exception():
    event = schedule().events[0]
    event = replace(event, trigger=replace(event.trigger, moves_object=True, intervention_entity="mug"))
    held = context(event, grasped_entities=("mug",))
    assert evaluate_trigger(event, held).status is TriggerStatus.WAITING_UNGRASPED_OBJECT
    forced = replace(event, trigger=replace(event.trigger, forced_external_displacement=True))
    assert evaluate_trigger(forced, held).ready
    assert evaluate_trigger(forced, context(event, physical=False, grasped_entities=("mug",))).status is TriggerStatus.WAITING_PHYSICAL_FEASIBILITY


def test_clearance_never_certifies_revalidation_or_allows_stale_evidence():
    event = next(e for e in schedule().events if e.family is EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN)
    assert evaluate_trigger(event, context(event, previous=10)).ready
    assert not has_fresh_revalidation(event, None, injected_observation_version=5)
    fresh = FreshRevalidation(event.event_id, "evidence-1", 6, True, "shared-verifier")
    assert has_fresh_revalidation(event, fresh, injected_observation_version=5)
    for invalid in (replace(fresh, observation_version=5), replace(fresh, successful=False), replace(fresh, event_id="another-event")):
        assert not has_fresh_revalidation(event, invalid, injected_observation_version=5)


def test_public_references_do_not_encode_truth_in_identifiers():
    item = schedule()
    for event in item.events:
        public = event.public_reference()
        assert set(public) == {"event_id", "event_index"}
        assert event.event_id.startswith("ev_") and len(event.event_id) == 27
        assert not any(f.value.lower() in event.event_id.lower() for f in EventFamily)
    # The identity at each position is independent of the hidden family chosen.
    assert [e.event_id for e in item.events] == [e.event_id for e in schedule(seed=10).events]


def test_trajectory_failure_keeps_all_remaining_events_and_cannot_resume():
    master = schedule()
    scheduler = SemanticScheduler(master)
    event = master.events[0]
    scheduler.record_delivery(context(event, step=10))
    failed = scheduler.remaining_after_failure()
    assert len(failed) == 7
    assert all(item.status is TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE and item.include_in_denominator for item in failed)
    assert scheduler.decision(context(master.events[1], step=30, previous=10)).status is TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE
    with pytest.raises(ValueError, match="ready next event"):
        scheduler.record_delivery(context(master.events[1], step=30, previous=10))
    assert len(SemanticScheduler(master, ProtocolName.END_TO_END).remaining_after_failure()) == 4


def test_delivery_never_mutates_arm_inputs_and_owns_no_arm_state():
    master = schedule()
    scheduler = SemanticScheduler(master)
    arm = {"accepted_revision": 3, "expired_occurrences": ["old@1"]}
    before = canonical_json(arm)
    facts = {master.events[0].trigger.predicate: True}
    current = TriggerContext(10, facts, {master.events[0].trigger.physical_feasibility_guard: True})
    facts.clear()
    assert scheduler.decision(current).ready  # Caller mutation cannot alter snapshot.
    scheduler.record_delivery(current)
    assert canonical_json(arm) == before
    assert not hasattr(scheduler, "arm_state")
    with pytest.raises(TypeError):
        scheduler.record_delivery(current, arm_state=arm)
    with pytest.raises(TypeError):
        current.semantic_facts["bad"] = True


def test_observed_failure_and_policy_time_cannot_be_reset():
    master = schedule()
    scheduler = SemanticScheduler(master)
    first = master.events[0]
    assert scheduler.decision(context(first, prior_failure=True)).terminal_failure
    assert scheduler.decision(context(first)).status is TriggerStatus.EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE
    with pytest.raises(ValueError, match="cannot rewind"):
        scheduler.decision(context(first, step=29))
    missed = SemanticScheduler(master)
    assert missed.decision(context(first, step=251)).status is TriggerStatus.EVENT_TRIGGER_WINDOW_MISSED
    assert len(missed.remaining_after_failure()) == 8
