"""The bridge from the CoPE semantic layer into the FROZEN repair engine.

Both `CoPEPatchPolicy` and `FSRPCPolicy` enter this package after producing
their state update, and from here on the code path is identical. Nothing in
`rekep_repair/` is modified or re-implemented; it is imported and called.
"""
from .continuation_capture import capture_continuation
from .engine import RepairOutcome, SharedRepairEngine
from .goal_compiler import (
    ConstraintStateToRepairGoalCompiler, RepairRequirements, RequirementSource,
)
from .stages import REQUIRED_ORDER, PipelineStage, assert_complete

__all__ = ["capture_continuation", "RepairOutcome", "SharedRepairEngine",
           "ConstraintStateToRepairGoalCompiler", "RepairRequirements",
           "RequirementSource", "PipelineStage", "REQUIRED_ORDER",
           "assert_complete"]
