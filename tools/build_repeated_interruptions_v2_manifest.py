#!/usr/bin/env python3
"""Build a sealed v2 master manifest from verified catalog evidence; zero calls."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cope_benchmark.repeated_v2.canonical import canonical_json, canonical_sha256
from cope_benchmark.repeated_v2.config import load_config
from cope_benchmark.repeated_v2.manifest import build_manifest, expected_counts, write_manifest
from cope_benchmark.repeated_v2.task_catalog import load_task_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task-catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        catalog = load_task_catalog(args.task_catalog)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        rows = build_manifest(config, catalog, source_commit=commit)
        file_hash = write_manifest(args.output, rows)
        report = {"status": "MASTER_MANIFEST_BUILT", "provider_calls": 0, "vla_calls": 0,
                  "manifest_sha256": canonical_sha256(rows), "file_sha256": file_hash,
                  "counts": expected_counts(len(rows) // 15, config)}
    except (ValueError, OSError) as exc:
        print(canonical_json({"status": getattr(exc, "status", "BLOCKED_MANIFEST"),
                              "error": str(exc), "provider_calls": 0, "vla_calls": 0}))
        return 2
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
