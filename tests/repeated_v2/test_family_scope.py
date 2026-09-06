"""Task-local support must limit execution without erasing unknown-scope gaps."""

import pytest

from cope_benchmark.repeated_v2.canonical import canonical_sha256
from cope_benchmark.repeated_v2.enums import EventFamily
from cope_benchmark.repeated_v2.scheduler import (
    build_balanced_master_schedules, build_master_schedule, validate_schedule,
)
from cope_benchmark.repeated_v2.task_catalog import (
    CatalogBlockedError, EVENT_FAMILIES, TaskCatalog, select_eligible_tasks, task_catalog_gaps,
)
from tests.repeated_v2.catalog_fixtures import synthetic_catalog
from tests.repeated_v2.test_scheduler import trigger_map


UNSUPPORTED = {'GOAL_RECEPTACLE_OR_GROUNDING_CHANGED', 'USER_REPLACES_ACTIVE_GOAL'}
SUPPORTED = tuple(family for family in EVENT_FAMILIES if family not in UNSUPPORTED)


def restricted_catalog():
    raw = synthetic_catalog().to_dict()
    for task in raw['tasks']:
        task['supported_event_families'] = list(SUPPORTED)
        for name in ('semantic_triggers', 'event_feasibility', 'safe_event_injection_poses'):
            task[name] = {key: value for key, value in task[name].items() if key in SUPPORTED}
    return raw


def test_certified_eight_family_scope_includes_every_eligible_task():
    catalog = TaskCatalog.from_dict(restricted_catalog())
    assert task_catalog_gaps(catalog, allow_synthetic=True) == ()
    assert [task.task_id for task in select_eligible_tasks(catalog, allow_synthetic=True)] == list(range(10))
    with pytest.raises(CatalogBlockedError, match='synthetic'):
        select_eligible_tasks(catalog)


def test_unsupported_failed_assessment_is_retained_but_does_not_drive_selection():
    raw = restricted_catalog()
    raw['tasks'][0]['event_feasibility']['USER_REPLACES_ACTIVE_GOAL'] = {
        'passed': False, 'evidence_refs': ['synthetic-fixture://unsupported'],
        'covered_state_ids': list(range(5)),
    }
    catalog = TaskCatalog.from_dict(raw)
    assert len(select_eligible_tasks(catalog, allow_synthetic=True)) == 10
    assert catalog.tasks[0].event_feasibility['USER_REPLACES_ACTIVE_GOAL']['passed'] is False
    raw['tasks'][0]['event_feasibility']['TARGET_OBJECT_DISPLACED']['passed'] = False
    selected = select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)
    assert [task.task_id for task in selected] == list(range(1, 10))


@pytest.mark.parametrize('field', ['semantic_triggers', 'event_feasibility', 'safe_event_injection_poses'])
def test_declared_supported_family_still_needs_its_metadata(field):
    raw = restricted_catalog()
    raw['tasks'][0][field].pop('TARGET_OBJECT_DISPLACED')
    with pytest.raises(CatalogBlockedError, match='TARGET_OBJECT_DISPLACED'):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)


@pytest.mark.parametrize('support', [list(SUPPORTED) + ['UNKNOWN_FAMILY'], list(SUPPORTED) + [SUPPORTED[0]]])
def test_unknown_or_duplicate_declared_family_cannot_be_silently_normalized(support):
    raw = restricted_catalog()
    raw['tasks'][0]['supported_event_families'] = support
    with pytest.raises(CatalogBlockedError, match='supported event families'):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)
    with pytest.raises(ValueError, match='BLOCKED_TASK_CATALOG_GAP'):
        build_master_schedule('scope', semantic_triggers=trigger_map(), supported_event_families=support)


