#!/usr/bin/env python3
"""Run explicit object/region Oracle skill canaries in LIBERO."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Sequence

from cope_benchmark.oracle_skill_controller import LiberoOracleSkillController
from libero_experiment_core import (
    ExperimentConfig,
    create_libero_env,
    get_benchmark_suite,
)


def parse_operation(value: str) -> tuple[str, str]:
    pieces = value.split(":", 1)
    if len(pieces) != 2 or not all(piece.strip() for piece in pieces):
        raise argparse.ArgumentTypeError("operation must be OBJECT:TARGET_REGION")
    return pieces[0].strip(), pieces[1].strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="libero_10")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--trial-id", type=int, default=0)
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument(
        "--operation",
        action="append",
        type=parse_operation,
        required=True,
        help="explicit OBJECT:TARGET_REGION pair; may be repeated",
    )
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser


def phase_summary(phases: Sequence[object]) -> str:
    return ";".join(
        f"{phase.phase}:{phase.steps}:{'' if phase.final_error_m is None else f'{phase.final_error_m:.5f}'}"
        for phase in phases
    )


def main() -> int:
    args = build_parser().parse_args()
    suite = get_benchmark_suite(args.suite)
    task = suite.get_task(args.task_id)
    initial_states = list(suite.get_task_init_states(args.task_id))
    if args.trial_id >= len(initial_states):
        raise ValueError(f"trial {args.trial_id} outside 0..{len(initial_states) - 1}")

    cfg = ExperimentConfig(
        checkpoint="oracle-skill-controller",
        task_id=args.task_id,
        trial_id=args.trial_id,
        resolution=args.resolution,
    )
    env, prompt = create_libero_env(task, cfg)
    try:
        env.reset()
        observation = env.set_init_state(initial_states[args.trial_id])
        controller = LiberoOracleSkillController(env, observation)
        warmup = controller.warmup()
        rows: list[dict[str, object]] = []
        for operation_index, (object_name, target_region) in enumerate(args.operation):
            result = controller.pick_and_place(object_name, target_region)
            rows.append(
                {
                    "suite": args.suite,
                    "task_id": args.task_id,
                    "trial_id": args.trial_id,
                    "prompt": prompt,
                    "operation_index": operation_index,
                    "object_name": object_name,
                    "target_region_name": target_region,
                    "success": result.success,
                    "failure_reason": result.failure_reason or "",
                    "grasp_acquired": result.grasp_acquired,
                    "object_lift_m": f"{result.object_lift_m:.6f}",
                    "target_predicate": result.target_predicate,
                    "skill_steps": result.total_steps,
                    "environment_steps": controller.total_steps,
                    "task_success_after_operation": bool(env.env._check_success()),
                    "warmup_steps": warmup.steps,
                    "phase_summary": phase_summary(result.phases),
                }
            )
            print(rows[-1], flush=True)
            if not result.success:
                break
    finally:
        env.close()

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    return 0 if rows and all(bool(row["success"]) for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
