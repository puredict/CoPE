"""Reusable benchmark primitives for repeated-interruption experiments.

The package deliberately contains no CoPE state engine.  Formal recovery
implementations are injected through the adapter protocol so the benchmark can
consume the canonical engine from ``method/cope-state-semantics``.
"""

from .interruptions import (
    INTERRUPTION_LIBRARY_VERSION,
    InterruptionEvent,
    InterruptionType,
)
from .task_progress import ProgressPredicateSpec, ProgressTracker

__all__ = [
    "INTERRUPTION_LIBRARY_VERSION",
    "InterruptionEvent",
    "InterruptionType",
    "ProgressPredicateSpec",
    "ProgressTracker",
]
