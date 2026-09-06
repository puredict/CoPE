#!/usr/bin/env python3
"""Prove the registered task succeeds with lineage and fails when it is flattened."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cope.lineage_benchmark.models import ScenarioSpec  # noqa: E402
from cope.lineage_benchmark.state import active_plan, apply_patch_document  # noqa: E402
from cope.lineage_benchmark.task import build_scenario, oracle_patch  # noqa: E402
from cope.lineage_benchmark.world import SymbolicBasketWorld  # noqa: E402


def main() -> int:
    scenario = build_scenario(ScenarioSpec(
        seed=0,
        profile="causal_gate",
        initial_slots=10,
        lineage_depth=6,
        max_output_tokens=4096,
        model_timeout_s=90.0,
    ))
    state = scenario.initial_state
    for event in scenario.events[:-1]:
        state = apply_patch_document(
            state, oracle_patch(state, event), event, scenario.critical_logical_id
        )
    surface_only_plan = active_plan(state, scenario.critical_logical_id)
    final_event = scenario.events[-1]
    restored = apply_patch_document(
        state,
        oracle_patch(state, final_event),
        final_event,
        scenario.critical_logical_id,
    )
    lineage_plan = active_plan(restored, scenario.critical_logical_id)
    world = SymbolicBasketWorld()
    with tempfile.TemporaryDirectory() as tmp:
        correct = world.execute(
            lineage_plan,
            scenario.expected_plan,
            seed=0,
            episode_dir=Path(tmp) / "correct",
        )
        flattened = world.execute(
            surface_only_plan,
            scenario.expected_plan,
            seed=0,
            episode_dir=Path(tmp) / "flattened",
        )
    report = {
        "schema_version": "cope-fsrpc-r3-causal-gate-v1",
        "same_surface_first_action": lineage_plan[0] == surface_only_plan[0],
        "different_bound_continuation": lineage_plan[1:] != surface_only_plan[1:],
        "lineage_aware_task_success": correct["physical_success"],
        "surface_only_task_success": flattened["physical_success"],
        "passed": bool(
            lineage_plan[0] == surface_only_plan[0]
            and lineage_plan[1:] != surface_only_plan[1:]
            and correct["physical_success"]
            and not flattened["physical_success"]
        ),
        "lineage_plan": lineage_plan,
        "surface_only_plan": surface_only_plan,
        "expected_assignment": correct["expected_assignment"],
        "surface_only_assignment": flattened["observed_assignment"],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

