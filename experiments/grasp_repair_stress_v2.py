#!/usr/bin/env python3
"""Frozen 80-mm acquisition stress gate on task-1 development states 0--4."""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import OracleSkillConfig
from experiments.grasp_repair_development import (
    ALTERNATIVES,
    AUTHORIZED_STATE_IDS,
    PROVIDER_ENV_NAMES,
    repository_commit_and_clean,
    run_episode,
    sha256_file,
)
from libero_experiment_core import get_benchmark_suite


ARM_CONFIGS = {
    "stress_single_80mm": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.080, 0.0),),
    ),
    "stress_candidate_80mm": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.080, 0.0), (0.0, 0.0)) + ALTERNATIVES,
    ),
}
ARM_ORDER = tuple(ARM_CONFIGS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("provider credentials forbidden: " + ",".join(populated))
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope_bounded_regrasp_stress_v2",
        "runtime_git_commit": runtime_commit,
        "authorized_state_ids": list(AUTHORIZED_STATE_IDS),
        "arm_order": list(ARM_ORDER),
        "arm_configs": {name: asdict(config) for name, config in ARM_CONFIGS.items()},
        "arm_config_sha256": {
            name: stable_hash(asdict(config)) for name, config in ARM_CONFIGS.items()
        },
        "states_5_49_not_indexed": True,
        "provider_calls": 0,
        "provider_credentials_present": False,
    }
    (args.output_dir / "00_RUN_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(1)
    initial_states = suite.get_task_init_states(1)
    journal = args.output_dir / "01_ATTEMPT_JOURNAL.txt"
    rows: list[dict[str, Any]] = []
    for state_id in AUTHORIZED_STATE_IDS:
        for arm in ARM_ORDER:
            row = run_episode(
                task=task,
                initial_state=initial_states[state_id],
                state_id=state_id,
                arm=arm,
                config=ARM_CONFIGS[arm],
                resolution=args.resolution,
            )
            rows.append(row)
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(row) + "\n")
            print(canonical_json(row), flush=True)

    with (args.output_dir / "02_RESULTS.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    by_arm = {
        arm: sum(row["prefix_success"] for row in rows if row["arm"] == arm)
        for arm in ARM_ORDER
    }
    candidate_rows = [row for row in rows if row["arm"] == "stress_candidate_80mm"]
    regrasp_activated = all(
        "regrasp_1_open_gripper" in row["phase_summary"] for row in candidate_rows
    )
    gates = {
        "candidate_all_success": by_arm["stress_candidate_80mm"] == 5,
        "candidate_strictly_better": (
            by_arm["stress_candidate_80mm"] > by_arm["stress_single_80mm"]
        ),
        "candidate_regrasp_activated_all": regrasp_activated,
    }
    failures = Counter(
        f"{row['arm']}:{row['failure_class']}"
        for row in rows
        if not row["prefix_success"]
    )
    result = [
        "# Bounded regrasp stress v2 result",
        "",
        f"- Runtime commit: `{runtime_commit}`",
        f"- Successes by arm: `{canonical_json(by_arm)}`",
        f"- Gate results: `{canonical_json(gates)}`",
        f"- Failure classes: `{canonical_json(dict(sorted(failures.items())))}`",
        "- Provider calls: **0**",
        "- States 5--49 indexed by this runner: **no**",
    ]
    (args.output_dir / "03_RESULT.md").write_text(
        "\n".join(result) + "\n", encoding="utf-8"
    )
    artifacts = sorted(
        path for path in args.output_dir.iterdir() if path.name != "04_SHA256SUMS.txt"
    )
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in artifacts) + "\n",
        encoding="utf-8",
    )
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
