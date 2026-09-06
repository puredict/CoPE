#!/usr/bin/env python3
"""Real simulator reset/skill/checkpoint/candidate/video preflight gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "code", ROOT):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from cope.backends import make_backend  # noqa: E402


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def candidate_debug(backend, out_dir: Path) -> list[dict]:
    """Force collision, invalid handoff, and accepted real rollout records."""

    root = backend.checkpoint("debug-root")
    handoff = np.asarray(backend.obs["robot0_eef_pos"], dtype=float).copy()
    rows = []

    def save_candidate_video(index: int) -> dict:
        import imageio.v2 as imageio

        frames = backend.frames[int(root.payload["frame_count"]) :]
        path = out_dir / f"candidate_{index}.mp4"
        writer = imageio.get_writer(str(path), fps=20, macro_block_size=1)
        try:
            for frame in frames:
                writer.append_data(np.asarray(frame, dtype=np.uint8))
        finally:
            writer.close()
        return {"path": str(path), "frames": len(frames), "bytes": path.stat().st_size}

    # candidate 0: adversarially place a protected object in the gripper path
    # inside this isolated branch, then issue real OSC hold controls. MuJoCo
    # must report the resulting robot/protected-object contact.
    before_contacts = backend.collision_status()["unsafe_contact_count"]
    start_action = len(backend.controller.action_history)
    world_edit = backend.debug_place_object_on_robot_geom("butter")
    phase = backend.controller.hold("candidate0_protected_collision", 5, gripper=1.0)
    backend.step_count = backend.controller.total_steps
    status = backend.collision_status()
    collision = status["unsafe_contact_count"] > before_contacts
    rows.append(
        {
            "candidate_index": 0,
            "name": "downward_collision",
            "accepted": False,
            "failure_class": "collision" if collision else "collision_not_observed",
            "reason": "real MuJoCo unsafe contact observed" if collision else "expected collision absent",
            "controller_record": phase.__dict__,
            "candidate_world_edit": world_edit,
            "controls": backend.controller.action_history[start_action:],
            "collision_status": status,
            "checkpoint_before": root.to_dict(),
        }
    )
    rows[-1]["video"] = save_candidate_video(0)
    restore0 = backend.restore(root)
    rows[-1]["restore"] = restore0

    # candidate 1: safe Cartesian departure that intentionally fails the
    # captured continuation handoff contract.
    start_action = len(backend.controller.action_history)
    move = backend.debug_cartesian_move(
        "candidate1_invalid_handoff",
        [handoff[0] + 0.14, handoff[1], handoff[2]],
        max_steps=30,
    )
    eef = np.asarray(backend.obs["robot0_eef_pos"], dtype=float)
    handoff_error = float(np.linalg.norm(eef[:2] - handoff[:2]))
    collision1 = backend.collision_status()["unsafe_contact_count"] > before_contacts
    invalid_handoff = handoff_error > 0.08
    rows.append(
        {
            "candidate_index": 1,
            "name": "invalid_handoff",
            "accepted": False,
            "failure_class": "invalid_handoff" if invalid_handoff else "handoff_rejection_not_observed",
            "reason": f"actual handoff error {handoff_error:.6f} m",
            "handoff_error_m": handoff_error,
            "controller_record": move,
            "controls": backend.controller.action_history[start_action:],
            "new_collision": collision1,
            "checkpoint_before": root.to_dict(),
        }
    )
    rows[-1]["video"] = save_candidate_video(1)
    restore1 = backend.restore(root)
    rows[-1]["restore"] = restore1

    # candidate 2: stationary hold at the checkpoint, attachment retained,
    # no new unsafe contact, and handoff contract satisfied.
    before2 = backend.collision_status()["unsafe_contact_count"]
    start_action = len(backend.controller.action_history)
    phase = backend.controller.hold("candidate2_hold", 2, gripper=1.0)
    backend.step_count = backend.controller.total_steps
    eef2 = np.asarray(backend.obs["robot0_eef_pos"], dtype=float)
    handoff_error2 = float(np.linalg.norm(eef2[:2] - handoff[:2]))
    attached2 = backend.attachment_status()["attached"]
    collision2 = backend.collision_status()["unsafe_contact_count"] > before2
    accepted2 = handoff_error2 <= 0.08 and attached2 and not collision2
    rows.append(
        {
            "candidate_index": 2,
            "name": "checkpoint_hold",
            "accepted": bool(accepted2),
            "failure_class": "" if accepted2 else "acceptance_contract_failed",
            "reason": "actual rollout satisfies handoff, attachment, and collision checks",
            "handoff_error_m": handoff_error2,
            "attached": bool(attached2),
            "new_collision": bool(collision2),
            "controller_record": phase.__dict__,
            "controls": backend.controller.action_history[start_action:],
            "checkpoint_before": root.to_dict(),
        }
    )
    rows[-1]["video"] = save_candidate_video(2)
    restore2 = backend.restore(root)
    rows[-1]["restore"] = restore2
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite preflight output: {args.out}")
    args.out.mkdir(parents=True)

    backend = make_backend(args.backend)
    meta = backend.initialize(args.backend_config)
    reset = backend.reset(seed=0)
    backend.begin_leg({"id": "g_milk", "object": "milk", "target": "basket_A"})
    checkpoint = backend.checkpoint("pre-pick")
    # A reversible MuJoCo state edit proves native save/restore before motion.
    moved = backend.move_target("basket_C", [0.01, 0.0, 0.0])
    changed_hash = backend.state_hash()
    restored = backend.restore(checkpoint)
    native_restore_ok = (
        changed_hash != checkpoint.state_hash
        and restored["actual_hash"] == checkpoint.state_hash
    )

    pick = backend.pick_current_object()
    debug = candidate_debug(backend, args.out) if pick.get("success") else []
    placement = backend.place_current_object() if pick.get("success") else {
        "success": False,
        "failure_reason": "pick_failed",
    }
    settle = backend.settle_world() if placement.get("success") else {
        "stable": False,
        "steps": 0,
        "reason": "placement_failed",
    }
    task_metrics = backend.task_success({"milk": "basket_A"}, ())
    task_metrics["stability_gate_passed"] = bool(settle.get("stable"))
    task_metrics["revised_task_success"] = bool(
        task_metrics.get("revised_task_success")
        and task_metrics["stability_gate_passed"]
    )
    video = backend.write_video(args.out / "video.mp4")
    (args.out / "simulator.log").write_text(
        "\n".join(backend.simulator_log) + "\n", encoding="utf-8"
    )
    write_json(args.out / "debug_candidate_rollouts.json", debug)
    candidate_gate = (
        len(debug) == 3
        and debug[0]["failure_class"] == "collision"
        and debug[1]["failure_class"] == "invalid_handoff"
        and debug[2]["accepted"]
        and all(row["restore"]["exact"] for row in debug)
    )
    result = {
        "backend": meta,
        "reset": reset,
        "native_checkpoint_restore": {
            "checkpoint": checkpoint.to_dict(),
            "changed_hash": changed_hash,
            "restore": restored,
            "passed": native_restore_ok,
            "world_edit": moved,
        },
        "pick": pick,
        "placement": placement,
        "final_settle": settle,
        "task_metrics": task_metrics,
        "candidate_debug": debug,
        "candidate_gate_passed": candidate_gate,
        "video": video,
        "preflight_passed": bool(
            native_restore_ok
            and pick.get("success")
            and placement.get("success")
            and settle.get("stable")
            and task_metrics.get("revised_task_success")
            and candidate_gate
            and video.get("written")
        ),
    }
    result["finish"] = backend.finish_episode()
    write_json(args.out / "preflight.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str), flush=True)
    return 0 if result["preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
