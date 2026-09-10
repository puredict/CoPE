"""Deterministic contract artifact hashing and manifest verification."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_rows(root: Path) -> list[tuple[str, str, int]]:
    artifacts = [
        *sorted((root / "cope_benchmark" / "exp1_trace_contract_v1").glob("*.py")),
        *sorted((root / "schemas" / "exp1_trace_contract_v1").glob("*")),
        *sorted((root / "tests" / "fixtures" / "exp1_trace_contract_v1").glob("*.json")),
        root / "docs" / "EXP1_TRACE_CONTRACT_V1.md",
        root / "tools" / "export_exp1_trace_contract_v1.py",
        root / "tools" / "freeze_exp1_trace_contract_v1.py",
    ]
    return [
        (path.relative_to(root).as_posix(), file_sha256(path), path.stat().st_size)
        for path in artifacts
        if path.is_file()
    ]


def read_manifest(path: Path) -> list[tuple[str, str, int]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["relative_path", "sha256", "bytes"]:
            raise ValueError("unexpected contract manifest header")
        return [(row["relative_path"], row["sha256"], int(row["bytes"])) for row in reader]


def verify_manifest(root: Path, manifest_path: Path) -> None:
    actual = build_rows(root)
    expected = read_manifest(manifest_path)
    if actual != expected:
        raise ValueError("contract hash manifest mismatch")
