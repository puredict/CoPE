"""RepairCandidate -- one instantiated, orderable repair program."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from ..program.continuation import Continuation
from ..program.stage import StageSpec


@dataclass
class RepairCandidate:
    template_name: str
    stages: List[StageSpec]
    continuation: Continuation
    # optional explicit internal edges for adversarial/legality testing;
    # when None the candidate is treated as a simple chain over ``stages``.
    internal_edges: Optional[Set[Tuple[str, str]]] = None

    # populated by filters/rollout/scorer
    legal: Optional[bool] = None
    legality_reason: str = ""
    feasible: Optional[bool] = None
    feasibility_reason: str = ""
    rollout: Optional[object] = None      # RolloutReport
    score: float = float("inf")
    score_terms: dict = field(default_factory=dict)

    @property
    def stage_ids(self) -> List[str]:
        return [s.stage_id for s in self.stages]

    def provides_restore(self) -> bool:
        return any(s.metadata.get("provides_restore") for s in self.stages)

    def is_terminal(self) -> bool:
        return any(s.metadata.get("terminal") for s in self.stages)
