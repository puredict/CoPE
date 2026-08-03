"""Privileged, goal-conditioned LIBERO skills for pipeline qualification.

This controller intentionally uses simulator state for object and region
geometry.  It is an oracle execution substrate, not a learned-policy baseline.
Its purpose is to test whether high-level commitment edits can be executed
without conflating them with language-policy failures.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

import numpy as np


@dataclass(frozen=True)
class OracleSkillConfig:
    translation_scale_m: float = 0.05
    position_tolerance_m: float = 0.008
    stable_steps: int = 3
    max_move_steps: int = 40
    warmup_steps: int = 10
    approach_height_m: float = 0.16
    grasp_offset_m: float = 0.005
    close_steps: int = 20
    lift_height_m: float = 0.20
    transfer_height_m: float = 0.72
    release_offset_m: float = 0.10
    open_steps: int = 10
    retreat_height_m: float = 0.15
    settle_steps: int = 20
    minimum_lift_m: float = 0.08
    # Absolute world-frame XY offsets used for bounded grasp acquisition.
    # The default contains only the historical centered grasp and therefore
    # preserves the exact legacy action trace.  Robustness experiments must
    # opt into additional attempts explicitly.
    grasp_attempt_xy_offsets_m: tuple[tuple[float, float], ...] = ((0.0, 0.0),)

    def __post_init__(self) -> None:
        if not self.grasp_attempt_xy_offsets_m:
            raise ValueError("at least one grasp attempt offset is required")
        for offset in self.grasp_attempt_xy_offsets_m:
            if len(offset) != 2 or not all(np.isfinite(value) for value in offset):
                raise ValueError("grasp attempt offsets must be finite XY pairs")


@dataclass
class PhaseRecord:
    phase: str
    steps: int
    final_error_m: float | None = None
    done: bool = False
    reward: float = 0.0


@dataclass
class OracleSkillResult:
    object_name: str
    target_region_name: str
    success: bool
    failure_reason: str | None
    grasp_acquired: bool
    object_lift_m: float
    target_predicate: bool
    total_steps: int
    phases: list[PhaseRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HeldObjectCheckpoint:
    object_name: str
    object_start_position: tuple[float, float, float]
    captured_eef_position: tuple[float, float, float]
    success: bool
    failure_reason: str | None
    grasp_acquired: bool
    object_lift_m: float
    total_steps: int
    phases: list[PhaseRecord] = field(default_factory=list)


@dataclass
class ReturnHeldResult:
    object_name: str
    success: bool
    failure_reason: str | None
    released: bool
    return_position_error_m: float
    total_steps: int
    phases: list[PhaseRecord] = field(default_factory=list)


class LiberoOracleSkillController:
    """Closed-loop Cartesian pick-place controller with explicit goal symbols."""

    def __init__(
        self,
        env: Any,
        observation: dict[str, Any],
        config: OracleSkillConfig | None = None,
        step_observer: Callable[[np.ndarray, int], None] | None = None,
    ) -> None:
        self.env = env
        self.base_env = getattr(env, "env", env)
        self.observation = observation
        self.config = config or OracleSkillConfig()
        self.step_observer = step_observer
        self.total_steps = 0
        # Retain the exact low-level commands issued through env.step so
        # paired experimental arms can prove they share a prefix.  This is
        # evidence only: it is never read by the control policy.
        self.action_history: list[tuple[float, ...]] = []

    def position(self, state_name: str) -> np.ndarray:
        if state_name not in self.base_env.object_states_dict:
            available = sorted(self.base_env.object_states_dict)
            raise KeyError(f"unknown LIBERO state {state_name!r}; available={available}")
        state = self.base_env.object_states_dict[state_name].get_geom_state()
        return np.asarray(state["pos"], dtype=float).copy()

    def _step(self, action: Sequence[float]) -> tuple[float, bool]:
        canonical_action = np.asarray(action, dtype=np.float64)
        self.action_history.append(
            tuple(float(value) for value in canonical_action)
        )
        self.observation, reward, done, _ = self.env.step(canonical_action)
        self.total_steps += 1
        if self.step_observer is not None:
            self.step_observer(canonical_action.copy(), self.total_steps)
        return float(reward), bool(done)

    def action_prefix_sha256(self, step_count: int | None = None) -> str:
        """Hash the exact env.step action prefix using a stable encoding."""

        prefix = (
            self.action_history
            if step_count is None
            else self.action_history[:step_count]
        )
        actions = np.asarray(prefix, dtype="<f8")
        digest = hashlib.sha256()
        digest.update(str(actions.shape).encode("ascii"))
        digest.update(actions.tobytes(order="C"))
        return digest.hexdigest()

    def hold(self, phase: str, steps: int, gripper: float) -> PhaseRecord:
        reward = 0.0
        done = False
        executed = 0
        action = np.zeros(7, dtype=float)
        action[6] = float(gripper)
        for _ in range(steps):
            reward, done = self._step(action)
            executed += 1
            if done:
                break
        return PhaseRecord(phase=phase, steps=executed, done=done, reward=reward)

    def move_to(
        self,
        phase: str,
        target_position: Sequence[float],
        gripper: float,
        max_steps: int | None = None,
        translation_action_limit: float = 1.0,
    ) -> PhaseRecord:
        cfg = self.config
        target = np.asarray(target_position, dtype=float)
        if not 0.0 < translation_action_limit <= 1.0:
            raise ValueError("translation_action_limit must be in (0, 1]")
        stable = 0
        reward = 0.0
        done = False
        error = float("inf")
        executed = 0
        for _ in range(max_steps or cfg.max_move_steps):
            eef = np.asarray(self.observation["robot0_eef_pos"], dtype=float)
            delta = target - eef
            error = float(np.linalg.norm(delta))
            if error <= cfg.position_tolerance_m:
                stable += 1
            else:
                stable = 0
            if stable >= cfg.stable_steps:
                break
            action = np.zeros(7, dtype=float)
            action[:3] = np.clip(
                delta / cfg.translation_scale_m,
                -translation_action_limit,
                translation_action_limit,
            )
            action[6] = float(gripper)
            reward, done = self._step(action)
            executed += 1
            if done:
                break
        eef = np.asarray(self.observation["robot0_eef_pos"], dtype=float)
        error = float(np.linalg.norm(target - eef))
        return PhaseRecord(
            phase=phase,
            steps=executed,
            final_error_m=error,
            done=done,
            reward=reward,
        )

    def is_grasping(self, object_name: str) -> bool:
        obj = self.base_env.objects_dict[object_name]
        gripper = self.base_env.robots[0].gripper
        return bool(self.base_env._check_grasp(gripper, obj))

    def in_region(self, object_name: str, target_region_name: str) -> bool:
        return bool(
            self.base_env._eval_predicate(
                ["in", str(object_name), str(target_region_name)]
            )
        )

    def warmup(self) -> PhaseRecord:
        return self.hold("warmup", self.config.warmup_steps, gripper=-1.0)

    def acquire_grasp(
        self,
        object_name: str,
        object_start: np.ndarray,
    ) -> tuple[bool, list[PhaseRecord]]:
        """Try the frozen centered grasp, then optional bounded XY alternatives."""

        cfg = self.config
        phases: list[PhaseRecord] = []
        for attempt_index, (dx, dy) in enumerate(cfg.grasp_attempt_xy_offsets_m):
            if attempt_index:
                phases.append(
                    self.hold(
                        f"regrasp_{attempt_index}_open_gripper",
                        cfg.open_steps,
                        gripper=-1.0,
                    )
                )
            # A failed close can displace the object.  Every alternative is
            # relative to the current oracle geometry, not stale start state.
            object_now = object_start if attempt_index == 0 else self.position(object_name)
            offset = np.array([float(dx), float(dy), 0.0])
            prefix = "" if attempt_index == 0 else f"regrasp_{attempt_index}_"
            phases.append(
                self.move_to(
                    f"{prefix}approach_object",
                    object_now
                    + offset
                    + np.array([0.0, 0.0, cfg.approach_height_m]),
                    gripper=-1.0,
                )
            )
            phases.append(
                self.move_to(
                    f"{prefix}descend_to_grasp",
                    object_now
                    + offset
                    + np.array([0.0, 0.0, cfg.grasp_offset_m]),
                    gripper=-1.0,
                )
            )
            phases.append(
                self.hold(
                    f"{prefix}close_gripper", cfg.close_steps, gripper=1.0
                )
            )
            if self.is_grasping(object_name):
                return True, phases
        return False, phases

    def pick_object(self, object_name: str) -> HeldObjectCheckpoint:
        """Pick and lift an object, returning a resumable physical checkpoint."""

        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_start = self.position(object_name)
        grasp, grasp_phases = self.acquire_grasp(object_name, object_start)
        phases.extend(grasp_phases)
        if grasp:
            lift_target = np.asarray(
                self.observation["robot0_eef_pos"], dtype=float
            ).copy()
            lift_target[2] += cfg.lift_height_m
            phases.append(self.move_to("lift_object", lift_target, gripper=1.0))
        lift = float(self.position(object_name)[2] - object_start[2])
        retained = grasp and self.is_grasping(object_name) and lift >= cfg.minimum_lift_m
        eef = tuple(
            float(value) for value in self.observation["robot0_eef_pos"]
        )
        reason = None
        if not grasp:
            reason = "grasp_not_acquired"
        elif not retained:
            reason = "object_not_retained_during_lift"
        return HeldObjectCheckpoint(
            object_name=object_name,
            object_start_position=tuple(float(value) for value in object_start),
            captured_eef_position=eef,
            success=bool(retained),
            failure_reason=reason,
            grasp_acquired=bool(grasp),
            object_lift_m=lift,
            total_steps=self.total_steps - start_steps,
            phases=phases,
        )

    def place_held(
        self,
        checkpoint: HeldObjectCheckpoint,
        target_region_name: str,
    ) -> OracleSkillResult:
        """Continue a valid held-object checkpoint into a target region."""

        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_name = checkpoint.object_name
        if not checkpoint.success or not self.is_grasping(object_name):
            return OracleSkillResult(
                object_name=object_name,
                target_region_name=target_region_name,
                success=False,
                failure_reason="invalid_or_stale_held_checkpoint",
                grasp_acquired=checkpoint.grasp_acquired,
                object_lift_m=checkpoint.object_lift_m,
                target_predicate=False,
                total_steps=0,
                phases=phases,
            )
        region = self.position(target_region_name)
        transfer_z = max(
            cfg.transfer_height_m,
            float(self.observation["robot0_eef_pos"][2]),
            float(region[2] + cfg.release_offset_m + cfg.retreat_height_m),
        )
        phases.append(
            self.move_to(
                "transfer_above_target",
                [region[0], region[1], transfer_z],
                gripper=1.0,
            )
        )
        phases.append(
            self.move_to(
                "descend_to_release",
                [region[0], region[1], region[2] + cfg.release_offset_m],
                gripper=1.0,
            )
        )
        if self.in_region(object_name, target_region_name):
            return OracleSkillResult(
                object_name=object_name,
                target_region_name=target_region_name,
                success=True,
                failure_reason=None,
                grasp_acquired=True,
                object_lift_m=checkpoint.object_lift_m,
                target_predicate=True,
                total_steps=self.total_steps - start_steps,
                phases=phases,
            )
        phases.append(self.hold("open_gripper", cfg.open_steps, gripper=-1.0))
        retreat = np.asarray(
            self.observation["robot0_eef_pos"], dtype=float
        ).copy()
        retreat[2] += cfg.retreat_height_m
        phases.append(self.move_to("retreat", retreat, gripper=-1.0))
        phases.append(self.hold("settle", cfg.settle_steps, gripper=-1.0))
        target_predicate = self.in_region(object_name, target_region_name)
        return OracleSkillResult(
            object_name=object_name,
            target_region_name=target_region_name,
            success=target_predicate,
            failure_reason=None if target_predicate else "target_predicate_false",
            grasp_acquired=True,
            object_lift_m=checkpoint.object_lift_m,
            target_predicate=target_predicate,
            total_steps=self.total_steps - start_steps,
            phases=phases,
        )

    def return_held_to_start(
        self,
        checkpoint: HeldObjectCheckpoint,
    ) -> ReturnHeldResult:
        """Safely restore a no-longer-required held object near its start pose."""

        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_name = checkpoint.object_name
        object_start = np.asarray(checkpoint.object_start_position, dtype=float)
        if not checkpoint.success or not self.is_grasping(object_name):
            return ReturnHeldResult(
                object_name=object_name,
                success=False,
                failure_reason="invalid_or_stale_held_checkpoint",
                released=False,
                return_position_error_m=float("inf"),
                total_steps=0,
                phases=phases,
            )
        safe_z = max(
            cfg.transfer_height_m,
            float(self.observation["robot0_eef_pos"][2]),
            float(object_start[2] + cfg.approach_height_m),
        )
        phases.append(
            self.move_to(
                "return_above_start",
                [object_start[0], object_start[1], safe_z],
                gripper=1.0,
            )
        )
        phases.append(
            self.move_to(
                "return_descend",
                object_start + np.array([0.0, 0.0, cfg.grasp_offset_m]),
                gripper=1.0,
            )
        )
        phases.append(self.hold("return_release", cfg.open_steps, gripper=-1.0))
        retreat = np.asarray(
            self.observation["robot0_eef_pos"], dtype=float
        ).copy()
        retreat[2] += cfg.retreat_height_m
        phases.append(self.move_to("return_retreat", retreat, gripper=-1.0))
        phases.append(self.hold("return_settle", cfg.settle_steps, gripper=-1.0))
        final_position = self.position(object_name)
        position_error = float(np.linalg.norm(final_position - object_start))
        released = not self.is_grasping(object_name)
        success = released and position_error <= 0.06
        return ReturnHeldResult(
            object_name=object_name,
            success=success,
            failure_reason=None if success else "safe_return_verification_failed",
            released=released,
            return_position_error_m=position_error,
            total_steps=self.total_steps - start_steps,
            phases=phases,
        )

    def pick_and_place(
        self,
        object_name: str,
        target_region_name: str,
    ) -> OracleSkillResult:
        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_start = self.position(object_name)
        region = self.position(target_region_name)

        grasp, grasp_phases = self.acquire_grasp(object_name, object_start)
        phases.extend(grasp_phases)
        if not grasp:
            return OracleSkillResult(
                object_name=object_name,
                target_region_name=target_region_name,
                success=False,
                failure_reason="grasp_not_acquired",
                grasp_acquired=False,
                object_lift_m=float(self.position(object_name)[2] - object_start[2]),
                target_predicate=False,
                total_steps=self.total_steps - start_steps,
                phases=phases,
            )

        lift_target = np.asarray(
            self.observation["robot0_eef_pos"], dtype=float
        ).copy()
        lift_target[2] += cfg.lift_height_m
        phases.append(self.move_to("lift_object", lift_target, gripper=1.0))
        lift = float(self.position(object_name)[2] - object_start[2])
        if lift < cfg.minimum_lift_m or not self.is_grasping(object_name):
            return OracleSkillResult(
                object_name=object_name,
                target_region_name=target_region_name,
                success=False,
                failure_reason="object_not_retained_during_lift",
                grasp_acquired=True,
                object_lift_m=lift,
                target_predicate=False,
                total_steps=self.total_steps - start_steps,
                phases=phases,
            )

        transfer_z = max(
            cfg.transfer_height_m,
            float(self.observation["robot0_eef_pos"][2]),
            float(region[2] + cfg.release_offset_m + cfg.retreat_height_m),
        )
        phases.append(
            self.move_to(
                "transfer_above_target",
                [region[0], region[1], transfer_z],
                gripper=1.0,
            )
        )
        phases.append(
            self.move_to(
                "descend_to_release",
                [region[0], region[1], region[2] + cfg.release_offset_m],
                gripper=1.0,
            )
        )
        # Narrow insertion tasks may become successful while the object is
        # still grasped.  Releasing after the target predicate is established
        # can knock the object back out of the region.
        if self.in_region(object_name, target_region_name):
            return OracleSkillResult(
                object_name=object_name,
                target_region_name=target_region_name,
                success=True,
                failure_reason=None,
                grasp_acquired=grasp,
                object_lift_m=lift,
                target_predicate=True,
                total_steps=self.total_steps - start_steps,
                phases=phases,
            )
        phases.append(self.hold("open_gripper", cfg.open_steps, gripper=-1.0))

        retreat = np.asarray(
            self.observation["robot0_eef_pos"], dtype=float
        ).copy()
        retreat[2] += cfg.retreat_height_m
        phases.append(self.move_to("retreat", retreat, gripper=-1.0))
        phases.append(self.hold("settle", cfg.settle_steps, gripper=-1.0))

        target_predicate = self.in_region(object_name, target_region_name)
        return OracleSkillResult(
            object_name=object_name,
            target_region_name=target_region_name,
            success=target_predicate,
            failure_reason=None if target_predicate else "target_predicate_false",
            grasp_acquired=grasp,
            object_lift_m=lift,
            target_predicate=target_predicate,
            total_steps=self.total_steps - start_steps,
            phases=phases,
        )
