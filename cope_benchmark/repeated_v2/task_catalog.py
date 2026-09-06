"""Versioned LIBERO-10 task semantics; missing evidence always blocks selection.

Static BDDL semantics do not establish interruption feasibility. The checked-in
catalog is therefore an auditable inventory, not a declaration of eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .task_calibration import CalibrationBlockedError, summarize_calibration


CATALOG_SCHEMA_VERSION = "repeated_v2_task_catalog_v1"
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "task_catalogs" / "repeated_v2.json"
STRUCTURAL_CHECKS = (
    "two_independently_verifiable_milestones",
    "completed_milestone_preservable",
    "safe_changeable_grounding",
    "cross_skill_requirement_or_persistent_preference",
)
EVENT_FAMILIES = (
    "TARGET_OBJECT_DISPLACED", "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED",
    "TEMPORARY_NO_GO_APPEARS", "TEMPORARY_NO_GO_CLEARS",
    "USER_ADDS_PERSISTENT_PREFERENCE", "TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE",
    "TOOL_OR_TARGET_AVAILABLE_AGAIN", "USER_REPLACES_ACTIVE_GOAL",
    "USER_CANCELS_ACTIVE_GOAL", "USER_REISSUES_RETIRED_GOAL",
)
PHYSICAL_EVENT_FAMILIES = EVENT_FAMILIES[:4] + EVENT_FAMILIES[5:7]
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class CatalogBlockedError(ValueError):
    def __init__(self, reasons: Iterable[str], status: str = "BLOCKED_TASK_CATALOG_GAPS"):
        self.status = status
        self.reasons = tuple(sorted(set(reasons)))
        super().__init__(f"{status}: {'; '.join(self.reasons)}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("catalog mappings require string keys")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if type(value) is float and not math.isfinite(value):
        raise ValueError("catalog values must be finite")
    if value is None or type(value) in (str, int, bool, float):
        return value
    raise ValueError(f"unsupported catalog value {type(value).__name__}")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class TaskRecord:
    task_id: int
    task_name: str
    original_instruction: str
    object_aliases: Mapping[str, str]
    receptacle_region_aliases: Mapping[str, str]
    initial_achievement_goals: tuple[Mapping[str, Any], ...]
    maintenance_invariants: tuple[Mapping[str, Any], ...]
    hard_safety_constraints: tuple[Mapping[str, Any], ...]
    soft_preference_templates: tuple[Mapping[str, Any], ...]
    milestone_predicates: tuple[Mapping[str, Any], ...]
    alternative_valid_goals: tuple[Mapping[str, Any], ...]
    replaceable_goal_families: tuple[str, ...]
    safe_event_injection_poses: Mapping[str, Any]
    supported_event_families: tuple[str, ...]
    semantic_triggers: Mapping[str, Mapping[str, Any]]
    dynamic_evaluator_predicates: tuple[Mapping[str, Any], ...]
    planner_compiler_metadata: Mapping[str, Any]
    initial_state_digests: Mapping[str, str]
    structural_checks: Mapping[str, Mapping[str, Any]]
    event_feasibility: Mapping[str, Mapping[str, Any]]
    calibration_records: tuple[Mapping[str, Any], ...]
    source_refs: tuple[Mapping[str, Any], ...]
    unresolved_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _freeze(getattr(self, field.name)))
        if type(self.task_id) is not int or not 0 <= self.task_id < 10:
            raise ValueError("task_id must be an integer in 0..9")
        for name in ("task_name", "original_instruction"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("object_aliases", "receptacle_region_aliases", "safe_event_injection_poses", "semantic_triggers",
                     "planner_compiler_metadata", "initial_state_digests", "structural_checks", "event_feasibility"):
            if not isinstance(getattr(self, name), Mapping):
                raise ValueError(f"{name} must be a mapping")
        for field in fields(self):
            if field.name not in ("task_id", "task_name", "original_instruction") and "tuple" in str(field.type):
                if not isinstance(getattr(self, field.name), tuple):
                    raise ValueError(f"{field.name} must be a sequence")
        for name in ("initial_achievement_goals", "maintenance_invariants", "hard_safety_constraints",
                     "soft_preference_templates", "milestone_predicates", "alternative_valid_goals",
                     "dynamic_evaluator_predicates", "calibration_records", "source_refs"):
            if any(not isinstance(item, Mapping) for item in getattr(self, name)):
                raise ValueError(f"{name} requires mapping records")
        for name in ("replaceable_goal_families", "supported_event_families", "unresolved_fields"):
            if any(not isinstance(item, str) or not item for item in getattr(self, name)):
                raise ValueError(f"{name} requires nonempty strings")
        for name in ("semantic_triggers", "structural_checks", "event_feasibility"):
            if any(not isinstance(item, Mapping) for item in getattr(self, name).values()):
                raise ValueError(f"{name} requires mapping values")
        if any(not isinstance(value, str) for value in self.initial_state_digests.values()):
            raise ValueError("initial_state_digests requires strings")
        for records in (self.initial_achievement_goals, self.alternative_valid_goals, self.milestone_predicates):
            for record in records:
                for key in ("family_key", "milestone_id", "predicate", "verifier", "source_ref"):
                    if key in record and not isinstance(record[key], str):
                        raise ValueError(f"{key} must be a string")
                if "arguments" in record and (not isinstance(record["arguments"], tuple)
                                             or any(not isinstance(arg, str) for arg in record["arguments"])):
                    raise ValueError("predicate arguments must be a sequence of simulator-name strings")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TaskRecord":
        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as exc:
            raise CatalogBlockedError((f"invalid task record schema: {exc}",)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {field.name: _thaw(getattr(self, field.name)) for field in fields(self)}

    @property
    def semantic_trigger_definitions(self) -> Mapping[str, Mapping[str, Any]]:
        return self.semantic_triggers


@dataclass(frozen=True)
class TaskCatalog:
    schema_version: str
    task_suite: str
    selection_rule: str
    provenance_kind: str
    tasks: tuple[TaskRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if self.schema_version != CATALOG_SCHEMA_VERSION or self.task_suite != "libero_10":
            raise CatalogBlockedError(("catalog version/suite differs from frozen v2",))
        if self.selection_rule != "all_semantically_eligible":
            raise CatalogBlockedError(("task selection must include all semantically eligible tasks",))
        if self.provenance_kind not in ("source_backed", "synthetic_test_fixture"):
            raise CatalogBlockedError(("catalog provenance is invalid",))
        if not all(isinstance(task, TaskRecord) for task in self.tasks):
            raise CatalogBlockedError(("tasks must contain TaskRecord objects",))
        ids = [task.task_id for task in self.tasks]
        if sorted(ids) != list(range(10)):
            raise CatalogBlockedError(("catalog must enumerate each LIBERO-10 task exactly once",))
        if len({task.task_name for task in self.tasks}) != 10:
            raise CatalogBlockedError(("catalog task names must be distinct",))
        object.__setattr__(self, "tasks", tuple(sorted(self.tasks, key=lambda task: task.task_id)))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TaskCatalog":
        try:
            copied = dict(value)
            copied["tasks"] = tuple(TaskRecord.from_dict(task) for task in copied["tasks"])
            return cls(**copied)
        except (TypeError, KeyError, ValueError) as exc:
            if isinstance(exc, CatalogBlockedError):
                raise
            raise CatalogBlockedError((f"invalid catalog schema: {exc}",)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "task_suite": self.task_suite,
                "selection_rule": self.selection_rule, "provenance_kind": self.provenance_kind,
                "tasks": [task.to_dict() for task in self.tasks]}


def load_task_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> TaskCatalog:
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CatalogBlockedError((f"duplicate catalog JSON key: {key}",))
            result[key] = value
        return result
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"nonfinite value {value}")))
        return TaskCatalog.from_dict(value)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, CatalogBlockedError):
            raise
        raise CatalogBlockedError((f"cannot load catalog: {exc}",)) from exc


def _task_gaps(task: TaskRecord, *, allow_synthetic: bool) -> tuple[str, ...]:
    from .scheduler import SemanticTrigger

    errors = []
    for name in task.unresolved_fields:
        errors.append(f"unresolved {name}")
    for name in ("object_aliases", "receptacle_region_aliases", "initial_achievement_goals", "hard_safety_constraints",
                 "soft_preference_templates", "alternative_valid_goals", "replaceable_goal_families",
                 "dynamic_evaluator_predicates", "planner_compiler_metadata", "source_refs"):
        if not getattr(task, name):
            errors.append(f"missing {name}")
    for mapping in (task.object_aliases, task.receptacle_region_aliases):
        if any(not isinstance(value, str) or not value.strip() for value in mapping.values()):
            errors.append("aliases require explicit simulator names")
    goal_families = {goal.get("family_key") for goal in task.initial_achievement_goals}
    if len(goal_families) != len(task.initial_achievement_goals):
        errors.append("duplicate initial goal families")
    for family in task.replaceable_goal_families:
        if family not in goal_families:
            errors.append(f"replaceable family absent from initial goals: {family}")
    for goal in task.initial_achievement_goals + task.alternative_valid_goals:
        if not all(goal.get(key) for key in ("family_key", "predicate", "arguments", "source_ref")):
            errors.append("goal definition missing semantic fields/source")
    if len(task.milestone_predicates) < 2:
        errors.append("fewer than two verified milestone definitions")
    milestone_ids = [record.get("milestone_id") for record in task.milestone_predicates]
    if len(set(milestone_ids)) != len(milestone_ids):
        errors.append("duplicate milestone IDs")
    for milestone in task.milestone_predicates:
        if not all(milestone.get(key) for key in ("milestone_id", "predicate", "arguments", "verifier", "source_ref")):
            errors.append("milestone definition lacks verifier/predicate/source")
    independent = [record for record in task.milestone_predicates if record.get("independent") is True]
    if len({(record.get("predicate"), tuple(record.get("arguments", ()))) for record in independent}) < 2:
        errors.append("fewer than two independently verified distinct milestone predicates")
    if not any(record.get("can_remain_valid") is True for record in task.milestone_predicates):
        errors.append("no verified preservable milestone")
    for source in task.source_refs:
        if not isinstance(source.get("uri"), str) or not source.get("uri") or not isinstance(source.get("sha256"), str) or not _SHA256.fullmatch(source["sha256"]):
            errors.append("source reference requires URI and SHA256")
    for key in STRUCTURAL_CHECKS:
        check = task.structural_checks.get(key, {})
        if type(check.get("passed")) is not bool or not check.get("evidence_refs"):
            errors.append(f"unverified structural check {key}")
    for state_id in range(5):
        if not _SHA256.fullmatch(task.initial_state_digests.get(str(state_id), "")):
            errors.append(f"missing initial state digest {state_id}")
    supported = set(task.supported_event_families)
    unknown = supported - set(EVENT_FAMILIES)
    duplicate_support = len(supported) != len(task.supported_event_families)
    unresolved_support = not supported or "supported_event_families" in task.unresolved_fields
    if unresolved_support:
        # Keep the inventory gap and audit all families until
        # task-local scope is resolved. Empty scope cannot erase missing data.
        if supported != set(EVENT_FAMILIES) or duplicate_support:
            errors.append("task-specific event family support is unresolved; auditing all ten candidates")
    if unknown:
        errors.append(f"unknown supported event families: {sorted(unknown)}")
    if duplicate_support:
        errors.append("duplicate supported event families")
    if unresolved_support or unknown or duplicate_support:
        audited_families = EVENT_FAMILIES
    else:
        audited_families = tuple(family for family in EVENT_FAMILIES if family in supported)
        categories = {
            "grounding shift": bool(supported & set(EVENT_FAMILIES[:2])),
            "temporary lifecycle": any(set(pair) <= supported for pair in (
                EVENT_FAMILIES[2:4], EVENT_FAMILIES[5:7])),
            "persistent preference": EVENT_FAMILIES[4] in supported,
            "goal retirement": bool(supported & set(EVENT_FAMILIES[7:9])),
            "fresh goal reissue": EVENT_FAMILIES[9] in supported,
        }
        for category, covered in categories.items():
            if not covered:
                errors.append(f"supported event families lack scientific category: {category}")
    for family in audited_families:
        check = task.event_feasibility.get(family, {})
        if type(check.get("passed")) is not bool or not check.get("evidence_refs") or tuple(check.get("covered_state_ids", ())) != tuple(range(5)):
            errors.append(f"unverified event feasibility {family}")
        trigger = task.semantic_triggers.get(family, {})
        try:
            SemanticTrigger.from_dict(trigger)
        except (TypeError, ValueError) as exc:
            errors.append(f"invalid semantic trigger {family}: {exc}")
        if not trigger.get("predicate") or not trigger.get("physical_feasibility_guard"):
            errors.append(f"missing semantic trigger/guard {family}")
        earliest, latest, gap = (trigger.get(key) for key in ("earliest_policy_step", "latest_policy_step", "min_steps_since_previous_event"))
        if any(type(value) is not int for value in (earliest, latest, gap)) or not (0 <= earliest <= latest <= 260 and gap >= 10):
            errors.append(f"invalid semantic trigger window {family}")
        if family in PHYSICAL_EVENT_FAMILIES:
            intervention = task.safe_event_injection_poses.get(family)
            if not isinstance(intervention, Mapping) or not intervention.get("evidence_refs") or not intervention.get("entity"):
                errors.append(f"missing certified safe event injection poses/regions {family}")
            elif not intervention.get("pose") and not intervention.get("region"):
                errors.append(f"safe intervention lacks an explicit pose or region {family}")
            elif intervention.get("entity") not in set(task.object_aliases.values()) | set(task.receptacle_region_aliases.values()):
                errors.append(f"safe intervention entity is absent from task aliases {family}")
            elif intervention.get("pose"):
                pose = intervention["pose"]
                if not isinstance(pose, tuple) or len(pose) != 3 or any(type(value) not in (int, float) for value in pose):
                    errors.append(f"safe intervention pose must have three numeric coordinates {family}")
    try:
        summarize_calibration(task.task_id, task.calibration_records,
                              initial_state_digests=task.initial_state_digests, allow_synthetic=allow_synthetic)
    except CalibrationBlockedError as exc:
        errors.extend(exc.reasons)
    return tuple(sorted(set(errors)))


def task_catalog_gaps(catalog: TaskCatalog, *, allow_synthetic: bool = False) -> tuple[str, ...]:
    errors = []
    if catalog.provenance_kind == "synthetic_test_fixture" and not allow_synthetic:
        errors.append("synthetic catalogs are forbidden for formal selection")
    for task in catalog.tasks:
        errors.extend(f"task {task.task_id}: {reason}" for reason in _task_gaps(task, allow_synthetic=allow_synthetic))
    return tuple(errors)


def select_eligible_tasks(catalog: TaskCatalog, *, allow_synthetic: bool = False) -> tuple[TaskRecord, ...]:
    gaps = task_catalog_gaps(catalog, allow_synthetic=allow_synthetic)
    if gaps:
        raise CatalogBlockedError(gaps)
    selected = tuple(task for task in catalog.tasks
                     if all(task.structural_checks[key]["passed"] for key in STRUCTURAL_CHECKS)
                     and all(task.event_feasibility[family]["passed"] for family in task.supported_event_families)
                     and summarize_calibration(task.task_id, task.calibration_records,
                                               initial_state_digests=task.initial_state_digests,
                                               allow_synthetic=allow_synthetic).eligible_success_rate)
    if len(selected) < 8:
        raise CatalogBlockedError((f"need at least 8 eligible tasks; found {len(selected)}",),
                                  "BLOCKED_INSUFFICIENT_ELIGIBLE_TASKS")
    summaries = [summarize_calibration(task.task_id, task.calibration_records,
                                      initial_state_digests=task.initial_state_digests,
                                      allow_synthetic=allow_synthetic) for task in catalog.tasks]
    if len({(summary.policy_id, summary.checkpoint_sha256, summary.protocol_sha256) for summary in summaries}) != 1:
        raise CatalogBlockedError(("all tasks must share a clean calibration policy/checkpoint/protocol",))
    return selected


def validate_task_catalog(catalog: TaskCatalog, *, require_eligible: bool = True,
                          allow_synthetic: bool = False) -> None:
    if require_eligible:
        select_eligible_tasks(catalog, allow_synthetic=allow_synthetic)
    else:
        gaps = task_catalog_gaps(catalog, allow_synthetic=allow_synthetic)
        if gaps:
            raise CatalogBlockedError(gaps)
