#!/usr/bin/env python3
"""CLI for the read-only normalized Experiment-1 public trace exporter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope_benchmark.exp1_trace_contract_v1.exporter import export_public_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--read-only-root", action="append", default=[])
    args = parser.parse_args()
    print(
        export_public_bundle(
            args.input, args.output, read_only_roots=args.read_only_root
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
