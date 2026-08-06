#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope_benchmark.adapters import (  # noqa: E402
    CorrectnessNoOpAdapter,
    FORMAL_METHODS,
    formal_run_gate,
)
from cope_benchmark.interruption_scheduler import InterruptionScheduler  # noqa: E402
from cope_benchmark.interruptions import (  # noqa: E402
    InterruptionEvent,
    InterruptionType,
    LiberoInterruptionContext,
)
from cope_benchmark.metrics import score_step_constraints  # noqa: E402
from cope_benchmark.repeated_manifest import (  # noqa: E402
    read_jsonl,
    validate_manifest_rows,
)
from cope_benchmark.task_progress import (  # noqa: E402
    LiberoStateView,
    ProgressTracker,
    get_task_definition,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - runtime dependency diagnostic
        raise RuntimeError("PyYAML is required to read the repeated-interruptions config") from exc
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a mapping")
    return value


def _git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _episode_path(out_dir: Path, pair_key: str, method: str) -> Path:
    return out_dir / "episodes" / f"{pair_key}__{method}.json"


def _select_covering_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(rows)
    candidates = [row for row in rows if row["event_schedule"]]
    uncovered = set(value.value for value in InterruptionType)
    selected: list[dict[str, Any]] = []
    while uncovered:
        best = max(
            candidates,
            key=lambda row: len(
                uncovered
                & {str(event["event_type"]) for event in row.get("event_schedule", ())}
            ),
        )
        covered = {str(event["event_type"]) for event in best["event_schedule"]}
        if not uncovered & covered:
            raise RuntimeError(f"manifest cannot cover interruption types {sorted(uncovered)}")
        selected.append(best)
        uncovered -= covered
        candidates.remove(best)
    zero = next(
        (row for row in rows if int(row["pair_fields"]["interruption_count"]) == 0),
        None,
    )
    if zero is not None:
        selected.insert(0, zero)
    represented_tasks = {int(row["pair_fields"]["task_id"]) for row in selected}
    all_tasks = sorted({int(row["pair_fields"]["task_id"]) for row in rows})
    for task_id in all_tasks:
        if task_id in represented_tasks:
            continue
        task_probe = next(
            row
            for row in rows
            if int(row["pair_fields"]["task_id"]) == task_id
            and int(row["pair_fields"]["interruption_count"]) == 3
        )
        selected.append(task_probe)
    return selected


def _create_control_env(task: Any, *, use_camera_obs: bool) -> Any:
    from libero.libero import get_libero_path
    from libero.libero.envs.env_wrapper import ControlEnv

    bddl = (
        Path(get_libero_path("bddl_files"))
        / str(task.problem_folder)
        / str(task.bddl_file)
    )
    return ControlEnv(
        bddl_file_name=str(bddl),
        use_camera_obs=use_camera_obs,
        has_renderer=False,
        has_offscreen_renderer=use_camera_obs,
        camera_names=["agentview", "robot0_eye_in_hand"] if use_camera_obs else [],
        ignore_done=True,
        horizon=1000,
    )


def _eef_position(env: Any) -> tuple[float, float, float]:
    inner = getattr(env, "env", env)
    site_id = inner.robots[0].eef_site_id
    return tuple(float(value) for value in inner.sim.data.site_xpos[site_id])


def _contact_impulse_proxy(env: Any) -> float:
    inner = getattr(env, "env", env)
    forces = np.asarray(inner.sim.data.cfrc_ext, dtype=float)
    if not forces.size:
        return 0.0
    return float(np.max(np.linalg.norm(forces[:, :3], axis=1)) * inner.control_timestep)


def _already_complete(
    path: Path,
    *,
    expected_config_hash: str,
    expected_schedule_hash: str,
) -> bool:
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        value.get("complete")
        and value.get("phase") == "correctness"
        and (value.get("provenance") or {}).get("config_hash") == expected_config_hash
        and value.get("event_schedule_hash") == expected_schedule_hash
    )


