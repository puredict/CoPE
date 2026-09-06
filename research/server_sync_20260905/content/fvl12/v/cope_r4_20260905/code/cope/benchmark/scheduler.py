"""Method-independent interruption scheduler.

## The defect this replaces

v2 delivered interruptions on *goal completion*:

    if trigger2 in completed_goal_ids:      # e.g. "g_milk"
        deliver(u2)

In the LIBERO/MuJoCo pilot the milk grasp failed in seeds 1 and 3
(`grasp_not_acquired`). `g_milk` therefore never completed, the restore event
keyed on it never fired, and **8 of 30 primary I2/I4 episodes silently never
tested restoration at all** -- while still being counted as valid I2/I4
episodes. A controller failure was able to delete an experimental condition.

## The replacement

Every interruption is delivered on a **pre-registered elapsed-step schedule**
that no method and no task outcome can influence:

    t_u1      = absolute simulator step, fixed per (condition, seed)
    t_u2      = t_u1_actual + delta_steps        (relative to actual delivery)

`t_u2` is anchored on the *actual* delivery step of `u1` rather than on its
scheduled step, so a small delivery delay on the first event does not compress
the interval the second event was designed to leave.

Nothing in the trigger consults goal completion, slot identity, method-specific
task state, or grasp success. The only thing that can prevent delivery is the
episode ending first -- and that is recorded explicitly, never omitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Pre-registered schedules, in simulator steps. Chosen from the v2 pilot's
#: observed delivery points so the new schedule lands at the same phase of the
#: task, which keeps the two revisions comparable.
#:
#:   u1_step      absolute step at which the first interruption is delivered
#:   u2_delta     steps AFTER the actual u1 delivery for the second
SCHEDULES: Dict[str, Dict[str, Optional[int]]] = {
    "nominal": {"u1_step": None, "u2_delta": None},
    "I1": {"u1_step": 340, "u2_delta": None},
    "I2": {"u1_step": 110, "u2_delta": 450},
    "I3": {"u1_step": 340, "u2_delta": 230},
    "I4": {"u1_step": 110, "u2_delta": 450},
    "I5": {"u1_step": 110, "u2_delta": 200, "u3_delta": 260},
}

#: The synthetic CPU world advances ~45 steps per episode where LIBERO/MuJoCo
#: advances ~700-900, so the same absolute numbers would never be reached.
#: Both profiles are pre-registered and method-independent; only the step scale
#: differs, and the profile is selected by the BACKEND, never by the method.
SCHEDULES_CPU: Dict[str, Dict[str, Optional[int]]] = {
    "nominal": {"u1_step": None, "u2_delta": None},
    "I1": {"u1_step": 18, "u2_delta": None},
    "I2": {"u1_step": 5, "u2_delta": 26},
    "I3": {"u1_step": 18, "u2_delta": 13},
    "I4": {"u1_step": 5, "u2_delta": 26},
    "I5": {"u1_step": 5, "u2_delta": 9, "u3_delta": 22},
}

PROFILES = {"libero": SCHEDULES, "cpu": SCHEDULES_CPU}

NOT_DELIVERED_TERMINATED = "event_not_delivered_due_to_episode_termination"


@dataclass
class ScheduledEvent:
    """One pre-registered interruption and what actually happened to it."""
    event_id: str
    tag: str                        # u1 / u2 / u3
    scheduled_step: int
    actual_delivery_step: Optional[int] = None
    event_delivered: bool = False
    delivery_delay: Optional[int] = None
    delivery_failure_reason: str = ""
    world_state_hash_before: str = ""
    world_state_hash_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class InterruptionScheduler:
    """Owns the schedule for one episode. Constructed before any policy exists.

    Deterministic in (condition, seed) only. `spec.method` is deliberately not a
    constructor argument -- the scheduler cannot see which arm it is serving.
    """
    condition: str
    seed: int
    n_updates: int
    u1_step: Optional[int] = None
    u2_delta: Optional[int] = None
    u3_delta: Optional[int] = None
    events: List[ScheduledEvent] = field(default_factory=list)
    _fired: set = field(default_factory=set)
    _anchor: Optional[int] = None

    profile: str = "libero"

    @classmethod
    def for_condition(cls, condition: str, seed: int, n_updates: int,
                      profile: str = "libero") -> "InterruptionScheduler":
        """`profile` is chosen by the BACKEND's step scale, never by the method."""
        s = PROFILES.get(profile, SCHEDULES).get(condition, {})
        return cls(condition=condition, seed=seed, n_updates=n_updates,
                   u1_step=s.get("u1_step"), u2_delta=s.get("u2_delta"),
                   u3_delta=s.get("u3_delta"), profile=profile)

    # ------------------------------------------------------------------
    def scheduled_step_for(self, tag: str) -> Optional[int]:
        """Absolute step at which `tag` is due, or None if not yet anchored."""
        if tag == "u1":
            return self.u1_step
        if self._anchor is None:
            return None
        if tag == "u2":
            return None if self.u2_delta is None else self._anchor + self.u2_delta
        if tag == "u3":
            return None if self.u3_delta is None else self._anchor + self.u3_delta
        return None

    def tags(self) -> Tuple[str, ...]:
        return ("u1", "u2", "u3")[: self.n_updates]

    # ------------------------------------------------------------------
    def due(self, sim_step: int) -> List[str]:
        """Tags due at or before `sim_step`, in order, that have not fired.

        Pure function of the simulator step. It never inspects goals, slots,
        grasp outcomes or the method.
        """
        out: List[str] = []
        for tag in self.tags():
            if tag in self._fired:
                continue
            due_at = self.scheduled_step_for(tag)
            if due_at is None:
                # a later event whose anchor has not been set yet
                break
            if sim_step >= due_at:
                out.append(tag)
            else:
                break
        return out

    # ------------------------------------------------------------------
    def mark_delivered(self, tag: str, sim_step: int, event_id: str,
                       hash_before: str = "", hash_after: str = "") -> ScheduledEvent:
        scheduled = self.scheduled_step_for(tag)
        ev = ScheduledEvent(
            event_id=event_id, tag=tag,
            scheduled_step=int(scheduled if scheduled is not None else sim_step),
            actual_delivery_step=int(sim_step), event_delivered=True,
            delivery_delay=int(sim_step - (scheduled if scheduled is not None
                                           else sim_step)),
            world_state_hash_before=hash_before,
            world_state_hash_after=hash_after)
        self._fired.add(tag)
        if tag == "u1":
            # anchor the relative schedule on ACTUAL delivery
            self._anchor = int(sim_step)
        self.events.append(ev)
        return ev

    # ------------------------------------------------------------------
    def finalize(self, final_step: int, reason: str = NOT_DELIVERED_TERMINATED
                 ) -> List[ScheduledEvent]:
        """Record every scheduled event that never ran. Never omit silently."""
        for tag in self.tags():
            if tag in self._fired:
                continue
            scheduled = self.scheduled_step_for(tag)
            self.events.append(ScheduledEvent(
                event_id=f"{self.condition}-{tag}", tag=tag,
                scheduled_step=int(scheduled) if scheduled is not None else -1,
                actual_delivery_step=None, event_delivered=False,
                delivery_delay=None,
                delivery_failure_reason=(
                    reason if scheduled is None or final_step < scheduled
                    else "event_not_delivered_despite_reachable_step")))
            self._fired.add(tag)
        return self.events

    # ------------------------------------------------------------------
    @property
    def all_delivered(self) -> bool:
        return bool(self.events) and all(e.event_delivered for e in self.events)

    @property
    def n_delivered(self) -> int:
        return sum(1 for e in self.events if e.event_delivered)

    def schedule_fingerprint(self) -> str:
        """Method-independent fingerprint: paired arms must produce the same one."""
        import hashlib
        import json
        payload = {"condition": self.condition, "seed": self.seed,
                   "n_updates": self.n_updates, "u1_step": self.u1_step,
                   "u2_delta": self.u2_delta, "u3_delta": self.u3_delta,
                   "profile": self.profile}
        return hashlib.blake2b(json.dumps(payload, sort_keys=True).encode(),
                               digest_size=8).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {"condition": self.condition, "seed": self.seed,
                "profile": self.profile, "n_updates": self.n_updates,
                "schedule_fingerprint": self.schedule_fingerprint(),
                "u1_step": self.u1_step, "u2_delta": self.u2_delta,
                "u3_delta": self.u3_delta, "anchor_step": self._anchor,
                "events": [e.to_dict() for e in self.events],
                "all_delivered": self.all_delivered,
                "n_delivered": self.n_delivered}
