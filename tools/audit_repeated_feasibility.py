#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.interruptions import AxisAlignedBox  # noqa: E402
from cope_benchmark.repeated_manifest import read_jsonl  # noqa: E402
from cope_benchmark.task_progress import (  # noqa: E402
    TASK_DEFINITIONS,
    LiberoStateView,
    ProgressTracker,
)


def _free_joints(env: Any) -> list[str]:
    sim = env.sim
    return sorted(
        str(sim.model.joint_id2name(index))
        for index in range(int(sim.model.njnt))
        if sim.model.joint_id2name(index)
        and int(sim.model.jnt_type[index]) == 0
        and not str(sim.model.joint_id2name(index)).startswith(("robot", "gripper"))
    )


def _eef_position(env: Any) -> list[float]:
    site_id = env.env.robots[0].eef_site_id
    return [float(value) for value in env.sim.data.site_xpos[site_id]]


def _no_go_payload_by_task(manifest_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in manifest_rows:
        task_id = int(row["pair_fields"]["task_id"])
        for event in row["event_schedule"]:
            if event["event_type"] == "temporary_no_go_zone_appears":
                result.setdefault(task_id, event["payload"])
    return result


def audit(manifest: Path) -> dict[str, Any]:
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs.env_wrapper import ControlEnv

    suite_status: dict[str, Any] = {}
    for name, suite_class in sorted(benchmark.get_benchmark_dict().items()):
        try:
            suite = suite_class()
            suite_status[name] = {"available": True, "n_tasks": int(suite.n_tasks)}
        except Exception as exc:
            suite_status[name] = {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    rows = read_jsonl(manifest)
    no_go_payloads = _no_go_payload_by_task(rows)
    suite = benchmark.get_benchmark_dict()["libero_10"]()
    task_reports: list[dict[str, Any]] = []
    for key in sorted(TASK_DEFINITIONS):
        definition = TASK_DEFINITIONS[key]
        task = suite.get_task(definition.task_id)
        bddl = (
            Path(get_libero_path("bddl_files"))
            / str(task.problem_folder)
            / str(task.bddl_file)
        )
        env = ControlEnv(
            bddl_file_name=str(bddl),
            use_camera_obs=False,
            has_renderer=False,
            has_offscreen_renderer=False,
            camera_names=[],
            ignore_done=True,
        )
        try:
            env.seed(20260724)
            env.reset()
            available_joints = _free_joints(env)
            state_reports: list[dict[str, Any]] = []
            initial_states = suite.get_task_init_states(definition.task_id)
            for state_id in range(5):
                initial_state = initial_states[state_id]
                env.set_init_state(initial_state)
                view = LiberoStateView(env)
                progress = ProgressTracker(definition).sample(view, policy_step=0)
                eef = _eef_position(env)
                zone = AxisAlignedBox.from_payload(no_go_payloads[definition.task_id])
                state_reports.append(
                    {
                        "state_id": state_id,
                        "initial_state_digest": hashlib.sha256(
                            np.asarray(initial_state).tobytes()
                        ).hexdigest(),
                        "eef_position": eef,
                        "no_go_contains_reset_eef": zone.contains(eef),
                        "progress_initial": progress.to_dict(),
                        "final_success_initial": bool(view.final_success()),
                    }
                )
            task_reports.append(
                {
                    "task_id": definition.task_id,
                    "task_name": definition.task_name,
                    "language": definition.language,
                    "bddl_file": str(bddl),
                    "available_initial_states": len(initial_states),
                    "audited_state_count": len(state_reports),
                    "target_joints": list(definition.target_joints),
                    "receptacle_joints": list(definition.receptacle_joints),
                    "tool_joints": list(definition.tool_joints),
                    "all_declared_free_joints_exist": set(
                        (
                            *definition.target_joints,
                            *definition.receptacle_joints,
                            *definition.tool_joints,
                        )
                    ).issubset(available_joints),
                    "free_joints": available_joints,
                    "progress_predicate_count": len(definition.predicates),
                    "commitment_predicate_count": sum(
                        predicate.commitment for predicate in definition.predicates
                    ),
                    "states": state_reports,
                }
            )
        finally:
            env.close()

    return {
        "schema_version": "repeated_feasibility_probe_v1",
        "probe_kind": "real_installed_libero_mujoco_without_policy",
        "formal_policy_evidence": False,
        "installed_benchmark_root": get_libero_path("benchmark_root"),
        "installed_bddl_root": get_libero_path("bddl_files"),
        "suite_status": suite_status,
        "candidate_tasks": task_reports,
        "candidate_gate": {
            "all_have_at_least_two_commitment_predicates": all(
                task["commitment_predicate_count"] >= 2 for task in task_reports
            ),
            "all_have_five_audited_states": all(
                task["audited_state_count"] == 5 for task in task_reports
            ),
            "all_declared_free_joints_exist": all(
                task["all_declared_free_joints_exist"] for task in task_reports
            ),
            "no_go_excludes_all_reset_eef_positions": all(
                not state["no_go_contains_reset_eef"]
                for task in task_reports
                for state in task["states"]
            ),
        },
        "clean_calibration": {
            "status": "not_run",
            "reason": "OpenVLA checkpoint is not configured locally",
            "required_success_rate": 0.60,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = audit(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["candidate_gate"], indent=2, sort_keys=True))
    return 0 if all(result["candidate_gate"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
