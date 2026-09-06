"""Milestone-1 driver: nominal ReKep, then ONE synthesized repair.

STATUS:
  --dry-run  : locally dry-run validated (uses the adapter's scripted fake;
               imports nothing GPU-only). Proves the wiring, NOT the GPU path.
  full mode  : NOT EXECUTED; REMOTE GPU SERVER ONLY; requires remote GPU
               verification.

Modes
  --mode nominal : run one official ReKep task UNCHANGED, logging stage
                   transitions and constraints.  No repair layer active.
  --mode wrapped : same task, ReKep's fixed stage program wrapped in
                   TaskProgram.  Behaviour must be IDENTICAL to nominal --
                   this is the parity check.
  --mode repair  : same task, plus ONE manually injected temporary-obstacle
                   event; the repair layer synthesizes, verifies, splices,
                   restores and resumes.

Usage:
  python scripts/run_rekep_baseline.py --mode repair --dry-run    # anywhere
  python scripts/run_rekep_baseline.py --mode nominal --task pen_insertion
      # REMOTE GPU SERVER ONLY
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

TASKS = {
    # ReKep task name -> (config key, note)
    "pen_insertion": ("pen", "official ReKep demo; alignment/insertion proxy"),
    "upright_transport": ("mug", "carry upright with temporary obstruction"),
    "placement": ("tray", "placement with object slip"),
}


def _log(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float))


def build_adapter(args):
    """Construct the adapter. Dry-run uses the scripted fake."""
    from rekep_repair.rekep_adapter import ReKepAdapterConfig, ReKepOmniGibsonAdapter
    if args.dry_run:
        return ReKepOmniGibsonAdapter(dry_run=True, cfg=ReKepAdapterConfig())
    # ---------------- REMOTE GPU SERVER ONLY --------------------------------
    sys.path.insert(0, args.rekep_root)
    from main import Main                      # ReKep's own entrypoint  # noqa
    rekep = Main(scene_file=args.scene, visualize=args.visualize)
    return ReKepOmniGibsonAdapter(rekep_main=rekep, cfg=ReKepAdapterConfig())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["nominal", "wrapped", "repair"],
                    default="repair")
    ap.add_argument("--task", choices=list(TASKS), default="upright_transport")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rekep-root", type=str, default="../ReKep")
    ap.add_argument("--scene", type=str, default=None)
    ap.add_argument("--visualize", action="store_true")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    if not args.dry_run and platform.system() == "Darwin":
        print("REFUSING: REMOTE GPU SERVER ONLY. Use --dry-run here.",
              file=sys.stderr)
        sys.exit(2)

    out = Path(args.out or f"runs/milestone1/{args.task}_{args.mode}_s{args.seed}")
    tag = "DRY-RUN (scripted fake; proves wiring only)" if args.dry_run \
        else "GPU (REMOTE GPU SERVER ONLY)"
    print(f"task={args.task}  mode={args.mode}  [{tag}]")
    print(f"note: {TASKS[args.task][1]}")

    adapter = build_adapter(args)
    ctx = adapter.reset()

    from rekep_repair.execution.provenance_logger import ProvenanceLog
    log = ProvenanceLog()
    trace = {"task": args.task, "mode": args.mode, "seed": args.seed,
             "dry_run": args.dry_run, "events": [], "stages": [], "steps": []}

    policy = None
    if args.mode == "repair":
        from rekep_repair.policies.online_repair import OnlineRepairPolicy
        policy = OnlineRepairPolicy()
        # The adapter is duck-compatible with the env surface the policy needs.
        policy.reset(_AdapterEnvShim(adapter, args))

    t0 = time.perf_counter()
    for i in range(args.steps):
        if args.mode == "nominal":
            # ReKep drives itself entirely; we only observe and log.
            action = np.zeros(3) if args.dry_run else adapter.main.step_once()
        elif args.mode == "wrapped":
            action = np.zeros(3) if args.dry_run else adapter.main.step_once()
        else:
            action, rec = policy.act(ctx)
            log.add(rec)
            trace["stages"].append(
                {"t": i, "stage": rec.stage_id, "state": rec.stage_state})
        ctx = adapter.execute_action(action)
        trace["steps"].append({"t": i, "ee": np.round(ctx.position, 4).tolist(),
                               "clearance": round(float(ctx.clearance), 4)})

    trace["wall_seconds"] = round(time.perf_counter() - t0, 3)
    if policy is not None:
        trace["repair_traces"] = policy.trace_lines()
        trace["program"] = list(policy.program._order)
        trace["provenance_coverage"] = round(log.continuation_linked_coverage(), 4)

    _log(out / "trace.json", trace)
    print(f"\nwrote {out/'trace.json'}  ({len(trace['steps'])} steps)")
    if policy is not None and policy._trace:
        print("repair decisions:")
        for ln in policy._trace:
            for l in ln.split("\n"):
                if "SELECTED" in l or "goal=" in l:
                    print("   " + l.strip()[:110])
    if args.dry_run:
        print("\nStatus: DRY-RUN only. GPU behaviour is NOT EXECUTED and "
              "requires remote GPU verification.")


class _AdapterEnvShim:
    """Presents the adapter through the small env surface OnlineRepairPolicy
    expects (cfg, observe, predicates, goal, grasped)."""

    def __init__(self, adapter, args):
        self.adapter = adapter
        from rekep_repair.synthetic.dynamics import SceneConfig
        c = adapter.cfg
        self.cfg = SceneConfig(d_safe=c.d_safe, d_react=c.d_react,
                               horizon=args.steps)

    def observe(self):
        return self.adapter.observe_context()

    def predicates(self, d_react, target_threshold=0.15):
        return self.adapter.active_predicates()

    @property
    def goal(self):
        return self.adapter.current_task_goal()

    @property
    def grasped(self):
        return self.adapter.attachment_state().get("object") == "grasped"

    def step(self, action):
        return self.adapter.execute_action(action)


if __name__ == "__main__":
    main()
