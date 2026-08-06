#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


EXPECTED_CASES = {f"q{index:03d}" for index in range(75)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def truth(value: str) -> bool:
    return value.strip().lower() == "true"


def command_for(row: dict[str, str], output_csv: Path) -> list[str]:
    common = [
        "--state-id", row["state_id"],
        "--mode", row["arm"],
        "--max-move-steps", row["max_move_steps"],
        "--output-csv", str(output_csv),
    ]
    if row["family"] in {"reset", "milestone", "no_event"}:
        script = "experiments/oracle_replacement_gate.py"
    elif row["family"] == "timing":
        script = "experiments/oracle_interruption_timing_gate.py"
        common.extend(["--timing", row["timing"]])
    elif row["family"] == "repeated":
        script = "experiments/oracle_repeated_replacement_gate.py"
    else:
        raise ValueError(f"unsupported family {row['family']!r}")
    return [sys.executable, script, *common]


def run_case(row: dict[str, str], raw_dir: Path, environment: dict[str, str]) -> dict[str, str]:
    output_csv = raw_dir / f"{row['case_id']}.csv"
    command = command_for(row, output_csv)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    print(
        f"{row['case_id']} family={row['family']} arm={row['arm']} "
        f"state={row['state_id']} exit={completed.returncode}",
        flush=True,
    )
    return {
        "case_id": row["case_id"],
        "state_id": row["state_id"],
        "family": row["family"],
        "arm": row["arm"],
        "timing": row["timing"],
        "exit_code": str(completed.returncode),
        "raw_csv": str(output_csv),
        "raw_present": str(output_csv.is_file()),
        "stdout": completed.stdout.strip().replace("\n", "\\n"),
        "stderr": completed.stderr.strip().replace("\n", "\\n"),
    }


def main() -> int:
    args = parse_args()
    if args.workers not in (1, 2, 3, 4):
        raise ValueError("workers must be in 1..4")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    case_ids = {row.get("case_id", "") for row in rows}
    if len(rows) != 75 or case_ids != EXPECTED_CASES:
        raise ValueError("manifest is not the frozen 75-case assignment")
    for row in rows:
        if int(row["state_id"]) not in range(5):
            raise ValueError("manifest indexes a non-development state")
        if not truth(row["assigned"]) or not truth(row["development_state"]):
            raise ValueError("every row must be assigned development evidence")
        if truth(row["reserved_state_allowed"]):
            raise ValueError("reserved state access must remain disabled")
        if row["max_move_steps"] != "60":
            raise ValueError("manifest changed the frozen controller cap")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HOME": "/home/lijingsu/vla/cache/huggingface",
            "TRANSFORMERS_CACHE": "/home/lijingsu/vla/cache/transformers",
        }
    )
    results: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_case, row, raw_dir, environment): row
            for row in rows
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["case_id"])
    ledger = args.output_dir / "execution_ledger.csv"
    with ledger.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    raw_count = sum(truth(row["raw_present"]) for row in results)
    zero_count = sum(row["exit_code"] == "0" for row in results)
    print(f"assigned=75 raw={raw_count} exit_zero={zero_count}", flush=True)
    return 0 if raw_count == 75 else 2


if __name__ == "__main__":
    raise SystemExit(main())
