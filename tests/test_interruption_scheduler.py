from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cope_benchmark.interruption_scheduler import (
    InterruptionScheduler,
    canonical_event_digest,
    validate_event_sequence,
)
from cope_benchmark.interruptions import (
    BenchmarkConstraintState,
    InterruptionEvent,
    InterruptionType,
)


@dataclass
class FakeContext:
    constraint_state: BenchmarkConstraintState = field(default_factory=BenchmarkConstraintState)
    xyz: dict[str, list[float]] = field(
        default_factory=lambda: {
            "target_joint0": [0.0, 0.0, 0.5],
            "receptacle_joint0": [0.1, 0.1, 0.5],
            "tool_joint0": [0.0, -0.1, 0.5],
        }
    )
    refresh_count: int = 0

    def move_free_joint_xy(self, joint, dx, dy):
        before = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        self.xyz[joint][0] += dx
        self.xyz[joint][1] += dy
        after = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        return {"joint": joint, "before_qpos": before, "after_qpos": after}

    def set_free_joint_xy(self, joint, x, y):
        before = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        self.xyz[joint][0:2] = [x, y]
        after = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        return {"joint": joint, "before_qpos": before, "after_qpos": after}

    def set_free_joint_xyz(self, joint, x, y, z):
        before = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        self.xyz[joint] = [x, y, z]
        after = [*self.xyz[joint], 1.0, 0.0, 0.0, 0.0]
        return {"joint": joint, "before_qpos": before, "after_qpos": after}

    def free_joint_xyz(self, joint):
        return tuple(self.xyz[joint])

    def refresh_observation(self):
        self.refresh_count += 1
        return {"refresh": self.refresh_count}, {
            "fresh_observation": True,
            "consumed_noop_env_step": False,
            "method": "fake_force_update",
        }


def _event(event_id, event_type, step, payload):
    return InterruptionEvent(
        event_id=event_id,
        event_type=event_type,
        trigger_policy_step=step,
        payload=payload,
    )


def test_scheduler_is_deterministic_and_events_do_not_consume_policy_steps() -> None:
    events = (
        _event(
            "e0",
            InterruptionType.TARGET_OBJECT_MOVED,
            2,
            {"joint": "target_joint0", "dx": 0.1, "dy": -0.05},
        ),
        _event(
            "e1",
            InterruptionType.USER_ADDS_GENTLE_PREFERENCE,
            4,
            {
                "preference_id": "gentle",
                "translation_ceiling": 0.03,
                "eef_speed_ceiling": 0.2,
            },
        ),
    )
    first = InterruptionScheduler(events)
    second = InterruptionScheduler(events)
    assert first.schedule_digest == second.schedule_digest == canonical_event_digest(events)
    context = FakeContext()
    assert first.apply_due(context, policy_step=1)[0] == []
    records, observation = first.apply_due(context, policy_step=2)
    assert observation == {"refresh": 1}
    assert records[0].policy_step_before == records[0].policy_step_after == 2
    assert records[0].policy_step_unchanged_by_event
    assert first.apply_due(context, policy_step=2)[0] == []
    records, _ = first.apply_due(context, policy_step=4)
    assert records[0].fresh_observation
    assert first.complete


def test_scheduler_rejects_disappearance_or_availability_without_preceding_event() -> None:
    with pytest.raises(ValueError, match="disappears before"):
        validate_event_sequence(
            (
                _event(
                    "e0",
                    InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS,
                    2,
                    {"zone_id": "z"},
                ),
            )
        )
    with pytest.raises(ValueError, match="without unavailability"):
        validate_event_sequence(
            (
                _event(
                    "e0",
                    InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN,
                    2,
                    {
                        "tool_joint": "tool_joint0",
                        "release_xyz": [0.0, 0.0, 0.5],
                        "accessible_xyz_bounds": [[-0.3, 0.3], [-0.3, 0.3], [0.4, 0.8]],
                    },
                ),
            )
        )


def test_all_seven_interruptions_mutate_world_or_constraint_state_with_fresh_observation() -> None:
    events = (
        _event(
            "e0",
            InterruptionType.TARGET_OBJECT_MOVED,
            1,
            {"joint": "target_joint0", "dx": 0.1, "dy": 0.0},
        ),
        _event(
            "e1",
            InterruptionType.GOAL_RECEPTACLE_MOVED,
            2,
            {"joint": "receptacle_joint0", "dx": 0.0, "dy": 0.08},
        ),
        _event(
            "e2",
            InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS,
            3,
            {
                "zone_id": "z",
                "minimum": [-0.1, -0.1, 0.4],
                "maximum": [0.1, 0.1, 0.8],
            },
        ),
        _event(
            "e3",
            InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS,
            4,
            {"zone_id": "z"},
        ),
        _event(
            "e4",
            InterruptionType.USER_ADDS_GENTLE_PREFERENCE,
            5,
            {
                "preference_id": "gentle",
                "translation_ceiling": 0.03,
                "eef_speed_ceiling": 0.2,
                "contact_impulse_proxy_ceiling": 0.1,
            },
        ),
        _event(
            "e5",
            InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE,
            6,
            {
                "tool_joint": "tool_joint0",
                "unavailable_xyz": [0.5, 0.5, 0.5],
                "accessible_xyz_bounds": [[-0.3, 0.3], [-0.3, 0.3], [0.4, 0.8]],
            },
        ),
        _event(
            "e6",
            InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN,
            7,
            {
                "tool_joint": "tool_joint0",
                "release_xyz": [-0.2, 0.2, 0.5],
                "accessible_xyz_bounds": [[-0.3, 0.3], [-0.3, 0.3], [0.4, 0.8]],
            },
        ),
    )
    scheduler = InterruptionScheduler(events)
    context = FakeContext()
    for step in range(1, 8):
        records, _ = scheduler.apply_due(context, policy_step=step)
        assert len(records) == 1
        assert records[0].fresh_observation
        assert records[0].observation_refresh["consumed_noop_env_step"] is False
    assert scheduler.complete
    assert context.refresh_count == 7
    assert "z" not in context.constraint_state.active_no_go_zones
    assert "z" in context.constraint_state.retired_no_go_zones
    assert context.constraint_state.tool_availability["tool_joint0"] is True
    assert context.xyz["tool_joint0"][:2] == [-0.2, 0.2]
