#!/usr/bin/env python3
"""Finalize a complete live-provider smoke journal after client disconnect."""

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

from experiments.sequential_provider_development_smoke import (
    EXPECTED_CASE_MANIFEST_SHA256,
    SMOKE_RESULT_FIELDS,
    summarize_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip():
        raise RuntimeError("smoke finalizer requires a clean committed worktree")
    if hashlib.sha256(args.case_manifest.read_bytes()).hexdigest() != EXPECTED_CASE_MANIFEST_SHA256:
        raise RuntimeError("development smoke case manifest hash drift")
    with args.case_manifest.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    journal = args.result_dir / "01_JOURNAL.txt"
    output_csv = args.result_dir / "02_RESULTS.csv"
    report = args.result_dir / "03_RESULT.md"
    if not journal.is_file():
        raise FileNotFoundError(journal)
    if output_csv.exists() or report.exists():
        raise FileExistsError("derived smoke output already exists")
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    summary = summarize_smoke(cases, rows)
    with output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SMOKE_RESULT_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    gate = bool(summary["gate"])
    report.write_text(
        "# Sequential live-provider development smoke\n\n"
        f"- Gate: **{'PASS' if gate else 'FAIL'}**\n"
        f"- Passed event cells: **{summary['passed_event_cells']}/{summary['result_cells']}**\n"
        f"- Provider calls: **{summary['provider_calls']}**\n"
        "- Simulator states indexed: **0**\n"
        "- Recovery: derived from a complete retained append-only journal; no call rerun.\n",
        encoding="utf-8",
    )
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
