"""Live structured event logging (JSONL) for GPU episodes.

v1 wrote only a final JSON, so nothing about the repair decision was observable
while an episode ran -- and when seed 7 was killed, *no* repair evidence
survived. This logger appends one JSON object per event as it happens, so a
killed episode still leaves a usable trail.

Every event carries: sim_step, wall_time_s, seed, stage_id, candidate_id (when
applicable) and the numeric margins relevant to that event.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

EVENTS = (
    "EVENT_DETECTED", "CONTINUATION_CAPTURED", "REPAIR_GOAL", "SEARCH_EXPANDED",
    "CANDIDATE_GENERATED", "ROLLOUT_STARTED", "ROLLOUT_RESULT",
    "CANDIDATE_REJECTED", "CANDIDATE_SELECTED", "GRAPH_SPLICED",
    "RESTORE_CHECK", "STAGE_RESUMED", "TASK_SUCCESS_EVALUATION",
    # operational
    "EPISODE_START", "EPISODE_END", "SAFE_FALLBACK",
)


@dataclass
class StructuredLogger:
    path: Optional[Path] = None
    seed: Optional[int] = None
    echo: bool = True

    def __post_init__(self):
        self._t0 = time.perf_counter()
        self._sim_step_fn = None
        self._stage_fn = None
        if self.path is not None:
            self.path = Path(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")

    def bind(self, sim_step_fn=None, stage_fn=None) -> None:
        """Attach callables so every event auto-carries sim_step / stage_id."""
        self._sim_step_fn = sim_step_fn
        self._stage_fn = stage_fn

    def emit(self, event: str, **fields: Any) -> Dict[str, Any]:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}; add it to EVENTS")
        rec: Dict[str, Any] = {
            "event": event,
            "wall_time_s": round(time.perf_counter() - self._t0, 4),
            "seed": self.seed,
            "sim_step": self._safe(self._sim_step_fn),
            "stage_id": self._safe(self._stage_fn),
        }
        rec.update(fields)
        line = json.dumps(rec, default=_default)
        if self.path is not None:
            with open(self.path, "a") as f:
                f.write(line + "\n")
        if self.echo:
            print(f"[{event}] {line}", flush=True)
        return rec

    @staticmethod
    def _safe(fn):
        if fn is None:
            return None
        try:
            return fn()
        except Exception:
            return None


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.ndarray):
            return [float(x) for x in o.ravel()]
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, (np.bool_,)):
            return bool(o)
    except Exception:
        pass
    return str(o)
