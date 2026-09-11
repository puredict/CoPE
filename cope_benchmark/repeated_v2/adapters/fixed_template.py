"""Separate hand-written event-to-transition diagnostic.

This adapter deliberately is not a primary comparator.  It exposes the
performance ceiling and brittleness of a fixed lexical lookup table while
using the same public event boundary and atomic CoPE transaction kernel as the
learned typed editor.  Canonical event-family names and sealed targets are
never inputs.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from ..canonical import to_primitive
from ..compiler import compile_ledger
from ..enums import MethodName
from ..evidence import assert_public_safe, public_event_payload, validate_evidence_references
from ..patch_contract import PATCH_VERSION
from ..schema import EvidenceRecord, ExecutionContext, PersistentLedger
from ..state_engine import apply_cope, default_protected_ids, protected_projection_sha256


DIAGNOSTIC_METHOD = "fixed_event_template_editor"
_TRANSITIONS = frozenset({"PRESERVE", "INSERT", "SUSPEND", "OVERRIDE", "SET_PRIORITY", "EXPIRE", "RESTORE"})


@dataclass(frozen=True)
class FixedTemplateRule:
    """A lexical realization rule configured independently of sealed labels."""

    rule_id: str
    transition: str
    any_phrases: tuple[str, ...]
    required_phrases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or self.transition not in _TRANSITIONS:
            raise ValueError("invalid fixed template rule")
        phrases = self.any_phrases + self.required_phrases
        if not self.any_phrases or any(not phrase.strip() for phrase in phrases):
            raise ValueError("fixed template phrases must be nonempty")
        # Rule definitions are implementation configuration, but they still
        # must not smuggle canonical family labels or sealed fields into a
        # diagnostic transcript.
        assert_public_safe({"rule_id": self.rule_id, "phrases": phrases})

    def matches(self, text: str) -> bool:
        text = text.casefold()
        return (all(phrase.casefold() in text for phrase in self.required_phrases)
                and any(phrase.casefold() in text for phrase in self.any_phrases))


DEFAULT_FIXED_TEMPLATE_RULES = (
    FixedTemplateRule("explicit-reissue", "INSERT", ("request again", "ask again", "renew the request")),
    FixedTemplateRule("explicit-replacement", "OVERRIDE", ("instead", "replace the request", "switch the target")),
    FixedTemplateRule("explicit-cancellation", "EXPIRE", ("cancel", "no longer need", "withdraw the request")),
    FixedTemplateRule("explicit-priority", "SET_PRIORITY", ("give priority", "priority twenty", "raise priority")),
    FixedTemplateRule("persistent-preference", "INSERT", ("please prefer", "from now on", "handle gently")),
    FixedTemplateRule("availability-restored", "RESTORE", ("available again", "usable again", "path is clear", "restriction cleared")),
    FixedTemplateRule("temporary-interference", "SUSPEND", (
        "temporarily unavailable", "temporarily occluded", "not visible", "path is blocked",
        "safety boundary", "unsafe area", "moved away", "target changed",
    )),
    FixedTemplateRule("uncertain-observation", "PRESERVE", ("possibly", "uncertain", "low confidence", "may be hidden")),
)


@dataclass(frozen=True)
class FixedTemplateOutcome:
    method: str
    event_id: str
    event_index: int
    accepted: bool
    source_revision: int
    matched_rule_id: str | None
    transition: str | None
    proposal: Mapping[str, Any] | None
    rejection: str | None = None
    output_tokens: int = 0
    privileged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)


def leave_one_realization_out(rules: Sequence[FixedTemplateRule], held_out_rule_id: str) -> tuple[FixedTemplateRule, ...]:
    """Return a frozen diagnostic configuration with one realization omitted."""

    matches = [rule for rule in rules if rule.rule_id == held_out_rule_id]
    if len(matches) != 1:
        raise ValueError("held-out realization must identify exactly one configured rule")
    return tuple(rule for rule in rules if rule.rule_id != held_out_rule_id)


def _public_text(evidence: Any) -> str:
    values = [evidence.hypothesis, evidence.user_message or "", *evidence.affected_entity_hypotheses]
    return "\n".join(str(value) for value in values if value)


def _latest_commitment(public_history: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any] | None:
    for record in reversed(public_history):
        update = record.get("task_update") if isinstance(record, Mapping) else None
        if isinstance(update, Mapping) and isinstance(update.get(key), Mapping):
            return update[key]
    return None


def _new_slot(source: Mapping[str, Any], evidence: Any) -> dict[str, Any]:
    required = {"family_key", "role", "predicate", "arguments"}
    if required - source.keys():
        raise ValueError(f"public commitment update is missing {sorted(required - source.keys())}")
    return {
        "family_key": source["family_key"], "role": source["role"],
        "predicate": source["predicate"], "arguments": list(source["arguments"]),
        "lifecycle": "active", "grounding_validity": source.get("grounding_validity", "valid"),
        "priority": source.get("priority", 10), "hardness": source.get("hardness", "hard"),
        "source": source.get("source", "user"), "authority": source.get("authority", "user"),
        "restore_guard": copy.deepcopy(source.get("restore_guard", {})),
        "dependency_ids": list(source.get("dependency_ids", [])),
        "provenance": copy.deepcopy(source.get("provenance", {"public_event_id": evidence.event_id})),
        "evidence_ids": list(source.get("evidence_ids", evidence.evidence_ids)),
    }


class FixedEventTemplateEditor:
    """Deterministic diagnostic that maps visible phrases to typed transitions."""

    method = DIAGNOSTIC_METHOD
    provider_id = "deterministic_fixed_event_template_v1"

    def __init__(self, *, rules: Sequence[FixedTemplateRule] = DEFAULT_FIXED_TEMPLATE_RULES):
        self.rules = tuple(rules)
        if not self.rules or len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("fixed template rules must be nonempty and uniquely named")
        self.ledger: PersistentLedger | None = None
        self.episode_id: str | None = None
        self.last_outcome: FixedTemplateOutcome | None = None

    def start_episode(self, *, task: Mapping[str, Any], ledger: PersistentLedger,
                      context: ExecutionContext) -> None:
        assert_public_safe(task)
        assert_public_safe(context)
        self.episode_id = str(task.get("episode_id", "episode"))
        self.ledger = ledger
        self.last_outcome = None

    def _target(self, evidence: Any, transition: str) -> str:
        lifecycle = "suspended" if transition == "RESTORE" else "active"
        candidates = [slot for slot in self.ledger.slots if slot.lifecycle.value == lifecycle]
        if transition in {"SUSPEND", "OVERRIDE", "EXPIRE", "RESTORE"}:
            candidates = [slot for slot in candidates if slot.role.value == "achievement_goal"]
        elif transition == "SET_PRIORITY":
            candidates = [slot for slot in candidates if slot.role.value == "user_preference"]
        needles = {value.casefold() for value in evidence.affected_entity_hypotheses if value.strip()}
        if needles:
            matched = []
            for slot in candidates:
                haystack = {slot.occurrence_id.casefold(), slot.family_key.casefold(),
                            *(str(arg).casefold() for arg in slot.arguments)}
                if any(any(needle == item or needle in item for item in haystack) for needle in needles):
                    matched.append(slot)
            candidates = matched
        if len(candidates) != 1:
            raise ValueError("visible evidence does not identify exactly one live occurrence")
        return candidates[0].occurrence_id

    def _proposal(self, *, rule: FixedTemplateRule, evidence: Any,
                  context: ExecutionContext, public_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        transition = rule.transition
        target = None if transition in {"PRESERVE", "INSERT"} else self._target(evidence, transition)
        scope = [] if target is None else [target]
        protected = list(default_protected_ids(self.ledger, scope))
        proposal = {
            "schema_version": PATCH_VERSION, "episode_id": self.episode_id,
            "event_index": evidence.event_index, "base_revision": self.ledger.revision,
            "affected_scope": scope, "protected_ids": protected,
            "protected_projection_sha256": protected_projection_sha256(self.ledger, protected, context),
            "evidence_ids": list(evidence.evidence_ids), "checks": [], "operations": [], "confidence": 1.0,
        }
        if transition == "PRESERVE":
            return proposal
        if transition == "SUSPEND":
            guard = _latest_commitment(public_history, "restore_guard")
            if guard is None:
                raise ValueError("suspension requires a public restore_guard")
            proposal["operations"] = [{"op": "SUSPEND", "occurrence_id": target,
                                       "restore_guard": copy.deepcopy(guard), "grounding_validity": "invalid"}]
        elif transition == "RESTORE":
            slot = next(slot for slot in self.ledger.slots if slot.occurrence_id == target)
            check_id = f"fixed-check-{evidence.event_index}"
            proposal["checks"] = [{"kind": "REVALIDATE", "check_id": check_id,
                "occurrence_id": target, "evidence_ids": list(evidence.evidence_ids),
                "guard": to_primitive(slot.restore_guard), "result": True}]
            proposal["operations"] = [{"op": "RESTORE", "occurrence_id": target,
                                       "check_id": check_id, "grounding_validity": "valid"}]
        elif transition == "EXPIRE":
            proposal["operations"] = [{"op": "EXPIRE", "occurrence_id": target}]
        elif transition == "SET_PRIORITY":
            update = _latest_commitment(public_history, "priority_update")
            if update is None or type(update.get("priority")) not in (int, float):
                raise ValueError("priority transition requires a public numeric priority_update")
            proposal["operations"] = [{"op": "SET_PRIORITY", "occurrence_id": target,
                                       "priority": update["priority"]}]
        elif transition in {"INSERT", "OVERRIDE"}:
            key = "new_commitment" if transition == "INSERT" else "replacement_commitment"
            update = _latest_commitment(public_history, key)
            if update is None:
                raise ValueError(f"{transition.lower()} transition requires a public {key}")
            request_id = f"fixed-request-{evidence.event_index}"
            operation = {"op": transition, "request_id": request_id, "slot": _new_slot(update, evidence)}
            if target is not None:
                operation["occurrence_id"] = target
            proposal["operations"] = [operation]
        return proposal

    def on_event(self, *, evidence: Any, public_history: Sequence[Mapping[str, Any]],
                 context: ExecutionContext, evidence_records: Sequence[EvidenceRecord] = ()) -> FixedTemplateOutcome:
        if self.ledger is None or self.episode_id is None:
            raise ValueError("start_episode must precede event adaptation")
        public_event_payload(evidence)
        assert_public_safe(public_history)
        assert_public_safe(context)
        if evidence_records:
            validate_evidence_references(evidence, evidence_records)
        matches = [rule for rule in self.rules if rule.matches(_public_text(evidence))]
        if not matches:
            outcome = FixedTemplateOutcome(self.method, evidence.event_id, evidence.event_index, False,
                self.ledger.revision, None, None, None,
                "visible evidence matched no rule")
            self.last_outcome = outcome
            return outcome
        # Tuple order is the fixed table's explicit priority.  This permits an
        # explicit user cancellation to dominate the same "not visible"
        # symptom that otherwise selects temporary suspension.
        rule = matches[0]
        proposal = None
        try:
            proposal = self._proposal(rule=rule, evidence=evidence, context=context,
                                      public_history=public_history)
            self.ledger = apply_cope(self.ledger, proposal, evidence_records=evidence_records,
                                     context=context, event_id=evidence.event_id,
                                     event_timestamp=evidence.timestamp)
        except (ValueError, TypeError, KeyError) as exc:
            outcome = FixedTemplateOutcome(self.method, evidence.event_id, evidence.event_index, False,
                self.ledger.revision, rule.rule_id, rule.transition, proposal, str(exc))
        else:
            outcome = FixedTemplateOutcome(self.method, evidence.event_id, evidence.event_index, True,
                self.ledger.revision, rule.rule_id, rule.transition, proposal)
        self.last_outcome = outcome
        return outcome

    def compile_state(self, *, context: ExecutionContext):
        if self.ledger is None:
            raise ValueError("start_episode must precede compilation")
        # The diagnostic uses the typed carrier and common compiler but remains
        # separately labelled in its outcome/report, outside MethodName.
        return compile_ledger(ledger=self.ledger, context=context, source_method=MethodName.COPE_TYPED_EDIT)

    def snapshot(self) -> dict[str, Any]:
        return {"schema_version": "fixed-template-snapshot-v1", "episode_id": self.episode_id,
                "rules": to_primitive([asdict(rule) for rule in self.rules]), "ledger": to_primitive(self.ledger),
                "last_outcome": None if self.last_outcome is None else self.last_outcome.to_dict()}

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        if snapshot.get("schema_version") != "fixed-template-snapshot-v1":
            raise ValueError("fixed template snapshot interface mismatch")
        if snapshot.get("rules") != to_primitive([asdict(rule) for rule in self.rules]):
            raise ValueError("fixed template configuration changed on resume")
        self.episode_id = snapshot["episode_id"]
        self.ledger = PersistentLedger.from_dict(snapshot["ledger"])
        self.last_outcome = (None if snapshot["last_outcome"] is None
                             else FixedTemplateOutcome(**snapshot["last_outcome"]))


__all__ = ["DEFAULT_FIXED_TEMPLATE_RULES", "DIAGNOSTIC_METHOD", "FixedEventTemplateEditor",
           "FixedTemplateOutcome", "FixedTemplateRule", "leave_one_realization_out"]
