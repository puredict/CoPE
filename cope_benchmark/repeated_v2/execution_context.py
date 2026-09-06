"""Execution context is owned by perception, verification, and execution.

The event injector deliberately has no access to this type. Phase 1 defines
the records only; mutation authorization belongs to the later runtime.
"""

from .schema import BeliefFact, ContinuationState, ExecutionContext, ProgressCertificate

__all__ = ["BeliefFact", "ContinuationState", "ExecutionContext", "ProgressCertificate"]
