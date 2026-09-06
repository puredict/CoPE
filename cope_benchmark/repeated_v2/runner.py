"""Continuous v2 runtime, common action executor and verified boundary resume.

Environment, detector and sealed truth are harness capabilities. Methods see
public evidence/context; planners see compiled accepted semantics; policies see
only sensory observations and compiled instructions. No oracle reset path exists.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import importlib
import json
import random
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from .dynamic_evaluator import SealedDynamicEvaluator, record
from .continuation_backend import RecoveryGateBlocked, UnsupportedPlanningSemantics


class RuntimeBlocked(RuntimeError):
    def __init__(self, status: str, detail: str):
        self.status = status
        super().__init__(f"{status}: {detail}")


def json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return json_value(value.to_dict())
    if is_dataclass(value):
        return {k: json_value(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    if value is None or type(value) in (str, bool, int, float):
        return value
    if hasattr(value, "value"):
        return json_value(value.value)
    raise TypeError(f"nonserializable runtime value: {type(value).__name__}")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(json_value(value), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _tuple_tree(value):
    return tuple(_tuple_tree(x) for x in value) if isinstance(value, list) else value


def capture_rng() -> dict[str, Any]:
    result = {"python": json_value(random.getstate())}
    try:
        import numpy as np
        name, keys, pos, gauss, cache = np.random.get_state()
        result["numpy"] = [name, keys.tolist(), pos, gauss, cache]
    except ImportError:
        pass
    return result


def restore_rng(state: Mapping[str, Any]) -> None:
    random.setstate(_tuple_tree(state["python"]))
    if "numpy" in state:
        import numpy as np
        name, keys, pos, gauss, cache = state["numpy"]
        np.random.set_state((name, np.asarray(keys, dtype="uint32"), pos, gauss, cache))


@dataclass(frozen=True)
class ObservationReceipt:
    payload: Mapping[str, Any]
    observation_ref: str
    version: int
    policy_step: int


@dataclass(frozen=True)
class InjectionReceipt:
    """Private harness record. Only public_evidence enters an ordinary method."""
    public_evidence: Any
    canonical_ledger: Any
    legitimately_invalidated_milestones: tuple[str, ...] = ()
    evidence_records: tuple[Any, ...] = ()
    affected_occurrence_ids: tuple[str, ...] = ()
    hidden_effect: Any = None


class RuntimeEnvironment(Protocol):
    provider_id: str
    def reset(self, *, task: Mapping, initial_state_id: int, seed: int) -> ObservationReceipt: ...
    def observe(self) -> ObservationReceipt: ...
    def snapshot(self) -> Mapping: ...
    def restore(self, snapshot: Mapping) -> None: ...
    def step(self, action: Sequence[float]) -> ObservationReceipt: ...
    def execute_macro(self, macro: Mapping) -> ObservationReceipt: ...
    def inject(self, event: Any) -> InjectionReceipt: ...
    def trigger_context(self, *, previous_event_step: int | None) -> Any: ...
    def public_context(self, observation: ObservationReceipt, previous: Any) -> Any: ...
    def macro_complete(self, macro: Mapping, context: Any) -> bool: ...
    def sealed_predicate(self, predicate: str, arguments: Sequence[str]) -> bool: ...
    def sealed_progress(self) -> Sequence[Any]: ...
    def sealed_planning_problem(self) -> Any: ...
    def sealed_protected_projection(self) -> Sequence[Mapping]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class RuntimeConfig:
    protocol: str
    max_policy_steps: int = 260
    phase: str = "pilot"
    action_dimension: int = 7
    action_chunk_horizon: int = 8
    fallback: str = "retain_and_replan"
    fixture: bool = False
    information_condition: str = "evidence_matched"

    def __post_init__(self):
        if self.protocol not in {"controlled", "end_to_end"}:
            raise ValueError("unknown protocol")
        if self.phase not in {"pilot", "development", "formal", "test"}:
            raise ValueError("unknown phase")
        if self.max_policy_steps <= 0 or self.action_dimension <= 0 or self.action_chunk_horizon <= 0:
            raise ValueError("invalid action budget")
        if self.fallback not in {"retain_and_replan", "terminate"}:
            raise ValueError("fallback must be frozen")
        if self.phase == "formal" and self.fixture:
            raise RuntimeBlocked("INVALID_FIXTURE_FORMAL_RUN", "fixtures are never formal evidence")
        if self.information_condition not in {"evidence_matched", "token_matched"}:
            raise ValueError("unknown information condition")


class JournaledReasoner:
    """Durably records the exact provider request before its only invocation."""
    def __init__(self, reasoner: Any, journal: Any, guard: Callable[[], None]):
        self.reasoner, self.journal, self.guard = reasoner, journal, guard
        self.key = None
        self.calls_this_event = 0
        self.last_seconds = None

    def bind(self, key) -> None:
        self.key, self.calls_this_event = key, 0
        self.last_seconds = None

    def count_tokens(self, messages):
        return self.reasoner.count_tokens(messages)

    def complete(self, *, messages, config):
        from .provider import ReasonerResponse
        if self.key is None or self.calls_this_event:
            raise RuntimeBlocked("INVALID_EVENT_CALL_BUDGET", "one adaptation call per event")
        self.calls_this_event += 1
        self.guard()
        request = {"messages": json_value(messages), "config": json_value(config)}
        def invoke(_):
            self.guard()
            value = self.reasoner.complete(messages=messages, config=config)
            return json_value(value)
        response = self.journal.call_once(self.key, request, invoke)
        self.last_seconds = self.journal.invocation_seconds(self.key)
        return ReasonerResponse(**response)


class CommonExecutor:
    """Exactly one common executor for all methods, with occurrence-bound traces."""
    version = "common_executor_v2.1"

    def __init__(self, *, environment: RuntimeEnvironment, config: RuntimeConfig,
                 policy=None, guard=lambda: None, planner=None):
        self.environment, self.config, self.policy, self.guard = environment, config, policy, guard
        self.planner = planner
        self.plan: list[dict] = []
        self.cursor = 0
        self.chunk: list[list[float]] = []
        self.trace: list[dict] = []
        self.plan_number = 0
        self.started = False
        self.problem_sha256 = None
        if config.protocol == "end_to_end":
            if policy is None:
                raise RuntimeBlocked("BLOCKED_VLA_ADAPTER_UNAVAILABLE", "no VLA adapter supplied")
            from .vla_adapter import require_vla_adapter
            require_vla_adapter(policy, formal=not config.fixture)

    def begin(self, plan: Any, problem: Any) -> None:
        data = json_value(plan)
        if not isinstance(data, dict):
            raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "planner must return an execution plan")
        if data.get("problem_id") != problem.problem_id or data.get("planning_problem_sha256") != digest(problem):
            raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "plan belongs to a different accepted problem")
        self.problem_sha256 = digest(problem)
        if data.get("status", "OK") not in {"OK", "READY", "SOLVED", "PLAN_READY", "planned"}:
            raise RuntimeBlocked("METHOD_PLANNING_FAILURE", str(data.get("status")))
        actions = data.get("macro_actions", data.get("actions", data.get("steps")))
        if actions is None:
            raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "plan has no explicit macro actions")
        active = set(problem.active_goal_occurrence_ids)
        normalized = []
        for index, macro in enumerate(actions):
            macro = json_value(macro)
            oid = macro.get("target_occurrence_id", macro.get("occurrence_id"))
            # A wrong occurrence is kept in the trace for sealed scoring; do not
            # silently substitute an active target or infer one from task identity.
            if oid is None and not macro.get("recovery", False):
                raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "macro has no occurrence binding")
            instruction = macro.get("compiled_instruction", macro.get("instruction"))
            if instruction is None:
                raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "macro has no explicit instruction")
            if isinstance(instruction, str):
                instruction = {"instruction": instruction}
            if not isinstance(instruction, Mapping):
                raise RuntimeBlocked("INVALID_EXECUTION_PLAN", "instruction must be text or a public mapping")
            normalized.append({**macro, "target_occurrence_id": oid,
                "compiled_instruction": instruction,
                "macro_id": f"plan{self.plan_number}/macro{index}",
                "target_in_accepted_active_set": oid in active})
        self.plan = normalized
        self.plan_number += 1
        self.cursor, self.chunk, self.started = 0, [], False

    @property
    def finished(self) -> bool:
        return self.cursor >= len(self.plan)

    def step(self, observation: ObservationReceipt, context: Any) -> tuple[ObservationReceipt, dict | None]:
        if self.finished:
            return observation, None
        macro = self.plan[self.cursor]
        if not self.started:
            if hasattr(self.planner, "before_macro"):
                self.planner.before_macro(macro)
            if self.policy is not None:
                self.policy.begin_subgoal(deepcopy(macro["compiled_instruction"]))
            self.started = True
        before = observation.policy_step
        self.guard()
        start = time.monotonic()
        if self.config.protocol == "controlled":
            updated = self.environment.execute_macro(deepcopy(macro))
            values, raw_values, action_space = None, None, None
        else:
            from .vla_adapter import public_observation, validate_action_chunk, to_environment_action
            if not self.chunk:
                self.guard()
                chunk = self.policy.act(public_observation(observation.payload))
                horizon = min(self.config.action_chunk_horizon,
                              self.policy.identity.get("max_chunk_horizon", self.config.action_chunk_horizon))
                values_chunk = validate_action_chunk(chunk, action_dim=self.config.action_dimension,
                                                     max_horizon=horizon)
                self.chunk = [list(row) for row in values_chunk.values]
            raw_values = list(self.chunk.pop(0))
            values = list(to_environment_action(self.policy, raw_values))
            action_space = self.policy.identity["action_space"]
            updated = self.environment.step(values)
        if updated.policy_step != before + 1:
            raise RuntimeBlocked("INVALID_POLICY_STEP_ACCOUNTING", "every action consumes exactly one counted step")
        entry = {"step": updated.policy_step, "macro_id": macro["macro_id"],
            "planning_problem_sha256": self.problem_sha256,
            "target_occurrence_id": macro["target_occurrence_id"], "values": values,
            "raw_values": raw_values, "action_space": action_space,
            "compiled_instruction": macro["compiled_instruction"],
            "observation_before": observation.observation_ref,
            "observation_after": updated.observation_ref,
            "execution_kind": "controlled_mechanism" if self.config.protocol == "controlled" else "learned_vla",
            "inference_and_step_seconds": time.monotonic() - start}
        self.trace.append(entry)
        return updated, entry

    def observe_completion(self, context: Any) -> None:
        if not self.finished and self.started and self.environment.macro_complete(self.plan[self.cursor], context):
            if self.plan[self.cursor].get("recovery"):
                self.planner.complete_recovery_stage(stage_id=self.plan[self.cursor]["stage_id"], context=context)
            self.cursor += 1
            self.chunk, self.started = [], False

    def snapshot(self) -> dict:
        policy = None
        if self.policy is not None:
            from .vla_adapter import snapshot_adapter
            policy = snapshot_adapter(self.policy)
        return json_value({"plan": self.plan, "cursor": self.cursor, "chunk": self.chunk,
            "trace": self.trace, "plan_number": self.plan_number, "started": self.started,
            "problem_sha256": self.problem_sha256, "policy": policy})

    def restore(self, data: Mapping) -> None:
        for key in ("plan", "cursor", "chunk", "trace", "plan_number", "started", "problem_sha256"):
            setattr(self, key, deepcopy(data[key]))
        if self.policy is not None:
            from .vla_adapter import restore_adapter
            restore_adapter(self.policy, data["policy"])


class EpisodeRunner:
    """Run one independent (master episode, method) continuous trajectory.

    Each completed boundary snapshot contains its pending result. This closes
    the snapshot/result crash gap without repeating a provider call. Mid-segment
    simulator work may be replayed from a verified boundary; final traces contain
    only the recovered trajectory. Never use this rollback runner on real robots.
    """
    def __init__(self, *, config: RuntimeConfig, environment: RuntimeEnvironment,
                 method: Any, planner: Any, journal: Any, policy=None,
                 frozen_identity: Mapping | None = None,
                 current_identity: Callable[[], Mapping] | None = None):
        self.config, self.env, self.method, self.planner, self.journal = config, environment, method, planner, journal
        self.frozen_identity = deepcopy(dict(frozen_identity or {}))
        self.current_identity = current_identity
        if config.phase == "formal" and (not self.frozen_identity or current_identity is None):
            raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "formal identity and live verifier are required")
        self.executor = CommonExecutor(environment=environment, config=config, policy=policy, guard=self._guard, planner=planner)
        self.journal.freeze_metadata(self.frozen_identity or {"phase": config.phase, "protocol": config.protocol, "fixture": config.fixture})
        self._proxy = None
        gateway = getattr(method, "gateway", None)
        if gateway is not None:
            self._proxy = JournaledReasoner(gateway.reasoner, journal, self._guard)
            gateway.reasoner = self._proxy

    def _guard(self):
        if self.current_identity is not None and self.config.phase != "formal":
            self.journal.verify_metadata(self.current_identity())
        if self.config.phase == "formal":
            try:
                from .freeze import validate_frozen_bundle
            except ImportError as exc:
                raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "phase4 freeze validator unavailable") from exc
            validate_frozen_bundle(self.frozen_identity, current_identity=self.current_identity)
            self.journal.verify_metadata(self.frozen_identity)
            if getattr(self.planner, "uses_hidden_truth", None) is not False:
                raise RuntimeBlocked("INVALID_PRIVILEGED_PLANNER", "planner reads hidden truth")
            if self.executor.policy is not None and self.executor.policy.identity["checkpoint_sha256"] != self.frozen_identity["identities"]["vla"]["checkpoint_sha256"]:
                raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "VLA checkpoint differs from frozen identity")
            gateway = getattr(self.method, "gateway", None)
            if gateway is not None:
                markers = ("fake", "mock", "scripted", "oracle", "fixture", "noop", "dry_run")
                identifiers = [gateway.config.provider, gateway.config.model, type(self._proxy.reasoner).__name__]
                if any(marker in str(value).lower() for value in identifiers for marker in markers):
                    raise RuntimeBlocked("INVALID_FORMAL_REASONER", "fixture or privileged reasoner")
                expected = self.frozen_identity["identities"]["reasoner"]
                if gateway.config.provider != expected["provider_id"] or gateway.config.model != expected["model_id"]:
                    raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "reasoner model differs from freeze")

    def _key(self, index):
        return (self.config.protocol, self.episode_id, self.method_name, index)

    def _snapshot(self, *, index, label, pending_result=None):
        payload = {"runtime_version": "continuous_v2.1", "identity": self.identity,
            "environment": json_value(self.env.snapshot()), "rng": capture_rng(),
            "method": self.method.snapshot(), "context": json_value(self.context),
            "observation": json_value(self.observation), "executor": self.executor.snapshot(),
            "evaluator": self.evaluator.snapshot(), "history": self.history,
            "delivered": self.delivered, "previous_event_step": self.previous_event_step,
            "pending_result": pending_result, "index": index}
        payload["planning_problem"] = json_value(self.problem)
        payload["planning_seconds"] = self.planning_seconds
        payload["pre_execution_metrics"] = self.pre_execution_metrics
        payload["execution_started_at"] = self.execution_started_at
        payload["adaptation_metrics"] = self.adaptation_metrics
        if hasattr(self.planner, "snapshot"):
            payload["planner"] = json_value(self.planner.snapshot())
        self.journal.save_snapshot(self._key(index), payload, label=label)
        return digest(payload)

    def _restore(self, payload):
        from .schema import ExecutionContext, PlanningProblem
        if payload["identity"] != self.identity:
            raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "episode identity changed on resume")
        self._guard()
        self.env.restore(payload["environment"])
        restore_rng(payload["rng"])
        self.method.restore(payload["method"])
        self.context = ExecutionContext.from_dict(payload["context"])
        self.problem = PlanningProblem.from_dict(payload["planning_problem"]) if payload["planning_problem"] is not None else None
        self.planning_seconds = payload["planning_seconds"]
        self.pre_execution_metrics = deepcopy(payload.get("pre_execution_metrics", {}))
        self.execution_started_at = payload.get("execution_started_at")
        self.adaptation_metrics = deepcopy(payload.get("adaptation_metrics", {}))
        self.observation = ObservationReceipt(**payload["observation"])
        self.executor.restore(payload["executor"])
        self.evaluator.restore(payload["evaluator"])
        self.history = deepcopy(payload["history"])
        self.delivered = payload["delivered"]
        self.previous_event_step = payload["previous_event_step"]
        if "planner" in payload:
            if not hasattr(self.planner, "restore"):
                raise RuntimeBlocked("BLOCKED_PLANNER_RESUME_UNAVAILABLE", "planner has no restore implementation")
            self.planner.restore(payload["planner"])
        actual = self.env.observe()
        if (actual.policy_step, actual.version, actual.observation_ref) != (self.observation.policy_step, self.observation.version, self.observation.observation_ref):
            raise RuntimeBlocked("INVALID_SNAPSHOT_RESTORE", "environment did not restore exact boundary")
        if digest(actual.payload) != digest(self.observation.payload):
            raise RuntimeBlocked("INVALID_SNAPSHOT_RESTORE", "restored sensory observation differs")

    def _observe(self, action=None):
        self.context = self.env.public_context(self.observation, self.context)
        for cert in self.env.sealed_progress():
            self.evaluator.certify_progress(cert)
        self.evaluator.monitor(self.env.sealed_predicate, step=self.observation.policy_step, action=action)
        self.executor.observe_completion(self.context)

    def _compile(self):
        self._guard()
        start_compile = time.monotonic()
        self.problem = None
        self.planning_seconds = 0.0
        self.pre_execution_metrics = {}
        self.execution_started_at = None
        try:
            problem = self.method.compile_state(context=self.context)
        except ValueError as exc:
            raise RuntimeBlocked("METHOD_COMPILATION_FAILURE", type(exc).__name__) from exc
        self.problem = problem
        self.pre_execution_metrics = {"compilation_seconds": time.monotonic() - start_compile}
        if hasattr(self.env, "sealed_planning_problem"):
            from .dynamic_evaluator import compare_planning_problems
            canonical = self.env.sealed_planning_problem()
            self.pre_execution_metrics.update(compare_planning_problems(problem, canonical))
            self.pre_execution_metrics.update({"pre_execution_fidelity_problem_sha256": digest(problem),
                "fidelity_evaluated_at": time.monotonic(), "canonical_problem_sha256": digest(canonical)})
        elif self.config.phase == "formal":
            raise RuntimeBlocked("BLOCKED_SEALED_PLANNING_EVALUATOR_UNAVAILABLE", "formal fidelity evaluator required")
        if hasattr(self.env, "sealed_protected_projection"):
            from .dynamic_evaluator import compare_protected_planning_projection
            projection = self.env.sealed_protected_projection()
            assessment = compare_protected_planning_projection(problem, projection)
            self.adaptation_metrics.update(assessment)
            self.adaptation_metrics["protected_planning_projection_sha256"] = digest(projection)
        elif self.config.phase == "formal":
            raise RuntimeBlocked("BLOCKED_MECHANISM_MEASUREMENT_UNAVAILABLE", "sealed representation-neutral protection audit required")
        self.execution_started_at = None
        start = time.monotonic()
        try:
            plan = self.planner.solve(problem=problem, context=self.context)
        except (UnsupportedPlanningSemantics, RecoveryGateBlocked) as exc:
            raise RuntimeBlocked("METHOD_PLANNING_FAILURE", type(exc).__name__) from exc
        finally:
            self.planning_seconds = time.monotonic() - start
        self.executor.begin(plan, problem)

    def _boundary_result(self, index, *, status="COMPLETED", timeout=False):
        evaluation = self.evaluator.evaluate(self.env.sealed_predicate, timeout=timeout,
            manual_intervention=bool(getattr(self.env, "manual_intervention", False)), required_events=index)
        outcomes = evaluation.to_dict()
        outcomes["success"] = evaluation.success and status == "COMPLETED"
        result = {"protocol": self.config.protocol, "master_episode_id": self.episode_id,
            "method": self.method_name, "event_index": index, "status": status,
            "checkpoint": index in (0, 1, 2, 4, 8), "phase": self.config.phase,
            "fixture": self.config.fixture,
            "final_active_task_success_after_last_event": outcomes["success"],
            "success": outcomes["success"], "evaluation": outcomes,
            "planning_problem": json_value(self.problem), "planning_problem_sha256": digest(self.problem),
            "execution_problem_sha256": self.executor.problem_sha256 if self.execution_started_at is not None else None,
            "action_trace_sha256": digest(self.executor.trace), "action_count": len(self.executor.trace),
            "high_level_calls": 1 if index and self._proxy is not None and self.journal.phase(self._key(index)) in {"response", "result"} else 0,
            "planning_seconds": self.planning_seconds,
            "method_state_sha256": digest(self.method.snapshot())}
        result.update(self._row_identity())
        result["metrics"] = {**self.pre_execution_metrics, **self.adaptation_metrics}
        result["execution_started_at"] = self.execution_started_at
        if "fidelity_evaluated_at" in self.pre_execution_metrics:
            result["metrics"]["execution_started_at"] = self.execution_started_at
            result["metrics"]["fidelity_precedes_execution"] = (self.execution_started_at is not None and
                self.pre_execution_metrics["fidelity_evaluated_at"] <= self.execution_started_at)
        self._snapshot(index=index, label="completed", pending_result=result)
        self.journal.record_result(self._key(index), result)
        return result

    def _row_identity(self):
        return {"information_condition": self.config.information_condition,
                "master_schedule_sha256": self.identity["schedule_sha256"],
                "freeze_sha256": self.frozen_identity.get("bundle_sha256"),
                "privileged": self.method_name == "oracle_persistent_update",
                "evidence_admissibility": ("diagnostic_oracle" if self.method_name == "oracle_persistent_update"
                    else "formal" if self.config.phase == "formal" else "qualification")}

    def run(self, *, master_episode_id: str, task: Mapping, initial_state_id: int, seed: int,
            initial_ledger: Any, initial_context: Any, schedule: Any, resume=False) -> dict:
        from .scheduler import evaluate_trigger
        self.episode_id = master_episode_id
        self.method_name = str(getattr(self.method.method, "value", self.method.method))
        self.events = tuple(schedule.events[:4] if self.config.protocol == "end_to_end" else schedule.events)
        self.identity = {"master_episode_id": master_episode_id, "method": self.method_name,
            "task_sha256": digest(task), "initial_state_id": initial_state_id, "seed": seed,
            "schedule_sha256": digest(schedule), "initial_ledger_sha256": digest(initial_ledger),
            "config_sha256": digest(self.config)}
        self._guard()
        existing_episode = self.journal.get_episode(self._key(0))
        if existing_episode is not None:
            if not resume:
                raise RuntimeBlocked("INVALID_DUPLICATE_EPISODE", "use verified resume for completed episodes")
            self.journal.inspect_integrity([self._key(i) for i in range(len(self.events) + 1)],
                snapshot_label="completed", scope=self._key(0)[:3]).require_valid()
            last = self.journal.load_snapshot(self._key(existing_episode["reached_events"]), label="completed")
            if last["identity"] != self.identity:
                raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "completed episode identity changed")
            return existing_episode
        if not resume and (self.journal.snapshot_exists(self._key(0), label="initial") or
                           any(self.journal.phase(self._key(i)) != "new" for i in range(len(self.events) + 1))):
            raise RuntimeBlocked("INVALID_PARTIAL_RESUME_REQUIRED", "existing trajectory requires explicit resume")
        self.observation = self.env.reset(task=task, initial_state_id=initial_state_id, seed=seed)
        self.context = initial_context
        self.method.start_episode(task={**dict(task), "episode_id": master_episode_id}, ledger=initial_ledger, context=initial_context)
        self.evaluator = SealedDynamicEvaluator(initial_ledger, required_events=len(self.events))
        self.history, self.delivered, self.previous_event_step = [], 0, None
        self.adaptation_metrics = {}
        if self.executor.policy is not None:
            from .vla_adapter import public_observation
            self.executor.policy.reset(task={"language": str(task.get("language", task.get("instruction", "")))},
                                       seed=seed, initial_observation=public_observation(self.observation.payload))
        current = 0
        restored_completed = False
        restored_initial = False
        failure = None
        if resume:
            for index in range(len(self.events), -1, -1):
                if self.journal.snapshot_exists(self._key(index), label="completed"):
                    payload = self.journal.load_snapshot(self._key(index), label="completed")
                    self._restore(payload)
                    if self.journal.event_result(self._key(index)) is None:
                        self.journal.record_result(self._key(index), payload["pending_result"])
                    current, restored_completed = index, True
                    saved_status = payload["pending_result"]["status"]
                    failure = saved_status if saved_status != "COMPLETED" else None
                    break
            else:
                if self.journal.snapshot_exists(self._key(0), label="initial"):
                    self._restore(self.journal.load_snapshot(self._key(0), label="initial"))
                    restored_initial = True
        if not restored_completed and not restored_initial:
            self._observe()
            try:
                self._compile()
            except RuntimeBlocked as exc:
                if not exc.status.startswith("METHOD_"):
                    raise
                failure = exc.status
            if failure is None and not self.journal.snapshot_exists(self._key(0), label="initial"):
                self._snapshot(index=0, label="initial")
        results = []
        while True:
            if not restored_completed:
                while True:
                    if failure:
                        break
                    decision = None
                    if self.delivered < len(self.events):
                        trigger = self.env.trigger_context(previous_event_step=self.previous_event_step)
                        decision = evaluate_trigger(self.events[self.delivered], trigger)
                        if decision.ready:
                            break
                        if decision.status.value.startswith("BLOCKED_"):
                            raise RuntimeBlocked(decision.status.value, "semantic trigger evidence unavailable")
                        if decision.terminal_failure:
                            failure = decision.status.value
                            break
                    if self.executor.finished:
                        # Finishing the plan before a scheduled semantic event is
                        # a retained trajectory failure, never a dropped cell.
                        if self.delivered < len(self.events):
                            failure = "METHOD_TERMINATED_BEFORE_REQUIRED_EVENT"
                        break
                    if self.observation.policy_step >= self.config.max_policy_steps:
                        failure = "METHOD_TIMEOUT"
                        break
                    execution_started_before = self.execution_started_at
                    if self.execution_started_at is None:
                        self.execution_started_at = time.monotonic()
                    trace_start = len(self.executor.trace)
                    try:
                        self.observation, action = self.executor.step(self.observation, self.context)
                        self._observe(action)
                    except (UnsupportedPlanningSemantics, RecoveryGateBlocked) as exc:
                        # A semantic recovery gate failure retains this trajectory;
                        # backend/environment availability exceptions remain fatal.
                        if len(self.executor.trace) == trace_start:
                            self.execution_started_at = execution_started_before
                        failure = "METHOD_RECOVERY_EXECUTION_FAILURE"
                        break
                results.append(self._boundary_result(current, status=failure or "COMPLETED", timeout=failure == "METHOD_TIMEOUT"))
            restored_completed = False
            if failure or self.delivered >= len(self.events):
                break
            event = self.events[self.delivered]
            index = event.event_index
            # If a crash occurred after this pre-boundary was stored, restore
            # it before repeating the deterministic simulator injection.
            if self.journal.snapshot_exists(self._key(index), label="pre"):
                self._restore(self.journal.load_snapshot(self._key(index), label="pre"))
            else:
                if hasattr(self.planner, "capture"):
                    self.planner.capture(context=self.context, event_id=event.event_id)
                self._snapshot(index=index, label="pre")
            before_state = digest(self.method.snapshot())
            before = self.observation
            injection = self.env.inject(event)
            if digest(self.method.snapshot()) != before_state:
                raise RuntimeBlocked("INVALID_EVENT_STATE_LEAKAGE", "injector changed method state")
            fresh = self.env.observe()
            if fresh.policy_step != before.policy_step or fresh.version <= before.version or fresh.observation_ref == before.observation_ref:
                raise RuntimeBlocked("INVALID_STALE_POST_EVENT_OBSERVATION", "fresh observation with no hidden policy step is required")
            self.observation = fresh
            self.evaluator.update_canonical(injection.canonical_ledger, event_id=event.event_id,
                legitimately_invalidated_milestones=injection.legitimately_invalidated_milestones)
            self.context = self.env.public_context(fresh, self.context)
            evidence = injection.public_evidence
            if evidence.timestamp < fresh.version or fresh.observation_ref not in evidence.observation_refs:
                raise RuntimeBlocked("INVALID_STALE_EVENT_EVIDENCE", "event evidence must reference fresh observation")
            if self._proxy is not None:
                self._proxy.bind(self._key(index))
            previous_method = self.method.snapshot()
            self._guard()
            kwargs = dict(evidence=evidence, public_history=deepcopy(self.history), context=self.context)
            if self.method_name == "oracle_persistent_update":
                kwargs["canonical_ledger"] = injection.canonical_ledger
                kwargs["hidden_effect"] = injection.hidden_effect
            elif self._proxy is not None:
                kwargs["evidence_records"] = injection.evidence_records
            try:
                outcome = self.method.on_event(**kwargs)
            except ValueError as exc:
                # Transport/provider exceptions after an intent remain ambiguous;
                # only deterministic pre-call/interface failures are method failures.
                if self.journal.phase(self._key(index)) == "ambiguous_intent":
                    from .journal import AmbiguousCallError
                    raise AmbiguousCallError("provider call interrupted before a durable response") from exc
                if type(exc).__name__ == "LeakageError":
                    raise RuntimeBlocked("INVALID_PUBLIC_INPUT_LEAKAGE", "public input leakage scan rejected the event") from exc
                failure = "METHOD_ADAPTATION_FAILURE"
                outcome = {"accepted": False, "rejection": type(exc).__name__}
            outcome_data = json_value(outcome)
            accepted = outcome_data.get("accepted", True) if isinstance(outcome_data, dict) else True
            if self.config.phase == "formal" and self.method_name != "oracle_persistent_update" and outcome_data.get("fixture", False):
                raise RuntimeBlocked("INVALID_FORMAL_REASONER", "provider returned fixture evidence")
            from .dynamic_evaluator import protected_history_corruption
            self.adaptation_metrics = {"invalid_transaction": not accepted,
                "history_corruption": protected_history_corruption(previous_method, self.method.snapshot(),
                    allowed_occurrence_ids=injection.affected_occurrence_ids)}
            if self._proxy is not None and self.method.gateway.logs and self.method.gateway.logs[-1].event_index == index:
                log = self.method.gateway.logs[-1]
                self.adaptation_metrics.update({"input_tokens": log.input_tokens,
                    "output_tokens": log.output_tokens, "reasoner_seconds": self._proxy.last_seconds})
            if not accepted:
                # The adapter owns its append-only rejection log. Its accepted
                # state must remain unchanged; do not overwrite evolving memory.
                now = self.method.snapshot()
                fields = ("ledger", "directive", "summary", "regenerated_fields", "revision", "accepted_state")
                if any(previous_method.get(k) != now.get(k) for k in fields):
                    raise RuntimeBlocked("INVALID_REJECTED_STATE_MUTATION", "rejected proposal changed accepted state")
                if self.config.fallback == "terminate":
                    failure = "METHOD_REJECTED_TERMINATED"
            self.history.append({"event": json_value(evidence), "observation_ref": fresh.observation_ref})
            self.previous_event_step, self.delivered, current = fresh.policy_step, index, index
            self._observe()
            try:
                self._compile()
            except RuntimeBlocked as exc:
                if not exc.status.startswith("METHOD_"):
                    raise
                failure = exc.status
            if failure:
                results.append(self._boundary_result(current, status=failure))
                break
        for event in self.events[self.delivered:]:
            key = self._key(event.event_index)
            if self.journal.event_result(key) is None:
                retained = self.evaluator.evaluate(self.env.sealed_predicate, timeout=failure == "METHOD_TIMEOUT",
                    manual_intervention=bool(getattr(self.env, "manual_intervention", False))).to_dict()
                retained.update(success=False, required_events_reached=False)
                self.journal.record_result(key, {"protocol": self.config.protocol,
                    "master_episode_id": self.episode_id, "method": self.method_name,
                    "event_index": event.event_index, "status": "EVENT_UNREACHED_DUE_TO_PRIOR_FAILURE",
                    "success": False, "final_active_task_success_after_last_event": False,
                    "checkpoint": event.event_index in (0,1,2,4,8), "prior_failure": failure,
                    "high_level_calls": 0, "phase": self.config.phase, "fixture": self.config.fixture,
                    "source_boundary_event_index": self.delivered,
                    "source_boundary_sha256": digest(self.journal.load_snapshot(self._key(self.delivered), label="completed")),
                    "evaluation": retained, "metrics": {"history_corruption": self.adaptation_metrics.get("history_corruption")},
                    **self._row_identity()})
        evaluation = self.evaluator.evaluate(self.env.sealed_predicate,
            timeout=failure == "METHOD_TIMEOUT", manual_intervention=bool(getattr(self.env, "manual_intervention", False)))
        final_outcomes = evaluation.to_dict()
        final_outcomes["success"] = evaluation.success and failure is None
        episode = {"protocol": self.config.protocol, "master_episode_id": self.episode_id,
            "method": self.method_name, "status": failure or "COMPLETED", "phase": self.config.phase,
            "fixture": self.config.fixture, "required_events": len(self.events), "reached_events": self.delivered,
            "success": evaluation.success and failure is None,
            "final_active_task_success_after_last_event": evaluation.success and failure is None,
            "evaluation": final_outcomes, "action_trace": self.executor.trace,
            "action_trace_sha256": digest(self.executor.trace)}
        episode.update(self._row_identity())
        self.journal.record_episode(self._key(0), episode)
        return episode

    def close(self):
        try:
            if self.executor.policy is not None:
                self.executor.policy.close()
        finally:
            self.env.close()


def load_runtime_factory(spec: str, *, config: Mapping) -> Any:
    if not spec or ":" not in spec:
        raise RuntimeBlocked("BLOCKED_RUNTIME_ENVIRONMENT_UNAVAILABLE", "configure module.path:factory")
    module, name = spec.split(":", 1)
    try:
        return getattr(importlib.import_module(module), name)(config=dict(config))
    except (ImportError, AttributeError) as exc:
        raise RuntimeBlocked("BLOCKED_RUNTIME_ENVIRONMENT_UNAVAILABLE", "runtime factory unavailable") from exc
