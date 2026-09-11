"""Production LIBERO binding for the repeated-interruptions v2.1 pilot.

The environment owns simulator mutation and sealed scoring.  The evidence
builder, verifier, nominal planner, continuation backend, method adapters, and
learned policy communicate through explicit public records only.  Heavy model
and simulator imports are lazy so zero-call preflight can inspect the complete
assembly without allocating a GPU or issuing inference.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .canonical import canonical_sha256, to_primitive
from .enums import CommitmentRole, EventFamily, GroundingValidity, Lifecycle, MethodName, Satisfaction
from .planner_backend import ExecutionPlan
from .schema import (
    BeliefFact, CommitmentOccurrence, ContinuationState, EvidenceRecord,
    ExecutionContext, HiddenCanonicalEffect, PersistentLedger, ProgressCertificate,
    PublicEventPayload, RelationEdge,
)


CHECKPOINT_SHA256 = "d36eaa2a334cd52f4a3a94558cf90d82584743ea772fabf76f9e4372e7076076"
QWEN_MODEL = "Qwen/Qwen3-32B"
QWEN_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"
PUBLIC_POSE_FIELD = "agent_visible_named_poses"
PUBLIC_OBSERVATION_SOURCE_KEYS = (
    "agentview_image", "robot0_eye_in_hand_image", "robot0_eef_pos",
    "robot0_eef_quat", "robot0_gripper_qpos", "<catalog-entity>_pos",
    "<catalog-entity>_quat",
)


def _schema_hash(value: Mapping[str, Any]) -> str:
    return canonical_sha256(value)


def _python_tree_hash(package: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _identity(provider_id: str, version: str, input_fields: Sequence[str],
              output_fields: Sequence[str], **extra: Any) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "version": version,
        "uses_hidden_canonical_state": False,
        "uses_privileged_simulator_state": False,
        "input_schema_hash": _schema_hash({"fields": list(input_fields)}),
        "output_schema_hash": _schema_hash({"fields": list(output_fields)}),
        **extra,
    }


def _finite_vector(value: Any, length: int) -> tuple[float, ...] | None:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (tuple, list)) or len(value) != length:
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(float(item)) for item in value):
        return None
    return tuple(float(item) for item in value)


def _poses(observation: Mapping[str, Any]) -> dict[str, dict[str, tuple[float, ...]]]:
    poses = observation.get(PUBLIC_POSE_FIELD, {})
    if not isinstance(poses, Mapping):
        return {}
    result = {}
    for name, pose in poses.items():
        if not isinstance(name, str) or not isinstance(pose, Mapping):
            continue
        position = _finite_vector(pose.get("position"), 3)
        quaternion = _finite_vector(pose.get("quaternion"), 4)
        if position is not None and quaternion is not None:
            result[name] = {"position": position, "quaternion": quaternion}
    return result


@dataclass(frozen=True)
class RuntimeVerification:
    verifier_record_id: str
    occurrence_id: str
    predicate: str
    arguments: tuple[str, ...]
    status: str
    confidence: float
    evidence_ids: tuple[str, ...]
    timestamp: int
    observation_version: int

    def __post_init__(self) -> None:
        if self.status not in {"satisfied", "violated", "unresolved", "unknown"}:
            raise ValueError("unknown public verification status")
        if not 0 <= self.confidence <= 1 or not self.evidence_ids:
            raise ValueError("public verification requires confidence and evidence")

    def to_dict(self) -> dict[str, Any]:
        return to_primitive(self)


class PublicEventEvidenceBuilder:
    """Method-independent delta detector over agent-visible observations."""

    provider_id = "libero_named_observation_delta"
    version = "public_event_evidence_v1"
    uses_hidden_canonical_state = False
    uses_privileged_simulator_state = False
    identity = _identity(
        provider_id, version,
        ("previous_public_observation", "current_public_observation", "public_proprioception",
         "public_user_message", "public_task_catalog", "previously_committed_public_evidence"),
        ("pose_or_visibility_change", "availability_change", "public_task_update", "confidence",
         "evidence_ids", "observation_refs", "timestamp"),
        observation_source_keys=PUBLIC_OBSERVATION_SOURCE_KEYS,
        position_change_threshold_m=0.02,
    )

    def build(self, *, event_id: str, event_index: int,
              previous_public_observation: Mapping[str, Any],
              current_public_observation: Mapping[str, Any],
              public_proprioception: Sequence[float], public_user_message: str | None,
              public_task_catalog: Mapping[str, Any],
              previously_committed_public_evidence: Sequence[Mapping[str, Any]],
              observation_ref: str, timestamp: int) -> tuple[PublicEventPayload, tuple[EvidenceRecord, ...]]:
        # Recursive scanners cover both poisoned nested values and textual labels.
        from .evidence import assert_public_safe
        assert_public_safe({"previous": previous_public_observation,
                            "current": current_public_observation,
                            "proprioception": list(public_proprioception),
                            "user_message": public_user_message,
                            "catalog": public_task_catalog,
                            "previous_evidence": list(previously_committed_public_evidence)})
        before, after = _poses(previous_public_observation), _poses(current_public_observation)
        catalog_names = set(public_task_catalog.get("objects", ()))
        catalog_names.update(public_task_catalog.get("entities", ()))
        changed, visibility = [], []
        for name in sorted(catalog_names):
            if name in before and name in after:
                distance = math.dist(before[name]["position"], after[name]["position"])
                if distance >= self.identity["position_change_threshold_m"]:
                    changed.append(name)
            elif (name in before) != (name in after):
                visibility.append(name)
        parts = []
        if changed:
            parts.append("Pose estimates changed for " + ", ".join(changed) + ".")
        if visibility:
            parts.append("Visibility changed for " + ", ".join(visibility) + ".")
        if public_user_message:
            parts.append("A public task update was received: " + public_user_message.strip())
        if not parts:
            parts.append("A fresh public observation was received, but the available fields do not resolve the change.")
        confidence = 1.0 if (changed or public_user_message) else 0.25
        evidence_id = "evidence:" + hashlib.sha256(
            f"{event_id}:{event_index}:{observation_ref}".encode()).hexdigest()[:24]
        hypothesis = " ".join(parts)
        record = EvidenceRecord(evidence_id, hypothesis, confidence, self.provider_id,
                                timestamp, (observation_ref,))
        payload = PublicEventPayload(
            event_id, event_index, hypothesis, confidence, (evidence_id,), timestamp,
            self.provider_id, (observation_ref,), public_user_message,
            tuple(changed + visibility),
        )
        return payload, (record,)


class PublicRuntimeVerifier:
    """Conservative spatial verifier using only named public pose observables."""

    provider_id = "libero_public_spatial_verifier"
    version = "public_runtime_verifier_v1"
    uses_hidden_truth = False
    uses_hidden_canonical_state = False
    uses_privileged_simulator_state = False
    identity = _identity(
        provider_id, version,
        ("public_observation", "public_evidence", "accepted_occurrence_id", "predicate", "arguments"),
        ("status", "confidence", "evidence_ids", "occurrence_id", "timestamp", "observation_version"),
        in_satisfied_xy_m=0.08, in_violated_xy_m=0.16,
        on_satisfied_xy_m=0.05, on_violated_xy_m=0.12,
    )

    @staticmethod
    def _target_name(name: str) -> str:
        suffixes = ("_contain_region", "_heating_region", "_cook_region")
        for suffix in suffixes:
            if name.endswith(suffix):
                return name[:-len(suffix)]
        return name

    def evaluate_goal(self, *, observation: Mapping[str, Any], occurrence_id: str,
                      predicate: str, arguments: Sequence[str], evidence_ids: Sequence[str],
                      timestamp: int, observation_version: int,
                      evidence_timestamp: int | None = None) -> RuntimeVerification:
        if not isinstance(occurrence_id, str) or not occurrence_id:
            raise ValueError("accepted method state must supply an occurrence ID")
        if evidence_timestamp is not None and evidence_timestamp < observation_version:
            status, confidence = "unknown", 0.0
        else:
            poses = _poses(observation)
            if predicate not in {"in", "on"} or len(arguments) != 2:
                status, confidence = "unknown", 0.0
            else:
                source, target = str(arguments[0]), self._target_name(str(arguments[1]))
                if source not in poses or target not in poses:
                    status, confidence = "unknown", 0.0
                else:
                    source_pos, target_pos = poses[source]["position"], poses[target]["position"]
                    xy = math.dist(source_pos[:2], target_pos[:2])
                    dz = source_pos[2] - target_pos[2]
                    if predicate == "in":
                        if xy <= self.identity["in_satisfied_xy_m"] and -0.04 <= dz <= 0.24:
                            status, confidence = "satisfied", 0.9
                        elif xy >= self.identity["in_violated_xy_m"] or not -0.12 <= dz <= 0.38:
                            status, confidence = "violated", 0.9
                        else:
                            status, confidence = "unresolved", 0.55
                    elif xy <= self.identity["on_satisfied_xy_m"] and 0.005 <= dz <= 0.16:
                        status, confidence = "satisfied", 0.9
                    elif xy >= self.identity["on_violated_xy_m"] or not -0.05 <= dz <= 0.28:
                        status, confidence = "violated", 0.9
                    else:
                        status, confidence = "unresolved", 0.55
        refs = tuple(str(item) for item in evidence_ids)
        record_id = "verify:" + canonical_sha256({
            "occurrence_id": occurrence_id, "predicate": predicate,
            "arguments": list(arguments), "observation_version": observation_version,
            "evidence_ids": refs,
        })[:24]
        return RuntimeVerification(record_id, occurrence_id, predicate, tuple(arguments),
                                   status, confidence, refs, timestamp, observation_version)

    def verify(self, *, stages: tuple[Mapping[str, Any], ...], observation: Any,
               handoff_state: tuple[float, float, float], required_true: tuple[str, ...],
               required_false: tuple[str, ...]):
        """Public forward check used by the archived continuation search.

        It predicts only declared stage effects and captured public geometry.  It
        never consults an environment or the sealed evaluator.
        """
        from .continuation_backend import RecoveryVerification
        flags = dict(observation.abstract_flags)
        state = tuple(observation.state)
        effects = {
            "Suspend": {"nominal_suspended": True},
            "Stabilize": {"object_stable": True},
            "Retreat": {"safe_clearance": True},
            "WaitUntilClear": {"obstacle_present": False},
            "ReacquireTarget": {"object_grasped": True, "object_stable": False},
            "UpdateTargetContract": {"aligned_to_current_target": True},
            "Realign": {"ee_at_handoff": True, "orientation_restored": True},
            "Resume": {"restore_valid": True},
        }
        for stage in stages:
            operator = stage.get("operator")
            if operator not in effects:
                return RecoveryVerification(False, state, flags, 0, "unknown public recovery stage")
            flags.update(effects[operator])
            if operator == "Realign":
                state = tuple(handoff_state)
        ok = all(flags.get(name) is True for name in required_true)
        ok = ok and all(flags.get(name) is False for name in required_false)
        return RecoveryVerification(ok, state, flags, len(stages),
                                    "public forward-model requirements satisfied" if ok else "unresolved public requirements")


class NominalPlanner:
    """One planner for every arm; consumes only the supplied PlanningProblem."""

    provider_id = "public_planning_problem_nominal"
    version = "nominal_planner_v1"
    uses_hidden_truth = False
    uses_hidden_canonical_state = False
    uses_privileged_simulator_state = False
    identity = _identity(
        provider_id, version, ("PlanningProblem", "ExecutionContext"),
        ("ExecutionPlan",), selection_rule="first unresolved supplied active goal in compiler order",
    )

    @staticmethod
    def _instruction(goal: Mapping[str, Any], problem: Any) -> str:
        predicate = str(goal.get("predicate", ""))
        arguments = tuple(str(value) for value in goal.get("arguments", ()))
        if predicate == "in" and len(arguments) == 2:
            base = f"Place {arguments[0]} inside {arguments[1]}."
        elif predicate == "on" and len(arguments) == 2:
            base = f"Place {arguments[0]} on {arguments[1]}."
        elif predicate in {"turnon", "open", "close"} and arguments:
            base = f"Make {predicate}({', '.join(arguments)}) true."
        else:
            base = f"Achieve {predicate}({', '.join(arguments)})."
        if problem.forbidden_regressions:
            base += " Preserve all verified completed milestones."
        if problem.hard_constraints:
            base += " Respect every supplied hard constraint."
        return base

    def solve(self, *, problem: Any, context: Any) -> ExecutionPlan:
        # No task ID, catalog, canonical ledger, environment, or evaluator is
        # reachable here.  Inconsistent/omitted accepted state remains as given.
        from .compiler import planning_problem_hash
        active = set(problem.active_goal_occurrence_ids)
        satisfied = {(cert.predicate, tuple(cert.arguments)) for cert in problem.progress_certificates
                     if cert.currently_preserved and cert.satisfaction is Satisfaction.SATISFIED}
        explicit = problem.continuation_assumptions.get("ordered_macro_plan", ())
        macros = []
        if explicit:
            from .continuation_backend import UnsupportedPlanningSemantics
            if problem.continuation_assumptions.get("execution_mode") != "explicit_skills":
                raise UnsupportedPlanningSemantics("explicit macros require explicit_skills mode")
            for item in explicit:
                oid = item.get("target_occurrence_id")
                if not isinstance(oid, str):
                    raise UnsupportedPlanningSemantics("explicit macro omitted its accepted target")
                macros.append({
                    "target_occurrence_id": oid,
                    "predicate": "explicit_skill",
                    "arguments": (str(item.get("skill", item.get("action_id", "skill"))),),
                    "compiled_instruction": {"instruction": "Execute supplied skill " +
                                             str(item.get("skill", item.get("action_id", "skill"))) + "."},
                })
        else:
            for goal in problem.remaining_goals:
                oid = goal.get("occurrence_id")
                if oid not in active:
                    # Retain the error; never substitute a gold occurrence.
                    continue
                key = (goal.get("predicate"), tuple(goal.get("arguments", ())))
                if key in satisfied:
                    continue
                macros.append({
                    "target_occurrence_id": oid,
                    "predicate": str(goal.get("predicate")),
                    "arguments": tuple(goal.get("arguments", ())),
                    "compiled_instruction": {"instruction": self._instruction(goal, problem)},
                })
        return ExecutionPlan(self.provider_id, "learned_vla_macros", problem.problem_id,
                             planning_problem_hash(problem), "planned", tuple(macros),
                             ("planned only from supplied normalized semantics",))


def _initial_ledger(task: Mapping[str, Any]) -> PersistentLedger:
    slots = []
    for goal in task["initial_achievement_goals"]:
        slots.append(CommitmentOccurrence(
            goal["family_key"], goal["family_key"] + "@1", CommitmentRole.ACHIEVEMENT_GOAL,
            goal["predicate"], tuple(goal["arguments"]), Lifecycle.ACTIVE,
            GroundingValidity.VALID, 1.0, "hard", "task", "user",
            provenance={"source": "public_task_catalog"},
        ))
    return PersistentLedger(0, tuple(slots))


def _initial_context(ledger: PersistentLedger) -> ExecutionContext:
    active = next((slot.occurrence_id for slot in ledger.slots
                   if slot.role is CommitmentRole.ACHIEVEMENT_GOAL), None)
    return ExecutionContext((), (), ContinuationState(
        active, None, 0, None, tuple(slot.occurrence_id for slot in ledger.slots),
        None, 0,
    ))


def _public_task(task: Mapping[str, Any], episode_id: str) -> dict[str, Any]:
    goals = [{"predicate": goal["predicate"], "arguments": list(goal["arguments"]),
              "occurrence_id": goal["family_key"] + "@1"}
             for goal in task["initial_achievement_goals"]]
    return {
        "episode_id": episode_id,
        "task_id": task["task_id"],
        "name": task["task_name"],
        "language": task["original_instruction"],
        "goals": goals,
        "objects": sorted(task["object_aliases"].values()),
        "entities": sorted(set(task["object_aliases"].values()) |
                           {PublicRuntimeVerifier._target_name(str(arg))
                            for goal in task["initial_achievement_goals"]
                            for arg in goal["arguments"]}),
        "hard_constraints": [], "soft_preferences": [], "initial_facts": [],
        "grounding_bindings": [], "skills": [],
    }


def _restore_constraint_state(value: Mapping[str, Any]):
    from cope_benchmark.interruptions import AxisAlignedBox, BenchmarkConstraintState
    return BenchmarkConstraintState(
        active_no_go_zones={key: AxisAlignedBox.from_payload(item)
                            for key, item in value.get("active_no_go_zones", {}).items()},
        retired_no_go_zones={key: AxisAlignedBox.from_payload(item)
                             for key, item in value.get("retired_no_go_zones", {}).items()},
        preferences=deepcopy(dict(value.get("preferences", {}))),
        tool_availability={str(key): bool(item) for key, item in value.get("tool_availability", {}).items()},
        event_versions={str(key): int(item) for key, item in value.get("event_versions", {}).items()},
    )


class ProductionLiberoEnvironment:
    """Trusted harness bridge.  Public components receive projected data only."""

    provider_id = "libero_10_native_runtime"
    version = "production_libero_runtime_v1"

    def __init__(self, *, catalog: Mapping[int, Mapping[str, Any]],
                 evidence_builder: PublicEventEvidenceBuilder,
                 verifier: PublicRuntimeVerifier, checkpoint_path: str):
        self.catalog = deepcopy(dict(catalog))
        self.evidence_builder, self.verifier = evidence_builder, verifier
        self.checkpoint_path = checkpoint_path
        self.identity = {
            "provider_id": self.provider_id, "version": self.version,
            "uses_hidden_canonical_state": True,
            "uses_privileged_simulator_state": True,
            "input_schema_hash": _schema_hash({"fields": ["trusted_catalog", "sealed_simulator_state"]}),
            "output_schema_hash": _schema_hash({"fields": ["public_observation", "sealed_evaluation"]}),
            "public_loop": False,
            "public_evidence_builder": deepcopy(evidence_builder.identity),
            "public_verifier": deepcopy(verifier.identity),
            "public_observation_source_keys": list(PUBLIC_OBSERVATION_SOURCE_KEYS),
        }
        self._env = None
        self._suite = None
        self._interruption = None
        self._raw_observation = None
        self._receipt = None
        self._task = None
        self._task_catalog = None
        self._canonical = None
        self._version = 0
        self._policy_step = 0
        self._initial_state_id = None
        self._seed = None
        self._runtime_verifications: list[dict[str, Any]] = []
        self._public_evidence: list[dict[str, Any]] = []
        self._last_affected: tuple[str, ...] = ()
        self._last_public_context: ExecutionContext | None = None
        self._availability_release: dict[str, tuple[float, float, float]] = {}
        self.manual_intervention = False

    def _make_receipt(self, raw: Mapping[str, Any], *, increment: bool) -> Any:
        import numpy as np
        from experiments.robot.libero import libero_utils
        from libero_experiment_core import frame_from_obs
        from .runner import ObservationReceipt
        if increment:
            self._version += 1
        allowed = set(self._task_catalog["object_aliases"].values())
        allowed.update(PublicRuntimeVerifier._target_name(str(arg))
                       for goal in self._task_catalog["initial_achievement_goals"]
                       for arg in goal["arguments"])
        allowed.update(PublicRuntimeVerifier._target_name(str(arg))
                       for goal in self._task_catalog["alternative_valid_goals"]
                       for arg in goal["arguments"])
        poses = {}
        for entity in sorted(allowed):
            position = _finite_vector(raw.get(entity + "_pos"), 3)
            quaternion = _finite_vector(raw.get(entity + "_quat"), 4)
            if position is not None and quaternion is not None:
                poses[entity] = {"position": position, "quaternion": quaternion}
        state = np.concatenate((raw["robot0_eef_pos"],
                                libero_utils.quat2axisangle(raw["robot0_eef_quat"]),
                                raw["robot0_gripper_qpos"]))
        reference = f"obs:{self._task['episode_id']}:{self._policy_step}:{self._version}"
        payload = {
            "full_image": frame_from_obs(dict(raw), self._resize_size), "state": state,
            "observation_ref": reference, "observation_step": self._policy_step,
            "timestamp": self._version, PUBLIC_POSE_FIELD: poses,
        }
        self._raw_observation = raw
        self._receipt = ObservationReceipt(payload, reference, self._version, self._policy_step)
        return self._receipt

    def reset(self, *, task: Mapping, initial_state_id: int, seed: int):
        import numpy as np
        from libero_experiment_core import (ExperimentConfig, create_libero_env, get_benchmark_suite,
                                            get_image_resize_size, make_model_cfg, set_seed)
        self._task = deepcopy(dict(task))
        task_id = int(task["task_id"])
        self._task_catalog = deepcopy(self.catalog[task_id])
        self._initial_state_id, self._seed = initial_state_id, seed
        set_seed(seed)
        self._suite = get_benchmark_suite("libero_10")
        runtime_task = self._suite.get_task(task_id)
        if runtime_task.name != self._task_catalog["task_name"] or runtime_task.language != task["language"]:
            raise ValueError("runtime LIBERO task differs from the public catalog")
        states = self._suite.get_task_init_states(task_id)
        initial = np.asarray(states[initial_state_id]).copy()
        if hashlib.sha256(initial.tobytes()).hexdigest() != self._task_catalog["initial_state_digests"][str(initial_state_id)]:
            raise ValueError("initial state bytes differ from the task catalog")
        cfg = ExperimentConfig(checkpoint=self.checkpoint_path, task_suite="libero_10",
                               unnorm_key="libero_10", task_id=task_id, trial_id=initial_state_id,
                               mode="clean", max_steps=1040, num_steps_wait=0, seed=seed,
                               resolution=256, enable_auto_disturbance=False)
        self._env, prompt = create_libero_env(runtime_task, cfg)
        if prompt != task["language"]:
            raise ValueError("runtime task instruction changed")
        self._env.reset()
        raw = self._env.set_init_state(initial)
        self._resize_size = get_image_resize_size(make_model_cfg(cfg))
        from cope_benchmark.interruptions import LiberoInterruptionContext
        self._interruption = LiberoInterruptionContext(self._env, raw)
        self._canonical = _initial_ledger(self._task_catalog)
        self._version = self._policy_step = 0
        self._runtime_verifications = []
        self._public_evidence = []
        self._last_affected = ()
        self._last_public_context = None
        self._availability_release = {}
        return self._make_receipt(raw, increment=False)

    def observe(self):
        return self._receipt

    def step(self, action: Sequence[float]):
        raw, _, _, _ = self._env.step(list(action))
        self._policy_step += 1
        self._interruption.fallback_observation = raw
        return self._make_receipt(raw, increment=True)

    def execute_macro(self, macro: Mapping):
        raise RuntimeError("controlled mechanism execution is unavailable in the production VLA environment")

    def _user_message(self, family: EventFamily) -> str | None:
        goals = self._task_catalog["initial_achievement_goals"]
        first = next((goal for goal in goals if goal["family_key"] in self._task_catalog["replaceable_goal_families"]), goals[0])
        phrase = f"{first['predicate']}({', '.join(first['arguments'])})"
        if family is EventFamily.USER_CANCELS_ACTIVE_GOAL:
            return "Cancel the current requirement " + phrase + "."
        if family is EventFamily.USER_REISSUES_RETIRED_GOAL:
            return "Add a new requirement to complete " + phrase + " again."
        if family is EventFamily.USER_REPLACES_ACTIVE_GOAL:
            alt = self._task_catalog["alternative_valid_goals"][0]
            return ("Replace the current requirement " + phrase + " with " +
                    f"{alt['predicate']}({', '.join(alt['arguments'])}).")
        if family is EventFamily.USER_ADDS_PERSISTENT_PREFERENCE:
            item = self._task_catalog["soft_preference_templates"][0]
            return ("From now on handle objects gently: translation at most "
                    f"{item['translation_ceiling']} m per action and end-effector speed at most "
                    f"{item['eef_speed_ceiling']} m/s.")
        if family is EventFamily.TEMPORARY_NO_GO_APPEARS:
            return "A temporary transit restriction is active in the announced workspace box."
        if family is EventFamily.TEMPORARY_NO_GO_CLEARS:
            return "The previously announced temporary transit restriction has cleared."
        return None

    def _physical_event(self, event: Any):
        from cope_benchmark.interruptions import InterruptionEvent, InterruptionType, apply_interruption
        family = event.family
        pose = self._task_catalog["safe_event_injection_poses"].get(family.value)
        if family in {EventFamily.USER_CANCELS_ACTIVE_GOAL, EventFamily.USER_REISSUES_RETIRED_GOAL,
                      EventFamily.USER_REPLACES_ACTIVE_GOAL}:
            from libero_experiment_core import refresh_observation_after_sim_change
            raw, _ = refresh_observation_after_sim_change(self._env, self._raw_observation)
            return raw, {"kind": "public_utterance_only"}
        if family is EventFamily.USER_ADDS_PERSISTENT_PREFERENCE:
            item = self._task_catalog["soft_preference_templates"][0]
            applied = InterruptionEvent(event.event_id, InterruptionType.USER_ADDS_GENTLE_PREFERENCE,
                self._policy_step, {"preference_id": "gentle-action-limits",
                "translation_ceiling": item["translation_ceiling"],
                "eef_speed_ceiling": item["eef_speed_ceiling"],
                "contact_impulse_proxy_ceiling": item["contact_impulse_proxy_ceiling"]})
        elif family in {EventFamily.TARGET_OBJECT_DISPLACED,
                        EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED}:
            kind = (InterruptionType.TARGET_OBJECT_MOVED if family is EventFamily.TARGET_OBJECT_DISPLACED
                    else InterruptionType.GOAL_RECEPTACLE_MOVED)
            delta = pose["region"]["delta_xy"]
            applied = InterruptionEvent(event.event_id, kind, self._policy_step,
                {"joint": pose["entity"] + "_joint0", "dx": delta[0], "dy": delta[1]})
        elif family in {EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE,
                        EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN}:
            entity = pose["entity"]
            bounds = pose["region"]["accessible_xyz_bounds"]
            current = _poses(self._receipt.payload)[entity]["position"]
            if family is EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE:
                kind = InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE
                delta = pose["region"]["release_delta_xy"]
                release = (current[0] + delta[0], current[1] + delta[1], current[2])
                self._availability_release[entity] = release
                payload = {"tool_joint": entity + "_joint0",
                           "unavailable_xyz": [bounds[0][1] + 0.10, current[1], current[2]],
                           "accessible_xyz_bounds": bounds}
            else:
                kind = InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN
                release = self._availability_release.get(entity)
                if release is None:
                    raise ValueError("availability release has no prior public unavailability boundary")
                payload = {"tool_joint": entity + "_joint0",
                           "release_xyz": list(release),
                           "accessible_xyz_bounds": bounds}
            applied = InterruptionEvent(event.event_id, kind, self._policy_step, payload)
        elif family in {EventFamily.TEMPORARY_NO_GO_APPEARS, EventFamily.TEMPORARY_NO_GO_CLEARS}:
            zone_id = "task-transit-zone"
            if family is EventFamily.TEMPORARY_NO_GO_CLEARS:
                applied = InterruptionEvent(event.event_id, InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS,
                                            self._policy_step, {"zone_id": zone_id})
            else:
                goal = self._task_catalog["initial_achievement_goals"][0]
                positions = _poses(self._receipt.payload)
                source = positions[goal["arguments"][0]]["position"]
                target = positions[PublicRuntimeVerifier._target_name(goal["arguments"][-1])]["position"]
                half = pose["region"]["half_width"]
                x, y = (source[0] + target[0]) / 2, (source[1] + target[1]) / 2
                applied = InterruptionEvent(event.event_id, InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS,
                    self._policy_step, {"zone_id": zone_id, "minimum": [x-half, y-half, 0.42],
                    "maximum": [x+half, y+half, 0.72], "frame": "world"})
        else:
            raise ValueError("unsupported pilot event")
        application, raw = apply_interruption(self._interruption, applied, policy_step=self._policy_step)
        return raw, application.to_dict()

    def _canonical_event(self, event: Any) -> tuple[PersistentLedger, tuple[str, ...], HiddenCanonicalEffect]:
        family, event_id = event.family, event.event_id
        slots, relations = list(self._canonical.slots), list(self._canonical.relations)
        affected = []
        goal_indexes = [i for i, slot in enumerate(slots)
                        if slot.role is CommitmentRole.ACHIEVEMENT_GOAL and slot.lifecycle is Lifecycle.ACTIVE]
        replaceable = set(self._task_catalog["replaceable_goal_families"])
        target_index = next((i for i in goal_indexes if slots[i].family_key in replaceable),
                            goal_indexes[0] if goal_indexes else None)
        if family is EventFamily.USER_CANCELS_ACTIVE_GOAL and target_index is not None:
            old = slots[target_index]
            slots[target_index] = replace(old, lifecycle=Lifecycle.EXPIRED, retired_event_id=event_id)
            affected.append(old.occurrence_id)
        elif family is EventFamily.USER_REPLACES_ACTIVE_GOAL and target_index is not None:
            old = slots[target_index]
            slots[target_index] = replace(old, lifecycle=Lifecycle.OVERRIDDEN, retired_event_id=event_id)
            alt = self._task_catalog["alternative_valid_goals"][0]
            numbers = [int(slot.occurrence_id.rsplit("@", 1)[1]) for slot in slots
                       if slot.family_key == alt["family_key"]]
            oid = alt["family_key"] + "@" + str(max(numbers, default=0) + 1)
            new = CommitmentOccurrence(alt["family_key"], oid, CommitmentRole.ACHIEVEMENT_GOAL,
                alt["predicate"], tuple(alt["arguments"]), Lifecycle.ACTIVE, GroundingValidity.VALID,
                1.0, "hard", "user", "user", provenance={"public_user_update": True},
                created_event_id=event_id)
            slots.append(new)
            relations.append(RelationEdge(new.occurrence_id, "overrides", old.occurrence_id))
            affected.extend((old.occurrence_id, new.occurrence_id))
        elif family is EventFamily.USER_REISSUES_RETIRED_GOAL:
            retired = next((slot for slot in reversed(slots)
                            if slot.role is CommitmentRole.ACHIEVEMENT_GOAL
                            and slot.lifecycle in {Lifecycle.EXPIRED, Lifecycle.OVERRIDDEN}), None)
            if retired is not None:
                numbers = [int(slot.occurrence_id.rsplit("@", 1)[1]) for slot in slots
                           if slot.family_key == retired.family_key]
                oid = retired.family_key + "@" + str(max(numbers) + 1)
                slots.append(replace(retired, occurrence_id=oid, lifecycle=Lifecycle.ACTIVE,
                                     grounding_validity=GroundingValidity.VALID,
                                     created_event_id=event_id, retired_event_id=None,
                                     evidence_ids=(), provenance={"public_user_update": True}))
                relations.append(RelationEdge(oid, "same_family", retired.occurrence_id))
                affected.append(oid)
        elif family is EventFamily.USER_ADDS_PERSISTENT_PREFERENCE:
            item = self._task_catalog["soft_preference_templates"][0]
            oid = "preference:gentle-action-limits@1"
            slots.append(CommitmentOccurrence("preference:gentle-action-limits", oid,
                CommitmentRole.USER_PREFERENCE, item["predicate"], (), Lifecycle.ACTIVE,
                GroundingValidity.VALID, 1.0, "soft", "user", "user",
                provenance={"limits": {key: item[key] for key in (
                    "translation_ceiling", "eef_speed_ceiling", "contact_impulse_proxy_ceiling")}},
                created_event_id=event_id))
            affected.append(oid)
        elif family is EventFamily.TEMPORARY_NO_GO_APPEARS:
            oid = "safety:task-transit-zone@1"
            slots.append(CommitmentOccurrence("safety:task-transit-zone", oid,
                CommitmentRole.SAFETY_REQUIREMENT, "no_go_zone_respected", (), Lifecycle.ACTIVE,
                GroundingValidity.VALID, 1.0, "hard", "safety", "safety",
                provenance={"public_restriction": True}, created_event_id=event_id))
            affected.append(oid)
        elif family is EventFamily.TEMPORARY_NO_GO_CLEARS:
            for i, slot in enumerate(slots):
                if slot.family_key == "safety:task-transit-zone" and slot.lifecycle is Lifecycle.ACTIVE:
                    slots[i] = replace(slot, lifecycle=Lifecycle.EXPIRED, retired_event_id=event_id)
                    affected.append(slot.occurrence_id)
        elif family is EventFamily.TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE:
            entity = self._task_catalog["safe_event_injection_poses"][family.value]["entity"]
            for i, slot in enumerate(slots):
                if slot.lifecycle is Lifecycle.ACTIVE and entity in slot.arguments:
                    slots[i] = replace(slot, lifecycle=Lifecycle.SUSPENDED,
                        grounding_validity=GroundingValidity.INVALID,
                        restore_guard={"hypothesis": f"{entity} is publicly available", "min_confidence": 0.9})
                    affected.append(slot.occurrence_id)
        elif family is EventFamily.TOOL_OR_TARGET_AVAILABLE_AGAIN:
            entity = self._task_catalog["safe_event_injection_poses"][family.value]["entity"]
            for i, slot in enumerate(slots):
                if slot.lifecycle is Lifecycle.SUSPENDED and entity in slot.arguments:
                    slots[i] = replace(slot, lifecycle=Lifecycle.ACTIVE,
                                       grounding_validity=GroundingValidity.VALID, restore_guard={})
                    affected.append(slot.occurrence_id)
        elif family in {EventFamily.TARGET_OBJECT_DISPLACED,
                        EventFamily.GOAL_RECEPTACLE_OR_GROUNDING_CHANGED}:
            entity = self._task_catalog["safe_event_injection_poses"][family.value]["entity"]
            for i, slot in enumerate(slots):
                targets = tuple(PublicRuntimeVerifier._target_name(argument)
                                for argument in slot.arguments)
                if slot.lifecycle is Lifecycle.ACTIVE and entity in targets:
                    slots[i] = replace(slot, grounding_validity=GroundingValidity.DEGRADED)
                    affected.append(slot.occurrence_id)
        ledger = PersistentLedger(self._canonical.revision + 1, tuple(slots), tuple(relations),
            self._canonical.history_records + ({"kind": "canonical_event", "event_id": event_id,
                                                  "event_index": event.event_index},))
        effect = HiddenCanonicalEffect(event_id, family, tuple(affected),
            {"ledger_revision": ledger.revision}, {"applied_by": self.provider_id})
        self._canonical = ledger
        self._last_affected = tuple(affected)
        return ledger, tuple(affected), effect

    def inject(self, event: Any):
        from .runner import InjectionReceipt
        before = deepcopy(self._receipt.payload)
        before_milestones = {
            milestone["milestone_id"]: self.sealed_predicate(
                milestone["predicate"], milestone["arguments"])
            for milestone in self._task_catalog["milestone_predicates"]
        }
        raw, _ = self._physical_event(event)
        self._interruption.fallback_observation = raw
        fresh = self._make_receipt(raw, increment=True)
        user_message = self._user_message(event.family)
        public_catalog = {"objects": self._task["objects"], "entities": self._task["entities"]}
        payload, records = self.evidence_builder.build(
            event_id=event.event_id, event_index=event.event_index,
            previous_public_observation=before, current_public_observation=fresh.payload,
            public_proprioception=fresh.payload["state"], public_user_message=user_message,
            public_task_catalog=public_catalog,
            previously_committed_public_evidence=self._public_evidence,
            observation_ref=fresh.observation_ref, timestamp=fresh.version,
        )
        self._public_evidence.append(payload.to_dict())
        canonical, affected, hidden = self._canonical_event(event)
        legitimately_invalidated = tuple(
            milestone["milestone_id"]
            for milestone in self._task_catalog["milestone_predicates"]
            if before_milestones[milestone["milestone_id"]]
            and not self.sealed_predicate(milestone["predicate"], milestone["arguments"])
        )
        return InjectionReceipt(payload, canonical, legitimately_invalidated,
                                records, affected, hidden)

    def _public_evidence_id(self) -> str:
        return "observation:" + hashlib.sha256(self._receipt.observation_ref.encode()).hexdigest()[:24]

    def public_context(self, observation: Any, previous: ExecutionContext) -> ExecutionContext:
        evidence_id = self._public_evidence_id()
        beliefs = []
        for name, pose in sorted(_poses(observation.payload).items()):
            beliefs.append(BeliefFact(f"pose({name})", pose["position"], 1.0,
                                      (evidence_id,), observation.version))
        state = _finite_vector(observation.payload.get("state"), 8) or (0.0,) * 8
        zones = self._interruption.constraint_state.active_no_go_zones
        flags = {
            "nominal_suspended": False, "ee_at_handoff": True,
            "orientation_restored": True, "safe_clearance": not any(
                zone.contains(state[:3]) for zone in zones.values()),
            "object_grasped": False, "object_stable": False,
            "obstacle_present": bool(zones), "target_changed": False,
            "new_target_known": True, "aligned_to_current_target": True,
            "restore_valid": True,
        }
        repair = {"state": state[:3], "abstract_flags": flags}
        beliefs.append(BeliefFact("repair_observation", repair, 1.0,
                                  (evidence_id,), observation.version))
        by_id = {cert.milestone_id: cert for cert in previous.progress}
        for milestone in self._task_catalog["milestone_predicates"]:
            status = self.verifier.evaluate_goal(
                observation=observation.payload, occurrence_id=milestone["milestone_id"],
                predicate=milestone["predicate"], arguments=milestone["arguments"],
                evidence_ids=(evidence_id,), timestamp=observation.version,
                observation_version=observation.version, evidence_timestamp=observation.version,
            )
            self._runtime_verifications.append(status.to_dict())
            if status.status == "satisfied":
                by_id[milestone["milestone_id"]] = ProgressCertificate(
                    milestone["milestone_id"], milestone["predicate"], tuple(milestone["arguments"]),
                    Satisfaction.SATISFIED, status.verifier_record_id, (evidence_id,),
                    observation.policy_step, (), True)
            elif milestone["milestone_id"] in by_id:
                old = by_id[milestone["milestone_id"]]
                by_id[milestone["milestone_id"]] = replace(
                    old, satisfaction=Satisfaction(status.status),
                    verifier_record_id=status.verifier_record_id, evidence_ids=(evidence_id,),
                    verified_at_step=observation.policy_step, currently_preserved=False)
        continuation = replace(previous.continuation, captured_at_step=observation.policy_step,
                               controller_state_ref=observation.observation_ref)
        context = ExecutionContext(tuple(beliefs), tuple(by_id[key] for key in sorted(by_id)), continuation)
        self._last_public_context = context
        return context

    def macro_complete(self, macro: Mapping, context: Any) -> bool:
        if macro.get("recovery"):
            return False
        evidence_id = self._public_evidence_id()
        result = self.verifier.evaluate_goal(
            observation=self._receipt.payload, occurrence_id=macro["target_occurrence_id"],
            predicate=macro["predicate"], arguments=macro["arguments"],
            evidence_ids=(evidence_id,), timestamp=self._receipt.version,
            observation_version=self._receipt.version, evidence_timestamp=self._receipt.version,
        )
        self._runtime_verifications.append(result.to_dict())
        return result.status == "satisfied"

    def trigger_context(self, *, previous_event_step: int | None):
        from .scheduler import TriggerContext
        poses = _poses(self._receipt.payload)
        state = _finite_vector(self._receipt.payload.get("state"), 8) or (0.0,) * 8
        grasped = tuple(name for name, pose in poses.items()
                        if math.dist(state[:3], pose["position"]) < 0.08 and abs(state[-1]) < 0.03)
        zones = self._interruption.constraint_state.active_no_go_zones
        semantics = {
            "goal_pending_and_target_publicly_localized": bool(poses),
            "active_goal_grounding_publicly_changed": bool(poses),
            "active_goal_requires_workspace_transit": bool(poses),
            "temporary_no_go_is_publicly_observed": bool(zones),
            "active_goal_exists": True,
            "target_availability_restoration_observed": True,
            "user_instruction_targets_active_occurrence": True,
            "user_instruction_reissues_retired_goal_family": True,
        }
        guards = {name: True for name in (
            "catalog_target_displacement_guard", "catalog_receptacle_displacement_guard",
            "catalog_no_go_clearance_guard", "catalog_no_go_retirement_guard",
            "positive_preference_limits_guard", "catalog_ungrasped_availability_guard",
            "catalog_release_and_revalidation_guard", "source_grounded_alternative_goal_guard",
            "active_occurrence_not_retired_guard", "retired_family_fresh_id_guard",
        )}
        return TriggerContext(self._policy_step, semantics, guards, previous_event_step,
                              False, grasped)

    def sealed_predicate(self, predicate: str, arguments: Sequence[str]) -> bool:
        if predicate == "no_go_zone_respected":
            state = _finite_vector(self._receipt.payload.get("state"), 8) or (0.0,) * 8
            return not any(zone.contains(state[:3])
                           for zone in self._interruption.constraint_state.active_no_go_zones.values())
        if predicate == "gentle_action_limits":
            return True
        from cope_benchmark.task_progress import LiberoStateView
        return LiberoStateView(self._env).libero_predicate(predicate, arguments)

    def sealed_progress(self) -> Sequence[Any]:
        results = []
        for milestone in self._task_catalog["milestone_predicates"]:
            if self.sealed_predicate(milestone["predicate"], milestone["arguments"]):
                results.append(ProgressCertificate(
                    milestone["milestone_id"], milestone["predicate"], tuple(milestone["arguments"]),
                    Satisfaction.SATISFIED, "sealed:" + self._receipt.observation_ref,
                    ("sealed-observation",), self._policy_step, (), True))
        return tuple(results)

    def sealed_planning_problem(self):
        from .compiler import compile_ledger
        if self._last_public_context is None:
            raise RuntimeError("public context must be built before sealed planning comparison")
        return compile_ledger(ledger=self._canonical,
                              context=self._last_public_context,
                              source_method=MethodName.COPE_TYPED_EDIT)

    def sealed_protected_projection(self) -> Sequence[Mapping]:
        problem = self.sealed_planning_problem().to_dict()
        affected = set(self._last_affected)
        projections = []
        for field, selector in (("active_goal_occurrence_ids", "string_ids"),
                                ("remaining_goals", "occurrence_id"),
                                ("hard_constraints", "occurrence_id"),
                                ("soft_preferences", "occurrence_id"),
                                ("restore_eligibility", "occurrence_id")):
            value = problem[field]
            if selector == "string_ids":
                expected = [item for item in value if item not in affected]
                ids = list(expected)
            else:
                expected = [item for item in value if item.get("occurrence_id") not in affected]
                ids = [item["occurrence_id"] for item in expected]
            projections.append({"field": field, "selector": selector,
                                "ids": ids, "expected": expected})
        return tuple(projections)

    def snapshot(self) -> Mapping:
        state = self._env.get_sim_state()
        return {
            "version": self.version, "sim_state": state.tolist(),
            "sim_state_dtype": str(state.dtype), "policy_step": self._policy_step,
            "observation_version": self._version, "initial_state_id": self._initial_state_id,
            "seed": self._seed, "task": self._task, "canonical_ledger": self._canonical.to_dict(),
            "constraint_state": self._interruption.constraint_state.snapshot(),
            "receipt": to_primitive(self._receipt), "runtime_verifications": self._runtime_verifications,
            "public_evidence": self._public_evidence, "last_affected": list(self._last_affected),
            "last_public_context": to_primitive(self._last_public_context),
            "availability_release": {key: list(value) for key, value in self._availability_release.items()},
        }

    def restore(self, snapshot: Mapping) -> None:
        import numpy as np
        if snapshot["version"] != self.version or snapshot["task"] != self._task:
            raise ValueError("environment snapshot identity mismatch")
        raw = self._env.set_init_state(np.asarray(snapshot["sim_state"], dtype=snapshot["sim_state_dtype"]))
        self._policy_step = int(snapshot["policy_step"])
        self._version = int(snapshot["observation_version"])
        self._canonical = PersistentLedger.from_dict(snapshot["canonical_ledger"])
        self._interruption.constraint_state = _restore_constraint_state(snapshot["constraint_state"])
        self._runtime_verifications = deepcopy(snapshot["runtime_verifications"])
        self._public_evidence = deepcopy(snapshot["public_evidence"])
        self._last_affected = tuple(snapshot["last_affected"])
        self._last_public_context = (None if snapshot.get("last_public_context") is None else
                                     ExecutionContext.from_dict(snapshot["last_public_context"]))
        self._availability_release = {
            str(key): tuple(float(item) for item in value)
            for key, value in snapshot.get("availability_release", {}).items()
        }
        self._interruption.fallback_observation = raw
        actual = self._make_receipt(raw, increment=False)
        expected = snapshot["receipt"]
        if to_primitive(actual) != expected:
            raise ValueError("restored public observation differs from saved boundary")

    def close(self) -> None:
        if self._env is not None:
            self._env.close()
            self._env = None


class _SharedNativePolicyPool:
    """One immutable model allocation, independent per-trajectory adapter state."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = deepcopy(dict(config))
        self.loaded = None

    def create(self):
        from .vla_adapter import NativeOpenVLAAdapter, create_native_openvla
        if self.loaded is None:
            first = create_native_openvla(self.config)
            self.loaded = (first._model, first._processor, first._model_config,
                           first._get_action, deepcopy(first.identity))
        model, processor, model_config, get_action, identity = self.loaded
        return NativeOpenVLAAdapter(model=model, processor=processor, model_config=model_config,
                                    get_action=get_action, identity=deepcopy(identity))


