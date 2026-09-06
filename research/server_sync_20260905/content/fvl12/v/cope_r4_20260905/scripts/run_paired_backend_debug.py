#!/usr/bin/env python3
"""Run the required same-seed CoPE/FSR-PC debug matrix over I1--I4."""

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
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite debug root: {args.out}")
    args.out.mkdir(parents=True)

    summary = []
    for condition in ("I1", "I2", "I3", "I4"):
        for method in ("CoPE", "FSR-PC"):
            episode_dir = (
                args.out / method / condition / f"seed_{args.seed:02d}"
            )
            result = run_backend_episode(
                BasketTaskSpec(
                    seed=args.seed, condition=condition, method=method
                ),
                backend_name=args.backend,
                backend_config=args.backend_config,
                episode_dir=episode_dir,
                verbose=False,
            )
            row = {
                "episode_id": result["episode_id"],
                "condition": condition,
                "method": method,
                "seed": args.seed,
                "initial_state_hash": result["reset_meta"]["state_hash"],
                "event_steps": [
                    event["simulator_step"] for event in result["events"]
                ],
                "success": result["metrics"]["revised_task_success"],
                "valid": result["denominators"]["valid_episodes"],
                "pipelines_complete": result["metrics"]["pipelines_complete"],
                "repairs_invoked": result["metrics"]["repairs_invoked"],
                "candidate_isolation_valid": result["denominators"][
                    "candidate_isolation_valid"
                ],
                "no_task_object_attached": result["task_metrics"][
                    "no_task_object_attached"
                ],
                "stability_gate_passed": result["task_metrics"][
                    "stability_gate_passed"
                ],
                "episode_dir": str(episode_dir),
            }
            summary.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
            if not (
                row["valid"] == 1
                and row["success"]
                and row["candidate_isolation_valid"]
                and row["no_task_object_attached"]
                and row["stability_gate_passed"]
                and row["pipelines_complete"] == row["repairs_invoked"]
            ):
                (args.out / "paired_debug_summary.json").write_text(
                    json.dumps({"completed": False, "episodes": summary}, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                return 1

    (args.out / "paired_debug_summary.json").write_text(
        json.dumps({"completed": True, "episodes": summary}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
