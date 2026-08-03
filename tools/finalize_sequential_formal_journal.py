#!/usr/bin/env python3
"""Finalize a complete formal event journal after client disconnect."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.sequential_prompting import ARMS
from cope.types import canonical_json
from experiments.sequential_formal_runner import (
    EXPECTED_MANIFEST_SHA256,
    RESULT_FIELDS,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("formal finalizer requires a clean committed worktree")
    if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("formal manifest hash mismatch")
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    expected = {
        (row["sequence_id"], arm, event_index)
        for row in manifest for arm in ARMS for event_index in (1, 2)
    }
    journal = args.result_dir / "01_EVENT_JOURNAL.txt"
    output_csv = args.result_dir / "03_EVENT_RESULTS.csv"
    status_path = args.result_dir / "00_STATUS.txt"
    if not journal.is_file():
        raise FileNotFoundError(journal)
    if output_csv.exists() or status_path.exists():
        raise FileExistsError("derived formal output already exists")
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    keys = [
        (str(row["sequence_id"]), str(row["arm"]), int(row["event_index"]))
        for row in rows
    ]
    if len(rows) != 320 or len(set(keys)) != 320 or set(keys) != expected:
        raise ValueError("formal journal is incomplete, duplicate, or outside manifest")
    if any(set(row) != set(RESULT_FIELDS) for row in rows):
        raise ValueError("formal journal row schema mismatch")
    with output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    status = {
        "schema": "cope-sequential-formal-run-v1",
        "runtime_git_commit_at_recovery": commit,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "result_cells": 320,
        "provider_calls": sum(bool(row["provider_called"]) for row in rows),
        "retry_count": sum(int(row["retry_count"]) for row in rows),
        "formal_states_indexed": list(range(10, 30)),
        "reserve_states_30_49_indexed": False,
        "task1_state33_retried": False,
        "task1_states34_49_indexed": False,
        "journal_recovery": True,
    }
    status_path.write_text(canonical_json(status) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
