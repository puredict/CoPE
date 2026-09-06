"""Sealed, dynamic scoring. No runtime verifier output is accepted as truth.

The harness owns this object and the truth reader. Neither is passed to a method,
planner, nor policy. Python object isolation is a capability boundary, not an OS
sandbox for malicious plugins.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence


class EvaluationError(RuntimeError):
    status = "INVALID_SEALED_EVALUATION"


def record(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return deepcopy(value.to_dict())
    if is_dataclass(value):
        return asdict(value)
    return deepcopy(dict(value))


def predicate_key(predicate: str, arguments: Sequence[str]) -> str:
    import json
    return json.dumps([predicate, list(arguments)], separators=(",", ":"))


@dataclass(frozen=True)
class Evaluation:
    success: bool
    active_goals_satisfied: bool
    wrong_occurrence_execution: tuple[str, ...]
    completed_step_regression: tuple[str, ...]
    hard_constraint_violations: tuple[str, ...]
    required_events_reached: bool
    timeout: bool
    manual_intervention: bool
    active_goal_ids: tuple[str, ...]
    unsatisfied_goal_ids: tuple[str, ...]
    monitored_steps: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SealedDynamicEvaluator:
    """Independent predicate scoring against a hidden canonical ledger timeline.

    truth(predicate, arguments) must return a literal bool, raising for unsupported
    predicates. Unknown evidence cannot silently pass a hard constraint or goal.
    update_canonical is harness-only; a planner's omissions never change scoring.
    """
    version = "sealed_dynamic_v2.1"

    def __init__(self, canonical_ledger: Any, *, required_events: int):
        if required_events < 0:
            raise ValueError("negative event count")
        self._slots = self._read_slots(canonical_ledger)
        self._required_events = required_events
        self._event_ids: list[str] = []
        self._retired: set[str] = set()
        self._certificates: dict[str, dict[str, Any]] = {}
        self._wrong: set[str] = set()
        self._regressions: set[str] = set()
        self._violations: set[str] = set()
        self._completed_occurrences: set[str] = set()
        self._seen_macros: set[str] = set()
        self._monitored_steps = 0
        self._last_step = -1
        self._last_truth: dict[str, bool] = {}

    @staticmethod
    def _read_slots(ledger: Any) -> dict[str, dict[str, Any]]:
        data = record(ledger)
        slots = data.get("slots", data.get("occurrences", ()))
        if isinstance(slots, Mapping):
            slots = slots.values()
        result = {}
        for item in slots:
            slot = record(item)
            oid = slot.get("occurrence_id")
            if not isinstance(oid, str) or not oid or oid in result:
                raise EvaluationError("duplicate or missing canonical occurrence")
            result[oid] = slot
        return result

    @staticmethod
    def _active(slot: Mapping[str, Any]) -> bool:
        return slot.get("lifecycle") == "active"

    @staticmethod
    def _goal(slot: Mapping[str, Any]) -> bool:
        return slot.get("role") == "achievement_goal"

    @staticmethod
    def _truth(slot: Mapping[str, Any], reader: Callable) -> bool:
        try:
            value = reader(str(slot["predicate"]), tuple(slot.get("arguments", ())))
        except Exception as exc:
            raise EvaluationError("sealed predicate unavailable") from exc
        if type(value) is not bool:
            raise EvaluationError("sealed predicate must return bool")
        return value

    def certify_progress(self, certificate: Any) -> None:
        """Harness-only certificate from an independent sealed verifier."""
        cert = record(certificate)
        mid = str(cert["milestone_id"])
        if not cert.get("verifier_record_id"):
            raise EvaluationError("unverified milestone")
        self._certificates[mid] = cert

    def update_canonical(self, ledger: Any, *, event_id: str,
                         legitimately_invalidated_milestones: Sequence[str] = ()) -> None:
        if event_id in self._event_ids:
            raise EvaluationError("duplicate canonical event")
        new = self._read_slots(ledger)
        for oid, old in self._slots.items():
            if self._active(old) and (oid not in new or not self._active(new[oid])):
                self._retired.add(oid)
        # Old IDs cannot be brought back as new user reissues. A suspended
        # occurrence may legitimately resume, but expired/overridden ones cannot.
        for oid in self._retired:
            old = self._slots.get(oid, {})
            if old.get("lifecycle") in {"expired", "overridden"} and oid in new and self._active(new[oid]):
                raise EvaluationError("canonical reissue reused retired identity")
        for mid in legitimately_invalidated_milestones:
            self._certificates.pop(str(mid), None)
            self._completed_occurrences.discard(str(mid))
        self._slots = new
        self._event_ids.append(event_id)
        if len(self._event_ids) > self._required_events:
            raise EvaluationError("unexpected canonical event")

    def monitor(self, truth: Callable, *, step: int,
                action: Mapping[str, Any] | None = None) -> None:
        if step < self._last_step:
            raise EvaluationError("sealed monitor step regressed")
        self._last_step = step
        values = {oid: self._truth(s, truth) for oid, s in self._slots.items()
                  if self._active(s) and (self._goal(s) or s.get("hardness") == "hard")}
        if action is not None:
            oid = action.get("target_occurrence_id")
            macro = str(action.get("macro_id", ""))
            if not macro:
                raise EvaluationError("action missing macro binding")
            if oid is not None:
                slot = self._slots.get(oid)
                if slot is None or not self._active(slot) or not self._goal(slot):
                    self._wrong.add(str(oid))
                if macro not in self._seen_macros and oid in self._completed_occurrences:
                    self._regressions.add(str(oid))
            self._seen_macros.add(macro)
        for oid, slot in self._slots.items():
            if not self._active(slot):
                continue
            if slot.get("hardness") == "hard" and not self._goal(slot) and not values.get(oid, False):
                self._violations.add(oid)
            if self._goal(slot) and values.get(oid, False):
                self._completed_occurrences.add(oid)
        for mid, cert in self._certificates.items():
            if not self._truth(cert, truth):
                self._regressions.add(mid)
        self._last_truth = values
        self._monitored_steps += 1

    def evaluate(self, truth: Callable, *, timeout: bool = False,
                 manual_intervention: bool = False, required_events: int | None = None) -> Evaluation:
        self.monitor(truth, step=max(0, self._last_step))
        active = tuple(sorted(oid for oid, s in self._slots.items() if self._active(s) and self._goal(s)))
        unsatisfied = tuple(oid for oid in active if not self._last_truth[oid])
        reached = len(self._event_ids) == (self._required_events if required_events is None else required_events)
        success = not (unsatisfied or self._wrong or self._regressions or self._violations or timeout or manual_intervention) and reached
        return Evaluation(success, not unsatisfied, tuple(sorted(self._wrong)),
                          tuple(sorted(self._regressions)), tuple(sorted(self._violations)),
                          reached, bool(timeout), bool(manual_intervention), active,
                          unsatisfied, self._monitored_steps)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy({"version": self.version, "slots": self._slots,
            "required_events": self._required_events, "event_ids": self._event_ids,
            "retired": sorted(self._retired), "certificates": self._certificates,
            "wrong": sorted(self._wrong), "regressions": sorted(self._regressions),
            "violations": sorted(self._violations), "completed_occurrences": sorted(self._completed_occurrences),
            "seen_macros": sorted(self._seen_macros), "monitored_steps": self._monitored_steps,
            "last_step": self._last_step, "last_truth": self._last_truth})

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        data = deepcopy(dict(snapshot))
        if data.pop("version", None) != self.version or data["required_events"] != self._required_events:
            raise EvaluationError("sealed evaluator snapshot identity mismatch")
        for name in ("retired", "wrong", "regressions", "violations", "completed_occurrences", "seen_macros"):
            data[name] = set(data[name])
        for name, value in data.items():
            setattr(self, "_" + name, value)


FIDELITY_FIELDS = (
    "initial_facts", "active_goal_occurrence_ids", "remaining_goals", "hard_constraints",
    "soft_preferences", "forbidden_regressions", "grounding_bindings",
    "restore_eligibility", "progress_certificates", "continuation_assumptions",
)


def compare_planning_problems(proposed: Any, canonical: Any) -> dict[str, Any]:
    """Scoring-only semantic comparison, never returned to a method or planner.

    IDs/source revisions are audit metadata. List order is immaterial except
    continuation assumptions (including ordered programs). No field is filled in.
    Per-field F1 treats each complete semantic record as one item.
    """
    import json
    def key(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    actual, expected = record(proposed), record(canonical)
    fields = {}
    for name in FIDELITY_FIELDS:
        if name not in actual or name not in expected:
            raise EvaluationError("incomplete planning-fidelity input")
        left, right = actual[name], expected[name]
        if name != "continuation_assumptions" and isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
            a, b = {key(item) for item in left}, {key(item) for item in right}
            exact = a == b
            f1 = 1.0 if not a and not b else 2 * len(a & b) / (len(a) + len(b))
        else:
            exact = key(left) == key(right)
            f1 = float(exact)
        fields[name] = {"exact": exact, "f1": f1}
    return {"planning_fidelity_exact": all(v["exact"] for v in fields.values()),
            "planning_fidelity_macro_f1": sum(v["f1"] for v in fields.values()) / len(fields),
            "planning_fidelity_fields": fields}


def protected_history_corruption(before: Mapping[str, Any], after: Mapping[str, Any],
                                 *, allowed_occurrence_ids: Sequence[str]) -> bool | None:
    """Detect unrelated ledger changes where a method exposes a ledger.

    Interfaces without a ledger return unknown; absence of a representation is
    never counted as evidence that it preserved hidden history.
    """
    first, second = before.get("ledger"), after.get("ledger")
    if first is None or second is None:
        return None
    protected = set(SealedDynamicEvaluator._read_slots(first)) - set(allowed_occurrence_ids)
    a, b = SealedDynamicEvaluator._read_slots(first), SealedDynamicEvaluator._read_slots(second)
    return any(a[oid] != b.get(oid) for oid in protected)


def compare_protected_planning_projection(problem: Any, projections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Sealed, representation-neutral audit of unaffected planning obligations.

    A sealed canonical evaluator supplies explicit selectors for unaffected
    items. It must exclude event-authorized changes. This function selects from
    the submitted problem and compares; it cannot modify or complete that problem.
    Selectors use a record key (occurrence_id/milestone_id/key), string IDs, or
    mapping keys. Missing selected items fail preservation.
    """
    proposed = record(problem)
    comparisons = []
    for projection in projections:
        if set(projection) != {"field", "selector", "ids", "expected"}:
            raise EvaluationError("invalid protected projection schema")
        name, selector = projection["field"], projection["selector"]
        if name not in FIDELITY_FIELDS or name not in proposed:
            raise EvaluationError("unsupported protected planning field")
        ids = projection["ids"]
        if not isinstance(ids, (list, tuple)) or len(ids) != len(set(ids)) or not all(isinstance(i, str) for i in ids):
            raise EvaluationError("invalid protected projection identifiers")
        identifiers = set(ids)
        value = proposed[name]
        if selector == "mapping_keys":
            if not isinstance(value, Mapping):
                raise EvaluationError("protected projection expected mapping")
            selected = {k: v for k, v in value.items() if k in identifiers}
        elif selector == "string_ids":
            selected = sorted(i for i in value if i in identifiers)
        elif selector in {"occurrence_id", "milestone_id", "key"}:
            if not all(isinstance(v, Mapping) for v in value):
                raise EvaluationError("protected projection expected records")
            selected = sorted((dict(v) for v in value if v.get(selector) in identifiers), key=lambda v: str(v[selector]))
        else:
            raise EvaluationError("unsupported protected projection selector")
        import json
        normalize = lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        expected = projection["expected"]
        if selector == "string_ids":
            expected = sorted(expected)
        elif selector in {"occurrence_id", "milestone_id", "key"}:
            expected = sorted(expected, key=lambda v: str(v[selector]))
        comparisons.append({"field": name, "preserved": normalize(selected) == normalize(expected),
                            "selected": selected, "expected": expected})
    return {"history_corruption": any(not item["preserved"] for item in comparisons),
            "protected_planning_projection_checks": comparisons}