@pytest.mark.parametrize('unresolved', [False, True])
def test_unknown_scope_keeps_all_family_diagnostics(unresolved):
    raw = restricted_catalog()
    task = raw['tasks'][0]
    if unresolved:
        task['unresolved_fields'] = ['supported_event_families']
    else:
        task['supported_event_families'] = []
    for name in ('semantic_triggers', 'event_feasibility', 'safe_event_injection_poses'):
        task[name] = {}
    gaps = task_catalog_gaps(TaskCatalog.from_dict(raw), allow_synthetic=True)
    assert 'task 0: task-specific event family support is unresolved; auditing all ten candidates' in gaps
    for family in EVENT_FAMILIES:
        assert f'task 0: unverified event feasibility {family}' in gaps
        assert f'task 0: missing semantic trigger/guard {family}' in gaps


@pytest.mark.parametrize('removed,category', [
    ({'TARGET_OBJECT_DISPLACED'}, 'grounding shift'),
    ({'TEMPORARY_NO_GO_CLEARS', 'TOOL_OR_TARGET_AVAILABLE_AGAIN'}, 'temporary lifecycle'),
    ({'USER_ADDS_PERSISTENT_PREFERENCE'}, 'persistent preference'),
    ({'USER_CANCELS_ACTIVE_GOAL'}, 'goal retirement'),
    ({'USER_REISSUES_RETIRED_GOAL'}, 'fresh goal reissue'),
])
def test_restricted_scope_cannot_erase_scientific_category_coverage(removed, category):
    raw = restricted_catalog()
    raw['tasks'][0]['supported_event_families'] = [family for family in SUPPORTED if family not in removed]
    with pytest.raises(CatalogBlockedError, match=category):
        select_eligible_tasks(TaskCatalog.from_dict(raw), allow_synthetic=True)


def test_scheduler_never_uses_extra_unsupported_triggers_and_retains_exact_prefixes():
    specs = []
    for index in range(16):
        supported = SUPPORTED if index % 2 else EVENT_FAMILIES
        specs.append({'master_episode_id': f'scope-{index:02d}', 'semantic_triggers': trigger_map(),
                      'supported_event_families': supported})
    schedules = build_balanced_master_schedules(specs)
    assert schedules == build_balanced_master_schedules(list(reversed(specs)))
    support_by_id = {spec['master_episode_id']: set(spec['supported_event_families']) for spec in specs}
    for schedule in schedules:
        validate_schedule(schedule)
        assert len(schedule.events) == 8
        assert {event.family.value for event in schedule.events} <= support_by_id[schedule.master_episode_id]
        for checkpoint in (0, 1, 2, 4):
            assert schedule.prefix(checkpoint, protocol='end_to_end') == schedule.events[:checkpoint]


@pytest.mark.parametrize('missing', ['TEMPORARY_NO_GO_APPEARS', 'TEMPORARY_NO_GO_CLEARS',
                                     'TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE', 'TOOL_OR_TARGET_AVAILABLE_AGAIN'])
def test_current_eight_event_template_does_not_invent_missing_pair_families(missing):
    with pytest.raises(ValueError, match='unsupported eight-event template families'):
        build_master_schedule('scope', semantic_triggers=trigger_map(),
                              supported_event_families=[family for family in SUPPORTED if family != missing])


def test_explicit_supported_alternative_needs_no_displacement_trigger():
    supported = [family for family in EVENT_FAMILIES if family != 'TARGET_OBJECT_DISPLACED']
    triggers = {key: value for key, value in trigger_map().items() if key in supported}
    schedule = build_master_schedule('scope', semantic_triggers=triggers, supported_event_families=supported)
    assert EventFamily.TARGET_OBJECT_DISPLACED not in {event.family for event in schedule.events}


def test_all_ten_support_preserves_exact_pre_correction_schedule_bytes():
    specs = [{'master_episode_id': f'test-{index:03d}', 'semantic_triggers': trigger_map()} for index in range(32)]
    schedules = build_balanced_master_schedules(specs)
    # Digest recorded from the unchanged scheduler before this correction.
    assert canonical_sha256([schedule.to_dict() for schedule in schedules]) == (
        '8d23c31e77060f052b9f1f2b03d10360651f5320dede3008f9f34176e16df4bc')
