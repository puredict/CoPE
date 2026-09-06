"""The identical information packet delivered to EVERY adaptation policy.

Fairness rule (task spec §9 and §2): at an interruption FSR-PC receives exactly
the same information as CoPE. It is NOT deprived of completed progress or
history. Both receive this same object; a test asserts the serialized bytes are
identical before adaptation.
"""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class AdaptationInput:
    # world / robot
    world_state: Dict[str, Any]
    robot_state: Dict[str, Any]
    # progress -- explicitly given to BOTH methods
    completed_goals: Tuple[str, ...]
    pending_goals: Tuple[str, ...]
    cancelled_goals: Tuple[str, ...]
    # request and rules
    user_request: str
    safety_constraints: Tuple[Dict[str, Any], ...]
    # histories
    task_history: Tuple[Dict[str, Any], ...]
    event_history: Tuple[Dict[str, Any], ...]
    # perception + budget
    perception: Dict[str, Any]
    compute_budget: Dict[str, Any]
    # the triggering event
    event_id: str = ""
    event_step: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_state": self.world_state, "robot_state": self.robot_state,
            "completed_goals": list(self.completed_goals),
            "pending_goals": list(self.pending_goals),
            "cancelled_goals": list(self.cancelled_goals),
            "user_request": self.user_request,
            "safety_constraints": [dict(c) for c in self.safety_constraints],
            "task_history": [dict(h) for h in self.task_history],
            "event_history": [dict(h) for h in self.event_history],
            "perception": self.perception, "compute_budget": self.compute_budget,
            "event_id": self.event_id, "event_step": self.event_step,
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.serialize().encode()).hexdigest()
