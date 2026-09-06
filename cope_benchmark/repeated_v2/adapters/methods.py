"""Stateful event adapters. Semantic mistakes persist; rejected edits are atomic."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any

from ..compiler import compile_directive, compile_ledger
from ..enums import MethodName
from ..evidence import assert_public_safe, public_event_payload, validate_evidence_references
from ..history import FrozenRetrieverConfig, PublicHistoryIndex
from ..parsers import ProposalError, parse_proposal
from ..prompts import (build_messages, normalized_semantic_facts, primitive, public_task,
                       scan_public_input, semantic_information_sha256)
from ..provider import ReasonerGateway
from ..schema import EvidenceRecord, ExecutionContext, HiddenCanonicalEffect, PersistentLedger


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(primitive(value), sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _initial_directive(ledger: PersistentLedger, context: ExecutionContext, method: MethodName) -> dict:
    """Project the common initial task once; never use it to repair later output."""
    problem = primitive(compile_ledger(ledger=ledger, context=context, source_method=method))
    for field in ("problem_id", "source_method", "source_revision"):
        problem.pop(field)
    problem.update(schema_version="cope-repeated-v2/directive-1", ordered_macro_plan=[])
    return problem


@dataclass(frozen=True)
class AdapterOutcome:
    method: str
    event_id: str
    event_index: int
    accepted: bool
    source_revision: int
    proposal: Mapping[str, Any] | None
    rejection: str | None = None
    privileged: bool = False
    fixture: bool = False

    def to_dict(self) -> dict[str, Any]:
        return primitive(self)


class GenerativeAdapter:
    method: MethodName

    def __init__(self, gateway: ReasonerGateway, *, evidence_records: Sequence[EvidenceRecord] = (),
                 retriever_config: FrozenRetrieverConfig | None = None, recent_window: int = 8):
        if recent_window < 1:
            raise ValueError("Recent window must be positive")
        self.gateway = gateway
        self.provider_id = gateway.config.provider
        self.evidence_records = tuple(evidence_records)
        self.retriever_config = retriever_config or FrozenRetrieverConfig()
        self.recent_window = recent_window
        self.ledger: PersistentLedger | None = None
        self.directive: dict | None = None
        self.summary = ""
        self.regenerated_fields: dict | None = None
        # Allocation metadata is out of band. It has no requirements or state
        # values and is never passed to the reasoner or planning compiler.
        self.identity_registry: dict[str, str] = {}
        self.revision = 0
        self.task: dict = {}
        self.episode_id: str | None = None
        self.public_history: list[dict] = []
        self.index = PublicHistoryIndex(self.retriever_config)
        self.last_semantic_information_sha256: str | None = None
        self.last_outcome: AdapterOutcome | None = None

    @property
    def _persistent(self) -> bool:
        return self.method in {MethodName.COPE_TYPED_EDIT, MethodName.GENERIC_PERSISTENT_EDIT,
                               MethodName.FULL_STATE_REGENERATION}

    def start_episode(self, *, task: Mapping[str, Any], ledger: PersistentLedger,
                      context: ExecutionContext) -> None:
        self.task = public_task(task)
        self.episode_id = self.task.get("episode_id", "episode")
        scan_public_input(context, generic=True)
        normalized_semantic_facts(ledger=ledger, context=context, evidence={}, public_history=[])
        self.ledger = ledger if self._persistent else None
        self.revision = ledger.revision if self._persistent else 0
        self.directive = None if self._persistent else _initial_directive(ledger, context, self.method)
        self.regenerated_fields = None
        self.identity_registry = ({slot.occurrence_id: slot.family_key for slot in ledger.slots}
                                  if self.method == MethodName.FULL_STATE_REGENERATION else {})
        self.summary = ""
        self.public_history = []
        self.index = PublicHistoryIndex(self.retriever_config)
        self.last_outcome = None
        self.last_semantic_information_sha256 = None

    def _protections(self, context: ExecutionContext) -> list[dict]:
        from ..state_engine import default_protected_ids, protected_projection_sha256

        ids = [slot.occurrence_id for slot in self.ledger.slots]
        scopes = [[], *[[identifier] for identifier in ids], *[list(pair) for pair in combinations(ids, 2)]]
        families = {}
        for slot in self.ledger.slots:
            families.setdefault(slot.family_key, []).append(slot.occurrence_id)
        scopes.extend(families.values())
        if len(ids) > 1:
            scopes.append(ids)
        result = []
        seen = set()
        for scope in scopes:
            scope = sorted(scope)
            if tuple(scope) in seen:
                continue
            seen.add(tuple(scope))
            protected = default_protected_ids(self.ledger, affected_scope=scope)
            result.append({"affected_scope": scope, "protected_ids": list(protected),
                           "protected_projection_sha256": protected_projection_sha256(self.ledger, protected, context)})
        return result

    def _memory(self, evidence: Any, context: ExecutionContext) -> dict:
        if self._persistent:
            facts = normalized_semantic_facts(ledger=self.ledger, context=context, evidence=evidence,
                                              public_history=self.public_history,
                                              regenerated_fields=self.regenerated_fields)
            self.last_semantic_information_sha256 = semantic_information_sha256(facts)
            memory = {"semantic_facts": facts}
            if self.method != MethodName.FULL_STATE_REGENERATION:
                memory["protection_options"] = self._protections(context)
            return memory
        if self.method == MethodName.FULL_HISTORY_REPLAN:
            return {"public_history": self.public_history, "execution_context": primitive(context)}
        if self.method == MethodName.RAG_REPLAN:
            self.index.ingest(self.public_history)
            return {"retrieved_public_history": self.index.retrieve(evidence),
                    "execution_context": primitive(context)}
        if self.method == MethodName.SUMMARY_MEMORY_REPLAN:
            return {"summary": self.summary, "recent_public_history": self.public_history[-self.recent_window:],
                    "execution_context": primitive(context)}
        if self.method == MethodName.SKILL_LOCAL_REPLAN:
            current_skill = context.continuation.active_skill
            skills = {skill.get("name"): skill for skill in self.task.get("skills", [])}
            local = skills.get(current_skill, {})
            return {"active_skill": current_skill,
                    "local_preconditions": local.get("preconditions", self.task.get("local_preconditions", [])),
                    "local_postconditions": local.get("effects", self.task.get("local_postconditions", [])),
                    "recent_observation_action_window": self.public_history[-self.recent_window:],
                    "current_subgoal": self.task.get("current_subgoal"),
                    "public_event_evidence": primitive(evidence),
                    "current_observations": primitive(context.beliefs)}
        raise ValueError("Unknown generative interface")

    def _messages(self, evidence: Any, context: ExecutionContext) -> list[dict[str, str]]:
        memory = self._memory(evidence, context)
        messages = build_messages(method=self.method.value, task=self.task, evidence=evidence, memory=memory)
        if self.gateway.config.setting == "token_matched":
            # The policy only truncates public history lists. Never truncate
            # schema text or selectively omit ledger fields from one interface.
            history_keys = ("public_history", "retrieved_public_history", "recent_public_history",
                            "recent_observation_action_window")
            protection_options = self._protections(context) if self._persistent else None

            def budget_count() -> int:
                if not self._persistent:
                    return self.gateway.count_tokens(messages)
                # A shared worst-case contract envelope gives equal semantic
                # truncation for the three persistent representations. Schema
                # verbosity must not selectively remove one arm's evidence.
                counts = []
                for method in (MethodName.COPE_TYPED_EDIT, MethodName.GENERIC_PERSISTENT_EDIT,
                               MethodName.FULL_STATE_REGENERATION):
                    candidate = {"semantic_facts": memory["semantic_facts"]}
                    if method != MethodName.FULL_STATE_REGENERATION:
                        candidate["protection_options"] = protection_options
                    counts.append(self.gateway.count_tokens(build_messages(
                        method=method.value, task=self.task, evidence=evidence, memory=candidate)))
                return max(counts)

            while budget_count() > self.gateway.config.max_input_tokens:
                candidates = [(memory, key) for key in history_keys if memory.get(key)]
                facts = memory.get("semantic_facts", {})
                if facts.get("relevant_trace"):
                    candidates.append((facts, "relevant_trace"))
                if not candidates:
                    if self._persistent:
                        raise ValueError("The common persistent contract envelope exceeds the input token ceiling")
                    break
                target, key = candidates[0]
                target[key] = target[key][:-1]
                messages = build_messages(method=self.method.value, task=self.task, evidence=evidence, memory=memory)
        if self._persistent:
            self.last_semantic_information_sha256 = semantic_information_sha256(memory["semantic_facts"])
        return messages

    def on_event(self, *, evidence: Any, public_history: Sequence[Mapping[str, Any]],
                 context: ExecutionContext, evidence_records: Sequence[EvidenceRecord] | None = None) -> AdapterOutcome:
        if self.episode_id is None:
            raise ValueError("start_episode must precede event adaptation")
        public_event_payload(evidence)
        scan_public_input(public_history, generic=True)
        assert_public_safe(public_history)
        scan_public_input(context, generic=True)
        records = tuple(evidence_records) if evidence_records is not None else self.evidence_records
        if records:
            validate_evidence_references(evidence, records)
        history = primitive(public_history)
        if history[:len(self.public_history)] != self.public_history:
            raise ValueError("Public history cannot rewrite its previous prefix")
        self.public_history = history
        messages = self._messages(evidence, context)
        raw = self.gateway.call(episode_id=self.episode_id, event_index=evidence.event_index, messages=messages)
        proposal = None
        try:
            proposal = parse_proposal(self.method, raw)
            if self.method == MethodName.GENERIC_PERSISTENT_EDIT:
                scan_public_input(proposal, generic=True)
            self._accept(proposal, evidence=evidence, context=context, evidence_records=records)
        except (ValueError, TypeError, KeyError) as exc:
            outcome = AdapterOutcome(self.method.value, evidence.event_id, evidence.event_index, False,
                                     self.revision, proposal, str(exc), fixture=self.gateway.logs[-1].fixture)
        else:
            outcome = AdapterOutcome(self.method.value, evidence.event_id, evidence.event_index, True,
                                     self.revision, proposal, fixture=self.gateway.logs[-1].fixture)
        self.last_outcome = outcome
        return outcome

    def _accept(self, proposal: dict, *, evidence: Any, context: ExecutionContext,
                evidence_records: Sequence[EvidenceRecord]) -> None:
        if self.method in {MethodName.COPE_TYPED_EDIT, MethodName.GENERIC_PERSISTENT_EDIT}:
            from ..state_engine import apply_cope
            from ..generic_engine import apply_generic

            if proposal["episode_id"] != self.episode_id or proposal["event_index"] != evidence.event_index:
                raise ProposalError("Proposal episode/event does not match the consumed call")
            engine = apply_cope if self.method == MethodName.COPE_TYPED_EDIT else apply_generic
            ledger = engine(self.ledger, proposal, evidence_records=evidence_records, context=context,
                            event_id=evidence.event_id, event_timestamp=evidence.timestamp)
            compile_ledger(ledger=ledger, context=context, source_method=self.method)
            self.ledger = ledger
            self.revision = ledger.revision
        elif self.method == MethodName.FULL_STATE_REGENERATION:
            from ..state_engine import apply_full_state

            if proposal["base_revision"] != self.revision:
                raise ProposalError("Regeneration base revision mismatch")
            ledger = apply_full_state(self.ledger, proposal, event_id=evidence.event_id,
                                      event_index=evidence.event_index, identity_registry=self.identity_registry)
            fields = {key: proposal[key] for key in ("initial_facts", "progress_certificates", "continuation_assumptions")}
            compile_ledger(ledger=ledger, context=context, source_method=self.method, **fields)
            self.ledger, self.regenerated_fields, self.revision = ledger, copy.deepcopy(fields), ledger.revision
            self.identity_registry.update({slot.occurrence_id: slot.family_key for slot in ledger.slots})
        else:
            directive = proposal["planning_directive"] if self.method == MethodName.SUMMARY_MEMORY_REPLAN else proposal
            if self.method == MethodName.SUMMARY_MEMORY_REPLAN:
                scan_public_input(proposal["summary"], generic=True)
            compile_directive(directive=directive, context=context, source_method=self.method,
                              source_revision=self.revision + 1)
            self.directive = copy.deepcopy(directive)
            if self.method == MethodName.SUMMARY_MEMORY_REPLAN:
                self.summary = proposal["summary"]
            self.revision += 1

    def compile_state(self, *, context: ExecutionContext):
        if self._persistent:
            return compile_ledger(ledger=self.ledger, context=context, source_method=self.method,
                                  **(self.regenerated_fields or {}))
        if self.directive is None:
            raise ValueError("No accepted planning directive exists")
        return compile_directive(directive=self.directive, context=context, source_method=self.method,
                                 source_revision=self.revision)

    def snapshot(self) -> dict:
        return {"schema_version": "adapter-snapshot-v1", "method": self.method.value,
                "task": copy.deepcopy(self.task), "episode_id": self.episode_id,
                "ledger": primitive(self.ledger), "directive": copy.deepcopy(self.directive),
                "summary": self.summary, "regenerated_fields": copy.deepcopy(self.regenerated_fields),
                "identity_registry": dict(self.identity_registry),
                "revision": self.revision, "public_history": copy.deepcopy(self.public_history),
                "retriever_config": asdict(self.retriever_config), "recent_window": self.recent_window,
                "evidence_records": primitive(self.evidence_records), "gateway": self.gateway.snapshot(),
                "last_outcome": self.last_outcome.to_dict() if self.last_outcome else None,
                "last_semantic_information_sha256": self.last_semantic_information_sha256}

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        if snapshot["method"] != self.method.value or snapshot["schema_version"] != "adapter-snapshot-v1":
            raise ValueError("Snapshot interface mismatch")
        if snapshot["retriever_config"] != asdict(self.retriever_config) or snapshot["recent_window"] != self.recent_window:
            raise ValueError("Frozen memory configuration changed on resume")
        self.task = public_task(snapshot["task"])
        self.episode_id = snapshot["episode_id"]
        self.ledger = PersistentLedger.from_dict(snapshot["ledger"]) if snapshot["ledger"] is not None else None
        self.directive = copy.deepcopy(snapshot["directive"])
        self.summary = snapshot["summary"]
        self.regenerated_fields = copy.deepcopy(snapshot["regenerated_fields"])
        self.identity_registry = dict(snapshot["identity_registry"])
        self.revision = snapshot["revision"]
        self.public_history = copy.deepcopy(snapshot["public_history"])
        scan_public_input(self.public_history, generic=True)
        self.index = PublicHistoryIndex(self.retriever_config)
        if self.method == MethodName.RAG_REPLAN:
            self.index.ingest(self.public_history)
        self.evidence_records = tuple(EvidenceRecord.from_dict(record) for record in snapshot["evidence_records"])
        self.gateway.restore(snapshot["gateway"])
        self.last_outcome = AdapterOutcome(**snapshot["last_outcome"]) if snapshot["last_outcome"] else None
        self.last_semantic_information_sha256 = snapshot["last_semantic_information_sha256"]


class CoPETypedEdit(GenerativeAdapter):
    method = MethodName.COPE_TYPED_EDIT


class GenericPersistentEdit(GenerativeAdapter):
    method = MethodName.GENERIC_PERSISTENT_EDIT


class FullStateRegeneration(GenerativeAdapter):
    method = MethodName.FULL_STATE_REGENERATION


class FullHistoryReplan(GenerativeAdapter):
    method = MethodName.FULL_HISTORY_REPLAN


class RAGReplan(GenerativeAdapter):
    method = MethodName.RAG_REPLAN


class SummaryMemoryReplan(GenerativeAdapter):
    method = MethodName.SUMMARY_MEMORY_REPLAN


class SkillLocalReplan(GenerativeAdapter):
    method = MethodName.SKILL_LOCAL_REPLAN


def _fact_key(fact: Mapping[str, Any]) -> str:
    if "key" in fact:
        key = str(fact["key"])
        return key if "(" in key else key + "()"
    if "predicate" not in fact:
        raise ValueError("A classical fact needs key or predicate")
    return str(fact["predicate"]) + "(" + ",".join(str(arg) for arg in fact.get("arguments", [])) + ")"


def _fact_value(fact: Mapping[str, Any]) -> Any:
    return fact.get("value", True)


def _monitor_fact(fact: Mapping[str, Any]) -> dict:
    if "predicate" in fact:
        return {"predicate": fact["predicate"], "arguments": list(fact.get("arguments", [])),
                "value": _fact_value(fact)}
    return _key_record(_fact_key(fact), _fact_value(fact))


def _key_record(key: str, value: Any) -> dict:
    if "(" in key and key.endswith(")"):
        predicate, arguments = key.split("(", 1)
        return {"predicate": predicate, "arguments": arguments[:-1].split(",") if arguments[:-1] else [], "value": value}
    return {"predicate": key, "arguments": [], "value": value}


class ClassicalExecutionMonitor:
    """Deterministic fact/precondition/effect monitor with bounded breadth-first search.

    Internal state has ordinary predicate facts and milestones, with no commitment
    lifecycle, provenance graph or persistent occurrence identity. Planner output
    gets transient target labels only to satisfy the common downstream contract.
    """
    method = MethodName.CLASSICAL_EXECUTION_MONITOR
    provider_id = "deterministic_classical_monitor"

    def __init__(self, *, search_node_budget: int = 4096):
        if search_node_budget < 1:
            raise ValueError("Search budget must be positive")
        self.search_node_budget = search_node_budget
        self.task: dict = {}
        self.facts: dict[str, Any] = {}
        self.goals: list[dict] = []
        self.completed_milestones: dict[str, dict] = {}
        self.directive: dict | None = None
        self.revision = 0
        self.last_outcome: AdapterOutcome | None = None

    def start_episode(self, *, task: Mapping[str, Any], ledger: PersistentLedger, context: ExecutionContext) -> None:
        self.task = public_task(task)
        initial = _initial_directive(ledger, context, self.method)
        # Initial ledger semantics are supplied to every arm once. Strip its
        # commitment metadata immediately; this monitor retains ordinary facts.
        if "goals" not in self.task and "remaining_goals" not in self.task:
            self.task["goals"] = [_monitor_fact(goal) for goal in initial["remaining_goals"]]
        self.task.setdefault("initial_facts", initial["initial_facts"])
        self.task.setdefault("hard_constraints", [_monitor_fact(item) for item in initial["hard_constraints"]])
        self.task.setdefault("soft_preferences", [
            {**_monitor_fact(item), "weight": item.get("weight", item.get("priority", 0))}
            for item in initial["soft_preferences"]])
        self.task.setdefault("grounding_bindings", [_monitor_fact(item) for item in initial["grounding_bindings"]])
        self.facts = {_fact_key(fact): _fact_value(fact) for fact in self.task.get("initial_facts", [])}
        # Occurrence labels in a common task description are not carried into
        # this baseline's state; goals are plain predicates/arguments.
        self.goals = [_monitor_fact(goal) for goal in self.task.get("goals", self.task.get("remaining_goals", []))]
        self.completed_milestones = {}
        self.directive = None
        self.revision = 0
        self.last_outcome = None
        self._observe(context)
        self._rebuild_directive(context)

    def _observe(self, context: ExecutionContext) -> None:
        scan_public_input(context, generic=True)
        observed = set()
        for fact in context.beliefs:
            if fact.confidence >= 0.5:
                key = _fact_key({"key": fact.key})
                self.facts[key] = primitive(fact.value)
                observed.add(key)
        for certificate in context.progress:
            if certificate.currently_preserved and certificate.satisfaction.value == "satisfied":
                self.completed_milestones[certificate.milestone_id] = primitive(certificate)
                self.facts[_fact_key(primitive(certificate))] = True
            else:
                self.completed_milestones.pop(certificate.milestone_id, None)
                key = _fact_key(primitive(certificate))
                if key not in observed:
                    self.facts.pop(key, None)

    @staticmethod
    def _satisfied(facts: Mapping[str, Any], goals: Sequence[Mapping]) -> bool:
        return all(facts.get(_fact_key(goal), object()) == _fact_value(goal) for goal in goals)

    def _plan(self) -> tuple[list[str], str]:
        skills = self.task.get("skills", [])
        constraints = self.task.get("hard_constraints", [])
        start = copy.deepcopy(self.facts)
        queue = deque([(start, [])])
        visited = {_digest(start)}
        expanded = 0
        while queue and expanded < self.search_node_budget:
            state, plan = queue.popleft()
            expanded += 1
            if self._satisfied(state, self.goals):
                return plan, "goal_satisfied"
            for skill in skills:
                if not self._satisfied(state, skill.get("preconditions", [])):
                    continue
                next_state = dict(state)
                for effect in skill.get("effects", []):
                    next_state[_fact_key(effect)] = _fact_value(effect)
                for effect in skill.get("delete_effects", []):
                    next_state[_fact_key(effect)] = False
                if any(next_state.get(_fact_key(c), object()) != _fact_value(c) for c in constraints):
                    continue
                if any(next_state.get(_fact_key(c), object()) is False
                       for c in self.completed_milestones.values()):
                    continue
                digest = _digest(next_state)
                if digest not in visited:
                    visited.add(digest)
                    queue.append((next_state, plan + [skill["name"]]))
        return [], "search_budget_exhausted" if queue else "no_applicable_plan"

    def on_event(self, *, evidence: Any, public_history: Sequence[Mapping[str, Any]],
                 context: ExecutionContext, evidence_records: Sequence[EvidenceRecord] = ()) -> AdapterOutcome:
        public_event_payload(evidence)
        scan_public_input(public_history, generic=True)
        assert_public_safe(public_history)
        if evidence_records:
            validate_evidence_references(evidence, evidence_records)
        self._observe(context)
        # Structured public user/task messages can change ordinary PDDL targets;
        # no hidden event cause or canonical effect is used to select a rule.
        for record in public_history:
            if "task_update" in record:
                update = public_task(record["task_update"])
                self.task.update(update)
                if "goals" in update or "remaining_goals" in update:
                    self.goals = [_monitor_fact(goal) for goal in update.get("goals", update.get("remaining_goals", []))]
        self.revision += 1
        self._rebuild_directive(context)
        self.last_outcome = AdapterOutcome(self.method.value, evidence.event_id, evidence.event_index,
                                           True, self.revision, copy.deepcopy(self.directive))
        return self.last_outcome

    def _rebuild_directive(self, context: ExecutionContext) -> None:
        plan, status = self._plan()
        targets = [{**goal, "occurrence_id": f"monitor-target-{i}"} for i, goal in enumerate(self.goals)]
        skills = {skill["name"]: skill for skill in self.task.get("skills", [])}
        macro_steps = []
        for index, name in enumerate(plan):
            skill = skills[name]
            effects = [_monitor_fact(effect) for effect in skill.get("effects", [])]
            effects += [{**_monitor_fact(effect), "value": False} for effect in skill.get("delete_effects", [])]
            matching = next((target for target in targets if any(
                _fact_key(target) == _fact_key(effect) and _fact_value(target) == _fact_value(effect)
                for effect in effects)), targets[0] if targets else None)
            if matching is None:
                raise ValueError("A skill plan must be attached to a requested target")
            macro_steps.append({"action_id": f"monitor-action-{index}", "skill": name,
                "target_occurrence_id": matching["occurrence_id"],
                "preconditions": [_monitor_fact(fact) for fact in skill.get("preconditions", [])], "effects": effects})
        self.directive = {
            "schema_version": "cope-repeated-v2/directive-1",
            "initial_facts": [_key_record(key, value) for key, value in sorted(self.facts.items())],
            "active_goal_occurrence_ids": [target["occurrence_id"] for target in targets],
            "remaining_goals": targets, "hard_constraints": self.task.get("hard_constraints", []),
            "soft_preferences": self.task.get("soft_preferences", []),
            "forbidden_regressions": sorted(self.completed_milestones),
            "grounding_bindings": self.task.get("grounding_bindings", []), "restore_eligibility": [],
            "progress_certificates": list(self.completed_milestones.values()),
            "continuation_assumptions": {**primitive(context.continuation), "monitor_status": status,
                                         "execution_mode": "explicit_skills"},
            "ordered_macro_plan": macro_steps,
        }

    def compile_state(self, *, context: ExecutionContext):
        if self.directive is None:
            raise ValueError("No monitor event has been processed")
        return compile_directive(directive=self.directive, context=context, source_method=self.method,
                                 source_revision=self.revision)

    def snapshot(self) -> dict:
        return {"schema_version": "monitor-snapshot-v1", "task": copy.deepcopy(self.task),
                "facts": copy.deepcopy(self.facts), "goals": copy.deepcopy(self.goals),
                "completed_milestones": copy.deepcopy(self.completed_milestones),
                "directive": copy.deepcopy(self.directive), "revision": self.revision,
                "search_node_budget": self.search_node_budget}

    def restore(self, snapshot: Mapping) -> None:
        if snapshot["schema_version"] != "monitor-snapshot-v1" or snapshot["search_node_budget"] != self.search_node_budget:
            raise ValueError("Monitor snapshot/configuration mismatch")
        self.task = public_task(snapshot["task"])
        self.facts = copy.deepcopy(snapshot["facts"])
        self.goals = copy.deepcopy(snapshot["goals"])
        self.completed_milestones = copy.deepcopy(snapshot["completed_milestones"])
        self.directive = copy.deepcopy(snapshot["directive"])
        self.revision = snapshot["revision"]


class OraclePersistentUpdate:
    """Explicit privileged setter for diagnostic upper-bound fixtures only."""
    method = MethodName.ORACLE_PERSISTENT_UPDATE
    provider_id = "privileged_oracle_fixture"

    def __init__(self):
        self.ledger: PersistentLedger | None = None
        self.last_outcome: AdapterOutcome | None = None

    def start_episode(self, *, task: Mapping[str, Any], ledger: PersistentLedger, context: ExecutionContext) -> None:
        self.ledger = ledger
        self.last_outcome = None

    def on_event(self, *, evidence: Any, public_history: Sequence[Mapping[str, Any]], context: ExecutionContext,
                 canonical_ledger: PersistentLedger, hidden_effect: HiddenCanonicalEffect) -> AdapterOutcome:
        if type(hidden_effect) is not HiddenCanonicalEffect or type(canonical_ledger) is not PersistentLedger:
            raise ValueError("Oracle updates require explicitly typed privileged inputs")
        if hidden_effect.event_id != evidence.event_id:
            raise ValueError("Oracle effect/event mismatch")
        if self.ledger is None or canonical_ledger.revision <= self.ledger.revision:
            raise ValueError("Oracle canonical state must advance revision")
        self.ledger = canonical_ledger
        self.last_outcome = AdapterOutcome(self.method.value, evidence.event_id, evidence.event_index, True,
            canonical_ledger.revision, {"canonical_ledger": primitive(canonical_ledger),
                                       "hidden_effect": primitive(hidden_effect), "privileged": True}, privileged=True, fixture=True)
        return self.last_outcome

    def compile_state(self, *, context: ExecutionContext):
        if self.ledger is None:
            raise ValueError("No oracle state exists")
        return compile_ledger(ledger=self.ledger, context=context, source_method=self.method)

    def snapshot(self) -> dict:
        return {"schema_version": "oracle-snapshot-v1", "privileged": True,
                "ledger": primitive(self.ledger), "last_outcome": primitive(self.last_outcome)}

    def restore(self, snapshot: Mapping) -> None:
        if snapshot["schema_version"] != "oracle-snapshot-v1" or snapshot["privileged"] is not True:
            raise ValueError("Oracle snapshot must be explicitly privileged")
        self.ledger = PersistentLedger.from_dict(snapshot["ledger"]) if snapshot["ledger"] else None
        self.last_outcome = AdapterOutcome(**snapshot["last_outcome"]) if snapshot["last_outcome"] else None


_ADAPTERS = {
    MethodName.COPE_TYPED_EDIT: CoPETypedEdit, MethodName.GENERIC_PERSISTENT_EDIT: GenericPersistentEdit,
    MethodName.FULL_STATE_REGENERATION: FullStateRegeneration, MethodName.FULL_HISTORY_REPLAN: FullHistoryReplan,
    MethodName.RAG_REPLAN: RAGReplan, MethodName.SUMMARY_MEMORY_REPLAN: SummaryMemoryReplan,
    MethodName.SKILL_LOCAL_REPLAN: SkillLocalReplan, MethodName.CLASSICAL_EXECUTION_MONITOR: ClassicalExecutionMonitor,
    MethodName.ORACLE_PERSISTENT_UPDATE: OraclePersistentUpdate,
}


def create_adapter(method: MethodName | str, *, gateway: ReasonerGateway | None = None, **kwargs):
    cls = _ADAPTERS[MethodName(method)]
    if issubclass(cls, GenerativeAdapter):
        if gateway is None:
            raise ValueError("Generative interfaces require the common reasoner gateway")
        return cls(gateway, **kwargs)
    if gateway is not None:
        raise ValueError("Deterministic interfaces must not consume reasoner calls")
    return cls(**kwargs)
