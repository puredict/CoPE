"""P0-2 --- a genuine GPU candidate rollout verifier with state isolation.

v1 defect this replaces: candidates were scored by edit length only
(``note="no-rollout"``, score ``0.3*5 = 1.5`` identically for all three), and the
so-called "native rollout verification" was a shape/finiteness check on ReKep's
returned path, run **once, on the already-selected candidate**. Nothing was ever
rejected.

Here every candidate is simulated from an **identical restored checkpoint**,
using the host's own ReKep subgoal/path/IK/control stack, and is hard-rejected on
collision, solver failure, timeout, invalid attachment, unresolved event, or an
invalid continuation handoff.

The simulator is behind the :class:`ShadowRolloutHost` protocol so this file
imports nothing GPU-specific and the whole verifier is CPU-testable with a fake
host (see ``tests/test_gpu_rollout.py``).

**State isolation is enforced, not assumed**: the host must expose a
``state_hash()``; the verifier asserts the hash observed at the start of every
candidate equals the hash captured at checkpoint time, and records both.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

import numpy as np


class StateIsolationError(RuntimeError):
    """Raised when a candidate did not start from the checkpoint state."""


class ShadowRolloutHost(Protocol):
    """What the verifier needs from the simulator + ReKep stack.

    The GPU implementation wraps OmniGibson + ReKep's ``Main``; the CPU tests
    supply a deterministic fake. Neither is imported here.
    """

    def save_checkpoint(self) -> Any: ...
    def restore_checkpoint(self, checkpoint: Any) -> None: ...
    def state_hash(self) -> str: ...
    def simulate_operator_sequence(
        self, operators: Sequence[str], budget_steps: int) -> Dict[str, Any]: ...


@dataclass
class CandidateRolloutResult:
    """Structured, per-candidate verification record."""

    candidate_id: str
    operator_sequence: List[str]
    solver_success: Optional[bool] = None
    collision: Optional[bool] = None
    timeout: Optional[bool] = None
    osc_warning_count: Optional[int] = None
    workspace_clip_count: Optional[int] = None
    attachment_valid: Optional[bool] = None
    event_residual: List[str] = field(default_factory=list)
    handoff_error: Optional[float] = None
    predicted_xy_error: Optional[float] = None
    predicted_insertion_depth: Optional[float] = None
    predicted_tilt_error: Optional[float] = None
    predicted_success: Optional[bool] = None
    accepted: bool = False
    rejection_reason: Optional[str] = None
    verification_time_s: Optional[float] = None
    steps_simulated: Optional[int] = None
    # state-isolation provenance
    checkpoint_hash: Optional[str] = None
    pre_rollout_hash: Optional[str] = None
    isolation_ok: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RolloutLimits:
    budget_steps: int = 250
    max_osc_warnings: int = 40
    max_workspace_clips: int = 8
    max_handoff_error_m: float = 0.05


class GPUCandidateVerifier:
    """Verifies each candidate from an identical restored checkpoint."""

    def __init__(self, host: ShadowRolloutHost,
                 limits: Optional[RolloutLimits] = None,
                 logger=None):
        self.host = host
        self.limits = limits or RolloutLimits()
        self.log = logger

    def _emit(self, event: str, **kw) -> None:
        if self.log is not None:
            self.log.emit(event, **kw)

    # ------------------------------------------------------------------
    def verify_all(self, candidates: Sequence[Any]) -> List[CandidateRolloutResult]:
        """Roll out every candidate from one shared checkpoint.

        Returns results in input order. The checkpoint is restored **before**
        each candidate and once more at the end, so the live simulator is left
        exactly as it was found.
        """
        checkpoint = self.host.save_checkpoint()
        ckpt_hash = self.host.state_hash()
        results: List[CandidateRolloutResult] = []

        for i, cand in enumerate(candidates):
            cid = f"cand{i}"
            ops = [s.metadata.get("operator", "?") for s in cand.stages]
            res = CandidateRolloutResult(candidate_id=cid, operator_sequence=ops,
                                         checkpoint_hash=ckpt_hash)
            t0 = time.perf_counter()

            # --- STATE ISOLATION: restore, then prove we are back at ckpt ---
            self.host.restore_checkpoint(checkpoint)
            res.pre_rollout_hash = self.host.state_hash()
            res.isolation_ok = (res.pre_rollout_hash == ckpt_hash)
            if not res.isolation_ok:
                res.rejection_reason = (
                    f"state isolation violated: pre-rollout hash "
                    f"{res.pre_rollout_hash} != checkpoint {ckpt_hash}")
                res.verification_time_s = time.perf_counter() - t0
                results.append(res)
                self._emit("ROLLOUT_RESULT", candidate_id=cid, accepted=False,
                           reason=res.rejection_reason)
                raise StateIsolationError(res.rejection_reason)

            self._emit("ROLLOUT_STARTED", candidate_id=cid, operators=ops,
                       checkpoint_hash=ckpt_hash)

            # --- simulate under the host's own ReKep stack -----------------
            try:
                out = self.host.simulate_operator_sequence(
                    ops, budget_steps=self.limits.budget_steps)
            except Exception as e:                       # solver / sim blew up
                res.solver_success = False
                res.rejection_reason = f"solver/simulator exception: {e!r}"
                res.verification_time_s = time.perf_counter() - t0
                results.append(res)
                self._emit("CANDIDATE_REJECTED", candidate_id=cid,
                           reason=res.rejection_reason)
                continue

            self._absorb(res, out)
            res.verification_time_s = time.perf_counter() - t0
            self._decide(res)
            results.append(res)
            self._emit("ROLLOUT_RESULT", candidate_id=cid,
                       accepted=res.accepted, reason=res.rejection_reason,
                       handoff_error=res.handoff_error,
                       predicted_xy_error=res.predicted_xy_error,
                       osc_warnings=res.osc_warning_count,
                       steps=res.steps_simulated,
                       verification_time_s=round(res.verification_time_s, 4))
            if not res.accepted:
                self._emit("CANDIDATE_REJECTED", candidate_id=cid,
                           reason=res.rejection_reason)

        # leave the live simulator exactly as found
        self.host.restore_checkpoint(checkpoint)
        return results

    # ------------------------------------------------------------------
    @staticmethod
    def _absorb(res: CandidateRolloutResult, out: Dict[str, Any]) -> None:
        res.solver_success = bool(out.get("solver_success", False))
        res.collision = out.get("collision")
        res.timeout = out.get("timeout")
        res.osc_warning_count = out.get("osc_warning_count")
        res.workspace_clip_count = out.get("workspace_clip_count")
        res.attachment_valid = out.get("attachment_valid")
        res.event_residual = list(out.get("event_residual", []) or [])
        res.handoff_error = out.get("handoff_error")
        res.predicted_xy_error = out.get("predicted_xy_error")
        res.predicted_insertion_depth = out.get("predicted_insertion_depth")
        res.predicted_tilt_error = out.get("predicted_tilt_error")
        res.predicted_success = out.get("predicted_success")
        res.steps_simulated = out.get("steps_simulated")

    def _decide(self, res: CandidateRolloutResult) -> None:
        """Hard-reject rules. Order matters only for the reported reason."""
        L = self.limits
        if not res.solver_success:
            res.rejection_reason = "ReKep solver failed to return a usable path"
        elif res.collision:
            res.rejection_reason = "predicted collision during rollout"
        elif res.timeout:
            res.rejection_reason = "rollout exceeded the step budget (timeout)"
        elif res.attachment_valid is False:
            res.rejection_reason = "attachment lost during rollout"
        elif res.event_residual:
            res.rejection_reason = (
                f"event not resolved: residual {res.event_residual}")
        elif res.handoff_error is not None and \
                res.handoff_error > L.max_handoff_error_m:
            res.rejection_reason = (
                f"invalid handoff: error {res.handoff_error:.4f} m > "
                f"{L.max_handoff_error_m:.4f} m")
        elif res.osc_warning_count is not None and \
                res.osc_warning_count > L.max_osc_warnings:
            res.rejection_reason = (
                f"controller not converging: {res.osc_warning_count} OSC warnings "
                f"> {L.max_osc_warnings}")
        elif res.workspace_clip_count is not None and \
                res.workspace_clip_count > L.max_workspace_clips:
            res.rejection_reason = (
                f"{res.workspace_clip_count} workspace clips > "
                f"{L.max_workspace_clips}")
        else:
            res.accepted = True
            res.rejection_reason = None


def select_best(results: Sequence[CandidateRolloutResult]) -> Optional[CandidateRolloutResult]:
    """Pick among ACCEPTED candidates using measured rollout quantities.

    Ranking (lexicographic, all measured -- no structural tie-break first):
      1. predicted_success   (True first)
      2. predicted_xy_error  (smaller better)
      3. handoff_error       (smaller better)
      4. steps_simulated     (shorter better)
    """
    ok = [r for r in results if r.accepted]
    if not ok:
        return None
    def key(r: CandidateRolloutResult):
        return (
            0 if r.predicted_success else 1,
            r.predicted_xy_error if r.predicted_xy_error is not None else 1e9,
            r.handoff_error if r.handoff_error is not None else 1e9,
            r.steps_simulated if r.steps_simulated is not None else 1e9,
        )
    return min(ok, key=key)
