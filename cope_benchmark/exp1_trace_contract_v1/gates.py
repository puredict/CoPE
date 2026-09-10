"""Independent Experiment-1 dependency gates consumed by later experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXP1_INTERFACE_CONTRACT_FROZEN = "EXP1_INTERFACE_CONTRACT_FROZEN"
EXP1_TASK_CATALOG_FROZEN = "EXP1_TASK_CATALOG_FROZEN"
EXP1_FORMAL_TRACE_DATA_AVAILABLE = "EXP1_FORMAL_TRACE_DATA_AVAILABLE"


@dataclass(frozen=True)
class Experiment1DependencyGates:
    interface_contract_frozen: bool
    task_catalog_frozen: bool
    formal_trace_data_available: bool

    @classmethod
    def inspect(
        cls,
        *,
        contract_manifest: str | Path,
        task_catalog_manifest: str | Path | None = None,
        formal_trace_manifest: str | Path | None = None,
    ) -> "Experiment1DependencyGates":
        """Inspect presence only; task/trace gates never affect interface freeze."""
        return cls(
            interface_contract_frozen=Path(contract_manifest).is_file(),
            task_catalog_frozen=(
                task_catalog_manifest is not None and Path(task_catalog_manifest).is_file()
            ),
            formal_trace_data_available=(
                formal_trace_manifest is not None and Path(formal_trace_manifest).is_file()
            ),
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            EXP1_INTERFACE_CONTRACT_FROZEN: self.interface_contract_frozen,
            EXP1_TASK_CATALOG_FROZEN: self.task_catalog_frozen,
            EXP1_FORMAL_TRACE_DATA_AVAILABLE: self.formal_trace_data_available,
        }
