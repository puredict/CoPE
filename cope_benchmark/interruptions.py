from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


INTERRUPTION_LIBRARY_VERSION = "repeated_interruptions_v1"


class InterruptionType(str, Enum):
    TARGET_OBJECT_MOVED = "target_object_moved"
    GOAL_RECEPTACLE_MOVED = "goal_receptacle_moved"
    TEMPORARY_NO_GO_ZONE_APPEARS = "temporary_no_go_zone_appears"
    TEMPORARY_NO_GO_ZONE_DISAPPEARS = "temporary_no_go_zone_disappears"
    USER_ADDS_GENTLE_PREFERENCE = "user_adds_gentle_preference"
    TOOL_TEMPORARILY_UNAVAILABLE = "tool_temporarily_unavailable"
    TOOL_BECOMES_AVAILABLE_AGAIN = "tool_becomes_available_again"


@dataclass(frozen=True)
class AxisAlignedBox:
    """Closed axis-aligned world-space box used by the no-go scorer."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    frame: str = "world"

    def __post_init__(self) -> None:
        if self.frame != "world":
            raise ValueError("v1 no-go zones must use the world frame")
        if len(self.minimum) != 3 or len(self.maximum) != 3:
            raise ValueError("a no-go zone requires 3D minimum and maximum coordinates")
        if not all(math.isfinite(v) for v in (*self.minimum, *self.maximum)):
            raise ValueError("no-go coordinates must be finite")
        if any(lo >= hi for lo, hi in zip(self.minimum, self.maximum)):
            raise ValueError("each no-go maximum must be greater than its minimum")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AxisAlignedBox":
        return cls(
            minimum=tuple(float(v) for v in payload["minimum"]),
            maximum=tuple(float(v) for v in payload["maximum"]),
            frame=str(payload.get("frame", "world")),
        )

    def contains(self, point: Sequence[float]) -> bool:
        if len(point) < 3:
            raise ValueError("point must contain x, y, z")
        return all(lo <= float(v) <= hi for v, lo, hi in zip(point[:3], self.minimum, self.maximum))

    def segment_intersects(self, start: Sequence[float], end: Sequence[float]) -> bool:
        """Liang-Barsky slab test, including boundary contact as a violation."""

        if len(start) < 3 or len(end) < 3:
            raise ValueError("segment endpoints must contain x, y, z")
        t_min, t_max = 0.0, 1.0
        for idx, (lo, hi) in enumerate(zip(self.minimum, self.maximum)):
            origin = float(start[idx])
            delta = float(end[idx]) - origin
            if abs(delta) < 1e-12:
                if origin < lo or origin > hi:
                    return False
                continue
            entry = (lo - origin) / delta
            exit_ = (hi - origin) / delta
            if entry > exit_:
                entry, exit_ = exit_, entry
            t_min = max(t_min, entry)
            t_max = min(t_max, exit_)
            if t_min > t_max:
                return False
        return True


@dataclass(frozen=True)
class InterruptionEvent:
    event_id: str
    event_type: InterruptionType
    trigger_policy_step: int
    payload: dict[str, Any]
    trigger_predicate: dict[str, Any] = field(default_factory=lambda: {"kind": "policy_step_gte"})
    source: str = "preregistered_manifest"
    library_version: str = INTERRUPTION_LIBRARY_VERSION

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if self.trigger_policy_step < 0:
            raise ValueError("trigger_policy_step must be >= 0")
        if self.source != "preregistered_manifest":
            raise ValueError("formal schedules must come from the preregistered manifest")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["event_type"] = self.event_type.value
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InterruptionEvent":
        return cls(
            event_id=str(value["event_id"]),
            event_type=InterruptionType(str(value["event_type"])),
            trigger_policy_step=int(value["trigger_policy_step"]),
            trigger_predicate=dict(value.get("trigger_predicate", {"kind": "policy_step_gte"})),
            payload=dict(value["payload"]),
            source=str(value.get("source", "preregistered_manifest")),
            library_version=str(value.get("library_version", INTERRUPTION_LIBRARY_VERSION)),
        )


@dataclass
class BenchmarkConstraintState:
    active_no_go_zones: dict[str, AxisAlignedBox] = field(default_factory=dict)
    retired_no_go_zones: dict[str, AxisAlignedBox] = field(default_factory=dict)
    preferences: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_availability: dict[str, bool] = field(default_factory=dict)
    event_versions: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_no_go_zones": {
                key: asdict(value) for key, value in sorted(self.active_no_go_zones.items())
            },
            "retired_no_go_zones": {
                key: asdict(value) for key, value in sorted(self.retired_no_go_zones.items())
            },
            "preferences": {key: dict(value) for key, value in sorted(self.preferences.items())},
            "tool_availability": dict(sorted(self.tool_availability.items())),
            "event_versions": dict(sorted(self.event_versions.items())),
        }


class InterruptionContext(Protocol):
    """Minimal simulator bridge required by the versioned interruption library."""

    constraint_state: BenchmarkConstraintState

    def move_free_joint_xy(self, joint: str, dx: float, dy: float) -> dict[str, Any]: ...

    def set_free_joint_xy(self, joint: str, x: float, y: float) -> dict[str, Any]: ...

    def set_free_joint_xyz(self, joint: str, x: float, y: float, z: float) -> dict[str, Any]: ...

    def free_joint_xyz(self, joint: str) -> tuple[float, float, float]: ...

    def refresh_observation(self) -> tuple[dict[str, Any], dict[str, Any]]: ...


@dataclass(frozen=True)
class EventApplication:
    event_id: str
    event_type: str
    event_source: str
    payload: dict[str, Any]
    simulator_mutation: dict[str, Any]
    constraint_state_before: dict[str, Any]
    constraint_state_after: dict[str, Any]
    fresh_observation: bool
    observation_refresh: dict[str, Any]
    affected_slots: tuple[str, ...]
    policy_step_before: int
    policy_step_after: int
    policy_step_unchanged_by_event: bool
    invalid_restore: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_keys(payload: Mapping[str, Any], *keys: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ValueError(f"event payload is missing required keys: {missing}")


def _check_delta(record: Mapping[str, Any], dx: float, dy: float, tolerance: float = 1e-7) -> None:
    before = record["before_qpos"]
    after = record["after_qpos"]
    if abs((float(after[0]) - float(before[0])) - dx) > tolerance:
        raise RuntimeError("simulator x displacement differs from manifest payload")
    if abs((float(after[1]) - float(before[1])) - dy) > tolerance:
        raise RuntimeError("simulator y displacement differs from manifest payload")


def apply_interruption(
    context: InterruptionContext,
    event: InterruptionEvent,
    *,
    policy_step: int,
) -> tuple[EventApplication, dict[str, Any]]:
    """Apply an event without stepping the policy or simulator controller.

    Direct MuJoCo state edits are followed by ``sim.forward`` in the context
    implementation.  Every event, including task-constraint-only events,
    forces a fresh observation before policy inference resumes.
    """

    if event.library_version != INTERRUPTION_LIBRARY_VERSION:
        raise ValueError(
            f"event uses {event.library_version!r}; expected {INTERRUPTION_LIBRARY_VERSION!r}"
        )
    payload = event.payload
    before = context.constraint_state.snapshot()
    mutation: dict[str, Any] = {"kind": "constraint_only"}
    affected: list[str] = []
    invalid_restore = False

    if event.event_type in {
        InterruptionType.TARGET_OBJECT_MOVED,
        InterruptionType.GOAL_RECEPTACLE_MOVED,
    }:
        _require_keys(payload, "joint", "dx", "dy")
        joint = str(payload["joint"])
        dx, dy = float(payload["dx"]), float(payload["dy"])
        mutation = context.move_free_joint_xy(joint, dx, dy)
        _check_delta(mutation, dx, dy)
        role = "target_object" if event.event_type == InterruptionType.TARGET_OBJECT_MOVED else "goal_receptacle"
        affected.extend((f"world:{joint}:pose", f"task:{role}:reachable"))

    elif event.event_type == InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS:
        _require_keys(payload, "zone_id", "minimum", "maximum")
        zone_id = str(payload["zone_id"])
        if zone_id in context.constraint_state.active_no_go_zones:
            raise ValueError(f"no-go zone {zone_id!r} is already active")
        zone = AxisAlignedBox.from_payload(payload)
        context.constraint_state.active_no_go_zones[zone_id] = zone
        context.constraint_state.event_versions[f"no_go:{zone_id}"] = (
            context.constraint_state.event_versions.get(f"no_go:{zone_id}", 0) + 1
        )
        mutation = {"kind": "constraint_activation", "zone_id": zone_id, "geometry": asdict(zone)}
        affected.append(f"constraint:no_go:{zone_id}")

    elif event.event_type == InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS:
        _require_keys(payload, "zone_id")
        zone_id = str(payload["zone_id"])
        if zone_id not in context.constraint_state.active_no_go_zones:
            raise ValueError(f"cannot retire inactive no-go zone {zone_id!r}")
        zone = context.constraint_state.active_no_go_zones.pop(zone_id)
        context.constraint_state.retired_no_go_zones[zone_id] = zone
        context.constraint_state.event_versions[f"no_go:{zone_id}"] = (
            context.constraint_state.event_versions.get(f"no_go:{zone_id}", 0) + 1
        )
        mutation = {"kind": "constraint_retirement", "zone_id": zone_id, "geometry": asdict(zone)}
        affected.append(f"constraint:no_go:{zone_id}")

    elif event.event_type == InterruptionType.USER_ADDS_GENTLE_PREFERENCE:
        _require_keys(payload, "preference_id", "translation_ceiling", "eef_speed_ceiling")
        preference_id = str(payload["preference_id"])
        if preference_id in context.constraint_state.preferences:
            raise ValueError(f"preference {preference_id!r} already exists")
        preference = {
            "kind": "handle_gently",
            "translation_ceiling": float(payload["translation_ceiling"]),
            "eef_speed_ceiling": float(payload["eef_speed_ceiling"]),
            "contact_impulse_proxy_ceiling": float(
                payload.get("contact_impulse_proxy_ceiling", 0.12)
            ),
            "priority": str(payload.get("priority", "user_preference")),
            "source": "user_event",
            "mode": "active",
            "lineage": [event.event_id],
        }
        if min(
            preference["translation_ceiling"],
            preference["eef_speed_ceiling"],
            preference["contact_impulse_proxy_ceiling"],
        ) <= 0:
            raise ValueError("gentle-preference ceilings must be positive")
        context.constraint_state.preferences[preference_id] = preference
        context.constraint_state.event_versions[f"preference:{preference_id}"] = 1
        mutation = {"kind": "preference_activation", "preference": dict(preference)}
        affected.append(f"constraint:preference:{preference_id}")

    elif event.event_type == InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE:
        _require_keys(payload, "tool_joint", "unavailable_xyz", "accessible_xyz_bounds")
        joint = str(payload["tool_joint"])
        if context.constraint_state.tool_availability.get(joint) is False:
            raise ValueError(f"tool {joint!r} is already unavailable")
        old_xyz = context.free_joint_xyz(joint)
        unavailable_xyz = payload["unavailable_xyz"]
        mutation = context.set_free_joint_xyz(
            joint,
            float(unavailable_xyz[0]),
            float(unavailable_xyz[1]),
            float(unavailable_xyz[2]),
        )
        bounds = payload["accessible_xyz_bounds"]
        new_xyz = context.free_joint_xyz(joint)
        inside = all(
            float(axis_bounds[0]) <= coordinate <= float(axis_bounds[1])
            for coordinate, axis_bounds in zip(new_xyz, bounds)
        )
        if inside:
            raise RuntimeError("tool unavailability injection left the object in the accessible volume")
        mutation["pre_unavailability_xyz_for_audit_only"] = list(old_xyz)
        mutation["availability_predicate"] = {"inside_accessible_xyz_bounds": False}
        context.constraint_state.tool_availability[joint] = False
        context.constraint_state.event_versions[f"availability:{joint}"] = (
            context.constraint_state.event_versions.get(f"availability:{joint}", 0) + 1
        )
        affected.extend((f"world:{joint}:pose", f"constraint:availability:{joint}"))

    elif event.event_type == InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN:
        _require_keys(payload, "tool_joint", "release_xyz", "accessible_xyz_bounds")
        joint = str(payload["tool_joint"])
        if context.constraint_state.tool_availability.get(joint) is not False:
            raise ValueError(f"tool {joint!r} did not have a preceding unavailable event")
        # This is deliberately a release to a preregistered location, not a
        # snapshot restore.  Restoring a pre-event pose could roll back task
        # progress and would make the benchmark intervention method-dependent.
        release_xyz = payload["release_xyz"]
        mutation = context.set_free_joint_xyz(
            joint,
            float(release_xyz[0]),
            float(release_xyz[1]),
            float(release_xyz[2]),
        )
        bounds = payload["accessible_xyz_bounds"]
        new_xyz = context.free_joint_xyz(joint)
        inside = all(
            float(axis_bounds[0]) <= coordinate <= float(axis_bounds[1])
            for coordinate, axis_bounds in zip(new_xyz, bounds)
        )
        if not inside:
            raise RuntimeError("tool availability injection did not place the object in the accessible volume")
        mutation["availability_predicate"] = {"inside_accessible_xyz_bounds": True}
        mutation["release_semantics"] = "preregistered_location_not_snapshot_restore"
        context.constraint_state.tool_availability[joint] = True
        context.constraint_state.event_versions[f"availability:{joint}"] = (
            context.constraint_state.event_versions.get(f"availability:{joint}", 0) + 1
        )
        affected.extend((f"world:{joint}:pose", f"constraint:availability:{joint}"))

    else:  # pragma: no cover - exhaustive enum guard
        raise ValueError(f"unsupported interruption type {event.event_type!r}")

    observation, refresh = context.refresh_observation()
    fresh = bool(refresh.get("fresh_observation", False))
    if not fresh or bool(refresh.get("consumed_noop_env_step", True)):
        raise RuntimeError("event refresh must be fresh and consume no no-op environment step")
    after = context.constraint_state.snapshot()
    record = EventApplication(
        event_id=event.event_id,
        event_type=event.event_type.value,
        event_source=event.source,
        payload=dict(payload),
        simulator_mutation=mutation,
        constraint_state_before=before,
        constraint_state_after=after,
        fresh_observation=True,
        observation_refresh=dict(refresh),
        affected_slots=tuple(affected),
        policy_step_before=int(policy_step),
        policy_step_after=int(policy_step),
        policy_step_unchanged_by_event=True,
        invalid_restore=invalid_restore,
    )
    return record, observation


class LiberoInterruptionContext:
    """Thin bridge over the repository's audited LIBERO helpers."""

    def __init__(self, env: Any, fallback_observation: Any = None):
        self.env = env
        self.fallback_observation = fallback_observation
        self.constraint_state = BenchmarkConstraintState()

    def move_free_joint_xy(self, joint: str, dx: float, dy: float) -> dict[str, Any]:
        from libero_experiment_core import move_free_joint_xy

        return move_free_joint_xy(self.env, joint, dx, dy)

    def _joint(self, joint: str) -> tuple[Any, int]:
        from libero_experiment_core import validate_free_joint

        sim, _, qpos_addr = validate_free_joint(self.env, joint)
        return sim, qpos_addr

    def set_free_joint_xy(self, joint: str, x: float, y: float) -> dict[str, Any]:
        sim, qpos_addr = self._joint(joint)
        before = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
        sim.data.qpos[qpos_addr] = float(x)
        sim.data.qpos[qpos_addr + 1] = float(y)
        sim.forward()
        after = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
        return {
            "joint": joint,
            "before_qpos": before.tolist(),
            "after_qpos": after.tolist(),
            "operation": "set_xy_and_sim_forward",
        }

    def set_free_joint_xyz(self, joint: str, x: float, y: float, z: float) -> dict[str, Any]:
        sim, qpos_addr = self._joint(joint)
        before = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
        sim.data.qpos[qpos_addr] = float(x)
        sim.data.qpos[qpos_addr + 1] = float(y)
        sim.data.qpos[qpos_addr + 2] = float(z)
        sim.forward()
        after = sim.data.qpos[qpos_addr : qpos_addr + 7].copy()
        return {
            "joint": joint,
            "before_qpos": before.tolist(),
            "after_qpos": after.tolist(),
            "operation": "set_xyz_and_sim_forward",
        }

    def free_joint_xyz(self, joint: str) -> tuple[float, float, float]:
        sim, qpos_addr = self._joint(joint)
        return tuple(float(v) for v in sim.data.qpos[qpos_addr : qpos_addr + 3])

    def refresh_observation(self) -> tuple[dict[str, Any], dict[str, Any]]:
        from libero_experiment_core import refresh_observation_after_sim_change

        observation, meta = refresh_observation_after_sim_change(self.env, self.fallback_observation)
        normalized = dict(meta)
        normalized["fresh_observation"] = True
        normalized.setdefault("consumed_noop_env_step", False)
        return observation, normalized
