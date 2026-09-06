"""Instantiate typed templates into concrete RepairCandidates for an event."""

from __future__ import annotations

from typing import List

from ..events.event import Event
from ..program.continuation import Continuation
from .candidate import RepairCandidate
from .operator import OPERATORS, RepairParams
from .template_library import templates_for


class CandidateGenerator:
    """Baseline generator: instantiates prewritten typed templates (NOT
    synthesis).  Kept for the TemplateRepairPolicy baseline."""

    kind = "template-instantiation"

    def __init__(self, params: RepairParams):
        self.params = params

    def generate(self, event: Event, continuation: Continuation,
                 abstract_init=None, goal=None) -> List[RepairCandidate]:
        candidates: List[RepairCandidate] = []
        for template in templates_for(event.event_type):
            stages = []
            for idx, op_name in enumerate(template):
                op = OPERATORS[op_name]
                stages.append(op.instantiate(idx, event, continuation, self.params))
            candidates.append(
                RepairCandidate(
                    template_name="->".join(template),
                    stages=stages,
                    continuation=continuation,
                )
            )
        return candidates
