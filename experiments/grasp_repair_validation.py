#!/usr/bin/env python3
"""Locked bounded-regrasp validation on previously uninspected states 15--24."""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cope.types import canonical_json, stable_hash
from cope_benchmark.oracle_skill_controller import OracleSkillConfig
from experiments.grasp_repair_development import (
    ALTERNATIVES,
    PROVIDER_ENV_NAMES,
    repository_commit_and_clean,
    run_episode,
    sha256_file,
)
from libero_experiment_core import get_benchmark_suite


AUTHORIZED_STATE_IDS = tuple(range(15, 25))
ARM_CONFIGS = {
    "natural_legacy": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.0, 0.0),),
    ),
    "natural_candidate": OracleSkillConfig(
        max_move_steps=60,
        grasp_attempt_xy_offsets_m=((0.0, 0.0),) + ALTERNATIVES,
    ),
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
EXPECTED_CONFIG_HASHES = {
    "natural_legacy": "8adc9dcd496bc5bdae7e46c7e46e6cab4a4d6c710ad49bff4b0ff97adee4cab7",
    "natural_candidate": "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a",
    "stress_single_80mm": "4344f9fed4987bf206cf4cc15e9f614d369810e32ca1aa7c4ad81bdf17dfbe8a",
    "stress_candidate_80mm": "4fcb8ba265707b48b75f5566694b38d41080b4fb8d318ba0c632a022bcc841f4",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def exact_two_sided_sign_p(wins_a: int, wins_b: int) -> float:
    discordant = wins_a + wins_b
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, value)
        for value in range(min(wins_a, wins_b) + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * tail)


def paired_rows(rows: list[dict[str, Any]], left: str, right: str):
    for state_id in AUTHORIZED_STATE_IDS:
        left_row = next(
            row for row in rows if row["state_id"] == state_id and row["arm"] == left
        )
        right_row = next(
            row for row in rows if row["state_id"] == state_id and row["arm"] == right
        )
        yield left_row, right_row


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    runtime_commit = repository_commit_and_clean(repo_root)
    actual_hashes = {
        name: stable_hash(asdict(config)) for name, config in ARM_CONFIGS.items()
    }
    if actual_hashes != EXPECTED_CONFIG_HASHES:
        raise RuntimeError(
            "frozen controller configuration hash mismatch: "
            + canonical_json(actual_hashes)
        )
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("provider credentials forbidden: " + ",".join(populated))
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope_bounded_regrasp_validation_v1",
        "runtime_git_commit": runtime_commit,
        "authorized_state_ids": list(AUTHORIZED_STATE_IDS),
        "arm_order": list(ARM_ORDER),
        "arm_configs": {name: asdict(config) for name, config in ARM_CONFIGS.items()},
        "arm_config_sha256": actual_hashes,
        "states_0_14_not_indexed_by_runner": True,
        "states_25_49_not_indexed": True,
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
    natural_pairs = list(paired_rows(rows, "natural_legacy", "natural_candidate"))
    stress_pairs = list(
        paired_rows(rows, "stress_single_80mm", "stress_candidate_80mm")
    )
    natural_candidate_losses = sum(
        bool(left["prefix_success"]) and not bool(right["prefix_success"])
        for left, right in natural_pairs
    )
    natural_hash_equal = all(
        (
            left["action_prefix_sha256"] == right["action_prefix_sha256"]
            and left["simulator_state_sha256"] == right["simulator_state_sha256"]
        )
        for left, right in natural_pairs
        if left["prefix_success"] and right["prefix_success"]
    )
    stress_candidate_wins = sum(
        not bool(left["prefix_success"]) and bool(right["prefix_success"])
        for left, right in stress_pairs
    )
    stress_single_wins = sum(
        bool(left["prefix_success"]) and not bool(right["prefix_success"])
        for left, right in stress_pairs
    )
    stress_p = exact_two_sided_sign_p(stress_candidate_wins, stress_single_wins)
    candidate_stress_rows = [
        row for row in rows if row["arm"] == "stress_candidate_80mm"
    ]
    gates = {
        "natural_candidate_all_success": by_arm["natural_candidate"] == 10,
        "natural_candidate_no_losses": natural_candidate_losses == 0,
        "natural_shared_trajectory_exact": natural_hash_equal,
        "stress_candidate_all_success": by_arm["stress_candidate_80mm"] == 10,
        "stress_candidate_strictly_better": (
            by_arm["stress_candidate_80mm"] > by_arm["stress_single_80mm"]
        ),
        "stress_regrasp_activated_all": all(
            "regrasp_1_open_gripper" in row["phase_summary"]
            for row in candidate_stress_rows
        ),
    }
    failures = Counter(
        f"{row['arm']}:{row['failure_class']}"
        for row in rows
        if not row["prefix_success"]
    )
    result = [
        "# Bounded regrasp independent validation result",
        "",
        f"- Runtime commit: `{runtime_commit}`",
        f"- Successes by arm: `{canonical_json(by_arm)}`",
        f"- Gate results: `{canonical_json(gates)}`",
        f"- Failure classes: `{canonical_json(dict(sorted(failures.items())))}`",
        f"- Stress discordance (candidate wins, single wins): **{stress_candidate_wins}, {stress_single_wins}**",
        f"- Exact two-sided paired sign-test p-value: **{stress_p:.12g}**",
        "- Provider calls: **0**",
        "- States 25--49 indexed: **no**",
        "",
        "This validates a shared prefix-construction substrate; it is not a CoPE method comparison.",
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
