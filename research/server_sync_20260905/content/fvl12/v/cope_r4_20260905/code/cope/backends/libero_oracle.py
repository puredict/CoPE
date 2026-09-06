"""Privileged LIBERO Cartesian skills used only as a mechanism substrate.

The controller reads simulator geometry and therefore is not a learned-policy
baseline. It deliberately mirrors the already-qualified server-side oracle
skill interface so CoPE/FSR-PC comparisons differ only in state adaptation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

import numpy as np


@dataclass(frozen=True)
class OracleSkillConfig:
    translation_scale_m: float = 0.05
    position_tolerance_m: float = 0.008
    stable_steps: int = 3
    max_move_steps: int = 60
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


@dataclass
class PhaseRecord:
    phase: str
    steps: int
    final_error_m: float | None = None
    done: bool = False
    reward: float = 0.0


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReturnHeldResult:
    object_name: str
    success: bool
    failure_reason: str | None
    released: bool
    return_position_error_m: float
    total_steps: int
    phases: list[PhaseRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiberoOracleSkillController:
    """Closed-loop OSC_POSE pick/place with explicit object and region names."""

    def __init__(
        self,
        env: Any,
        observation: dict[str, Any],
        config: OracleSkillConfig | None = None,
        step_observer: Callable[[np.ndarray, int, dict[str, Any]], None] | None = None,
    ) -> None:
        self.env = env
        self.base_env = getattr(env, "env", env)
        self.observation = observation
        self.config = config or OracleSkillConfig()
        self.step_observer = step_observer
        self.total_steps = 0
        self.action_history: list[tuple[float, ...]] = []

    def position(self, state_name: str) -> np.ndarray:
        if state_name not in self.base_env.object_states_dict:
            raise KeyError(
                f"unknown LIBERO state {state_name!r}; "
                f"available={sorted(self.base_env.object_states_dict)}"
            )
        state = self.base_env.object_states_dict[state_name].get_geom_state()
        return np.asarray(state["pos"], dtype=float).copy()

    def _step(self, action: Sequence[float]) -> tuple[float, bool]:
        canonical = np.asarray(action, dtype=np.float64)
        self.action_history.append(tuple(float(value) for value in canonical))
        self.observation, reward, done, _ = self.env.step(canonical)
        self.total_steps += 1
        if self.step_observer is not None:
            self.step_observer(canonical.copy(), self.total_steps, self.observation)
        return float(reward), bool(done)

    def hold(self, phase: str, steps: int, gripper: float) -> PhaseRecord:
        action = np.zeros(7, dtype=float)
        action[6] = float(gripper)
        reward, done, executed = 0.0, False, 0
        for _ in range(steps):
            reward, done = self._step(action)
            executed += 1
            if done:
                break
        return PhaseRecord(phase, executed, done=done, reward=reward)

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
        stable, reward, done, executed = 0, 0.0, False, 0
        for _ in range(max_steps or cfg.max_move_steps):
            eef = np.asarray(self.observation["robot0_eef_pos"], dtype=float)
            delta = target - eef
            if float(np.linalg.norm(delta)) <= cfg.position_tolerance_m:
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
        error = float(
            np.linalg.norm(
                target - np.asarray(self.observation["robot0_eef_pos"], dtype=float)
            )
        )
        return PhaseRecord(phase, executed, error, done, reward)

    def is_grasping(self, object_name: str) -> bool:
        obj = self.base_env.objects_dict[object_name]
        return bool(
            self.base_env._check_grasp(self.base_env.robots[0].gripper, obj)
        )

    def in_region(self, object_name: str, target_region_name: str) -> bool:
        return bool(
            self.base_env._eval_predicate(
                ["in", str(object_name), str(target_region_name)]
            )
        )

    def warmup(self) -> PhaseRecord:
        return self.hold("warmup", self.config.warmup_steps, gripper=-1.0)

    def pick_object(self, object_name: str) -> HeldObjectCheckpoint:
        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_start = self.position(object_name)
        phases.append(
            self.move_to(
                "approach_object",
                object_start + np.array([0.0, 0.0, cfg.approach_height_m]),
                gripper=-1.0,
            )
        )
        phases.append(
            self.move_to(
                "descend_to_grasp",
                object_start + np.array([0.0, 0.0, cfg.grasp_offset_m]),
                gripper=-1.0,
            )
        )
        phases.append(self.hold("close_gripper", cfg.close_steps, gripper=1.0))
        grasp = self.is_grasping(object_name)
        if grasp:
            lift_target = np.asarray(
                self.observation["robot0_eef_pos"], dtype=float
            ).copy()
            lift_target[2] += cfg.lift_height_m
            phases.append(self.move_to("lift_object", lift_target, gripper=1.0))
        lift = float(self.position(object_name)[2] - object_start[2])
        retained = grasp and self.is_grasping(object_name) and lift >= cfg.minimum_lift_m
        reason = None
        if not grasp:
            reason = "grasp_not_acquired"
        elif not retained:
            reason = "object_not_retained_during_lift"
        return HeldObjectCheckpoint(
            object_name=object_name,
            object_start_position=tuple(float(v) for v in object_start),
            captured_eef_position=tuple(
                float(v) for v in self.observation["robot0_eef_pos"]
            ),
            success=bool(retained),
            failure_reason=reason,
            grasp_acquired=bool(grasp),
            object_lift_m=lift,
            total_steps=self.total_steps - start_steps,
            phases=phases,
        )

    def place_held(
        self, checkpoint: HeldObjectCheckpoint, target_region_name: str
    ) -> OracleSkillResult:
        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_name = checkpoint.object_name
        if not checkpoint.success or not self.is_grasping(object_name):
            return OracleSkillResult(
                object_name,
                target_region_name,
                False,
                "invalid_or_stale_held_checkpoint",
                checkpoint.grasp_acquired,
                checkpoint.object_lift_m,
                False,
                0,
                phases,
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
        # Geometric region membership while the gripper is still closed is not
        # a placement. Always release, retreat, and let the object settle before
        # evaluating the predicate.
        phases.append(self.hold("open_gripper", cfg.open_steps, gripper=-1.0))
        retreat = np.asarray(
            self.observation["robot0_eef_pos"], dtype=float
        ).copy()
        retreat[2] += cfg.retreat_height_m
        phases.append(self.move_to("retreat", retreat, gripper=-1.0))
        phases.append(self.hold("settle", cfg.settle_steps, gripper=-1.0))
        released = not self.is_grasping(object_name)
        predicate = self.in_region(object_name, target_region_name)
        success = bool(predicate and released)
        if not released:
            failure_reason = "object_still_attached_after_release"
        elif not predicate:
            failure_reason = "target_predicate_false_after_release"
        else:
            failure_reason = None
        return OracleSkillResult(
            object_name,
            target_region_name,
            bool(success),
            failure_reason,
            True,
            checkpoint.object_lift_m,
            bool(predicate),
            self.total_steps - start_steps,
            phases,
            released=bool(released),
        )

    def return_held_to_start(
        self, checkpoint: HeldObjectCheckpoint
    ) -> ReturnHeldResult:
        cfg = self.config
        phases: list[PhaseRecord] = []
        start_steps = self.total_steps
        object_name = checkpoint.object_name
        start = np.asarray(checkpoint.object_start_position, dtype=float)
        if not checkpoint.success or not self.is_grasping(object_name):
            return ReturnHeldResult(
                object_name,
                False,
                "invalid_or_stale_held_checkpoint",
                False,
                float("inf"),
                0,
                phases,
            )
        safe_z = max(
            cfg.transfer_height_m,
            float(self.observation["robot0_eef_pos"][2]),
            float(start[2] + cfg.approach_height_m),
        )
        phases.append(
            self.move_to(
                "return_above_start", [start[0], start[1], safe_z], gripper=1.0
            )
        )
        phases.append(
            self.move_to(
                "return_descend",
                start + np.array([0.0, 0.0, cfg.grasp_offset_m]),
                gripper=1.0,
            )
        )
        phases.append(self.hold("return_release", cfg.open_steps, gripper=-1.0))
        retreat = np.asarray(self.observation["robot0_eef_pos"], dtype=float).copy()
        retreat[2] += cfg.retreat_height_m
        phases.append(self.move_to("return_retreat", retreat, gripper=-1.0))
        phases.append(self.hold("return_settle", cfg.settle_steps, gripper=-1.0))
        error = float(np.linalg.norm(self.position(object_name) - start))
        released = not self.is_grasping(object_name)
        success = released and error <= 0.06
        return ReturnHeldResult(
            object_name,
            bool(success),
            None if success else "safe_return_verification_failed",
            bool(released),
            error,
            self.total_steps - start_steps,
            phases,
        )

    def pick_and_place(
        self, object_name: str, target_region_name: str
    ) -> OracleSkillResult:
        held = self.pick_object(object_name)
        return self.place_held(held, target_region_name)