def _run_correctness_episode(
    row: Mapping[str, Any],
    *,
    method: str,
    output_path: Path,
    use_camera_obs: bool,
) -> dict[str, Any]:
    from libero.libero import benchmark

    fields = row["pair_fields"]
    task_suite_name = str(fields["task_suite"])
    task_id = int(fields["task_id"])
    state_id = int(fields["state_id"])
    seed = int(fields["seed"])
    suite = benchmark.get_benchmark_dict()[task_suite_name]()
    task = suite.get_task(task_id)
    initial_state = suite.get_task_init_states(task_id)[state_id]
    digest = hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest()
    if digest != fields["initial_state_digest"]:
        raise RuntimeError("installed LIBERO initial state differs from preregistered manifest")

    definition = get_task_definition(task_suite_name, task_id)
    events = tuple(InterruptionEvent.from_dict(value) for value in row["event_schedule"])
    scheduler = InterruptionScheduler(events)
    adapter = CorrectnessNoOpAdapter(method)
    adapter.start_episode(task=row["task"], initial_instruction=definition.language)
    started = time.monotonic()
    env = _create_control_env(task, use_camera_obs=use_camera_obs)
    reset_count = 0
    rollback_count = 0
    try:
        env.seed(seed)
        env.reset()
        reset_count += 1
        observation = env.set_init_state(initial_state)
        context = LiberoInterruptionContext(env, observation)
        view = LiberoStateView(env)
        tracker = ProgressTracker(definition)
        event_records: list[dict[str, Any]] = []
        step_records: list[dict[str, Any]] = []
        progress_initial = tracker.sample(view, policy_step=0).to_dict()
        max_trigger = max((event.trigger_policy_step for event in events), default=0)
        final_policy_step = max_trigger + 1 if events else 1
        action_dim = int(getattr(env.env, "action_dim", 7))
        no_op = np.zeros(action_dim, dtype=float)
        reward = 0.0
        done = False
        info: dict[str, Any] = {}
        for policy_step in range(final_policy_step):
            progress_before = tracker.sample(view, policy_step).to_dict()
            applications, fresh_observation = scheduler.apply_due(
                context,
                policy_step=policy_step,
                progress=progress_before["current"],
            )
            if fresh_observation is not None:
                observation = fresh_observation
            for application in applications:
                event = next(value for value in events if value.event_id == application.event_id)
                progress_after = tracker.sample(view, policy_step).to_dict()
                event_information = {
                    "event": event.to_dict(),
                    "application": application.to_dict(),
                    "progress_before": progress_before,
                    "progress_after": progress_after,
                    "information_budget": row["budgets"]["information"],
                }
                decision = adapter.on_event(
                    event=event,
                    event_information=event_information,
                    observation=observation,
                    progress=progress_after["current"],
                )
                event_records.append(
                    {
                        **event_information,
                        "adapter_decision": decision.to_dict(),
                    }
                )

            eef_before = _eef_position(env)
            observation, reward, done, info = env.step(no_op)
            eef_after = _eef_position(env)
            violation = score_step_constraints(
                raw_action=no_op,
                executed_action=no_op,
                eef_position_before=eef_before,
                eef_position_after=eef_after,
                dt_seconds=float(env.env.control_timestep),
                contact_impulse_proxy=_contact_impulse_proxy(env),
                gentle_preferences=context.constraint_state.preferences,
                active_no_go_zones=context.constraint_state.active_no_go_zones,
                safety_shield_intervened=False,
            )
            progress_after_step = tracker.sample(view, policy_step + 1).to_dict()
            step_records.append(
                {
                    "policy_step": policy_step,
                    "progress": progress_after_step,
                    "raw_action": no_op.tolist(),
                    "executed_action": no_op.tolist(),
                    "violations": violation.to_dict(),
                    "reward": float(reward),
                    "done": bool(done),
                }
            )
        progress_final = tracker.sample(view, final_policy_step).to_dict()
        success = bool(view.final_success())
        result = {
            "schema_version": "repeated_episode_v1",
            "complete": True,
            "phase": "correctness",
            "evidence_admissibility": "benchmark_correctness_only_not_policy_evidence",
            "pair_key": row["pair_key"],
            "pair_fields": dict(fields),
            "method": method,
            "provider": adapter.provider_id,
            "task": dict(row["task"]),
            "event_sequence": [event.to_dict() for event in events],
            "event_schedule_hash": scheduler.schedule_digest,
            "event_records": event_records,
            "constraint_state_final": context.constraint_state.snapshot(),
            "progress_initial": progress_initial,
            "progress_final": progress_final,
            "progress_trace": step_records,
            "policy_step_budget": int(row["budgets"]["policy_steps"]),
            "policy_steps_consumed": final_policy_step,
            "event_injection_policy_steps": 0,
            "high_level_budget": int(row["budgets"]["high_level_calls"]),
            "high_level_calls": len(event_records),
            "success": success,
            "timeout": False,
            "termination_reason": "correctness_probe_complete",
            "manual_intervention": False,
            "reset_count": reset_count,
            "rollback_count": rollback_count,
            "fresh_observation_for_all_events": all(
                record["application"]["fresh_observation"] for record in event_records
            ),
            "events_consumed_no_policy_step": all(
                record["application"]["policy_step_unchanged_by_event"]
                for record in event_records
            ),
            "scheduler_complete": scheduler.complete,
            "runtime_seconds": time.monotonic() - started,
            "provenance": {
                **dict(row["provenance"]),
                "runtime_commit": _git_value("rev-parse", "HEAD"),
                "runtime_dirty": bool(_git_value("status", "--porcelain")),
                "config_hash": row["config_hash"],
            },
            "artifacts": {"episode_json": str(output_path)},
        }
        _atomic_json(output_path, result)
        return result
    finally:
        env.close()


