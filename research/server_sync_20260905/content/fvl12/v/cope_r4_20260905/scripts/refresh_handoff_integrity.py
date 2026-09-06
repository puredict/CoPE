#!/usr/bin/env python3
"""Regenerate the in-place final manifest and SHA-256 inventory.

Unlike the historical build script, this script never copies or deletes the
handoff tree. It inventories the already assembled package after real results
have been synchronized into it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKSUMS = ROOT / "SHA256SUMS.txt"
MANIFEST = ROOT / "handoff_manifest.json"
EXCLUDED_PARTS = {".pytest_cache", "__pycache__"}
EXCLUDED_NAMES = {".DS_Store", CHECKSUMS.name, MANIFEST.name}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file()
        and path.name not in EXCLUDED_NAMES
        and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    ]


def main() -> int:
    files_before_manifest = inventory()
    manifest = {
        "package": ROOT.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "scripts/refresh_handoff_integrity.py",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_snapshot_sha256": (
            "607704af05fd2fa1ccadcde9a3317fb0fefa113ab82312bf3515c154b8ee7418"
        ),
        "real_backend": "libero_mujoco",
        "simulator": "LIBERO/robosuite/MuJoCo",
        "controller": "OnTheGroundPanda OSC_POSE privileged geometry oracle",
        "learned_policy_used": False,
        "cuda_inference_used": False,
        "frozen_repair_core_included": True,
        "old_experiment_outputs_preserved": True,
        "excluded_generated_cache_parts": sorted(EXCLUDED_PARTS),
        "n_files_covered_by_sha256sums": len(files_before_manifest) + 1,
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    files = inventory() + [MANIFEST]
    files = sorted(set(files))
    CHECKSUMS.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(ROOT)}\n" for path in files),
        encoding="utf-8",
    )
    print(
        f"Inventoried {len(files)} files; manifest={MANIFEST.name}; "
        f"checksums={CHECKSUMS.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
