#!/usr/bin/env python3
"""Create a non-overwriting portable tarball and a complete SHA-256 manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
ALWAYS_EXCLUDE = {".DS_Store", "__pycache__", ".pytest_cache"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def include(path: Path, include_results: bool) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in ALWAYS_EXCLUDE for part in relative.parts):
        return False
    if path.suffix == ".pyc":
        return False
    if not include_results and relative.parts and relative.parts[0] == "results_r3":
        return False
    return path.is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new .tar.gz path outside project")
    parser.add_argument("--include-results", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    if out.exists() or out.with_suffix(out.suffix + ".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite {out} or its manifest")
    if ROOT == out or ROOT in out.parents:
        raise ValueError("archive output must be outside the project directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        path for path in ROOT.rglob("*") if include(path, args.include_results)
    )
    with tarfile.open(out, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=Path(ROOT.name) / path.relative_to(ROOT))
    manifest = {
        "schema_version": "cope-fsrpc-r3-handoff-manifest-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive": out.name,
        "archive_sha256": digest(out),
        "include_results": args.include_results,
        "n_files": len(files),
        "files": {
            str(path.relative_to(ROOT)): digest(path)
            for path in files
        },
    }
    manifest_path = out.with_suffix(out.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"archive={out}")
    print(f"manifest={manifest_path}")
    print(f"files={len(files)} sha256={manifest['archive_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