def validate_correctness_results(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(results)
    errors: list[str] = []
    pair_groups: dict[str, list[Mapping[str, Any]]] = {}
    covered: set[str] = set()
    for record in records:
        pair_groups.setdefault(str(record["pair_key"]), []).append(record)
        if record.get("phase") != "correctness":
            errors.append(f"{record.get('pair_key')}: non-correctness record mixed into Phase A")
        if record.get("provider") != "scripted_noop_correctness_only":
            errors.append(f"{record.get('pair_key')}: unexpected correctness provider")
        if not record.get("scheduler_complete"):
            errors.append(f"{record.get('pair_key')}: not all scheduled events fired")
        if not record.get("fresh_observation_for_all_events"):
            errors.append(f"{record.get('pair_key')}: an event lacked a fresh observation")
        if not record.get("events_consumed_no_policy_step"):
            errors.append(f"{record.get('pair_key')}: an event consumed a policy step")
        if int(record.get("rollback_count", -1)) != 0:
            errors.append(f"{record.get('pair_key')}: rollback detected")
        if int(record.get("reset_count", -1)) != 1:
            errors.append(f"{record.get('pair_key')}: hidden/additional reset detected")
        if record.get("manual_intervention"):
            errors.append(f"{record.get('pair_key')}: manual intervention must be false")
        if record.get("timeout") and record.get("success"):
            errors.append(f"{record.get('pair_key')}: timeout cannot be success")
        covered.update(event["event_type"] for event in record.get("event_sequence", ()))
    for pair_key, pair in pair_groups.items():
        if len(pair) != len(FORMAL_METHODS):
            errors.append(f"{pair_key}: expected two paired method records, found {len(pair)}")
            continue
        methods = {str(record["method"]) for record in pair}
        if methods != set(FORMAL_METHODS):
            errors.append(f"{pair_key}: method pair mismatch {sorted(methods)}")
        if len({record["event_schedule_hash"] for record in pair}) != 1:
            errors.append(f"{pair_key}: methods received different schedules")
        if len({json.dumps(record["event_sequence"], sort_keys=True) for record in pair}) != 1:
            errors.append(f"{pair_key}: methods received different event information")
    missing = sorted(set(value.value for value in InterruptionType) - covered)
    if missing:
        errors.append(f"Phase A did not cover event types {missing}")
    return {
        "passed": not errors,
        "errors": errors,
        "episode_count": len(records),
        "pair_count": len(pair_groups),
        "event_types_covered": sorted(covered),
        "gates": {
            "deterministic_event_schedules": not any("different schedules" in error for error in errors),
            "paired_event_equality": not any("different event information" in error for error in errors),
            "no_hidden_reset_or_rollback": not any(
                "reset detected" in error or "rollback detected" in error for error in errors
            ),
            "event_does_not_consume_policy_step": not any(
                "consumed a policy step" in error for error in errors
            ),
            "fresh_observation": not any("fresh observation" in error for error in errors),
            "all_seven_event_types": not missing,
            "manual_intervention_excluded": not any(
                "manual intervention" in error for error in errors
            ),
            "timeout_not_success": not any("timeout cannot be success" in error for error in errors),
        },
    }


def run_correctness(
    *,
    manifest_path: Path,
    out_dir: Path,
    use_camera_obs: bool,
    limit_pairs: int | None,
) -> dict[str, Any]:
    rows = read_jsonl(manifest_path)
    manifest_validation = validate_manifest_rows(rows, expect_full=True)
    if not manifest_validation["passed"]:
        raise RuntimeError(f"manifest validation failed: {manifest_validation['errors']}")
    selected = _select_covering_rows(rows)
    if limit_pairs is not None:
        selected = selected[:limit_pairs]
    results: list[dict[str, Any]] = []
    for row in selected:
        for method in FORMAL_METHODS:
            path = _episode_path(out_dir, row["pair_key"], method)
            if _already_complete(
                path,
                expected_config_hash=str(row["config_hash"]),
                expected_schedule_hash=str(row["event_schedule_hash"]),
            ):
                results.append(json.loads(path.read_text(encoding="utf-8")))
                continue
            results.append(
                _run_correctness_episode(
                    row,
                    method=method,
                    output_path=path,
                    use_camera_obs=use_camera_obs,
                )
            )
    validation = validate_correctness_results(results)
    summary = {
        "phase": "correctness",
        "not_formal_policy_evidence": True,
        "manifest": str(manifest_path),
        "manifest_validation": manifest_validation,
        "correctness_validation": validation,
        "episodes": [record["artifacts"]["episode_json"] for record in results],
    }
    _atomic_json(out_dir / "correctness_summary.json", summary)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("correctness", "clean_calibration", "pilot", "formal", "gate"),
        default="correctness",
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--use-camera-obs", action="store_true")
    parser.add_argument("--limit-pairs", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = _load_yaml(args.config)
    if args.phase == "gate":
        output = {
            phase: formal_run_gate(config, phase=phase)
            for phase in ("clean_calibration", "pilot", "formal")
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    blockers = formal_run_gate(config, phase=args.phase)
    if blockers:
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "started": False,
                    "blocked": True,
                    "blockers": blockers,
                    "no_fake_results_created": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    if args.phase != "correctness":
        # The canonical adapters and state engine are intentionally not copied
        # into this branch.  The gate above becomes passable only after those
        # external factories and their exact commits are configured.
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "started": False,
                    "blocked": True,
                    "blockers": [
                        "formal rollout binding must be supplied by the main-experiment adapter dependency"
                    ],
                    "no_fake_results_created": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    summary = run_correctness(
        manifest_path=args.manifest,
        out_dir=args.out_dir,
        use_camera_obs=args.use_camera_obs,
        limit_pairs=args.limit_pairs,
    )
    print(json.dumps(summary["correctness_validation"], indent=2, sort_keys=True))
    return 0 if summary["correctness_validation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
