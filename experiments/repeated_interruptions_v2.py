#!/usr/bin/env python3
"""Run the v2 pilot/formal protocol with explicit production dependency gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pilot", "formal", "development"), required=True)
    parser.add_argument("--protocol", choices=("controlled", "end_to_end"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--information-condition", choices=("evidence_matched", "token_matched"), required=True)
    parser.add_argument("--task-catalog", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--frozen-bundle", "--freeze", dest="frozen_bundle", type=Path)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--num-shards", type=int, default=8)
    args = parser.parse_args(argv)
    from cope_benchmark.repeated_v2.pilot import run_experiment
    from cope_benchmark.repeated_v2.runner import RuntimeBlocked
    try:
        result = run_experiment(config_path=args.config, output_dir=args.output_dir,
                                phase=args.phase, protocol=args.protocol, resume=args.resume,
                                information_condition=args.information_condition,
                                task_catalog_path=args.task_catalog, manifest_path=args.manifest,
                                frozen_bundle_path=args.frozen_bundle,
                                shard_index=args.shard_index, num_shards=args.num_shards)
    except RuntimeBlocked as exc:
        result = {"status": exc.status, "phase": args.phase, "protocol": args.protocol}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0 if result.get("status") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
