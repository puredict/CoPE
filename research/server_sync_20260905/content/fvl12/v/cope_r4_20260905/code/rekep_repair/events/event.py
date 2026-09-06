"""Event types and the Event record produced by the detector."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple


class EventType(str, Enum):
    NONE = "NONE"
    OBSTACLE_INTRUSION = "OBSTACLE_INTRUSION"      # temporary obstacle / hand
    OBJECT_SLIP = "OBJECT_SLIP"                    # grasp slipped
    TARGET_RELOCATION = "TARGET_RELOCATION"        # target moved
    PERSISTENT_INFEASIBILITY = "PERSISTENT_INFEASIBILITY"


@dataclass(frozen=True)
class Event:
    """E_t = (type, severity, affected_entities, confidence)."""

    event_type: EventType
    severity: float = 0.0
    affected_entities: Tuple[str, ...] = ()
    confidence: float = 1.0
    t: int = 0
    event_id: str = ""
    payload: Dict[str, object] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.event_type != EventType.NONE

    @property
    def requires_program_repair(self) -> bool:
        """Mode-changing interruptions require structural repair; a pure
        geometric nudge does not.  We treat all non-NONE classes here as
        repair-requiring, but keep the hook explicit."""
        return self.is_active


NO_EVENT = Event(event_type=EventType.NONE)
