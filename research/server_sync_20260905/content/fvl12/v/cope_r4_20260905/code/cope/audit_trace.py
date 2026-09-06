"""Audit trace H_t: the structured decision record.

The memo's audit contribution is to "shift explainability from chain-of-thought
to a structured patch trace". The trace must be able to answer, from the record
alone:

  Q1 which goal was cancelled?
  Q2 which completed goal was preserved?
  Q3 why was a constraint suspended?
  Q4 what condition allowed restoration?
  Q5 which state replaced the old target?

## Representation neutrality (important for a fair comparison)

A trace made only of CoPE patch operations would answer all five by
construction and score FSR-PC at zero for circular reasons. So every query here
has **two** evidence paths:

  * patch evidence      -- typed `op` entries (CoPE)
  * regeneration evidence -- diffing consecutive `state_regenerated` snapshots
                             (FSR-PC)

Q1 and Q2 are recoverable from a regenerated state (a goal that comes back
expired was cancelled; a slot re-emitted as satisfied preserved its progress),
so FSR-PC can and does answer them. Q3, Q4 and Q5 ask for a *reason*, a
*restoration condition*, and a *replacement identity* -- none of which a bare
state snapshot carries.

There is a THIRD evidence path: **provenance**. Any method may attach
`reason` / `source_event` / `predecessor_slot` / `replacement_relation` /
`restoration_condition` to the slots it emits, and every query below will read
it. `FSR-PC_provenance` does exactly that while still regenerating the complete
state. This is what makes the score representation-neutral rather than a
restatement of CoPE's operator names: if provenance closes the gap, the audit
advantage is attributable to recording provenance, not to local editing.

Queries are also scored only when the episode actually poses them: see
`answerable(applicable=...)`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

QUERIES = ("Q1_which_goal_cancelled", "Q2_which_completed_preserved",
           "Q3_why_suspended", "Q4_restore_condition", "Q5_replacement_state")


@dataclass
class AuditTrace:
    entries: List[Dict[str, Any]] = field(default_factory=list)
    path: Optional[Path] = None

    def __post_init__(self):
        self._t0 = time.perf_counter()
        if self.path is not None:
            self.path = Path(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")

    def record(self, kind: str, **fields: Any) -> Dict[str, Any]:
        e = {"kind": kind, "t": round(time.perf_counter() - self._t0, 5), **fields}
        self.entries.append(e)
        if self.path is not None:
            with open(self.path, "a") as f:
                f.write(json.dumps(e, default=str) + "\n")
        return e

    # --- evidence extraction -------------------------------------------
    def _ops(self, op: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries
                if e.get("kind") == "op" and e.get("op") == op]

    def _regenerations(self) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e.get("kind") == "state_regenerated"]

    def _provenance(self) -> List[Dict[str, Any]]:
        """Per-slot provenance from ANY method that chooses to emit it."""
        out: List[Dict[str, Any]] = []
        for r in self._regenerations():
            for s in r.get("slots", []) or []:
                p = (s.get("payload") or {}).get("provenance")
                if isinstance(p, dict):
                    out.append({"slot_id": s.get("id"), "mode": s.get("mode"),
                                **p})
        return out

    # --- the five audit queries ----------------------------------------
    def q1_cancelled_goals(self) -> List[str]:
        """Patch evidence: Expire. Regeneration evidence: a slot re-emitted
        expired that was not expired in the previous snapshot."""
        out = [e["target_id"] for e in self._ops("Expire")]
        prev: Dict[str, str] = {}
        for r in self._regenerations():
            from .naming import canonical_id
            cur = {canonical_id(s["id"]): s["mode"] for s in r.get("slots", [])}
            for cid, mode in cur.items():
                if mode == "expired" and prev.get(cid, "active") != "expired":
                    out.append(cid)
            prev = cur
        return sorted({x for x in out if x})

    def q2_preserved_completed_goals(self) -> List[str]:
        """Patch evidence: Inherit / progress_preserved. Regeneration evidence:
        a slot re-emitted carrying `completed=True`."""
        out = [e["target_id"] for e in self._ops("Inherit")]
        out += [e["slot_id"] for e in self.entries
                if e.get("kind") == "progress_preserved"]
        from .naming import canonical_id
        for r in self._regenerations():
            for s in r.get("slots", []):
                if (s.get("payload") or {}).get("completed"):
                    out.append(canonical_id(s["id"]))
        return sorted({x for x in out if x})

    def q3_why_suspended(self, slot_id: str) -> Optional[str]:
        """Patch evidence (Suspend reason) OR provenance evidence.

        A bare regenerated snapshot records that a slot IS suspended, never WHY;
        a snapshot carrying provenance does.
        """
        from .naming import canonical_id
        for e in self._ops("Suspend"):
            if canonical_id(e.get("target_id") or "") == canonical_id(slot_id):
                return e.get("reason") or "(no reason recorded)"
        for p in self._provenance():
            if (canonical_id(p.get("slot_id") or "") == canonical_id(slot_id)
                    and p.get("replacement_relation") == "suspended"
                    and p.get("reason")):
                return p["reason"]
        return None

    def q4_restore_condition(self, slot_id: str) -> Optional[Dict[str, Any]]:
        """Patch evidence (Revalidate + Restore) OR a recorded restoration
        condition in provenance."""
        from .naming import canonical_id
        for p in self._provenance():
            if (canonical_id(p.get("slot_id") or "") == canonical_id(slot_id)
                    and p.get("restoration_condition")):
                return {"revalidation": "provenance",
                        "revalidation_reason": p.get("reason"),
                        "restore_reason": p["restoration_condition"]}
        reval = None
        for e in self.entries:
            if e.get("kind") != "op":
                continue
            if canonical_id(e.get("target_id") or "") != canonical_id(slot_id):
                continue
            if e.get("op") == "Revalidate":
                reval = e
            elif e.get("op") == "Restore" and e.get("applied"):
                return {"revalidation": (reval or {}).get("result"),
                        "revalidation_reason": (reval or {}).get("reason"),
                        "restore_reason": e.get("reason")}
        return None

    def q5_replacement_for(self, slot_id: str) -> Optional[str]:
        """Patch evidence (the override edge) OR a provenance `replaces`
        relation naming the predecessor."""
        from .naming import canonical_id
        for e in self._ops("Override"):
            if canonical_id(e.get("target_id") or "") == canonical_id(slot_id):
                return e.get("new_slot_id")
        for p in self._provenance():
            if (p.get("replacement_relation") == "replaces"
                    and canonical_id(p.get("predecessor_slot") or "")
                    == canonical_id(slot_id)):
                return p.get("slot_id")
        return None

    # --- aggregation ----------------------------------------------------
    def suspended_slots(self) -> List[str]:
        from .naming import canonical_id
        out = [canonical_id(e["target_id"]) for e in self._ops("Suspend")
               if e.get("target_id")]
        for r in self._regenerations():
            out += [canonical_id(s["id"]) for s in r.get("slots", [])
                    if s.get("mode") == "suspended"]
        out += [canonical_id(p["slot_id"]) for p in self._provenance()
                if p.get("replacement_relation") in ("suspended", "restored")
                and p.get("slot_id")]
        return sorted(set(out))

    def answer_all(self) -> Dict[str, Any]:
        suspended = self.suspended_slots()
        overridden = {e["target_id"]: e.get("new_slot_id")
                      for e in self._ops("Override")}
        for p in self._provenance():
            if p.get("replacement_relation") == "replaces" and p.get("predecessor_slot"):
                overridden.setdefault(p["predecessor_slot"], p.get("slot_id"))
        return {
            "Q1_cancelled_goals": self.q1_cancelled_goals(),
            "Q2_preserved_completed_goals": self.q2_preserved_completed_goals(),
            "Q3_why_suspended": {s: self.q3_why_suspended(s) for s in suspended},
            "Q4_restore_conditions": {s: self.q4_restore_condition(s)
                                      for s in suspended},
            "Q5_replacements": overridden,
        }

    def answerable(self, applicable: Optional[Dict[str, bool]] = None
                   ) -> Dict[str, Optional[bool]]:
        """Which queries the trace can answer.

        `applicable` marks the queries the episode actually poses; inapplicable
        queries return None (not-asked) instead of False (asked and failed), so
        a condition without a suspension is not scored as an audit failure.
        """
        a = self.answer_all()
        raw = {
            "Q1_which_goal_cancelled": len(a["Q1_cancelled_goals"]) > 0,
            "Q2_which_completed_preserved":
                len(a["Q2_preserved_completed_goals"]) > 0,
            "Q3_why_suspended": any(bool(v) for v in a["Q3_why_suspended"].values()),
            "Q4_restore_condition":
                any(bool(v) for v in a["Q4_restore_conditions"].values()),
            "Q5_replacement_state": len(a["Q5_replacements"]) > 0,
        }
        if applicable is None:
            return dict(raw)
        return {q: (raw[q] if applicable.get(q, False) else None) for q in QUERIES}

    def coverage(self, applicable: Optional[Dict[str, bool]] = None
                 ) -> Optional[float]:
        """Fraction of the *applicable* queries that the trace answers."""
        ans = self.answerable(applicable)
        asked = [v for v in ans.values() if v is not None]
        if not asked:
            return None
        return sum(1 for v in asked if v) / len(asked)
