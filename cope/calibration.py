from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
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


def load_resume_trace(
    path: str | Path,
    *,
    expected_warmup_steps: int,
    policy_step_budget: int,
) -> dict[str, Any]:
    trace_path = Path(path)
    records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    warmup = [row for row in records if row.get("record_type") == "warmup"]
    policy = [row for row in records if row.get("record_type") == "policy_step"]
    unexpected = [
        row
        for row in records
        if row.get("record_type") not in {"resume_replay", "warmup", "policy_step"}
    ]
    if unexpected:
        raise ValueError(f"resume trace contains unexpected record types: {trace_path}")
    if [int(row.get("warmup_step", -1)) for row in warmup] != list(
        range(expected_warmup_steps)
    ):
        raise ValueError("resume trace warmup steps are incomplete or non-contiguous")
    policy_steps = [int(row.get("policy_step", -1)) for row in policy]
    if policy_steps != list(range(len(policy))):
        raise ValueError("resume trace policy steps are incomplete or non-contiguous")
    if len(policy) >= policy_step_budget:
        raise ValueError("resume trace already consumed the complete policy budget")
    for row in policy:
        validation = row.get("action_validation") or {}
        if validation.get("passed") is not True:
            raise ValueError("resume trace contains an invalid action")
        if bool(row.get("done")) or float(row.get("reward", 0.0)) >= 1.0:
            raise ValueError("resume trace already reached a terminal success")
        action = row.get("environment_action")
        if not isinstance(action, list) or not action:
            raise ValueError("resume trace policy record lacks environment_action")
    return {
        "path": str(trace_path.resolve()),
        "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "warmup_records": warmup,
        "policy_records": policy,
        "policy_steps": len(policy),
    }


def partition_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    worker_id: int,
    worker_count: int,
) -> tuple[Mapping[str, Any], ...]:
    if worker_count <= 0 or worker_id < 0 or worker_id >= worker_count:
        raise ValueError("invalid worker partition")
    return tuple(
        entry for index, entry in enumerate(entries) if index % worker_count == worker_id
    )


def atomic_episode_claim(
    claim_path: str | Path,
    *,
    episode_id: str,
    worker_id: int,
    worker_count: int,
    config_hash: str,
    launcher_id: str,
    resume: bool,
) -> dict[str, Any]:
    path = Path(claim_path)
    expected = {
        "schema_version": "openvla-libero-calibration-claim-v1",
        "episode_id": episode_id,
        "worker_id": int(worker_id),
        "worker_count": int(worker_count),
        "config_hash": config_hash,
        "launcher_id": launcher_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".claim", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o644)
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            pass
        else:
            return {
                **expected,
                "claim_reused_for_resume": False,
                "path": str(path),
            }
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        identity_fields = (
            "schema_version",
            "episode_id",
            "worker_id",
            "worker_count",
            "config_hash",
        )
        if any(existing.get(field) != expected[field] for field in identity_fields):
            raise ValueError(f"existing claim identity mismatch: {path}")
        if not resume:
            raise FileExistsError(f"episode is already claimed: {episode_id}")
        return {**existing, "claim_reused_for_resume": True, "path": str(path)}
    raise RuntimeError(f"atomic claim publication failed without a winner: {path}")


def audit_terminal_records(
    *,
    entries: Sequence[Mapping[str, Any]],
    episode_roots: Sequence[str | Path],
    config_hash: str,
    checkpoint_revision: str,
) -> dict[str, Any]:
    expected = {str(entry["episode_id"]): dict(entry) for entry in entries}
    records_by_id: dict[str, list[dict[str, Any]]] = {}
    for root_value in episode_roots:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in root.rglob("episode.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            episode_id = str(record.get("episode_id", ""))
            record["_terminal_path"] = str(path.resolve())
            records_by_id.setdefault(episode_id, []).append(record)
    errors: list[str] = []
    unexpected = sorted(set(records_by_id) - set(expected))
    missing = sorted(set(expected) - set(records_by_id))
    duplicates = sorted(
        episode_id for episode_id, rows in records_by_id.items() if len(rows) != 1
    )
    if unexpected:
        errors.append(f"unexpected terminal episode IDs: {unexpected}")
    if missing:
        errors.append(f"missing terminal episode IDs: {missing}")
    if duplicates:
        errors.append(f"duplicate terminal episode IDs: {duplicates}")
    terminals: list[dict[str, Any]] = []
    for episode_id in sorted(set(expected) & set(records_by_id)):
        rows = records_by_id[episode_id]
        if len(rows) != 1:
            continue
        row = rows[0]
        entry = expected[episode_id]
        if row.get("complete") is not True or row.get("phase") != "calibration":
            errors.append(f"{episode_id}: record is not a complete calibration terminal")
        if row.get("config_hash") != config_hash:
            errors.append(f"{episode_id}: config_hash mismatch")
        if (row.get("checkpoint") or {}).get("revision") != checkpoint_revision:
            errors.append(f"{episode_id}: checkpoint revision mismatch")
        for field in ("task_id", "initial_state_id", "seed"):
            if int(row.get(field, -1)) != int(entry[field]):
                errors.append(f"{episode_id}: fixed {field} mismatch")
        terminals.append(row)
    return {
        "passed": not errors,
        "errors": errors,
        "expected_count": len(expected),
        "terminal_count": len(terminals),
        "missing_episode_ids": missing,
        "duplicate_episode_ids": duplicates,
        "unexpected_episode_ids": unexpected,
        "terminals": terminals,
    }
