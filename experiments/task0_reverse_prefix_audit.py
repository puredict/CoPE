#!/usr/bin/env python3
"""Frozen reverse-prefix audit on task-0 development states 0--9."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from cope.types import canonical_json, stable_hash
from experiments.multitask_prefix_audit import CONTROLLER_CONFIG, run_episode
from libero_experiment_core import get_benchmark_suite


STATE_IDS = tuple(range(10))
SPEC = {
    "task_id": 0,
    "done_object": "tomato_sauce_1",
    "pending_object": "alphabet_soup_1",
}
EXPECTED_CONFIG_HASH = "56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a"
PROVIDER_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip():
        raise RuntimeError("reverse-prefix audit requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if stable_hash(asdict(CONTROLLER_CONFIG)) != EXPECTED_CONFIG_HASH:
        raise RuntimeError("validated controller configuration hash mismatch")
    populated = [name for name in PROVIDER_ENV_NAMES if os.environ.get(name)]
    if populated:
        raise RuntimeError("provider credentials forbidden: " + ",".join(populated))
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema": "cope-task0-reverse-prefix-audit-v1",
        "runtime_git_commit": runtime_commit,
        "task_spec": SPEC,
        "authorized_state_ids": STATE_IDS,
        "controller_config_sha256": EXPECTED_CONFIG_HASH,
        "provider_calls": 0,
        "formal_states_indexed": False,
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
    }
    (args.output_dir / "00_METADATA.txt").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    suite = get_benchmark_suite("libero_10")
    task = suite.get_task(0)
    states = suite.get_task_init_states(0)
    rows = []
    journal = args.output_dir / "01_JOURNAL.txt"
    for state_id in STATE_IDS:
        row = run_episode(task, states[state_id], SPEC, state_id, args.resolution)
        rows.append(row)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(row) + "\n")
        print(canonical_json(row), flush=True)
    with (args.output_dir / "02_RESULTS.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    successes = sum(bool(row["prefix_success"]) for row in rows)
    failures = Counter(row["failure_class"] for row in rows if not row["prefix_success"])
    passed = successes == len(STATE_IDS)
    (args.output_dir / "03_RESULT.md").write_text(
        "# Task-0 reverse-prefix audit result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Successes: **{successes}/{len(STATE_IDS)}**\n"
        f"- Failures: `{canonical_json(dict(sorted(failures.items())))}`\n"
        "- Provider calls: **0**\n"
        "- Formal states indexed: **0**\n",
        encoding="utf-8",
    )
    artifacts = sorted(args.output_dir.iterdir())
    (args.output_dir / "04_SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in artifacts
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
