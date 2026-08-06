from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from cope.calibration import (
    CalibrationSeedScheme,
    audit_terminal_records,
    canonical_hash,
    wilson_interval,
)


PROTOCOL_LABEL = "standard_libero10_clean_calibration_horizon_520"
V1_PROTOCOL_LABEL = "nonstandard_truncated_calibration_horizon_220"
TASK_IDS = (1, 5, 7)
STATE_IDS = (0, 1, 2, 3, 4)
WORKER_COUNT = 8


def load_v2_config(path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for calibration v2") from exc
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("calibration v2 config root must be a mapping")
    validate_config_contract(value)
    return value


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path: str | Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def directory_inventory(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    records: list[dict[str, Any]] = []
    aggregate_lines: list[str] = []
    for path in sorted(item for item in base.rglob("*") if item.is_file()):
        relative = path.relative_to(base).as_posix()
        digest = sha256_file(path)
        records.append(
            {
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate_lines.append(f"{digest}  ./{relative}\n")
    aggregate = hashlib.sha256("".join(aggregate_lines).encode("utf-8")).hexdigest()
    return {
        "root": str(base),
        "file_count": len(records),
        "total_bytes": sum(int(record["bytes"]) for record in records),
        "inventory_sha256": aggregate,
        "files": records,
    }


def validate_v1_integrity(config: Mapping[str, Any]) -> dict[str, Any]:
    protected = config["v1_protection"]
    if protected.get("protocol_label") != V1_PROTOCOL_LABEL:
        raise ValueError("v1 protocol label must mark the 220-step run as nonstandard")
    inventory = directory_inventory(str(protected["path"]))
    if int(protected["file_count"]) != inventory["file_count"]:
        raise ValueError("protected v1 file count changed")
    if protected["inventory_sha256"] != inventory["inventory_sha256"]:
        raise ValueError("protected v1 inventory hash changed")
    parallel_inventory = directory_inventory(str(protected["parallel_path"]))
    if int(protected["parallel_file_count"]) != parallel_inventory["file_count"]:
        raise ValueError("protected parallel v1 file count changed")
    if (
        protected["parallel_inventory_sha256"]
        != parallel_inventory["inventory_sha256"]
    ):
        raise ValueError("protected parallel v1 inventory hash changed")
    return {"sequential": inventory, "parallel": parallel_inventory}


def validate_config_contract(config: Mapping[str, Any]) -> None:
    runtime = config["runtime"]
    checkpoint = config["checkpoint"]
    if config.get("schema_version") != "openvla-libero-calibration-v2":
        raise ValueError("unexpected calibration v2 schema")
    if config.get("protocol_label") != PROTOCOL_LABEL:
        raise ValueError("unexpected calibration v2 protocol label")
    if config.get("task_suite_name") != "libero_10":
        raise ValueError("task_suite_name must be libero_10")
    if config.get("task_suite") != config.get("task_suite_name"):
        raise ValueError("task_suite aliases disagree")
    if tuple(int(item) for item in config.get("task_ids", ())) != TASK_IDS:
        raise ValueError("calibration v2 task IDs must remain [1, 5, 7]")
    if tuple(int(item) for item in config.get("initial_state_ids", ())) != STATE_IDS:
        raise ValueError("calibration v2 state IDs must remain [0, 1, 2, 3, 4]")
    if int(runtime.get("warmup_simulator_steps", -1)) != 10:
        raise ValueError("LIBERO-10 calibration requires exactly 10 warmup steps")
    if int(runtime.get("policy_step_budget", -1)) != 520:
        raise ValueError("LIBERO-10 calibration requires exactly 520 policy steps")
    if int(runtime.get("total_environment_step_budget", -1)) != 530:
        raise ValueError("total environment budget must be 520 + 10")
    if runtime.get("center_crop") is not True:
        raise ValueError("official OpenVLA LIBERO evaluation requires center_crop=True")
    if runtime.get("success_predicate") != "libero_done_or_sparse_reward_ge_1":
        raise ValueError("success predicate changed")
    if runtime.get("gripper_transform") != "normalize_binarize_then_openvla_invert":
        raise ValueError("gripper transform changed")
    if runtime.get("model_consumes_proprio") is not False:
        raise ValueError("OpenVLA must remain image-language only")
    if int(runtime.get("adapter_state_dim", -1)) != 8:
        raise ValueError("adapter state contract changed")
    if runtime.get("shared_inference_server") is not False:
        raise ValueError("shared inference servers are forbidden")
    if checkpoint.get("repository") != "openvla/openvla-7b-finetuned-libero-10":
        raise ValueError("wrong checkpoint repository")
    if (
        checkpoint.get("revision")
        != "80970322773f81baa2e22fe495d0487b93a05cfa"
    ):
        raise ValueError("wrong checkpoint revision")
    if (
        checkpoint.get("files_manifest_sha256")
        != "58773a8ef85515f695c99402f692dc5afe0fb71efd7f3984ff44c1f117c4f034"
    ):
        raise ValueError("wrong checkpoint file manifest hash")
    if checkpoint.get("processor_loader") != "local_upstream_prismatic_processor_v1":
        raise ValueError("wrong processor loader contract")
    if checkpoint.get("unnorm_key") != "libero_10":
        raise ValueError("wrong OpenVLA unnorm key")
    if checkpoint.get("model_consumes_proprio") is not False:
        raise ValueError("checkpoint proprio contract changed")
    task_identity = config["libero_runtime"]["task_identity"]
    if tuple(sorted(int(key) for key in task_identity)) != TASK_IDS:
        raise ValueError("runtime task identity keys changed")


def build_v2_entries(config: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    validate_config_contract(config)
    scheme = CalibrationSeedScheme.from_mapping(config["seed_scheme"])
    identities = config["libero_runtime"]["task_identity"]
    entries: list[dict[str, Any]] = []
    seeds: set[int] = set()
    for task_ordinal, task_id in enumerate(TASK_IDS):
        identity = identities[str(task_id)]
        for state_id in STATE_IDS:
            seed = scheme.derive(task_ordinal=task_ordinal, state_id=state_id)
            if seed in seeds:
                raise ValueError(f"duplicate calibration v2 seed {seed}")
            seeds.add(seed)
            entries.append(
                {
                    "episode_id": (
                        f"calibration_v2__task{task_id:02d}"
                        f"__state{state_id:02d}__seed{seed}"
                    ),
                    "protocol_label": PROTOCOL_LABEL,
                    "task_id": task_id,
                    "task_name": identity["task_name"],
                    "description": identity["description"],
                    "bddl_file": identity["bddl_file"],
                    "bddl_sha256": identity["bddl_sha256"],
                    "initial_state_id": state_id,
                    "initial_state_sha256": identity["state_sha256"][str(state_id)],
                    "seed": seed,
                }
            )
    if len(entries) != 15:
        raise ValueError("calibration v2 must contain exactly 15 entries")
    return tuple(entries)


def validate_static_manifest(
    config: Mapping[str, Any], manifest_path: str | Path
) -> tuple[dict[str, Any], ...]:
    expected = build_v2_entries(config)
    actual = read_jsonl(manifest_path)
    if actual != expected:
        raise ValueError("versioned calibration v2 manifest does not match deterministic rebuild")
    if len({str(entry["episode_id"]) for entry in actual}) != 15:
        raise ValueError("calibration v2 manifest IDs are not unique")
    return actual


def ensure_output_separation(
    *, v1_root: str | Path, v2_root: str | Path
) -> tuple[Path, Path]:
    protected = Path(v1_root).resolve()
    output = Path(v2_root).resolve()
    if output == protected or protected in output.parents or output in protected.parents:
        raise ValueError("v2 output must be independent from protected v1 output")
    return protected, output


def _git_commit(path: str | Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def validate_runtime_task_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs.bddl_utils import robosuite_parse_problem

    expected_runtime = config["libero_runtime"]
    actual_version = importlib.metadata.version("libero")
    if actual_version != str(expected_runtime["package_version"]):
        raise ValueError("LIBERO package version mismatch")
    source_commit = _git_commit(str(expected_runtime["source_path"]))
    if source_commit != str(expected_runtime["source_commit"]):
        raise ValueError("LIBERO source commit mismatch")
    suite = benchmark.get_benchmark_dict()["libero_10"]()
    observed: dict[str, Any] = {
        "package_version": actual_version,
        "source_commit": source_commit,
        "suite_class": f"{type(suite).__module__}.{type(suite).__qualname__}",
        "suite_task_count": int(suite.n_tasks),
        "task_identity": {},
    }
    for task_id in TASK_IDS:
        task = suite.get_task(task_id)
        bddl_path = Path(suite.get_task_bddl_file_path(task_id)).resolve()
        parsed = robosuite_parse_problem(str(bddl_path))
        init_path = (
            Path(get_libero_path("init_states"))
            / task.problem_folder
            / task.init_states_file
        ).resolve()
        states = np.asarray(suite.get_task_init_states(task_id))
        actual = {
            "description": task.language,
            "task_name": task.name,
            "problem": task.problem,
            "problem_folder": task.problem_folder,
            "bddl_file": task.bddl_file,
            "bddl_path": str(bddl_path),
            "bddl_sha256": sha256_file(bddl_path),
            "bddl_bytes": bddl_path.stat().st_size,
            "fixtures": _json_safe(parsed["fixtures"]),
            "objects": _json_safe(parsed["objects"]),
            "obj_of_interest": _json_safe(parsed["obj_of_interest"]),
            "goal_state": _json_safe(parsed["goal_state"]),
            "init_states_file": task.init_states_file,
            "init_states_path": str(init_path),
            "init_states_file_sha256": sha256_file(init_path),
            "initial_state_array_shape": list(states.shape),
            "state_sha256": {
                str(state_id): hashlib.sha256(states[state_id].tobytes()).hexdigest()
                for state_id in STATE_IDS
            },
        }
        expected = expected_runtime["task_identity"][str(task_id)]
        compared_fields = (
            "description",
            "task_name",
            "problem",
            "problem_folder",
            "bddl_file",
            "bddl_sha256",
            "fixtures",
            "objects",
            "obj_of_interest",
            "goal_state",
            "init_states_file",
            "init_states_file_sha256",
            "state_sha256",
        )
        mismatches = [
            field
            for field in compared_fields
            if _json_safe(actual[field]) != _json_safe(expected[field])
        ]
        if mismatches:
            raise ValueError(
                f"runtime task identity mismatch for task {task_id}: {mismatches}"
            )
        observed["task_identity"][str(task_id)] = actual
    return observed


def validate_runtime_files(config: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = config["checkpoint"]
    checkpoint_root = Path(str(checkpoint["path"]))
    for name, digest in checkpoint["tokenizer_files"].items():
        path = checkpoint_root / str(name)
        if sha256_file(path) != str(digest):
            raise ValueError(f"checkpoint processor/tokenizer hash mismatch: {path}")
    for name, expected in checkpoint["weight_shards"].items():
        path = checkpoint_root / str(name)
        if path.stat().st_size != int(expected["bytes"]):
            raise ValueError(f"checkpoint shard size mismatch: {path}")
        if sha256_file(path) != str(expected["sha256"]):
            raise ValueError(f"checkpoint shard hash mismatch: {path}")
    official = config["official_protocol"]
    runner = Path(str(official["runner_path"]))
    if sha256_file(runner) != str(official["runner_worktree_sha256"]):
        raise ValueError("OpenVLA runner worktree hash mismatch")
    openvla_root = Path("/home/lijingsu/vla/src/openvla")
    if _git_commit(openvla_root) != str(official["checked_out_commit"]):
        raise ValueError("OpenVLA source commit mismatch")
    tracked_blob = subprocess.check_output(
        [
            "git",
            "-C",
            str(openvla_root),
            "ls-tree",
            "HEAD",
            "experiments/robot/libero/run_libero_eval.py",
        ],
        text=True,
    ).split()[2]
    if tracked_blob != str(official["runner_tracked_blob"]):
        raise ValueError("OpenVLA official runner tracked blob mismatch")
    paths = {
        "openvla_utils_sha256": openvla_root / "experiments/robot/openvla_utils.py",
        "robot_utils_sha256": openvla_root / "experiments/robot/robot_utils.py",
        "libero_utils_sha256": (
            openvla_root / "experiments/robot/libero/libero_utils.py"
        ),
    }
    for field, path in paths.items():
        if sha256_file(path) != str(official[field]):
            raise ValueError(f"OpenVLA runtime file hash mismatch: {path}")
    return {
        "checkpoint_path": str(checkpoint_root.resolve()),
        "checkpoint_revision": checkpoint["revision"],
        "processor_loader": checkpoint["processor_loader"],
        "tokenizer_files": dict(checkpoint["tokenizer_files"]),
        "official_protocol": dict(official),
        "runner_tracked_blob_observed": tracked_blob,
    }


def infrastructure_attempts(parallel_root: str | Path) -> list[dict[str, Any]]:
    root = Path(parallel_root)
    attempts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("attempt-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("attempt_status") == "infrastructure_failure":
            attempts.append({**record, "_attempt_path": str(path.resolve())})
    return attempts


def load_v2_resume_trace(
    path: str | Path, *, warmup_steps: int = 10, policy_step_budget: int = 520
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
        raise ValueError("resume trace contains unexpected record types")
    if [int(row.get("warmup_step", -1)) for row in warmup] != list(
        range(warmup_steps)
    ):
        raise ValueError("resume trace warmup steps are incomplete or non-contiguous")
    if [int(row.get("policy_step", -1)) for row in policy] != list(
        range(len(policy))
    ):
        raise ValueError("resume trace policy steps are incomplete or non-contiguous")
    if len(policy) > policy_step_budget:
        raise ValueError("resume trace exceeds the policy step budget")
    success_indices: list[int] = []
    for index, row in enumerate(policy):
        if (row.get("action_validation") or {}).get("passed") is not True:
            raise ValueError("resume trace contains an invalid action")
        action = row.get("environment_action")
        if not isinstance(action, list) or not action:
            raise ValueError("resume trace lacks an environment action")
        if bool(row.get("done")) or float(row.get("reward", 0.0)) >= 1.0:
            success_indices.append(index)
    if success_indices and success_indices != [len(policy) - 1]:
        raise ValueError("resume trace continued after a terminal success")
    return {
        "path": str(trace_path.resolve()),
        "sha256": sha256_file(trace_path),
        "warmup_records": warmup,
        "policy_records": policy,
        "policy_steps": len(policy),
        "terminal_success_recorded": bool(success_indices),
    }


def audit_v2_terminals(
    *,
    config: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    episode_roots: Sequence[str | Path],
    config_hash: str,
) -> dict[str, Any]:
    checkpoint_revision = str(config["checkpoint"]["revision"])
    base = audit_terminal_records(
        entries=entries,
        episode_roots=episode_roots,
        config_hash=config_hash,
        checkpoint_revision=checkpoint_revision,
    )
    expected = {str(entry["episode_id"]): entry for entry in entries}
    errors = list(base["errors"])
    for terminal in base["terminals"]:
        episode_id = str(terminal["episode_id"])
        entry = expected[episode_id]
        if terminal.get("schema_version") != "openvla-libero-clean-calibration-v2-episode":
            errors.append(f"{episode_id}: wrong terminal schema")
        if terminal.get("protocol_label") != PROTOCOL_LABEL:
            errors.append(f"{episode_id}: protocol label mismatch")
        if terminal.get("valid_experimental_terminal") is not True:
            errors.append(f"{episode_id}: invalid experimental terminal")
        if terminal.get("infrastructure_failure") is not False:
            errors.append(f"{episode_id}: infrastructure failure presented as terminal")
        for field in (
            "task_name",
            "description",
            "bddl_file",
            "bddl_sha256",
            "initial_state_sha256",
        ):
            if terminal.get(field) != entry[field]:
                errors.append(f"{episode_id}: fixed {field} mismatch")
        policy_steps = int(terminal.get("policy_steps_consumed", -1))
        warmup_steps = int(terminal.get("warmup_steps_consumed", -1))
        environment_steps = int(terminal.get("environment_steps_consumed", -1))
        if not 0 <= policy_steps <= 520:
            errors.append(f"{episode_id}: invalid policy step count")
        if warmup_steps != 10:
            errors.append(f"{episode_id}: warmup step count mismatch")
        if environment_steps != warmup_steps + policy_steps:
            errors.append(f"{episode_id}: environment step accounting mismatch")
        if environment_steps > 530:
            errors.append(f"{episode_id}: exceeded official environment budget")
        if terminal.get("termination_reason") not in {
            "libero_done",
            "libero_sparse_reward_ge_1",
            "policy_step_budget_exhausted",
            "valid_model_or_environment_failure",
        }:
            errors.append(f"{episode_id}: invalid experimental termination")
    return {**base, "passed": not errors, "errors": errors}


def summarize_v2(
    *, config: Mapping[str, Any], terminals: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    tasks: dict[str, Any] = {}
    selected: list[int] = []
    threshold = float(config["selection"]["minimum_clean_success_rate"])
    for task_id in TASK_IDS:
        rows = [row for row in terminals if int(row["task_id"]) == task_id]
        successes = sum(bool(row["success"]) for row in rows)
        total = len(rows)
        rate = successes / total if total else 0.0
        if total == 5 and rate >= threshold:
            selected.append(task_id)
        success_steps = [
            int(row["policy_steps_consumed"]) for row in rows if bool(row["success"])
        ]
        failure_steps = [
            int(row["policy_steps_consumed"]) for row in rows if not bool(row["success"])
        ]
        tasks[str(task_id)] = {
            "n": total,
            "successes": successes,
            "success_rate": rate,
            "wilson_95_ci": list(wilson_interval(successes, total)),
            "success_policy_steps": success_steps,
            "failure_policy_steps": failure_steps,
            "termination_breakdown": dict(
                sorted(Counter(str(row["termination_reason"]) for row in rows).items())
            ),
        }
    return {
        "complete": len(terminals) == 15,
        "episode_count": len(terminals),
        "expected_episode_count": 15,
        "tasks": tasks,
        "selected_task_ids": selected,
        "minimum_clean_success_rate": threshold,
        "pilot_authorized_by_calibration": bool(len(terminals) == 15 and selected),
        "calibration_excluded_from_evaluation": True,
        "protocol_label": PROTOCOL_LABEL,
    }
