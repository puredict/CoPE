#!/usr/bin/env python3
"""Run one explicitly named backend episode (debugging and manual review)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "code", ROOT):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from cope.benchmark.backend_episode import run_backend_episode  # noqa: E402
from cope.benchmark.basket_task import BasketTaskSpec  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    result = run_backend_episode(
        BasketTaskSpec(
            seed=args.seed, condition=args.condition, method=args.method
        ),
        backend_name=args.backend,
        backend_config=args.backend_config,
        episode_dir=args.out,
        verbose=args.verbose,
    )
    summary = {
        "episode_id": result["episode_id"],
        "success": result["metrics"]["revised_task_success"],
        "denominators": result["denominators"],
        "infrastructure_errors": result["infrastructure_errors"],
        "pipelines_complete": result["metrics"]["pipelines_complete"],
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if result["denominators"]["valid_episodes"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
