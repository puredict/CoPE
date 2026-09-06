"""Shared symbolic and real-LIBERO execution substrate for the final plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


def _assignment(plan: Sequence[Mapping[str, str]]) -> Dict[str, str]:
    return {str(action["object"]): str(action["target"]) for action in plan}


class SymbolicBasketWorld:
    """Deterministic semantics-only substrate used for local verification."""

    name = "symbolic_basket"

    def execute(
        self,
        plan: Sequence[Mapping[str, str]],
        expected_plan: Sequence[Mapping[str, str]],
        *,
        seed: int,
        episode_dir: Path,
        backend_config: Optional[Path] = None,
    ) -> Dict[str, Any]:
        del seed, episode_dir, backend_config
        placements: Dict[str, str] = {}
        actions: List[Dict[str, Any]] = []
        invalid_actions = 0
        for index, action in enumerate(plan):
            obj, target = str(action["object"]), str(action["target"])
            valid = (
                obj in {"butter", "milk", "yogurt"}
                and target in {"basket_A", "basket_B", "basket_C"}
                and obj not in placements
            )
            if valid:
                placements[obj] = target
            else:
                invalid_actions += 1
            actions.append({
                "index": index,
                "object": obj,
                "target": target,
                "role": str(action.get("role", "")),
                "success": valid,
                "failure_reason": "" if valid else "invalid_or_repeated_action",
            })
        expected = _assignment(expected_plan)
        exact = placements == expected
        return {
            "backend": self.name,
            "initialized": True,
            "actions": actions,
            "observed_assignment": placements,
            "expected_assignment": expected,
            "exact_assignment": exact,
            "physical_success": bool(exact and invalid_actions == 0),
            "invalid_action_count": invalid_actions,
            "controller_error": "",
            "video": {"written": False, "not_applicable": True},
            "finish": {},
        }


class LiberoBasketWorld:
    """Execute the compiled plan through r2's frozen geometry-oracle backend."""

    name = "libero_mujoco"

    def execute(
        self,
        plan: Sequence[Mapping[str, str]],
        expected_plan: Sequence[Mapping[str, str]],
        *,
        seed: int,
        episode_dir: Path,
        backend_config: Optional[Path] = None,
    ) -> Dict[str, Any]:
        if backend_config is None:
            raise ValueError("libero_mujoco requires backend_config")
        from ..backends import make_backend

        backend = make_backend("libero_mujoco")
        initialized = False
        rows: List[Dict[str, Any]] = []
        controller_error = ""
        meta: Dict[str, Any] = {}
        reset: Dict[str, Any] = {}
        task: Dict[str, Any] = {}
        settle: Dict[str, Any] = {}
        video: Dict[str, Any] = {"written": False}
        finish: Dict[str, Any] = {}
        try:
            meta = backend.initialize(backend_config)
            reset = backend.reset(seed)
            initialized = True
            for index, action in enumerate(plan):
                goal = {
                    "id": f"r3-action-{index:02d}",
                    "object": str(action["object"]),
                    "target": str(action["target"]),
                }
                begin = backend.begin_leg(goal)
                picked = backend.pick_current_object()
                placed: Dict[str, Any] = {}
                if bool(picked.get("success")):
                    placed = backend.place_current_object()
                row = {
                    "index": index,
                    "object": goal["object"],
                    "target": goal["target"],
                    "role": str(action.get("role", "")),
                    "begin": begin,
                    "pick": picked,
                    "place": placed,
                    "success": bool(picked.get("success")) and bool(placed.get("success")),
                }
                rows.append(row)
                if not row["success"]:
                    controller_error = str(
                        placed.get("failure_reason")
                        or picked.get("failure_reason")
                        or "oracle_action_failed"
                    )
                    break
            settle = backend.settle_world()
            expected = _assignment(expected_plan)
            task = backend.task_success(expected)
            video = backend.write_video(episode_dir / "video.mp4")
        except Exception as exc:  # evidence record is more useful than a lost run
            controller_error = f"{type(exc).__name__}: {exc}"
        finally:
            if initialized:
                try:
                    finish = backend.finish_episode()
                except Exception as exc:
                    finish = {"error": f"{type(exc).__name__}: {exc}"}

        exact = bool(
            task.get("revised_task_success", task.get("success", False))
        )
        return {
            "backend": self.name,
            "initialized": initialized,
            "backend_meta": meta,
            "reset_meta": reset,
            "actions": rows,
            "observed_assignment": task.get("observed_assignment", {}),
            "expected_assignment": _assignment(expected_plan),
            "exact_assignment": exact,
            "physical_success": bool(
                exact
                and len(rows) == len(plan)
                and all(row["success"] for row in rows)
                and not controller_error
            ),
            "invalid_action_count": sum(not row["success"] for row in rows),
            "controller_error": controller_error,
            "task_metrics": task,
            "settle": settle,
            "video": video,
            "finish": finish,
        }


WORLDS = {
    "symbolic_basket": SymbolicBasketWorld,
    "libero_mujoco": LiberoBasketWorld,
}


def make_world(name: str):
    try:
        return WORLDS[name]()
    except KeyError as exc:
        raise ValueError(f"unknown backend {name!r}; choose {sorted(WORLDS)}") from exc

