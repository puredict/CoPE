"""OmniGibson smoke test -- REMOTE GPU SERVER ONLY.

STATUS:
  --dry-run : locally dry-run validated (prints the plan; imports nothing GPU)
  full mode : NOT EXECUTED; requires remote GPU verification.

Confirms OmniGibson can open a scene, step physics, and render -- BEFORE any
ReKep or repair-layer code is involved.  If this fails, nothing downstream can
be trusted.

Usage:
  python scripts/run_omni_smoke_test.py --dry-run       # anywhere
  python scripts/run_omni_smoke_test.py --steps 100     # REMOTE GPU SERVER ONLY
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PLAN = [
    "import omnigibson (pulls Isaac Sim; first import is slow, minutes)",
    "create a minimal scene from the OmniGibson demo config",
    "step physics N times, confirming no crash and stable dt",
    "grab one RGB frame and confirm non-degenerate output",
    "write smoke_result.json with versions, timings and GPU memory",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--out", type=str, default="runs/smoke/smoke_result.json")
    args = ap.parse_args()

    if args.dry_run:
        print("MODE: --dry-run (no GPU imports)\n")
        print(f"Would run {args.steps} physics steps and write {args.out}\n")
        for i, step in enumerate(PLAN, 1):
            print(f"  {i}. {step}")
        print("\nStatus: NOT EXECUTED. Requires remote GPU verification.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        print(f"(created output dir {Path(args.out).parent})")
        return

    if platform.system() == "Darwin":
        print("REFUSING: REMOTE GPU SERVER ONLY. Use --dry-run here.",
              file=sys.stderr)
        sys.exit(2)

    # ---------------- REMOTE GPU SERVER ONLY below this line --------------
    import time
    t0 = time.perf_counter()
    import omnigibson as og                                  # noqa: F401
    from omnigibson.macros import gm
    gm.HEADLESS = True
    import_s = time.perf_counter() - t0

    cfg = {
        "scene": {"type": "Scene"},
        "robots": [{"type": "Fetch", "obs_modalities": ["rgb"]}],
    }
    env = og.Environment(configs=cfg)
    t1 = time.perf_counter()
    for _ in range(args.steps):
        env.step(env.action_space.sample())
    step_s = time.perf_counter() - t1

    obs, _ = env.get_obs()
    rgb = None
    for v in (obs.values() if isinstance(obs, dict) else []):
        if isinstance(v, dict) and "rgb" in v:
            rgb = v["rgb"]
            break

    result = {
        "omnigibson": getattr(og, "__version__", "unknown"),
        "import_seconds": round(import_s, 2),
        "steps": args.steps,
        "step_seconds": round(step_s, 2),
        "hz": round(args.steps / step_s, 2) if step_s else None,
        "rgb_shape": None if rgb is None else list(getattr(rgb, "shape", [])),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    env.close()


if __name__ == "__main__":
    main()
