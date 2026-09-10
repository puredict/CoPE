#!/usr/bin/env python3
"""Materialize the deterministic schema set and its hash manifest."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope_benchmark.exp1_trace_contract_v1.canonical import canonical_json
from cope_benchmark.exp1_trace_contract_v1.manifest import build_rows
from cope_benchmark.exp1_trace_contract_v1.occurrence import OCCURRENCE_ALLOCATOR_VERSION
from cope_benchmark.exp1_trace_contract_v1.schema_documents import SCHEMA_DOCUMENTS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    schema_root = root / "schemas" / "exp1_trace_contract_v1"
    schema_root.mkdir(parents=True, exist_ok=True)
    for filename, document in sorted(SCHEMA_DOCUMENTS.items()):
        (schema_root / filename).write_text(canonical_json(document) + "\n", encoding="utf-8")
    (schema_root / "OCCURRENCE_ALLOCATOR_VERSION.txt").write_text(
        OCCURRENCE_ALLOCATOR_VERSION + "\n", encoding="utf-8"
    )
    manifest = root / "manifests" / "exp1_trace_contract_v1_hashes.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["relative_path", "sha256", "bytes"])
        writer.writerows(build_rows(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