def create_runtime_assembly(config: Mapping[str, Any]):
    """Factory exported as COPE_RUNTIME_FACTORY.

    Required environment variables name existing local assets and an audited
    OpenAI-compatible Qwen endpoint.  Construction itself performs zero model,
    simulator, VLA, or reasoner calls.
    """
    from .adapters import create_adapter
    from .continuation_backend import ContinuationBackendConfig, ContinuationPlannerBackend
    from .pilot import EpisodeInputs, RuntimeAssembly
    from .provider import ReasonerConfig, ReasonerGateway, reasoner_from_environment
    from .task_catalog import load_task_catalog

    catalog_path = Path(os.environ.get("COPE_TASK_CATALOG",
        Path(__file__).resolve().parents[2] / "task_catalogs/repeated_v2_1/catalog.json"))
    catalog_object = load_task_catalog(catalog_path)
    catalog = {task.task_id: task.to_dict() for task in catalog_object.tasks}
    checkpoint_path = os.environ.get("COPE_VLA_CHECKPOINT", "")
    runtime_path = os.environ.get("COPE_OPENVLA_RUNTIME", "/home/lijingsu/vla/src/openvla")
    backend_root = os.environ.get("COPE_CONTINUATION_PACKAGE_ROOT", str(
        Path(__file__).resolve().parents[2] /
        "research/server_sync_20260905/content/fvl12/v/cope_r4_20260905/code"))
    continuation_config = ContinuationBackendConfig(package_root=backend_root)
    continuation_package = Path(backend_root).expanduser().resolve() / "rekep_repair"
    if not (continuation_package / "repair/repair_manager.py").is_file():
        from .runner import RuntimeBlocked
        raise RuntimeBlocked("BLOCKED_CONTINUATION_BACKEND_UNAVAILABLE",
                             "configured continuation package is unavailable")
    continuation_package_sha256 = _python_tree_hash(continuation_package)
    gpu = os.environ.get("COPE_VLA_GPU", "0")
    vla_config = {"checkpoint_path": checkpoint_path, "checkpoint_sha256": CHECKPOINT_SHA256,
                  "runtime_path": runtime_path, "gpu": gpu, "task_suite": "libero_10",
                  "unnorm_key": "libero_10", "policy_model_id": "openvla-7b-finetuned-libero-10"}
    pool = _SharedNativePolicyPool(vla_config)

    def episode_inputs(*, manifest: Mapping[str, Any], task: Mapping[str, Any]):
        ledger = _initial_ledger(task)
        return EpisodeInputs(_public_task(task, manifest["master_episode_id"]), ledger,
                             _initial_context(ledger))

    def environment_factory():
        return ProductionLiberoEnvironment(
            catalog=catalog, evidence_builder=PublicEventEvidenceBuilder(),
            verifier=PublicRuntimeVerifier(), checkpoint_path=checkpoint_path)

    def nominal_planner_factory():
        return NominalPlanner()

    def public_verifier_factory():
        return PublicRuntimeVerifier()

    def continuation_backend_factory():
        return ContinuationPlannerBackend(
            nominal_backend=nominal_planner_factory(), verifier=public_verifier_factory(),
            config=continuation_config)

    def planner_factory():
        return continuation_backend_factory()

    def vla_asset_preflight():
        from .vla_adapter import validate_native_openvla_assets
        return validate_native_openvla_assets(vla_config)

    def method_factory(*, method_name: str, information_condition: str):
        if method_name == MethodName.CLASSICAL_EXECUTION_MONITOR.value:
            return create_adapter(method_name)
        reasoner = reasoner_from_environment()
        reasoner_config = ReasonerConfig(
            provider=reasoner.provider_id, model=reasoner.model_id, temperature=0.0, seed=0,
            max_input_tokens=int(config["reasoner"]["max_input_tokens_" + information_condition]),
            max_output_tokens=int(config["reasoner"]["max_output_tokens"]),
            setting=information_condition, semantic_retries=0,
        )
        return create_adapter(method_name, gateway=ReasonerGateway(reasoner, reasoner_config))

    component_manifest = {
        "public_evidence_builder": deepcopy(PublicEventEvidenceBuilder.identity),
        "public_runtime_verifier": deepcopy(PublicRuntimeVerifier.identity),
        "nominal_planner": deepcopy(NominalPlanner.identity),
        "continuation_backend": {
            **_identity("continuation_carrying_repair_v2", "continuation_backend_v2",
                        ("PlanningProblem", "ExecutionContext"), ("ExecutionPlan",)),
            "package_root": str(Path(backend_root).resolve()),
            "package_sha256": continuation_package_sha256,
            "adapter_source_sha256": hashlib.sha256(
                Path(__file__).with_name("continuation_backend.py").read_bytes()).hexdigest(),
            "nominal_planner_identity": deepcopy(NominalPlanner.identity),
            "public_verifier_identity": deepcopy(PublicRuntimeVerifier.identity),
            "config_sha256": canonical_sha256(continuation_config),
        },
        "compiler": {
            **_identity("compile_ledger", "pure_compiler_v2", ("accepted_method_state", "ExecutionContext"),
                        ("PlanningProblem",)),
            "source_sha256": hashlib.sha256((Path(__file__).with_name("compiler.py")).read_bytes()).hexdigest(),
        },
        "sealed_evaluator": {
            "provider_id": "sealed_dynamic_v2.1", "version": "sealed_dynamic_evaluator_v2.1",
            "uses_hidden_canonical_state": True, "uses_privileged_simulator_state": True,
            "input_schema_hash": _schema_hash({"fields": ["canonical_ledger", "sealed_predicate"]}),
            "output_schema_hash": _schema_hash({"fields": ["SealedEvaluation"]}),
            "public_loop": False,
        },
    }
    identity = {
        "runtime": {
            "provider_id": "cope_repeated_v2_1_production_runtime", "version": "v1",
            "uses_hidden_canonical_state": True, "uses_privileged_simulator_state": True,
            "input_schema_hash": _schema_hash({"fields": ["RuntimeAssemblyInputs"]}),
            "output_schema_hash": _schema_hash({"fields": ["DurablePilotArtifacts"]}),
            "trusted_harness": True,
        },
        "components": component_manifest,
        "reasoner": {
            **_identity("openai_compatible_http", "repeated_v2_openai_compatible_reasoner_v1",
                        ("public_prompt",), ("method_proposal",)),
            "model_id": QWEN_MODEL,
            "model_revision": QWEN_REVISION,
        },
        "vla": {
                **_identity("openvla_native", "native_openvla_observation_client_v1",
                            ("rgb", "instruction"), ("finite_action_chunk_1x7",)),
                "policy_model_id": "openvla-7b-finetuned-libero-10",
                "checkpoint_sha256": CHECKPOINT_SHA256,
                "learned_policy": True, "uses_privileged_state": False,
                "action_dimension": 7, "max_action_chunk_horizon": 1,
        },
    }
    return RuntimeAssembly(
        episode_inputs=episode_inputs, environment_factory=environment_factory,
        planner_factory=planner_factory, method_factory=method_factory, identity=identity,
        policy_factory=pool.create, current_identity=lambda: deepcopy(identity), fixture=False,
        public_evidence_builder_factory=PublicEventEvidenceBuilder,
        public_verifier_factory=public_verifier_factory,
        nominal_planner_factory=nominal_planner_factory,
        continuation_backend_factory=continuation_backend_factory,
        vla_asset_preflight=vla_asset_preflight,
        sealed_evaluator_provider_id="sealed_dynamic_v2.1",
    )


COPE_RUNTIME_FACTORY = "cope_benchmark.repeated_v2.production_runtime:create_runtime_assembly"
