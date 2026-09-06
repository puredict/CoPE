"""Backend-neutral contract for real candidate rollout and task execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


class BackendUnavailable(RuntimeError):
    """The requested backend cannot be initialized on this machine."""


@dataclass
class BackendCheckpoint:
    """Opaque simulator checkpoint plus audit-safe metadata.

    ``payload`` remains backend-owned and is deliberately omitted from JSON
    output. The digest is the equality contract used around every candidate.
    """

    checkpoint_id: str
    state_hash: str
    step: int
    payload: Any = field(repr=False)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "state_hash": self.state_hash,
            "step": self.step,
            "metadata": dict(self.metadata),
        }


class SimulatorRepairBackend(ABC):
    """Common simulator surface consumed by both methods and the verifier."""

    backend_name: str

    @abstractmethod
    def initialize(self, config: str | Path | Mapping[str, Any]) -> Dict[str, Any]:
        """Load configuration and validate dependencies without silent fallback."""

    @abstractmethod
    def reset(self, seed: int) -> Dict[str, Any]:
        """Create one deterministic episode world."""

    @abstractmethod
    def begin_leg(self, goal: Mapping[str, Any]) -> Dict[str, Any]:
        """Select the current object and target while preserving world state."""

    @abstractmethod
    def observe(self) -> Any:
        """Return the shared execution context used by repair compilation."""

    @abstractmethod
    def step(self, action: Sequence[float]) -> Dict[str, Any]:
        """Apply one backend-neutral repair action to the real simulator."""

    @abstractmethod
    def checkpoint(self, label: str = "") -> BackendCheckpoint:
        """Capture simulator, controller, attachment, and backend bookkeeping."""

    @abstractmethod
    def restore(self, checkpoint: BackendCheckpoint) -> Dict[str, Any]:
        """Restore a checkpoint and prove exact state-hash equality."""

    def current_step(self) -> int:
        """Elapsed simulator steps. CONCRETE, with a portable default.

        Used by the interruption scheduler, which must be able to ask "how far
        into the episode are we?" without consulting goals, slots, controller
        outcomes or the method. Backends track this as `step_count`.
        """
        return int(getattr(self, "step_count", 0))

    @abstractmethod
    def state_hash(self) -> str:
        """Hash all state that can influence a candidate rollout."""

    @abstractmethod
    def retarget(self, target: str) -> Dict[str, Any]:
        """Change the active continuation target."""

    @abstractmethod
    def cancel_goal(self, goal_id: str) -> Dict[str, Any]:
        """Stop pursuit of a cancelled goal without marking it successful."""

    @abstractmethod
    def set_target_availability(self, target: str, available: bool) -> Dict[str, Any]:
        """Physically remove or restore a target in the simulated world."""

    @abstractmethod
    def move_target(self, target: str, delta_xyz: Sequence[float]) -> Dict[str, Any]:
        """Move a target body and refresh observations."""

    @abstractmethod
    def collision_status(self) -> Dict[str, Any]:
        """Return measured MuJoCo/simulator collision proxies."""

    @abstractmethod
    def attachment_status(self) -> Dict[str, Any]:
        """Return the active object/gripper attachment state."""

    @abstractmethod
    def task_success(
        self,
        expected_assignment: Mapping[str, str],
        cancelled_objects: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """Evaluate revised task semantics from simulator predicates."""

    @abstractmethod
    def settle_world(self) -> Dict[str, Any]:
        """Advance a method-neutral final stability gate before evaluation."""

    @abstractmethod
    def write_video(self, path: str | Path) -> Dict[str, Any]:
        """Write the episode frames to an MP4 artifact."""

    @abstractmethod
    def finish_episode(self) -> Dict[str, Any]:
        """Close simulator resources and return final backend diagnostics."""
