"""Frozen v2 vocabularies; lifecycle, grounding and progress are independent."""

from enum import Enum


class Lifecycle(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OVERRIDDEN = "overridden"
    EXPIRED = "expired"


class GroundingValidity(str, Enum):
    VALID = "valid"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class Satisfaction(str, Enum):
    UNRESOLVED = "unresolved"
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class CommitmentRole(str, Enum):
    ACHIEVEMENT_GOAL = "achievement_goal"
    MAINTENANCE_INVARIANT = "maintenance_invariant"
    SAFETY_REQUIREMENT = "safety_requirement"
    USER_PREFERENCE = "user_preference"
    GROUNDING_BINDING = "grounding_binding"


class MethodName(str, Enum):
    COPE_TYPED_EDIT = "cope_typed_edit"
    GENERIC_PERSISTENT_EDIT = "generic_persistent_edit"
    FULL_STATE_REGENERATION = "full_state_regeneration"
    FULL_HISTORY_REPLAN = "full_history_replan"
    RAG_REPLAN = "rag_replan"
    SUMMARY_MEMORY_REPLAN = "summary_memory_replan"
    SKILL_LOCAL_REPLAN = "skill_local_replan"
    CLASSICAL_EXECUTION_MONITOR = "classical_execution_monitor"
    ORACLE_PERSISTENT_UPDATE = "oracle_persistent_update"


class ProtocolName(str, Enum):
    CONTROLLED = "controlled"
    END_TO_END = "end_to_end"


class EventFamily(str, Enum):
    TARGET_OBJECT_DISPLACED = "TARGET_OBJECT_DISPLACED"
    GOAL_RECEPTACLE_OR_GROUNDING_CHANGED = "GOAL_RECEPTACLE_OR_GROUNDING_CHANGED"
    TEMPORARY_NO_GO_APPEARS = "TEMPORARY_NO_GO_APPEARS"
    TEMPORARY_NO_GO_CLEARS = "TEMPORARY_NO_GO_CLEARS"
    USER_ADDS_PERSISTENT_PREFERENCE = "USER_ADDS_PERSISTENT_PREFERENCE"
    TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE = "TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE"
    TOOL_OR_TARGET_AVAILABLE_AGAIN = "TOOL_OR_TARGET_AVAILABLE_AGAIN"
    USER_REPLACES_ACTIVE_GOAL = "USER_REPLACES_ACTIVE_GOAL"
    USER_CANCELS_ACTIVE_GOAL = "USER_CANCELS_ACTIVE_GOAL"
    USER_REISSUES_RETIRED_GOAL = "USER_REISSUES_RETIRED_GOAL"


class Operator(str, Enum):
    INSERT = "INSERT"
    SUSPEND = "SUSPEND"
    OVERRIDE = "OVERRIDE"
    SET_PRIORITY = "SET_PRIORITY"
    EXPIRE = "EXPIRE"
    RESTORE = "RESTORE"


NON_ORACLE_METHODS = tuple(m for m in MethodName if m is not MethodName.ORACLE_PERSISTENT_UPDATE)
