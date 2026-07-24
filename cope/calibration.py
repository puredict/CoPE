from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class CalibrationSeedScheme:
    name: str
    base_seed: int
    task_stride: int
    state_stride: int
    forbidden_evaluation_seeds: tuple[int, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CalibrationSeedScheme":
        scheme = cls(
            name=str(value.get("name", "")),
            base_seed=int(value.get("base_seed", -1)),
            task_stride=int(value.get("task_stride", 0)),
            state_stride=int(value.get("state_stride", 0)),
            forbidden_evaluation_seeds=tuple(
                int(item) for item in value.get("forbidden_evaluation_seeds", ())
            ),
        )
        if not scheme.name or scheme.base_seed < 0:
            raise ValueError("calibration seed scheme requires a name and non-negative base_seed")
        if scheme.task_stride <= 0 or scheme.state_stride <= 0:
            raise ValueError("calibration seed strides must be positive")
        return scheme

    def derive(self, *, task_ordinal: int, state_id: int) -> int:
        seed = (
            self.base_seed
            + int(task_ordinal) * self.task_stride
            + int(state_id) * self.state_stride
        )
        if seed in self.forbidden_evaluation_seeds:
            raise ValueError(f"derived calibration seed overlaps evaluation seed {seed}")
        return seed


def build_calibration_entries(
    *,
    task_ids: Iterable[int],
    state_ids: Iterable[int],
    seed_scheme: CalibrationSeedScheme,
) -> tuple[dict[str, int | str], ...]:
    tasks = tuple(int(item) for item in task_ids)
    states = tuple(int(item) for item in state_ids)
    if not tasks or not states:
        raise ValueError("calibration task_ids and state_ids cannot be empty")
    if len(tasks) != len(set(tasks)) or len(states) != len(set(states)):
        raise ValueError("calibration task_ids and state_ids must be unique")
    entries: list[dict[str, int | str]] = []
    seeds: set[int] = set()
    for task_ordinal, task_id in enumerate(tasks):
        for state_id in states:
            seed = seed_scheme.derive(task_ordinal=task_ordinal, state_id=state_id)
            if seed in seeds:
                raise ValueError(f"calibration seed scheme produced duplicate seed {seed}")
            seeds.add(seed)
            entries.append(
                {
                    "episode_id": f"calibration__task{task_id:02d}__state{state_id:02d}__seed{seed}",
                    "task_id": task_id,
                    "initial_state_id": state_id,
                    "seed": seed,
                }
            )
    return tuple(entries)


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > total:
        raise ValueError("successes must be within [0, total]")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            (proportion * (1.0 - proportion) + z * z / (4.0 * total)) / total
        )
        / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def validate_openvla_action(
    raw_action: Sequence[float],
    env_action: Sequence[float],
    *,
    expected_dim: int,
    action_low: Sequence[float],
    action_high: Sequence[float],
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    raw = tuple(float(item) for item in raw_action)
    env = tuple(float(item) for item in env_action)
    low = tuple(float(item) for item in action_low)
    high = tuple(float(item) for item in action_high)
    gates = {
        "raw_action_shape": len(raw) == expected_dim,
        "environment_action_shape": len(env) == expected_dim,
        "action_spec_shape": len(low) == expected_dim and len(high) == expected_dim,
        "finite": all(math.isfinite(item) for item in raw + env),
    }
    gates["environment_action_within_spec"] = bool(
        gates["action_spec_shape"]
        and gates["environment_action_shape"]
        and all(
            lower - tolerance <= value <= upper + tolerance
            for value, lower, upper in zip(env, low, high)
        )
    )
    gates["raw_gripper_in_unit_interval"] = bool(
        gates["raw_action_shape"] and -tolerance <= raw[-1] <= 1.0 + tolerance
    )
    gates["environment_gripper_binarized"] = bool(
        gates["environment_action_shape"] and abs(abs(env[-1]) - 1.0) <= tolerance
    )
    expected_gripper = -1.0 if raw and raw[-1] > 0.5 else 1.0
    gates["gripper_normalize_binarize_invert"] = bool(
        gates["raw_action_shape"]
        and gates["environment_action_shape"]
        and abs(raw[-1] - 0.5) > tolerance
        and abs(env[-1] - expected_gripper) <= tolerance
    )
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "raw_action": list(raw),
        "environment_action": list(env),
        "action_low": list(low),
        "action_high": list(high),
        "expected_dim": expected_dim,
    }
