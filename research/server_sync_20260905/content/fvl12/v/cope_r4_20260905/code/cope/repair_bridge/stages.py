"""The ten pipeline markers that a genuine end-to-end adaptation must emit.

An adaptation that does not emit all of these did not go through the repair
engine. `assert_complete()` is what the integration tests and the dry-run check
against, so "the engine is wired in" is a verifiable claim rather than a
docstring.

    EVENT                    an external interruption was delivered
    PATCH | REGENERATION     the semantic layer produced its state update
    CONTINUATION_CAPTURED    kappa_t taken BEFORE any physical adaptation
    REPAIR_GOAL_COMPILED     constraint-state semantics -> RepairGoal
    CANDIDATES_GENERATED     Omega_t, runtime operator synthesis
    ROLLOUT_RESULTS          sequential forward verification of each candidate
    CANDIDATE_SELECTED       argmin J subject to Legal/Feasible/RolloutOk
    GRAPH_SPLICED            TaskProgram+ = Splice(TaskProgram, Delta*, kappa)
    RESTORE_VALIDATED        non-tautological restore contract check
    STAGE_RESUMED            the interrupted stage resumed under kappa
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, List, Sequence, Tuple


class PipelineStage(str, Enum):
    EVENT = "EVENT"
    PATCH = "PATCH"
    REGENERATION = "REGENERATION"
    CONTINUATION_CAPTURED = "CONTINUATION_CAPTURED"
    REPAIR_GOAL_COMPILED = "REPAIR_GOAL_COMPILED"
    CANDIDATES_GENERATED = "CANDIDATES_GENERATED"
    ROLLOUT_RESULTS = "ROLLOUT_RESULTS"
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
    GRAPH_SPLICED = "GRAPH_SPLICED"
    RESTORE_VALIDATED = "RESTORE_VALIDATED"
    STAGE_RESUMED = "STAGE_RESUMED"
    # terminal alternative to CANDIDATE_SELECTED: nothing survived the filters
    SAFE_FALLBACK = "SAFE_FALLBACK"


#: The required order. `PATCH` and `REGENERATION` are alternatives at slot 1.
REQUIRED_ORDER: Tuple[PipelineStage, ...] = (
    PipelineStage.EVENT,
    PipelineStage.PATCH,                 # or REGENERATION
    PipelineStage.CONTINUATION_CAPTURED,
    PipelineStage.REPAIR_GOAL_COMPILED,
    PipelineStage.CANDIDATES_GENERATED,
    PipelineStage.ROLLOUT_RESULTS,
    PipelineStage.CANDIDATE_SELECTED,
    PipelineStage.GRAPH_SPLICED,
    PipelineStage.RESTORE_VALIDATED,
    PipelineStage.STAGE_RESUMED,
)

_ALT = {PipelineStage.PATCH: PipelineStage.REGENERATION}


def assert_complete(markers: Sequence[str]) -> Tuple[bool, List[str]]:
    """Check a marker sequence against `REQUIRED_ORDER`.

    Returns (ok, problems). Markers may repeat and may interleave with other
    entries; what is checked is that each required marker appears, and that the
    first occurrences are in the required order. A `SAFE_FALLBACK` run is
    legitimate but is NOT complete -- it is reported as such rather than
    silently accepted, because a pipeline that always falls back would emit no
    rollout evidence.
    """
    seq = [m for m in markers if m in set(s.value for s in PipelineStage)]
    problems: List[str] = []
    first: Dict[str, int] = {}
    for i, m in enumerate(seq):
        first.setdefault(m, i)

    if PipelineStage.SAFE_FALLBACK.value in first and \
            PipelineStage.CANDIDATE_SELECTED.value not in first:
        problems.append("safe fallback: no candidate survived, pipeline incomplete")

    prev = -1
    for stage in REQUIRED_ORDER:
        alt = _ALT.get(stage)
        idx = first.get(stage.value)
        if idx is None and alt is not None:
            idx = first.get(alt.value)
        if idx is None:
            name = stage.value + (f" (or {alt.value})" if alt else "")
            problems.append(f"missing marker: {name}")
            continue
        if idx < prev:
            problems.append(f"out of order: {stage.value}")
        prev = max(prev, idx)
    return (not problems), problems
