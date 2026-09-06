"""LIBERO/robosuite/MuJoCo backend with real state-isolated rollouts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from rekep_repair.execution.action import clip_action
from rekep_repair.execution.context import ExecutionContext
from rekep_repair.synthetic.dynamics import Obstacle, SceneConfig

from .base import BackendCheckpoint, BackendUnavailable, SimulatorRepairBackend
from .libero_oracle import (
    HeldObjectCheckpoint,
    LiberoOracleSkillController,
    OracleSkillConfig,
)


_ABSENT_OBSTACLE = Obstacle(
    p_start=np.array([9.0, 9.0]),
    p_end=np.array([9.0, 9.0]),
    radius=0.01,
    t_enter=0,
    t_exit=0,
)


class LiberoMujocoBackend(SimulatorRepairBackend):
    """Real simulator adapter; never falls back to Synthetic2D."""

    backend_name = "libero_mujoco"

    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.config_path: Path | None = None
        self.package_root: Path | None = None
        self.env = None
        self.obs: Dict[str, Any] | None = None
        self.controller: LiberoOracleSkillController | None = None
        self.held_checkpoint: HeldObjectCheckpoint | None = None
        self.seed = 0
        self.step_count = 0
        self.current_object: str | None = None
        self.current_target: str | None = None
        self.current_goal_id: str | None = None
        self.frames: list[np.ndarray] = []
        self.contact_records: list[Dict[str, Any]] = []
        self.simulator_log: list[str] = []
        self.cancelled_goal_ids: set[str] = set()
        self.unavailable_targets: set[str] = set()
        self.target_restore_qpos: Dict[str, np.ndarray] = {}
        self.initial_target_qpos: Dict[str, np.ndarray] = {}
        self._collision_detected = False
        self._checkpoint_counter = 0
        self._initial_object_positions: Dict[str, np.ndarray] = {}
        self._object_map: Dict[str, str] = {}
        self._target_region_map: Dict[str, str] = {}
        self._target_object_map: Dict[str, str] = {}
        self.cfg = SceneConfig(
            horizon=900,
            p_init=np.zeros(2),
            p_goal=np.zeros(2),
            theta_pour=0.0,
            theta_hold=0.0,
            d_safe=0.08,
            d_react=0.12,
            v_max=0.03,
            w_max=0.10,
            ws_lo=np.array([-0.35, -0.50]),
            ws_hi=np.array([0.35, 0.50]),
            obstacle=_ABSENT_OBSTACLE,
        )

    # ------------------------------------------------------------------ setup
    def initialize(self, config: str | Path | Mapping[str, Any]) -> Dict[str, Any]:
        if isinstance(config, Mapping):
            raw = copy.deepcopy(dict(config))
            config_path = None
        else:
            config_path = Path(config).expanduser().resolve()
            if not config_path.is_file():
                raise BackendUnavailable(f"backend config not found: {config_path}")
            try:
                import yaml
            except Exception as exc:  # pragma: no cover - server dependency
                raise BackendUnavailable("PyYAML is required by libero_mujoco") from exc
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if raw.get("backend") != self.backend_name:
            raise BackendUnavailable(
                f"config backend={raw.get('backend')!r}, expected {self.backend_name!r}"
            )
        try:
            from libero.libero.envs import OffScreenRenderEnv  # noqa: F401
            import mujoco
            import robosuite
        except Exception as exc:
            raise BackendUnavailable(
                "LIBERO/robosuite/MuJoCo imports failed; run through the documented "
                "server environment instead of using Synthetic2D"
            ) from exc

        self.config = raw
        self.config_path = config_path
        self.package_root = (
            config_path.parent.parent if config_path is not None else Path.cwd()
        )
        task = raw["task"]
        self._object_map = dict(task["abstract_objects"])
        self._target_region_map = dict(task["abstract_targets"])
        self._target_object_map = dict(task["target_objects"])
        limits = raw.get("limits", {})
        self.cfg.horizon = int(limits.get("horizon_steps", 900))
        return {
            "backend": self.backend_name,
            "simulator": "LIBERO/robosuite/MuJoCo",
            "mujoco_version": getattr(mujoco, "__version__", "unknown"),
            "robosuite_version": getattr(robosuite, "__version__", "unknown"),
            "bddl_file": str(self._bddl_path()),
            "controller": "OSC_POSE via privileged geometry oracle",
            "learned_policy_used": False,
            "mujoco_gl": os.environ.get("MUJOCO_GL", "unset"),
        }

    def _bddl_path(self) -> Path:
        if self.package_root is None:
            raise BackendUnavailable("initialize() must be called first")
        value = Path(self.config["task"]["bddl_file"])
        path = value if value.is_absolute() else self.package_root / value
        path = path.resolve()
        if not path.is_file():
            raise BackendUnavailable(f"BDDL task file not found: {path}")
        return path

    def reset(self, seed: int) -> Dict[str, Any]:
        from libero.libero.envs import OffScreenRenderEnv

        if not self.config:
            raise BackendUnavailable("initialize() must be called before reset()")
        if self.env is not None:
            self.env.close()
        render = self.config.get("render", {})
        self.env = OffScreenRenderEnv(
            bddl_file_name=str(self._bddl_path()),
            camera_names=[render.get("camera", "agentview"), "robot0_eye_in_hand"],
            camera_heights=int(render.get("height", 128)),
            camera_widths=int(render.get("width", 128)),
            horizon=int(self.config.get("limits", {}).get("horizon_steps", 900)),
            ignore_done=True,
        )
        self.seed = int(seed)
        self.env.seed(self.seed)
        self.obs = self.env.reset()
        self.controller = LiberoOracleSkillController(
            self.env,
            self.obs,
            OracleSkillConfig(
                max_move_steps=int(
                    self.config.get("limits", {}).get("max_move_steps", 60)
                ),
                settle_steps=int(
                    self.config.get("limits", {}).get("settle_steps", 40)
                ),
            ),
            step_observer=self._after_oracle_step,
        )
        self.held_checkpoint = None
        self.step_count = 0
        self.current_object = None
        self.current_target = None
        self.current_goal_id = None
        self.frames = []
        self.contact_records = []
        self.simulator_log = []
        self.cancelled_goal_ids.clear()
        self.unavailable_targets.clear()
        self.target_restore_qpos.clear()
        self.initial_target_qpos = {
            target: self._free_joint_qpos(obj).copy()
            for target, obj in self._target_object_map.items()
        }
        self._initial_object_positions = {
            abstract: self.controller.position(real).copy()
            for abstract, real in self._object_map.items()
        }
        self._collision_detected = False
        self._append_frame(self.obs)
        warmup = self.controller.warmup()
        self.step_count = self.controller.total_steps
        self._log("reset", seed=self.seed, warmup_steps=warmup.steps)
        return {
            "backend": self.backend_name,
            "seed": self.seed,
            "language": self.env.language_instruction,
            "objects": sorted(self.env.env.objects_dict),
            "regions": sorted(
                k for k in self.env.env.object_states_dict if "contain_region" in k
            ),
            "state_hash": self.state_hash(),
            "warmup_steps": warmup.steps,
        }

    # ------------------------------------------------------------------ leg
    def begin_leg(self, goal: Mapping[str, Any]) -> Dict[str, Any]:
        self._require_env()
        abstract_object = str(goal["object"])
        target = str(goal["target"])
        if abstract_object not in self._object_map:
            raise KeyError(f"unknown abstract object {abstract_object!r}")
        if target not in self._target_region_map:
            raise KeyError(f"unknown abstract target {target!r}")
        self.current_object = abstract_object
        self.current_target = target
        self.current_goal_id = str(goal.get("id", f"g_{abstract_object}"))
        self.held_checkpoint = None
        eef = np.asarray(self.obs["robot0_eef_pos"], dtype=float)
        self.cfg.p_init = eef[:2].copy()
        self.cfg.p_goal = self._target_position(target)[:2].copy()
        self._log(
            "begin_leg",
            goal_id=self.current_goal_id,
            object=abstract_object,
            target=target,
        )
        return {
            "goal_id": self.current_goal_id,
            "object": abstract_object,
            "sim_object": self._real_object(abstract_object),
            "target": target,
            "sim_target_region": self._target_region(target),
        }

    def pick_current_object(self) -> Dict[str, Any]:
        self._require_leg()
        assert self.controller is not None
        held = self.controller.pick_object(self._real_object(self.current_object))
        self.held_checkpoint = held
        self.step_count = self.controller.total_steps
        row = held.to_dict()
        self._log("pick_current_object", **row)
        return row

    def place_current_object(self) -> Dict[str, Any]:
        self._require_leg()
        assert self.controller is not None
        if self.current_target in self.unavailable_targets:
            row = {
                "success": False,
                "failure_reason": "target_unavailable",
                "object_name": self._real_object(self.current_object),
                "target_region_name": self._target_region(self.current_target),
                "total_steps": 0,
            }
            self._log("place_current_object", **row)
            return row
        if self.held_checkpoint is None:
            row = {
                "success": False,
                "failure_reason": "no_held_checkpoint",
                "total_steps": 0,
            }
        else:
            result = self.controller.place_held(
                self.held_checkpoint, self._target_region(self.current_target)
            )
            row = result.to_dict()
        self.step_count = self.controller.total_steps
        self._log("place_current_object", **row)
        return row

    def return_current_object(self) -> Dict[str, Any]:
        self._require_leg()
        assert self.controller is not None
        if self.held_checkpoint is None:
            row = {"success": True, "released": True, "reason": "nothing_held"}
        else:
            row = self.controller.return_held_to_start(self.held_checkpoint).to_dict()
        self.step_count = self.controller.total_steps
        self._log("return_current_object", **row)
        return row

    def debug_cartesian_move(
        self, label: str, target_xyz: Sequence[float], max_steps: int = 30
    ) -> Dict[str, Any]:
        """Preflight-only real OSC move used to exercise rejection gates."""

        self._require_leg()
        assert self.controller is not None
        attached = self.attachment_status()["attached"]
        record = self.controller.move_to(
            label,
            target_xyz,
            gripper=1.0 if attached else -1.0,
            max_steps=int(max_steps),
        )
        self.step_count = self.controller.total_steps
        return asdict(record)

    def debug_place_object_xyz(
        self, abstract_object: str, xyz: Sequence[float]
    ) -> Dict[str, Any]:
        """Preflight-only adversarial world edit inside a candidate branch."""

        real = self._real_object(abstract_object)
        before = self._free_joint_qpos(real)
        after = before.copy()
        after[:3] = np.asarray(xyz, dtype=float)[:3]
        self._set_free_joint_qpos(real, after)
        realized = self._free_joint_qpos(real)
        return {
            "object": abstract_object,
            "sim_object": real,
            "before_qpos": before.tolist(),
            "after_qpos": realized.tolist(),
            "world_changed": not np.allclose(before, realized),
        }

    def debug_place_object_on_robot_geom(
        self,
        abstract_object: str,
        geom_name: str = "robot0_link6_collision",
    ) -> Dict[str, Any]:
        """Place a protected body at a named robot collision geometry."""

        self._require_env()
        geom_id = self.env.sim.model.geom_name2id(geom_name)
        xyz = np.asarray(self.env.sim.data.geom_xpos[geom_id], dtype=float).copy()
        row = self.debug_place_object_xyz(abstract_object, xyz)
        # Observe contacts immediately after the state edit and before the
        # solver can separate interpenetrating bodies on the first control step.
        contact_start = len(self.contact_records)
        self._record_contacts(np.zeros(7, dtype=float))
        row.update(
            {
                "robot_geom": geom_name,
                "robot_geom_xyz": xyz.tolist(),
                "mujoco_ncon_after_edit": int(self.env.sim.data.ncon),
                "contacts_after_edit": copy.deepcopy(
                    self.contact_records[contact_start:]
                ),
            }
        )
        return row

    # ------------------------------------------------------------------ repair API
    def observe(self) -> ExecutionContext:
        self._require_leg()
        assert self.controller is not None and self.obs is not None
        eef = np.asarray(self.obs["robot0_eef_pos"], dtype=float)
        real_object = self._real_object(self.current_object)
        grasped = self.controller.is_grasping(real_object)
        object_pos = self.controller.position(real_object)
        goal = self._target_position(self.current_target)[:2]
        nominal = self.cfg.p_goal
        object_poses = {
            abstract: self.controller.position(real).tolist()
            for abstract, real in self._object_map.items()
        }
        target_poses = {
            abstract: self._target_position(abstract).tolist()
            for abstract in self._target_region_map
        }
        qvel = self._free_joint_qvel(real_object)
        linear_speed = float(np.linalg.norm(qvel[:3]))
        angular_speed = float(np.linalg.norm(qvel[3:]))
        stability_cfg = self.config.get("metrics", {}).get("stability", {})
        object_stable = bool(
            linear_speed <= float(stability_cfg.get("max_linear_speed_m_s", 0.05))
            and angular_speed
            <= float(stability_cfg.get("max_angular_speed_rad_s", 1.0))
        )
        collision = self.collision_status()
        return ExecutionContext(
            t=self.step_count,
            state=np.array([eef[0], eef[1], 0.0], dtype=float),
            obstacle_pos=None,
            obstacle_radius=0.0,
            clearance=float("inf"),
            task_goal=goal.copy(),
            nominal_goal=nominal.copy(),
            target_displacement=float(np.linalg.norm(goal - nominal)),
            object_pos=object_pos[:2].copy(),
            object_grasped=bool(grasped),
            slipped=not bool(grasped),
            reacquire_pos=object_pos[:2].copy(),
            attachments={"object": "grasped" if grasped else "released"},
            extra={
                "robot_state": {
                    "eef_xyz": eef.tolist(),
                    "eef_quat": np.asarray(
                        self.obs.get("robot0_eef_quat", [0.0, 0.0, 0.0, 1.0]),
                        dtype=float,
                    ).tolist(),
                },
                "eef_xyz": eef.tolist(),
                "active_stage": "nominal_leg",
                "active_goal_id": self.current_goal_id,
                "object": self.current_object,
                "target": self.current_target,
                "object_poses": object_poses,
                "target_poses": target_poses,
                "attachment_state": {
                    "attached": bool(grasped),
                    "object": self.current_object,
                },
                "stability": {
                    "object_stable": object_stable,
                    "linear_speed_m_s": linear_speed,
                    "angular_speed_rad_s": angular_speed,
                },
                "collision_clearance": {
                    **collision,
                    "clearance_m": float("inf"),
                },
                "current_task_goal": goal.tolist(),
                "continuation_handoff_fields": {
                    "state": [float(eef[0]), float(eef[1]), 0.0],
                    "attachment": "grasped" if grasped else "released",
                },
                "restore_contract_fields": {
                    "state": [float(eef[0]), float(eef[1]), 0.0],
                    "task_goal": goal.tolist(),
                    "target_displacement": float(np.linalg.norm(goal - nominal)),
                },
                "state_hash": self.state_hash(),
            },
        )

    def step(self, action: Sequence[float]) -> Dict[str, Any]:
        self._require_leg()
        assert self.controller is not None and self.obs is not None
        desired = np.asarray(action, dtype=float)
        if desired.shape != (3,):
            raise ValueError(f"repair action must have shape (3,), got {desired.shape}")
        clipped = clip_action(desired, self.cfg.v_max, self.cfg.w_max)
        low = np.zeros(7, dtype=float)
        scale = self.controller.config.translation_scale_m
        low[:2] = np.clip(clipped[:2] / scale, -1.0, 1.0)
        real_object = self._real_object(self.current_object)
        low[6] = 1.0 if self.controller.is_grasping(real_object) else -1.0
        reward, done = self.controller._step(low)
        self.obs = self.controller.observation
        self.step_count = self.controller.total_steps
        collision = self.collision_status()
        return {
            "step": self.step_count,
            "desired_action": desired.tolist(),
            "clipped_action": clipped.tolist(),
            "env_action": low.tolist(),
            "reward": reward,
            "done": done,
            "collision": collision["collision"],
            "unsafe_contact_count": collision["unsafe_contact_count"],
        }

    # ------------------------------------------------------------------ checkpoints
    def checkpoint(self, label: str = "") -> BackendCheckpoint:
        self._require_env()
        sim = self.env.sim
        ctrl = self.env.env.robots[0].controller
        controller_state = {
            name: copy.deepcopy(getattr(ctrl, name))
            for name in (
                "goal_pos",
                "goal_ori",
                "goal_ori_mat",
                "initial_ee_pos",
                "initial_ee_ori_mat",
            )
            if hasattr(ctrl, name)
        }
        payload = {
            "sim_state": np.asarray(sim.get_state().flatten(), dtype=float).copy(),
            "data_ctrl": np.asarray(sim.data.ctrl, dtype=float).copy(),
            "mocap_pos": np.asarray(sim.data.mocap_pos, dtype=float).copy(),
            "mocap_quat": np.asarray(sim.data.mocap_quat, dtype=float).copy(),
            "controller_state": controller_state,
            "step_count": self.step_count,
            "oracle_total_steps": self.controller.total_steps if self.controller else 0,
            "oracle_action_history": copy.deepcopy(
                self.controller.action_history if self.controller else []
            ),
            "held_checkpoint": copy.deepcopy(self.held_checkpoint),
            "current_object": self.current_object,
            "current_target": self.current_target,
            "current_goal_id": self.current_goal_id,
            "unavailable_targets": set(self.unavailable_targets),
            "target_restore_qpos": copy.deepcopy(self.target_restore_qpos),
            "cancelled_goal_ids": set(self.cancelled_goal_ids),
            "collision_detected": self._collision_detected,
            "frame_count": len(self.frames),
            "contact_record_count": len(self.contact_records),
            "simulator_log_count": len(self.simulator_log),
        }
        self._checkpoint_counter += 1
        digest = self.state_hash()
        return BackendCheckpoint(
            checkpoint_id=(
                f"libero-s{self.seed}-t{self.step_count}-c{self._checkpoint_counter}-"
                f"{label or 'checkpoint'}"
            ),
            state_hash=digest,
            step=self.step_count,
            payload=payload,
            metadata={
                "sim_state_size": int(payload["sim_state"].size),
                "object": self.current_object,
                "target": self.current_target,
                "hash_quantization_decimals": 12,
            },
        )

    def restore(self, checkpoint: BackendCheckpoint) -> Dict[str, Any]:
        self._require_env()
        p = checkpoint.payload
        self.env.set_state(np.asarray(p["sim_state"], dtype=float))
        sim = self.env.sim
        if sim.data.ctrl.size:
            sim.data.ctrl[:] = p["data_ctrl"]
        if sim.data.mocap_pos.size:
            sim.data.mocap_pos[:] = p["mocap_pos"]
            sim.data.mocap_quat[:] = p["mocap_quat"]
        ctrl = self.env.env.robots[0].controller
        for name, value in p["controller_state"].items():
            setattr(ctrl, name, copy.deepcopy(value))
        sim.forward()
        self.env._post_process()
        self.env._update_observables(force=True)
        self.obs = self.env.env._get_observations()
        self.step_count = int(p["step_count"])
        self.current_object = p["current_object"]
        self.current_target = p["current_target"]
        self.current_goal_id = p["current_goal_id"]
        self.unavailable_targets = set(p["unavailable_targets"])
        self.target_restore_qpos = copy.deepcopy(p["target_restore_qpos"])
        self.cancelled_goal_ids = set(p["cancelled_goal_ids"])
        self._collision_detected = bool(p["collision_detected"])
        self.held_checkpoint = copy.deepcopy(p["held_checkpoint"])
        del self.frames[int(p["frame_count"]) :]
        del self.contact_records[int(p["contact_record_count"]) :]
        del self.simulator_log[int(p["simulator_log_count"]) :]
        if self.controller is not None:
            self.controller.observation = self.obs
            self.controller.total_steps = int(p["oracle_total_steps"])
            self.controller.action_history = copy.deepcopy(p["oracle_action_history"])
        actual = self.state_hash()
        if actual != checkpoint.state_hash:
            component_error = {
                "sim_state_max_abs": float(
                    np.max(
                        np.abs(
                            np.asarray(sim.get_state().flatten(), dtype=float)
                            - np.asarray(p["sim_state"], dtype=float)
                        )
                    )
                ),
                "data_ctrl_max_abs": float(
                    np.max(
                        np.abs(
                            np.asarray(sim.data.ctrl, dtype=float)
                            - np.asarray(p["data_ctrl"], dtype=float)
                        )
                    )
                )
                if sim.data.ctrl.size
                else 0.0,
                "mocap_pos_max_abs": float(
                    np.max(
                        np.abs(
                            np.asarray(sim.data.mocap_pos, dtype=float)
                            - np.asarray(p["mocap_pos"], dtype=float)
                        )
                    )
                )
                if sim.data.mocap_pos.size
                else 0.0,
                "mocap_quat_max_abs": float(
                    np.max(
                        np.abs(
                            np.asarray(sim.data.mocap_quat, dtype=float)
                            - np.asarray(p["mocap_quat"], dtype=float)
                        )
                    )
                )
                if sim.data.mocap_quat.size
                else 0.0,
                "controller": {
                    name: float(
                        np.max(
                            np.abs(
                                np.asarray(getattr(ctrl, name), dtype=float)
                                - np.asarray(value, dtype=float)
                            )
                        )
                    )
                    for name, value in p["controller_state"].items()
                },
            }
            raise RuntimeError(
                "MuJoCo/controller restore hash mismatch: "
                f"expected={checkpoint.state_hash} actual={actual} "
                f"component_error={json.dumps(component_error, sort_keys=True)}"
            )
        return {
            "restored": True,
            "checkpoint_id": checkpoint.checkpoint_id,
            "expected_hash": checkpoint.state_hash,
            "actual_hash": actual,
            "exact": True,
            "canonical_hash_quantization_decimals": 12,
        }

    def state_hash(self) -> str:
        self._require_env()
        sim = self.env.sim
        digest = hashlib.sha256()
        arrays = (
            ("state", sim.get_state().flatten()),
            ("ctrl", sim.data.ctrl),
            ("mocap_pos", sim.data.mocap_pos),
            ("mocap_quat", sim.data.mocap_quat),
        )
        for name, value in arrays:
            array = self._canonical_hash_array(value)
            digest.update(name.encode("ascii"))
            digest.update(str(array.shape).encode("ascii"))
            digest.update(array.tobytes(order="C"))
        ctrl = self.env.env.robots[0].controller
        for name in ("goal_pos", "goal_ori", "goal_ori_mat"):
            if hasattr(ctrl, name):
                array = self._canonical_hash_array(getattr(ctrl, name))
                digest.update(name.encode("ascii"))
                digest.update(array.tobytes(order="C"))
        semantic = {
            "step": self.step_count,
            "object": self.current_object,
            "target": self.current_target,
            "goal_id": self.current_goal_id,
            "unavailable": sorted(self.unavailable_targets),
            "cancelled": sorted(self.cancelled_goal_ids),
            "collision_detected": bool(self._collision_detected),
            "unsafe_contact_count": sum(
                int(bool(row.get("unsafe"))) for row in self.contact_records
            ),
            "contact_record_count": len(self.contact_records),
            "frame_count": len(self.frames),
            "simulator_log_count": len(self.simulator_log),
            "oracle_steps": self.controller.total_steps if self.controller else 0,
            "oracle_action_count": len(self.controller.action_history)
            if self.controller
            else 0,
            "held_checkpoint": (
                self.held_checkpoint.to_dict()
                if self.held_checkpoint is not None
                else None
            ),
            "target_restore_qpos": {
                target: self._canonical_hash_array(qpos).tolist()
                for target, qpos in sorted(self.target_restore_qpos.items())
            },
        }
        digest.update(
            json.dumps(semantic, sort_keys=True, default=str).encode("utf-8")
        )
        return digest.hexdigest()

    @staticmethod
    def _canonical_hash_array(value: Any) -> np.ndarray:
        """Canonicalize sub-femtometer ``sim.forward`` normalization noise."""

        array = np.asarray(value, dtype="<f8").copy()
        array = np.round(array, decimals=12)
        array[np.abs(array) < 0.5e-12] = 0.0
        return array

    # ------------------------------------------------------------------ world edits
    def retarget(self, target: str) -> Dict[str, Any]:
        if target not in self._target_region_map:
            raise KeyError(f"unknown target {target!r}")
        before = self.current_target
        self.current_target = target
        self._log("retarget", before=before, after=target)
        return {
            "before": before,
            "after": target,
            "target_position": self._target_position(target).tolist(),
        }

    def cancel_goal(self, goal_id: str) -> Dict[str, Any]:
        self.cancelled_goal_ids.add(str(goal_id))
        returned = None
        if self.current_goal_id == goal_id and self.held_checkpoint is not None:
            returned = self.return_current_object()
        self._log("cancel_goal", goal_id=goal_id, returned=returned)
        return {"goal_id": goal_id, "cancelled": True, "return": returned}

    def set_target_availability(self, target: str, available: bool) -> Dict[str, Any]:
        obj = self._target_object(target)
        before = self._free_joint_qpos(obj).copy()
        if available:
            if target in self.target_restore_qpos:
                self._set_free_joint_qpos(obj, self.target_restore_qpos.pop(target))
            self.unavailable_targets.discard(target)
        else:
            self.target_restore_qpos.setdefault(target, before.copy())
            storage = np.asarray(
                self.config.get("world_events", {}).get(
                    "unavailable_storage_xyz", [0.0, 0.65, 0.65]
                ),
                dtype=float,
            )
            moved = before.copy()
            moved[:3] = storage
            self._set_free_joint_qpos(obj, moved)
            self.unavailable_targets.add(target)
        after = self._free_joint_qpos(obj).copy()
        self._log(
            "set_target_availability",
            target=target,
            available=bool(available),
            before_qpos=before.tolist(),
            after_qpos=after.tolist(),
        )
        return {
            "target": target,
            "available": bool(available),
            "before_qpos": before.tolist(),
            "after_qpos": after.tolist(),
            "world_changed": not np.allclose(before, after),
        }

    def move_target(self, target: str, delta_xyz: Sequence[float]) -> Dict[str, Any]:
        obj = self._target_object(target)
        before = self._free_joint_qpos(obj).copy()
        after = before.copy()
        after[:3] += np.asarray(delta_xyz, dtype=float)[:3]
        self._set_free_joint_qpos(obj, after)
        realized = self._free_joint_qpos(obj).copy()
        self._log(
            "move_target",
            target=target,
            before_qpos=before.tolist(),
            after_qpos=realized.tolist(),
        )
        return {
            "target": target,
            "before_qpos": before.tolist(),
            "after_qpos": realized.tolist(),
            "delta_xyz": (realized[:3] - before[:3]).tolist(),
            "world_changed": not np.allclose(before, realized),
        }

    # ------------------------------------------------------------------ metrics
    def collision_status(self) -> Dict[str, Any]:
        unsafe = [r for r in self.contact_records if r.get("unsafe")]
        return {
            "collision": bool(self._collision_detected),
            "unsafe_contact_count": len(unsafe),
            "unsafe_contacts": unsafe[-20:],
            "total_contact_observations": len(self.contact_records),
        }

    def attachment_status(self) -> Dict[str, Any]:
        if self.controller is None or self.current_object is None:
            return {"attached": False, "object": self.current_object}
        attached = self.controller.is_grasping(self._real_object(self.current_object))
        return {
            "attached": bool(attached),
            "object": self.current_object,
            "sim_object": self._real_object(self.current_object),
        }

    def task_success(self, expected_assignment, cancelled_objects=()) -> Dict[str, Any]:
        self._require_env()
        assert self.controller is not None
        expected = {}
        for abstract_object, abstract_target in expected_assignment.items():
            ok = self.controller.in_region(
                self._real_object(abstract_object), self._target_region(abstract_target)
            )
            expected[abstract_object] = {
                "target": abstract_target,
                "predicate": bool(ok),
            }
        cancelled = {}
        for abstract_object in cancelled_objects:
            occupied = {
                target: self.controller.in_region(
                    self._real_object(abstract_object), region
                )
                for target, region in self._target_region_map.items()
            }
            cancelled[abstract_object] = occupied
        cancellation_violation = any(any(v.values()) for v in cancelled.values())
        stale = {}
        nominal = self.config["task"]["nominal_assignment"]
        for abstract_object, target in expected_assignment.items():
            old = nominal.get(abstract_object)
            stale[abstract_object] = bool(
                old
                and old != target
                and self.controller.in_region(
                    self._real_object(abstract_object), self._target_region(old)
                )
            )
        progress = sum(int(v["predicate"]) for v in expected.values())
        stability_cfg = self.config.get("metrics", {}).get("stability", {})
        max_linear = float(stability_cfg.get("max_linear_speed_m_s", 0.02))
        max_angular = float(stability_cfg.get("max_angular_speed_rad_s", 0.5))
        object_stability = self._object_stability(
            max_linear=max_linear, max_angular=max_angular
        )
        all_objects_stable = all(
            row["stable"] for row in object_stability.values()
        )
        object_attachment = {
            abstract_object: bool(self.controller.is_grasping(real_object))
            for abstract_object, real_object in self._object_map.items()
        }
        no_task_object_attached = not any(object_attachment.values())
        control_dt_s = float(
            self.config.get("platform", {}).get("control_dt_s", 0.05)
        )
        result = {
            "revised_task_success": bool(
                expected
                and all(v["predicate"] for v in expected.values())
                and not cancellation_violation
                and not self._collision_detected
                and all_objects_stable
                and no_task_object_attached
            ),
            "expected_predicates": expected,
            "progress_completed": progress,
            "progress_total": len(expected),
            "progress_fraction": progress / max(1, len(expected)),
            "cancellation_violation": bool(cancellation_violation),
            "cancelled_object_regions": cancelled,
            "stale_goal_execution": any(stale.values()),
            "stale_goal_by_object": stale,
            "redirected_goal_success": all(
                expected[obj]["predicate"]
                for obj, tgt in expected_assignment.items()
                if self.config["task"]["nominal_assignment"].get(obj) != tgt
            ),
            "object_stability": object_stability,
            "object_positions": {
                abstract_object: self.controller.position(real_object).tolist()
                for abstract_object, real_object in self._object_map.items()
            },
            "all_objects_stable": bool(all_objects_stable),
            "object_attachment": object_attachment,
            "no_task_object_attached": bool(no_task_object_attached),
            "stability_thresholds": {
                "max_linear_speed_m_s": max_linear,
                "max_angular_speed_rad_s": max_angular,
            },
            "collision": bool(self._collision_detected),
            "unsafe_contact": bool(self._collision_detected),
            "environment_steps": self.step_count,
            "task_time": self.step_count * control_dt_s,
            "task_time_s": self.step_count * control_dt_s,
        }
        return result

    def settle_world(self) -> Dict[str, Any]:
        """Wait for real object dynamics, using a consecutive-step gate."""

        self._require_env()
        assert self.controller is not None
        cfg = self.config.get("metrics", {}).get("stability", {})
        max_linear = float(cfg.get("max_linear_speed_m_s", 0.02))
        max_angular = float(cfg.get("max_angular_speed_rad_s", 0.5))
        consecutive_required = int(cfg.get("consecutive_steps", 10))
        max_steps = int(cfg.get("final_settle_max_steps", 200))
        consecutive = 0
        samples: list[Dict[str, Any]] = []
        executed = 0
        for index in range(max_steps):
            action = np.zeros(7, dtype=float)
            action[6] = -1.0
            self.controller._step(action)
            self.obs = self.controller.observation
            self.step_count = self.controller.total_steps
            executed += 1
            current = self._object_stability(
                max_linear=max_linear, max_angular=max_angular
            )
            all_stable = all(row["stable"] for row in current.values())
            consecutive = consecutive + 1 if all_stable else 0
            if index == 0 or (index + 1) % 10 == 0 or all_stable:
                samples.append(
                    {
                        "step": self.step_count,
                        "consecutive_stable": consecutive,
                        "objects": current,
                    }
                )
            if consecutive >= consecutive_required:
                break
        final = self._object_stability(
            max_linear=max_linear, max_angular=max_angular
        )
        result = {
            "stable": bool(consecutive >= consecutive_required),
            "steps": executed,
            "consecutive_stable_steps": consecutive,
            "required_consecutive_steps": consecutive_required,
            "max_steps": max_steps,
            "thresholds": {
                "max_linear_speed_m_s": max_linear,
                "max_angular_speed_rad_s": max_angular,
            },
            "final": final,
            "samples": samples,
        }
        self._log("settle_world", **result)
        return result

    def write_video(self, path: str | Path) -> Dict[str, Any]:
        import imageio.v2 as imageio

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if not self.frames:
            raise RuntimeError("cannot write video: no rendered frames captured")
        fps = int(self.config.get("render", {}).get("fps", 20))
        writer = imageio.get_writer(str(out), fps=fps, macro_block_size=1)
        try:
            for frame in self.frames:
                writer.append_data(np.asarray(frame, dtype=np.uint8))
        finally:
            writer.close()
        return {
            "written": out.is_file() and out.stat().st_size > 0,
            "path": str(out),
            "frames": len(self.frames),
            "fps": fps,
            "bytes": out.stat().st_size if out.exists() else 0,
        }

    def finish_episode(self) -> Dict[str, Any]:
        row = {
            "backend": self.backend_name,
            "seed": self.seed,
            "steps": self.step_count,
            "frames": len(self.frames),
            "collision": self._collision_detected,
            "contacts": len(self.contact_records),
            "state_hash": self.state_hash() if self.env is not None else None,
        }
        if self.env is not None:
            self.env.close()
            self.env = None
        return row

    # ------------------------------------------------------------------ helpers
    def _after_oracle_step(
        self, action: np.ndarray, step: int, observation: Dict[str, Any]
    ) -> None:
        self.obs = observation
        self.step_count = int(step)
        self._append_frame(observation)
        self._record_contacts(action)

    def _append_frame(self, observation: Mapping[str, Any]) -> None:
        camera = self.config.get("render", {}).get("camera", "agentview")
        key = f"{camera}_image"
        if key in observation:
            # MuJoCo offscreen images are upside down relative to display.
            self.frames.append(
                np.asarray(observation[key], dtype=np.uint8)[::-1, ::-1].copy()
            )

    def _record_contacts(self, action: np.ndarray) -> None:
        if self.env is None:
            return
        sim = self.env.sim
        current_real = (
            self._real_object(self.current_object) if self.current_object else ""
        )
        target_real = (
            self._target_object(self.current_target) if self.current_target else ""
        )
        robot_tokens = ("robot", "gripper", "finger", "hand", "link")
        allowed_tokens = tuple(x for x in (current_real, target_real) if x)
        for index in range(int(sim.data.ncon)):
            contact = sim.data.contact[index]
            names = sorted(
                (
                    str(sim.model.geom_id2name(int(contact.geom1)) or contact.geom1),
                    str(sim.model.geom_id2name(int(contact.geom2)) or contact.geom2),
                )
            )
            pair = " <-> ".join(names)
            has_robot = any(tok in pair for tok in robot_tokens)
            allowed = any(tok in pair for tok in allowed_tokens)
            # Intended gripper/object and object/receptacle contacts are not
            # collisions. Robot/table or robot/protected-object contacts are.
            downward_held_object_table = bool(
                current_real
                and current_real in pair
                and "living_room_table" in pair
                and len(action) >= 3
                and float(action[2]) < -0.2
            )
            protected_tokens = tuple(self._object_map.values()) + tuple(
                self._target_object_map.values()
            )
            unexpected_protected = bool(
                has_robot
                and any(token in pair for token in protected_tokens)
                and not allowed
            )
            unsafe = bool(unexpected_protected or downward_held_object_table)
            row = {
                "step": self.step_count,
                "pair": pair,
                "unsafe": unsafe,
                "action": np.asarray(action, dtype=float).tolist(),
            }
            self.contact_records.append(row)
            self._collision_detected = self._collision_detected or unsafe

    def _free_joint_qpos(self, object_name: str) -> np.ndarray:
        sim = self.env.sim
        joint = f"{object_name}_joint0"
        joint_id = sim.model.joint_name2id(joint)
        address = int(sim.model.jnt_qposadr[joint_id])
        return np.asarray(sim.data.qpos[address : address + 7], dtype=float).copy()

    def _free_joint_qvel(self, object_name: str) -> np.ndarray:
        sim = self.env.sim
        joint = f"{object_name}_joint0"
        joint_id = sim.model.joint_name2id(joint)
        address = int(sim.model.jnt_dofadr[joint_id])
        return np.asarray(sim.data.qvel[address : address + 6], dtype=float).copy()

    def _object_stability(
        self, *, max_linear: float, max_angular: float
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for abstract_object, real_object in self._object_map.items():
            velocity = self._free_joint_qvel(real_object)
            linear = float(np.linalg.norm(velocity[:3]))
            angular = float(np.linalg.norm(velocity[3:]))
            result[abstract_object] = {
                "linear_speed_m_s": linear,
                "angular_speed_rad_s": angular,
                "stable": bool(
                    linear <= max_linear and angular <= max_angular
                ),
            }
        return result

    def _set_free_joint_qpos(self, object_name: str, qpos: Sequence[float]) -> None:
        sim = self.env.sim
        joint_id = sim.model.joint_name2id(f"{object_name}_joint0")
        qaddr = int(sim.model.jnt_qposadr[joint_id])
        vaddr = int(sim.model.jnt_dofadr[joint_id])
        sim.data.qpos[qaddr : qaddr + 7] = np.asarray(qpos, dtype=float)
        sim.data.qvel[vaddr : vaddr + 6] = 0.0
        sim.forward()
        self.env._post_process()
        self.env._update_observables(force=True)
        self.obs = self.env.env._get_observations()
        if self.controller is not None:
            self.controller.observation = self.obs
        self._append_frame(self.obs)

    def _real_object(self, abstract: str) -> str:
        return self._object_map[str(abstract)]

    def _target_region(self, abstract: str) -> str:
        return self._target_region_map[str(abstract)]

    def _target_object(self, abstract: str) -> str:
        return self._target_object_map[str(abstract)]

    def _target_position(self, abstract: str) -> np.ndarray:
        assert self.controller is not None
        return self.controller.position(self._target_region(abstract))

    def _log(self, event: str, **fields: Any) -> None:
        self.simulator_log.append(
            json.dumps(
                {"event": event, "step": self.step_count, **fields},
                sort_keys=True,
                default=str,
            )
        )

    def _require_env(self) -> None:
        if self.env is None or self.obs is None or self.controller is None:
            raise RuntimeError("reset() must be called before using libero_mujoco")

    def _require_leg(self) -> None:
        self._require_env()
        if self.current_object is None or self.current_target is None:
            raise RuntimeError("begin_leg() must be called before leg operations")
