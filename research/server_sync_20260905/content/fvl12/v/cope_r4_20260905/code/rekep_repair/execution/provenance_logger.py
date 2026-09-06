"""Provenance logging: every executed action gets a causal lineage

    action <- stage <- (repair) <- event <- continuation

so we can compute provenance coverage (Sec. 11.5) and print a runtime trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class ActionRecord:
    t: int
    action: np.ndarray
    stage_id: str
    stage_mode: str
    stage_kind: str          # nominal | repair | resumed
    stage_state: str
    event_id: Optional[str] = None
    repair_template: Optional[str] = None
    continuation_ts: Optional[int] = None

    def has_complete_provenance(self) -> bool:
        # nominal actions map to a stage; repair/resumed actions must also map
        # back to an event + continuation.
        if self.stage_kind in ("repair", "resumed"):
            return self.event_id is not None and self.continuation_ts is not None
        return self.stage_id is not None


@dataclass
class ProvenanceLog:
    records: List[ActionRecord] = field(default_factory=list)

    def add(self, rec: ActionRecord) -> None:
        self.records.append(rec)

    def _recovery_records(self) -> List[ActionRecord]:
        """Actions produced by recovery behavior, method-neutrally: repair /
        resumed nodes (online) or non-nominal recovery states (baselines)."""
        return [r for r in self.records
                if r.stage_kind in ("repair", "resumed")
                or r.stage_state in ("SUSPENDED", "REPAIR_ACTIVE", "RESUMED", "FAILED")]

    def continuation_linked_coverage(self) -> float:
        """Fraction of actions with a FULL continuation-linked lineage
        (action<-stage<-repair<-event<-continuation).  This structurally
        favors methods that carry a continuation; use the neutral metrics below
        for cross-method fairness."""
        if not self.records:
            return 1.0
        n_ok = sum(1 for r in self.records if r.has_complete_provenance())
        return n_ok / len(self.records)

    # back-compat alias
    def coverage(self) -> float:
        return self.continuation_linked_coverage()

    def event_attribution_coverage(self) -> float:
        """Method-neutral: fraction of recovery actions attributable to a
        triggering event.  Offline branches and online repairs both qualify."""
        rec = self._recovery_records()
        if not rec:
            return 1.0
        return sum(1 for r in rec if r.event_id is not None) / len(rec)

    def policy_attribution_coverage(self) -> float:
        """Method-neutral: fraction of recovery actions attributable to a named
        recovery unit (branch/template/plan)."""
        rec = self._recovery_records()
        if not rec:
            return 1.0
        return sum(1 for r in rec if r.repair_template is not None) / len(rec)

    def repair_records(self) -> List[ActionRecord]:
        return [r for r in self.records if r.stage_kind in ("repair", "resumed")]
