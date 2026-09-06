"""Adapter preserving the shipped Synthetic2D execution substrate."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from .base import BackendCheckpoint, SimulatorRepairBackend


class Synthetic2DBackend(SimulatorRepairBackend):
    backend_name = "synthetic2d"

    def __init__(self) -> None:
        self.env = None
        self.seed = 0
        self.step_count = 0
        self.blocked: set[str] = set()
        self.cancelled: set[str] = set()

    def initialize(self, config=None) -> Dict[str, Any]:
        return {"backend": self.backend_name, "config": str(config or "built-in")}

    def reset(self, seed: int) -> Dict[str, Any]:
        self.seed = int(seed)
        self.step_count = 0
        self.env = None
        self.blocked.clear()
        self.cancelled.clear()
        return {"backend": self.backend_name, "seed": self.seed}

    def begin_leg(self, goal: Mapping[str, Any]) -> Dict[str, Any]:
        from cope.benchmark.basket_world import BasketLegEnv

        self.env = BasketLegEnv(
            str(goal["object"]),
            str(goal["target"]),
            seed=self.seed,
            blocked_targets=tuple(sorted(self.blocked)),
        )
        return {"object": self.env.object_name, "target": self.env.target_name}

    def _require(self):
        if self.env is None:
            raise RuntimeError("begin_leg() must be called before using Synthetic2DBackend")
        return self.env

    def observe(self):
        return self._require().observe()

    def step(self, action: Sequence[float]) -> Dict[str, Any]:
        env = self._require()
        ctx = env.step(np.asarray(action, dtype=float))
        self.step_count += 1
        return {
            "step": self.step_count,
            "state": np.asarray(ctx.state).tolist(),
            "collision": bool(ctx.clearance < 0.0),
        }

    def checkpoint(self, label: str = "") -> BackendCheckpoint:
        env = self._require()
        payload = copy.deepcopy(env.__dict__)
        return BackendCheckpoint(
            checkpoint_id=f"synthetic-{self.step_count}-{label or 'checkpoint'}",
            state_hash=self.state_hash(),
            step=self.step_count,
            payload=payload,
        )

    def restore(self, checkpoint: BackendCheckpoint) -> Dict[str, Any]:
        env = self._require()
        env.__dict__.clear()
        env.__dict__.update(copy.deepcopy(checkpoint.payload))
        self.step_count = checkpoint.step
        actual = self.state_hash()
        if actual != checkpoint.state_hash:
            raise RuntimeError(
                f"Synthetic2D restore hash mismatch: {actual} != {checkpoint.state_hash}"
            )
        return {"restored": True, "state_hash": actual}

    def state_hash(self) -> str:
        env = self._require()
        ctx = env.observe()
        payload = {
            "step": self.step_count,
            "state": np.asarray(ctx.state).tolist(),
            "goal": np.asarray(ctx.task_goal).tolist(),
            "attachments": dict(ctx.attachments),
            "target": env.target_name,
            "blocked": sorted(self.blocked),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def retarget(self, target: str) -> Dict[str, Any]:
        env = self._require()
        before = env.target_name
        env.retarget(target)
        return {"before": before, "after": target}

    def cancel_goal(self, goal_id: str) -> Dict[str, Any]:
        self.cancelled.add(str(goal_id))
        return {"goal_id": goal_id, "cancelled": True}

    def set_target_availability(self, target: str, available: bool) -> Dict[str, Any]:
        if available:
            self.blocked.discard(target)
        else:
            self.blocked.add(target)
        if self.env is not None:
            self.env.set_blocked(tuple(sorted(self.blocked)))
        return {"target": target, "available": bool(available)}

    def move_target(self, target: str, delta_xyz: Sequence[float]) -> Dict[str, Any]:
        from cope.benchmark.basket_world import BASKET_POS

        delta = np.asarray(delta_xyz, dtype=float)
        BASKET_POS[target] = BASKET_POS[target] + delta[:2]
        if self.env is not None and self.env.target_name == target:
            self.env.retarget(target)
        return {"target": target, "delta_xyz": delta.tolist()}

    def collision_status(self) -> Dict[str, Any]:
        ctx = self._require().observe()
        return {"collision": bool(ctx.clearance < 0.0), "clearance": ctx.clearance}

    def attachment_status(self) -> Dict[str, Any]:
        ctx = self._require().observe()
        return {"attached": bool(ctx.object_grasped), "attachments": dict(ctx.attachments)}

    def task_success(self, expected_assignment, cancelled_objects=()) -> Dict[str, Any]:
        env = self._require()
        placed = env.placement_valid()
        return {
            "revised_task_success": bool(placed),
            "current_leg_placed": bool(placed),
            "expected_assignment": dict(expected_assignment),
            "cancelled_objects": list(cancelled_objects),
        }

    def settle_world(self) -> Dict[str, Any]:
        return {"stable": True, "steps": 0, "backend": self.backend_name}

    def write_video(self, path: str | Path) -> Dict[str, Any]:
        return {"written": False, "path": str(path), "reason": "Synthetic2D has no raster renderer"}

    def finish_episode(self) -> Dict[str, Any]:
        self.env = None
        return {"backend": self.backend_name, "steps": self.step_count}
