#!/usr/bin/env python3
"""Finalize a complete interrupted terminal-audit journal without rerunning."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from cope.types import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    metadata = args.result_dir / "00_METADATA.txt"
    journal = args.result_dir / "01_JOURNAL.txt"
    outputs = [
        args.result_dir / "02_RESULTS.csv",
        args.result_dir / "03_RESULT.md",
        args.result_dir / "04_SHA256SUMS.txt",
    ]
    if not metadata.is_file() or not journal.is_file():
        raise FileNotFoundError("retained metadata or journal is missing")
    if any(path.exists() for path in outputs):
        raise FileExistsError("finalizer refuses existing derived output")
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    expected = {
        (orientation, state_id)
        for orientation in ("forward", "reverse")
        for state_id in range(10)
    }
    keys = [(str(row["prefix_orientation"]), int(row["state_id"])) for row in rows]
    if len(rows) != 20 or len(set(keys)) != 20 or set(keys) != expected:
        raise ValueError("journal is incomplete, duplicate, or outside frozen cells")
    if any(int(row["task_id"]) != 0 for row in rows):
        raise ValueError("journal contains an unauthorized task")
    with outputs[0].open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    successes = sum(bool(row["cell_success"]) for row in rows)
    failures = Counter(str(row["failure_class"]) for row in rows if not row["cell_success"])
    passed = successes == len(rows)
    outputs[1].write_text(
        "# Task-0 terminal-action audit result\n\n"
        f"- Gate: **{'PASS' if passed else 'FAIL'}**\n"
        f"- Passed cells: **{successes}/{len(rows)}**\n"
        f"- Failures: `{canonical_json(dict(sorted(failures.items())))}`\n"
        f"- Regrasp activations: **{sum(bool(row['regrasp_activated']) for row in rows)}/{len(rows)}**\n"
        "- Provider calls: **0**\n- Formal states indexed: **0**\n"
        "- Recovery: derived from a complete retained append-only journal; no episode rerun.\n",
        encoding="utf-8",
    )
    artifacts = [metadata, journal, outputs[0], outputs[1]]
    outputs[2].write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in artifacts
        ) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
