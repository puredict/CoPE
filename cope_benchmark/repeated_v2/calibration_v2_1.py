"""Pure protocol utilities for repeated-v2.1 calibration and horizons.

This module deliberately has no simulator, policy, provider, or method imports.
It freezes the statistical unit, state split, quantile convention, and horizon
rules before the v2.1 calibration outcomes are collected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence


PROTOCOL_VERSION = "repeated_v2_1_horizon_and_independence_v1"
AVAILABLE_STATE_IDS = tuple(range(50))
CALIBRATION_STATE_IDS = tuple(range(10))
FORMAL_STATE_IDS = tuple(range(10, 15))
DEVELOPMENT_STATE_IDS = tuple(range(15, 20))
RESERVE_STATE_IDS = tuple(range(20, 50))
CALIBRATION_TECHNICAL_SEED = 101
FORMAL_TECHNICAL_SEED = 11
CALIBRATION_MEASUREMENT_CEILING = 520
CLEAN_SUCCESS_INTERVAL = (0.40, 0.95)
MIN_SUCCESSFUL_UNIQUE_TRAJECTORIES = 3
MIN_UNIQUE_EVENT_OVERHEADS = 3
MIN_EVENT_FAMILIES_FOR_OVERHEAD = 2
CLEAN_HORIZON_BOUNDS = (320, 520)
EVENT_ALLOWANCE_BOUNDS = (32, 130)
INTERRUPTED_HORIZON_CAP = 1040
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class CalibrationV21Error(ValueError):
    """Raised when evidence cannot satisfy the frozen v2.1 protocol."""


@dataclass(frozen=True)
class HorizonDecision:
    status: str
    horizon: int | None
    successful_unique_trajectories: int
    completion_times: tuple[int, ...]
    q95_nearest_rank: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterruptedBudgetDecision:
    status: str
    horizon: int | None
    event_allowance: int | None
    unique_overhead_measurements: int
    event_family_count: int
    q95_nearest_rank: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise CalibrationV21Error(f"{label} must be an integer")
    return value


def validate_initial_state_split(
    *,
    available_state_ids: Iterable[int] = AVAILABLE_STATE_IDS,
    calibration_state_ids: Iterable[int] = CALIBRATION_STATE_IDS,
    formal_state_ids: Iterable[int] = FORMAL_STATE_IDS,
    development_state_ids: Iterable[int] = DEVELOPMENT_STATE_IDS,
    reserve_state_ids: Iterable[int] = RESERVE_STATE_IDS,
) -> None:
    """Validate exact coverage and pairwise disjointness of the frozen split."""
    named = {
        "calibration": tuple(calibration_state_ids),
        "formal": tuple(formal_state_ids),
        "development": tuple(development_state_ids),
        "reserve": tuple(reserve_state_ids),
    }
    available = tuple(available_state_ids)
    if len(set(available)) != len(available) or any(type(v) is not int for v in available):
        raise CalibrationV21Error("available state IDs must be distinct integers")
    for label, values in named.items():
        if len(set(values)) != len(values) or any(type(v) is not int for v in values):
            raise CalibrationV21Error(f"{label} state IDs must be distinct integers")
        if not set(values).issubset(available):
            raise CalibrationV21Error(f"{label} state IDs are outside the enumerated inventory")
    labels = tuple(named)
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            overlap = set(named[left]) & set(named[right])
            if overlap:
                raise CalibrationV21Error(f"{left}/{right} state IDs overlap: {sorted(overlap)}")
    covered = set().union(*(set(values) for values in named.values()))
    if covered != set(available):
        raise CalibrationV21Error("state split must cover the enumerated inventory exactly")


def validate_state_inventory(rows: Iterable[Mapping[str, Any]]) -> None:
    """Require 50 finite, hash-bound, unique states for every LIBERO-10 task."""
    parsed = tuple(rows)
    expected = {(task_id, state_id) for task_id in range(10) for state_id in AVAILABLE_STATE_IDS}
    actual: set[tuple[int, int]] = set()
    hashes: dict[int, set[str]] = {task_id: set() for task_id in range(10)}
    for row in parsed:
        task_id = int(row["task_id"])
        state_id = int(row["state_id"])
        key = (task_id, state_id)
        if key in actual:
            raise CalibrationV21Error(f"duplicate inventory row {key}")
        actual.add(key)
        digest = str(row["state_sha256"])
        if not _SHA256.fullmatch(digest):
            raise CalibrationV21Error(f"invalid state digest for {key}")
        if digest in hashes.get(task_id, set()):
            raise CalibrationV21Error(f"duplicate state bytes within task {task_id}")
        hashes.setdefault(task_id, set()).add(digest)
        finite = row.get("finite")
        if finite not in (True, "true", "True", 1, "1"):
            raise CalibrationV21Error(f"non-finite state {key}")
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise CalibrationV21Error(
            f"inventory differs from 10x50 grid; missing={missing[:5]}, unexpected={unexpected[:5]}"
        )
    validate_initial_state_split()


def calibration_grid(task_ids: Iterable[int] = range(10)) -> tuple[dict[str, int], ...]:
    """Return one technical run for each calibration task/state combination."""
    validate_initial_state_split()
    tasks = tuple(sorted(task_ids))
    if len(set(tasks)) != len(tasks) or any(type(v) is not int or not 0 <= v < 10 for v in tasks):
        raise CalibrationV21Error("task IDs must be distinct integers in 0..9")
    return tuple(
        {
            "task_id": task_id,
            "initial_state_id": state_id,
            "policy_seed": CALIBRATION_TECHNICAL_SEED,
        }
        for task_id in tasks
        for state_id in CALIBRATION_STATE_IDS
    )


def action_trajectory_sha256(actions: Iterable[Sequence[float]]) -> str:
    """Hash a complete finite 7-D action sequence with canonical JSON bytes."""
    normalized: list[list[float]] = []
    for step, action in enumerate(actions):
        values = list(action)
        if len(values) != 7:
            raise CalibrationV21Error(f"action {step} does not have seven coordinates")
        converted = []
        for coordinate in values:
            if type(coordinate) not in (int, float) or not math.isfinite(coordinate):
                raise CalibrationV21Error(f"action {step} contains a non-finite coordinate")
            converted.append(float(coordinate))
        normalized.append(converted)
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def group_duplicate_trajectories(
    records: Iterable[Mapping[str, Any]], *, digest_field: str = "action_trajectory_sha256"
) -> tuple[dict[str, Any], ...]:
    """Group same-state exact action sequences, ignoring nominal seed labels.

    Equal actions from distinct initialization states remain distinct physical
    trajectories.  ``initial_state_sha256`` is preferred when present; the
    frozen numeric state ID is the fallback for pre-amendment audit records.
    """
    groups: dict[tuple[int, str, str], list[Mapping[str, Any]]] = {}
    for row in records:
        task_id = _strict_int(row.get("task_id"), "task_id")
        state_id = _strict_int(row.get("initial_state_id"), "initial_state_id")
        state_digest = row.get("initial_state_sha256")
        if state_digest is None:
            state_identity = f"state_id:{state_id}"
        elif isinstance(state_digest, str) and _SHA256.fullmatch(state_digest):
            state_identity = f"sha256:{state_digest}"
        else:
            raise CalibrationV21Error("invalid initial_state_sha256")
        digest = row.get(digest_field)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CalibrationV21Error(f"invalid {digest_field}")
        groups.setdefault((task_id, state_identity, digest), []).append(row)
    output = []
    for (task_id, state_identity, digest), members in sorted(groups.items()):
        outcomes = {(row.get("success"), row.get("completion_policy_steps")) for row in members}
        if len(outcomes) != 1:
            raise CalibrationV21Error("exact duplicate action trajectories have conflicting outcomes")
        member_keys = tuple(
            sorted(
                (int(row["initial_state_id"]), int(row["policy_seed"]))
                for row in members
            )
        )
        success, completion = next(iter(outcomes))
        output.append(
            {
                "task_id": task_id,
                "initial_state_identity": state_identity,
                "action_trajectory_sha256": digest,
                "nominal_run_count": len(members),
                "members": member_keys,
                "success": success,
                "completion_policy_steps": completion,
            }
        )
    return tuple(output)


def nearest_rank_quantile(values: Iterable[int], q: float) -> int:
    """Return the preregistered conservative empirical nearest-rank quantile."""
    ordered = sorted(_strict_int(value, "quantile value") for value in values)
    if not ordered:
        raise CalibrationV21Error("quantile requires at least one observation")
    if not isinstance(q, (int, float)) or not math.isfinite(q) or not 0 < q <= 1:
        raise CalibrationV21Error("quantile probability must be in (0, 1]")
    return ordered[max(0, math.ceil(float(q) * len(ordered)) - 1)]


def derive_clean_horizon(records: Iterable[Mapping[str, Any]]) -> HorizonDecision:
    """Apply the frozen clean horizon rule to unique successful trajectories."""
    groups = group_duplicate_trajectories(records)
    completions: list[int] = []
    for group in groups:
        if group["success"] is True:
            completion = _strict_int(group["completion_policy_steps"], "completion_policy_steps")
            if not 1 <= completion <= CALIBRATION_MEASUREMENT_CEILING:
                raise CalibrationV21Error("successful completion lies outside the measurement ceiling")
            completions.append(completion)
    completions.sort()
    if len(completions) < MIN_SUCCESSFUL_UNIQUE_TRAJECTORIES:
        return HorizonDecision(
            "HORIZON_UNESTIMABLE",
            None,
            len(completions),
            tuple(completions),
            None,
            f"requires at least {MIN_SUCCESSFUL_UNIQUE_TRAJECTORIES} successful unique trajectories",
        )
    q95 = nearest_rank_quantile(completions, 0.95)
    proposed = math.ceil(1.20 * q95)
    horizon = min(CLEAN_HORIZON_BOUNDS[1], max(CLEAN_HORIZON_BOUNDS[0], proposed))
    return HorizonDecision(
        "HORIZON_ESTIMATED",
        horizon,
        len(completions),
        tuple(completions),
        q95,
        "clip(ceil(1.20 * empirical nearest-rank Q95), 320, 520)",
    )


def derive_interrupted_budget(
    clean_horizon: int,
    interruption_count: int,
    overhead_records: Iterable[Mapping[str, Any]],
) -> InterruptedBudgetDecision:
    """Derive one task/K budget from unique paired calibration event overheads.

    Unknown fields, including a method identity, are ignored. Each admitted row
    must be a successful paired clean/event calibration measurement and supply
    the exact interrupted action-trajectory hash used for deduplication.
    """
    clean = _strict_int(clean_horizon, "clean_horizon")
    count = _strict_int(interruption_count, "interruption_count")
    if not CLEAN_HORIZON_BOUNDS[0] <= clean <= CLEAN_HORIZON_BOUNDS[1]:
        raise CalibrationV21Error("clean horizon is outside frozen bounds")
    if count < 0:
        raise CalibrationV21Error("interruption_count must be nonnegative")
    unique: dict[tuple[str, str], int] = {}
    families: set[str] = set()
    for row in overhead_records:
        if row.get("paired_success") is not True:
            continue
        digest = row.get("action_trajectory_sha256")
        family = row.get("event_family")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CalibrationV21Error("invalid event-overhead action trajectory digest")
        if not isinstance(family, str) or not family:
            raise CalibrationV21Error("event-overhead record lacks an event family")
        overhead = _strict_int(row.get("overhead_policy_steps"), "overhead_policy_steps")
        if overhead < 0:
            raise CalibrationV21Error("event overhead must be nonnegative")
        key = (family, digest)
        prior = unique.get(key)
        if prior is not None and prior != overhead:
            raise CalibrationV21Error("duplicate event-overhead trajectory has conflicting values")
        unique[key] = overhead
        families.add(family)
    if len(unique) < MIN_UNIQUE_EVENT_OVERHEADS or len(families) < MIN_EVENT_FAMILIES_FOR_OVERHEAD:
        return InterruptedBudgetDecision(
            "INTERRUPTED_BUDGET_UNESTIMABLE",
            None,
            None,
            len(unique),
            len(families),
            None,
            "requires at least three unique successful pairs spanning at least two event families",
        )
    q95 = nearest_rank_quantile(unique.values(), 0.95)
    allowance = min(
        EVENT_ALLOWANCE_BOUNDS[1],
        max(EVENT_ALLOWANCE_BOUNDS[0], math.ceil(1.20 * q95)),
    )
    horizon = min(INTERRUPTED_HORIZON_CAP, clean + count * allowance)
    return InterruptedBudgetDecision(
        "INTERRUPTED_BUDGET_ESTIMATED",
        horizon,
        allowance,
        len(unique),
        len(families),
        q95,
        "min(1040, H_clean(task) + K * clip(ceil(1.20 * Q95(overhead)), 32, 130))",
    )


validate_initial_state_split()
