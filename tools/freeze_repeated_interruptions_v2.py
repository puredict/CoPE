"""Create a fail-closed repeated-v2 freeze from explicit evidence; zero calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope_benchmark.repeated_v2.freeze import (  # noqa: E402
    FreezeBlocked, _load, build_freeze_bundle, write_freeze_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--phase3-sha", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--task-catalog", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact-map", help="JSON/TXT mapping the remaining evidence roles to actual paths")
    parser.add_argument("--identities", help="JSON/TXT exact public runtime identity mapping; no credentials")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    output = Path(args.output_dir).expanduser()
    output = output.resolve() if output.is_absolute() else (root / output).resolve()
    try:
        artifacts = _load(args.artifact_map) if args.artifact_map else {}
        if not isinstance(artifacts, dict):
            raise FreezeBlocked("artifact map must be an object mapping roles to paths")
        artifacts.update(config=args.config, catalog=args.task_catalog, manifest=args.manifest)
        identities = _load(args.identities) if args.identities else {}
        if not isinstance(identities, dict):
            raise FreezeBlocked("runtime identities must be an object")
        bundle = build_freeze_bundle(repo_root=args.repo_root, artifact_paths=artifacts,
                                     identities=identities, phase3_sha=args.phase3_sha)
        paths = write_freeze_artifacts(bundle, output_dir=output)
        print(json.dumps({"status": "FROZEN", "bundle_sha256": bundle["bundle_sha256"], "paths": paths}, sort_keys=True))
        return 0
    except (FreezeBlocked, OSError, ValueError, TypeError, KeyError) as error:
        status = getattr(error, "status", "BLOCKED_FORMAL_FREEZE")
        report = {"status": status, "formal_calls": 0, "reasons": getattr(error, "reasons", [str(error)])}
        if any(output.is_relative_to(root / p) for p in ("research", "docs")) and not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            with (output / "BLOCKED_FREEZE.txt").open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, sort_keys=True)
                handle.write("\n")
        print(json.dumps(report, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
