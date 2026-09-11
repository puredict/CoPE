from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .adapters import FORMAL_METHODS
from .interruption_scheduler import canonical_event_digest, validate_event_sequence
from .interruptions import INTERRUPTION_LIBRARY_VERSION, InterruptionEvent, InterruptionType
from .task_progress import TASK_DEFINITIONS, TASK_PROGRESS_VERSION, TaskProgressDefinition


MANIFEST_VERSION = "repeated_interruptions_v1"
DEFAULT_STATES = tuple(range(5))
DEFAULT_SEEDS = (11, 29, 47)
DEFAULT_INTERRUPTION_COUNTS = (0, 1, 2, 3)
# The v1 manifest was frozen around these four calibrated tasks.  Later task
# catalogs may extend TASK_DEFINITIONS, but must not silently expand this
# historical manifest or change its preregistered 240 pair rows.
REPEATED_V1_TASK_IDS = (0, 1, 4, 8)
DEFAULT_POLICY_BUDGET = 220
DEFAULT_HIGH_LEVEL_BUDGET = 4
DEFAULT_INFORMATION_BUDGET = {
    "event_payload_visibility": "identical_full_event_information",
    "simulator_truth_visibility": "scoring_and_injection_only",
    "image_observation": "fresh_post_event",
}

TOOL_RELEASE_Z = {
    "alphabet_soup_1_joint0": 0.46,
    "tomato_sauce_1_joint0": 0.48,
    "cream_cheese_1_joint0": 0.445,
    "butter_1_joint0": 0.44,
    "porcelain_mug_1_joint0": 0.48,
    "white_yellow_mug_1_joint0": 0.48,
    "moka_pot_1_joint0": 0.97,
    "moka_pot_2_joint0": 0.97,
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _choice_index(*values: Any, modulo: int) -> int:
    digest = canonical_hash(list(values))
    return int(digest[:16], 16) % modulo


def _event_families(count: int, has_receptacle: bool) -> tuple[tuple[InterruptionType, ...], ...]:
    target = InterruptionType.TARGET_OBJECT_MOVED
    receptacle = InterruptionType.GOAL_RECEPTACLE_MOVED
    appear = InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS
    disappear = InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS
    gentle = InterruptionType.USER_ADDS_GENTLE_PREFERENCE
    unavailable = InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE
    available = InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN
    if count == 0:
        return ((),)
    if count == 1:
        families = [(target,), (appear,), (gentle,), (unavailable,)]
        if has_receptacle:
            families.append((receptacle,))
        return tuple(families)
    if count == 2:
        families = [
            (appear, disappear),
            (unavailable, available),
            (target, gentle),
            (appear, target),
        ]
        if has_receptacle:
            families.extend(((receptacle, gentle), (target, receptacle)))
        return tuple(families)
    if count == 3:
        families = [
            (target, appear, disappear),
            (gentle, unavailable, available),
            (target, unavailable, available),
            (target, appear, gentle),
        ]
        if has_receptacle:
            families.extend(
                (
                    (receptacle, appear, disappear),
                    (target, receptacle, gentle),
                )
            )
        return tuple(families)
    raise ValueError("interruption count must be 0, 1, 2, or 3")


def _payload(
    event_type: InterruptionType,
    *,
    definition: TaskProgressDefinition,
    task_id: int,
    state_id: int,
    seed: int,
    count: int,
    pair_key: str,
    selected_tool_joint: str,
    selected_target_joint: str,
    selected_receptacle_joint: str | None,
) -> dict[str, Any]:
    sign_x = -1.0 if _choice_index(pair_key, event_type.value, "x", modulo=2) else 1.0
    sign_y = -1.0 if _choice_index(pair_key, event_type.value, "y", modulo=2) else 1.0
    if event_type == InterruptionType.TARGET_OBJECT_MOVED:
        return {
            "joint": selected_target_joint,
            "dx": 0.08 * sign_x,
            "dy": 0.06 * sign_y,
            "role": "task_target",
            "requested_displacement_norm": 0.1,
        }
    if event_type == InterruptionType.GOAL_RECEPTACLE_MOVED:
        if selected_receptacle_joint is None:
            raise ValueError(f"task {task_id} has no movable goal receptacle")
        return {
            "joint": selected_receptacle_joint,
            "dx": 0.06 * sign_x,
            "dy": 0.05 * sign_y,
            "role": "goal_receptacle",
            "requested_displacement_norm": (0.06**2 + 0.05**2) ** 0.5,
        }
    if event_type in {
        InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS,
        InterruptionType.TEMPORARY_NO_GO_ZONE_DISAPPEARS,
    }:
        payload: dict[str, Any] = {"zone_id": f"{pair_key}:zone0"}
        if event_type == InterruptionType.TEMPORARY_NO_GO_ZONE_APPEARS:
            z_min, z_max = (0.43, 0.90) if task_id != 8 else (0.92, 1.30)
            payload.update(
                {
                    # This corridor lies between the initial EEF position and
                    # the positive-y receptacles.  It does not contain the
                    # calibrated reset pose, avoiding an unavoidable violation
                    # at the instant the constraint appears.
                    "minimum": [-0.08, 0.10, z_min],
                    "maximum": [0.08, 0.20, z_max],
                    "frame": "world",
                    "violation_predicate": "eef_point_or_swept_segment_intersects_closed_aabb",
                    "physical_collision": False,
                    "visual_marker": False,
                }
            )
        return payload
    if event_type == InterruptionType.USER_ADDS_GENTLE_PREFERENCE:
        return {
            "preference_id": f"{pair_key}:gentle0",
            "translation_ceiling": 0.035,
            "eef_speed_ceiling": 0.22,
            "contact_impulse_proxy_ceiling": 0.12,
            "priority": "user_preference",
            "raw_violation_scored_before_shield": True,
            "shield_available_equally_to_both_methods": True,
        }
    if event_type == InterruptionType.TOOL_TEMPORARILY_UNAVAILABLE:
        release_z = TOOL_RELEASE_Z[selected_tool_joint]
        return {
            "tool_joint": selected_tool_joint,
            "unavailable_xyz": [0.43, 0.41, release_z],
            "accessible_xyz_bounds": [
                list(definition.workspace_xy_bounds[0]),
                list(definition.workspace_xy_bounds[1]),
                [release_z - 0.08, release_z + 0.35],
            ],
            "availability_predicate": "free_joint_xyz_inside_accessible_bounds",
            "real_simulator_object_mutation": True,
        }
    if event_type == InterruptionType.TOOL_BECOMES_AVAILABLE_AGAIN:
        release_z = TOOL_RELEASE_Z[selected_tool_joint]
        return {
            "tool_joint": selected_tool_joint,
            "release_xyz": [-0.24, 0.28, release_z],
            "accessible_xyz_bounds": [
                list(definition.workspace_xy_bounds[0]),
                list(definition.workspace_xy_bounds[1]),
                [release_z - 0.08, release_z + 0.35],
            ],
            "availability_predicate": "free_joint_xyz_inside_accessible_bounds",
            "restore_semantics": "preregistered_release_not_snapshot_restore",
        }
    raise ValueError(f"unsupported event type {event_type}")


def make_schedule(
    definition: TaskProgressDefinition,
    *,
    state_id: int,
    seed: int,
    interruption_count: int,
    pair_key: str,
) -> tuple[InterruptionEvent, ...]:
    families = _event_families(interruption_count, bool(definition.receptacle_joints))
    family = families[
        _choice_index(
            definition.task_suite,
            definition.task_id,
            state_id,
            seed,
            interruption_count,
            modulo=len(families),
        )
    ]
    target_joint = definition.target_joints[
        _choice_index(pair_key, "target", modulo=len(definition.target_joints))
    ]
    tool_joint = definition.tool_joints[
        _choice_index(pair_key, "tool", modulo=len(definition.tool_joints))
    ]
    receptacle_joint = (
        definition.receptacle_joints[
            _choice_index(pair_key, "receptacle", modulo=len(definition.receptacle_joints))
        ]
        if definition.receptacle_joints
        else None
    )
    steps = (55, 110, 165)
    events: list[InterruptionEvent] = []
    for index, event_type in enumerate(family):
        trigger = {
            "kind": "policy_step_gte",
            "step": steps[index],
            "preregistered": True,
        }
        events.append(
            InterruptionEvent(
                event_id=f"{pair_key}:e{index}",
                event_type=event_type,
                trigger_policy_step=steps[index],
                trigger_predicate=trigger,
                payload=_payload(
                    event_type,
                    definition=definition,
                    task_id=definition.task_id,
                    state_id=state_id,
                    seed=seed,
                    count=interruption_count,
                    pair_key=pair_key,
                    selected_tool_joint=tool_joint,
                    selected_target_joint=target_joint,
                    selected_receptacle_joint=receptacle_joint,
                ),
            )
        )
    validate_event_sequence(events)
    return tuple(events)


def _pair_key(task_id: int, state_id: int, seed: int, interruption_count: int) -> str:
    return (
        f"rpi-v1__libero_10-t{task_id:02d}__state{state_id:02d}"
        f"__seed{seed:03d}__n{interruption_count}"
    )


def generate_manifest_rows(
    *,
    initial_state_digests: Mapping[tuple[int, int], str],
    source_commit: str,
    checkpoint: str | None,
    dependency_commits: Mapping[str, str | None],
    states: Iterable[int] = DEFAULT_STATES,
    seeds: Iterable[int] = DEFAULT_SEEDS,
    interruption_counts: Iterable[int] = DEFAULT_INTERRUPTION_COUNTS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    definitions = [TASK_DEFINITIONS[("libero_10", task_id)] for task_id in REPEATED_V1_TASK_IDS]
    for definition in definitions:
        for state_id in states:
            state_digest = str(initial_state_digests.get((definition.task_id, int(state_id)), ""))
            if len(state_digest) != 64:
                raise ValueError(
                    f"missing full SHA-256 initial-state digest for task={definition.task_id}, state={state_id}"
                )
            for seed in seeds:
                for count in interruption_counts:
                    pair_key = _pair_key(definition.task_id, int(state_id), int(seed), int(count))
                    events = make_schedule(
                        definition,
                        state_id=int(state_id),
                        seed=int(seed),
                        interruption_count=int(count),
                        pair_key=pair_key,
                    )
                    row: dict[str, Any] = {
                        "manifest_version": MANIFEST_VERSION,
                        "interruption_library_version": INTERRUPTION_LIBRARY_VERSION,
                        "progress_version": TASK_PROGRESS_VERSION,
                        "pair_key": pair_key,
                        "pair_fields": {
                            "task_suite": definition.task_suite,
                            "task_id": definition.task_id,
                            "state_id": int(state_id),
                            "seed": int(seed),
                            "interruption_count": int(count),
                            "initial_state_digest": state_digest,
                            "policy_budget": DEFAULT_POLICY_BUDGET,
                            "high_level_budget": DEFAULT_HIGH_LEVEL_BUDGET,
                        },
                        "task": definition.to_dict(),
                        "methods": list(FORMAL_METHODS),
                        "event_schedule": [event.to_dict() for event in events],
                        "event_schedule_hash": canonical_event_digest(events),
                        "task_progress_predicates": [
                            predicate.to_dict() for predicate in definition.predicates
                        ],
                        "geometric_sanity": {
                            "workspace_xy_bounds": [
                                list(definition.workspace_xy_bounds[0]),
                                list(definition.workspace_xy_bounds[1]),
                            ],
                            "max_object_displacement_norm": 0.10,
                            "no_go_closed_aabb": True,
                            "runtime_post_injection_check_required": True,
                        },
                        "budgets": {
                            "policy_steps": DEFAULT_POLICY_BUDGET,
                            "high_level_calls": DEFAULT_HIGH_LEVEL_BUDGET,
                            "information": dict(DEFAULT_INFORMATION_BUDGET),
                            "event_injection_consumes_policy_step": False,
                        },
                        "provenance": {
                            "source_commit": source_commit,
                            "checkpoint": checkpoint,
                            "dependency_commits": dict(dependency_commits),
                            "manual_intervention": False,
                        },
                    }
                    row["config_hash"] = canonical_hash(row)
                    rows.append(row)
    return rows


def validate_manifest_rows(rows: Iterable[Mapping[str, Any]], *, expect_full: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    pair_keys: set[str] = set()
    counts: dict[int, int] = {}
    type_counts: dict[str, int] = {}
    rows_list = list(rows)
    for index, row in enumerate(rows_list):
        key = str(row.get("pair_key", ""))
        if not key or key in pair_keys:
            errors.append(f"row {index}: missing or duplicate pair_key {key!r}")
        pair_keys.add(key)
        copy = dict(row)
        config_hash = str(copy.pop("config_hash", ""))
        if canonical_hash(copy) != config_hash:
            errors.append(f"row {index}: config_hash mismatch")
        events = tuple(InterruptionEvent.from_dict(value) for value in row.get("event_schedule", ()))
        try:
            validate_event_sequence(events)
        except Exception as exc:
            errors.append(f"row {index}: invalid schedule: {exc}")
        if canonical_event_digest(events) != row.get("event_schedule_hash"):
            errors.append(f"row {index}: event_schedule_hash mismatch")
        interruption_count = int(row.get("pair_fields", {}).get("interruption_count", -1))
        if len(events) != interruption_count:
            errors.append(f"row {index}: count={interruption_count}, events={len(events)}")
        counts[interruption_count] = counts.get(interruption_count, 0) + 1
        for event in events:
            type_counts[event.event_type.value] = type_counts.get(event.event_type.value, 0) + 1
        if tuple(row.get("methods", ())) != FORMAL_METHODS:
            errors.append(f"row {index}: methods are not the fixed formal pair")
    if expect_full:
        if len(rows_list) != 240:
            errors.append(f"full manifest must contain 240 method-independent pairs, found {len(rows_list)}")
        expected = {count: 60 for count in DEFAULT_INTERRUPTION_COUNTS}
        if counts != expected:
            errors.append(f"full manifest count balance mismatch: {counts}, expected {expected}")
        missing_types = sorted(set(value.value for value in InterruptionType) - set(type_counts))
        if missing_types:
            errors.append(f"full manifest does not cover interruption types {missing_types}")
    return {
        "passed": not errors,
        "errors": errors,
        "row_count": len(rows_list),
        "formal_episode_count": len(rows_list) * len(FORMAL_METHODS),
        "interruption_count_rows": counts,
        "event_type_counts": dict(sorted(type_counts.items())),
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_libero_initial_state_digests() -> dict[tuple[int, int], str]:
    import numpy as np
    from libero.libero import benchmark

    suite = benchmark.get_benchmark_dict()["libero_10"]()
    result: dict[tuple[int, int], str] = {}
    for task_id in sorted(task_id for suite_name, task_id in TASK_DEFINITIONS if suite_name == "libero_10"):
        states = suite.get_task_init_states(task_id)
        for state_id in DEFAULT_STATES:
            result[(task_id, state_id)] = hashlib.sha256(
                np.asarray(states[state_id]).tobytes()
            ).hexdigest()
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--cope-state-commit", default=None)
    parser.add_argument("--adapter-commit", default=None)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.validate_only:
        validation = validate_manifest_rows(read_jsonl(args.output), expect_full=True)
    else:
        rows = generate_manifest_rows(
            initial_state_digests=load_libero_initial_state_digests(),
            source_commit=args.source_commit,
            checkpoint=args.checkpoint,
            dependency_commits={
                "method/cope-state-semantics": args.cope_state_commit,
                "main_experiment_adapters": args.adapter_commit,
            },
        )
        write_jsonl(args.output, rows)
        validation = validate_manifest_rows(rows, expect_full=True)
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0 if validation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
