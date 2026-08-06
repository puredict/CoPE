from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from cope.providers.base import load_object


@dataclass(frozen=True)
class DetectorResult:
    detected: bool
    event_packet: dict[str, Any] | None
    confidence: float | None
    latency_steps: int
    raw_output: Any


@runtime_checkable
class RecoveryEventDetector(Protocol):
    @property
    def metadata(self) -> dict[str, Any]: ...

    def detect(
        self,
        *,
        observation: dict[str, Any],
        public_action_history: tuple[dict[str, Any], ...],
        policy_step: int,
    ) -> DetectorResult: ...


DetectorFactory = Callable[[dict[str, Any]], RecoveryEventDetector]


def load_detector_factory(spec: str) -> DetectorFactory:
    factory = load_object(spec)
    if not callable(factory):
        raise TypeError(f"detector factory {spec!r} is not callable")
    return factory
