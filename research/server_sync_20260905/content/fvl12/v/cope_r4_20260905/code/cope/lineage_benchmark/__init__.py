"""Resource-bounded CoPE vs full-state regeneration benchmark.

The r3 benchmark keeps the r2 simulator/controller stack intact and adds a
lineage-sensitive long-horizon task plus an actual fixed-LLM adaptation path.
"""

from .task import LineageScenario, ScenarioSpec, build_scenario
from .runner import run_episode

__all__ = ["LineageScenario", "ScenarioSpec", "build_scenario", "run_episode"]
