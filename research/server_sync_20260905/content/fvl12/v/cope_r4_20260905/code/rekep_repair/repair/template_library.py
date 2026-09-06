"""Typed repair template library: EventType -> candidate operator sequences.

Multiple templates per event give the generator several candidates to filter
and score.  This is a finite typed library, but the runtime instantiates and
composes the operators against the actual event/state/continuation -- it is not
a lookup of a fully pre-written program.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..events.event import EventType

# Each template is an ordered tuple of operator names.
Template = Tuple[str, ...]

TEMPLATES: Dict[EventType, List[Template]] = {
    EventType.OBSTACLE_INTRUSION: [
        ("Suspend", "Retreat", "WaitUntilClear", "Realign", "Resume"),
        ("Suspend", "WaitUntilClear", "Realign", "Resume"),      # no retreat (feasibility decides)
    ],
    EventType.OBJECT_SLIP: [
        ("Suspend", "Stabilize", "ReacquireTarget", "Realign", "Resume"),
    ],
    EventType.TARGET_RELOCATION: [
        ("Suspend", "ReacquireTarget", "Realign", "Resume"),
    ],
    EventType.PERSISTENT_INFEASIBILITY: [
        ("Suspend", "SafeStop"),
    ],
}


def templates_for(event_type: EventType) -> List[Template]:
    return TEMPLATES.get(event_type, [])
