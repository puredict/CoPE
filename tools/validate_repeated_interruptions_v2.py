#!/usr/bin/env python3
"""Run deterministic zero-provider phase-1 checks without discovering adapters."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cope_benchmark.repeated_v2.canonical import canonical_json
from cope_benchmark.repeated_v2.config import load_config
from cope_benchmark.repeated_v2.manifest import read_manifest
from cope_benchmark.repeated_v2.preflight import run_preflight
from cope_benchmark.repeated_v2.task_catalog import load_task_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task-catalog", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        catalog = load_task_catalog(args.task_catalog)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        report = run_preflight(config, catalog, source_commit=commit,
                               manifest=read_manifest(args.manifest) if args.manifest else None)
    except (ValueError, OSError) as exc:
        report = {"status": getattr(exc, "status", "BLOCKED_PREFLIGHT_INPUT"), "passed": False,
                  "provider_calls": 0, "vla_calls": 0, "errors": [str(exc)]}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "preflight.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical_json(report) + "\n")
    print(canonical_json(report))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
