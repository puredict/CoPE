#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cope.calibration import (  # noqa: E402
    CalibrationSeedScheme,
    atomic_episode_claim,
    audit_terminal_records,
    build_calibration_entries,
    canonical_hash,
    load_resume_trace,
    partition_entries,
)
from experiments.openvla_libero_calibration import (  # noqa: E402
    _atomic_json,
    _checkpoint_identity,
    _exclusive_json,
    _git_identity,
    _load_yaml,
    _model_cfg,
    _run_clean_episode,
    _summarize_calibration,
)
from libero_experiment_core import load_model_and_processor  # noqa: E402


WORKER_COUNT = 8


def _entries(config: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    scheme = CalibrationSeedScheme.from_mapping(config["seed_scheme"])
    return tuple(
        dict(entry)
        for entry in build_calibration_entries(
            task_ids=config["task_ids"],
            state_ids=config["initial_state_ids"],
            seed_scheme=scheme,
        )
    )


def _episode_roots(parallel_root: Path, original_root: Path) -> list[Path]:
    return [original_root / "episodes"] + [
        parallel_root / "workers" / f"gpu{worker_id}" / "episodes"
        for worker_id in range(WORKER_COUNT)
    ]


def _partial_trace(episode_dir: Path) -> Path | None:
    attempts = sorted(episode_dir.glob("attempt-*.jsonl"))
    return attempts[-1] if attempts else None


def _validate_smoke(
    smoke_report: Path, *, config_hash: str, checkpoint_revision: str
) -> dict[str, Any]:
    smoke = json.loads(smoke_report.read_text(encoding="utf-8"))
    if smoke.get("passed") is not True:
        raise ValueError("parallel calibration requires a passed smoke report")
    if smoke.get("config_hash") != config_hash:
        raise ValueError("smoke/config hash mismatch")
    if (smoke.get("checkpoint") or {}).get("revision") != checkpoint_revision:
        raise ValueError("smoke/checkpoint revision mismatch")
    return smoke


def prepare(
    *,
    config_path: Path,
    smoke_report: Path,
    original_root: Path,
    parallel_root: Path,
    resume: bool,
) -> dict[str, Any]:
    config = _load_yaml(config_path)
    config_hash = canonical_hash(config)
    git = _git_identity()
    if not git["clean"]:
        raise RuntimeError(f"parallel scheduler requires a clean worktree:\n{git['status']}")
    checkpoint = _checkpoint_identity(config)
    smoke = _validate_smoke(
        smoke_report,
        config_hash=config_hash,
        checkpoint_revision=str(checkpoint["revision"]),
    )
    original_manifest_path = original_root / "run_manifest.json"
    original_manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    if original_manifest.get("phase") != "calibration":
        raise ValueError("original run manifest is not calibration")
    if original_manifest.get("config_hash") != config_hash:
        raise ValueError("original run/config hash mismatch")
    entries = _entries(config)
    original_audit = audit_terminal_records(
        entries=entries,
        episode_roots=[original_root / "episodes"],
        config_hash=config_hash,
        checkpoint_revision=str(checkpoint["revision"]),
    )
    if (
        original_audit["duplicate_episode_ids"]
        or original_audit["unexpected_episode_ids"]
        or any(
            "config_hash mismatch" in error
            or "checkpoint revision mismatch" in error
            or "fixed " in error
            for error in original_audit["errors"]
        )
    ):
        raise ValueError(f"invalid original calibration terminals: {original_audit['errors']}")
    original_terminal_ids = sorted(
        str(record["episode_id"]) for record in original_audit["terminals"]
    )
    resume_traces: dict[str, dict[str, Any]] = {}
    for entry in entries:
        episode_id = str(entry["episode_id"])
        if episode_id in original_terminal_ids:
            continue
        partial = _partial_trace(original_root / "episodes" / episode_id)
        if partial is None:
            continue
        trace = load_resume_trace(
            partial,
            expected_warmup_steps=int(config["runtime"]["warmup_simulator_steps"]),
            policy_step_budget=int(config["runtime"]["policy_step_budget"]),
        )
        resume_traces[episode_id] = {
            "path": trace["path"],
            "sha256": trace["sha256"],
            "policy_steps": trace["policy_steps"],
            "resume_mode": "deterministic_action_replay_without_model_reinference",
        }
    manifest_path = parallel_root / "parallel_manifest.json"
    launcher_id = "calibration-parallel-" + canonical_hash(
        {
            "config_hash": config_hash,
            "git_commit": git["commit"],
            "original_manifest": str(original_manifest_path.resolve()),
            "worker_count": WORKER_COUNT,
        }
    )[:16]
    manifest = {
        "schema_version": "openvla-libero-calibration-parallel-v1",
        "launcher_id": launcher_id,
        "worker_count": WORKER_COUNT,
        "config_path": str(config_path.resolve()),
        "config_hash": config_hash,
        "smoke_report": str(smoke_report.resolve()),
        "smoke_report_sha256": canonical_hash(smoke),
        "original_root": str(original_root.resolve()),
        "original_manifest": str(original_manifest_path.resolve()),
        "original_terminal_episode_ids": original_terminal_ids,
        "resume_traces": resume_traces,
        "entries": list(entries),
        "checkpoint": checkpoint,
        "git": git,
        "partition": {
            str(worker_id): [
                str(entry["episode_id"])
                for entry in partition_entries(
                    entries,
                    worker_id=worker_id,
                    worker_count=WORKER_COUNT,
                )
            ]
            for worker_id in range(WORKER_COUNT)
        },
        "invariants": {
            "fixed_checkpoint": True,
            "fixed_task_state_seed_entries": True,
            "policy_step_budget": int(config["runtime"]["policy_step_budget"]),
            "success_predicate": config["runtime"]["success_predicate"],
            "atomic_o_excl_claim": True,
            "independent_worker_output_directories": True,
            "one_model_per_worker": True,
            "shared_model_server": False,
            "terminal_episode_json_atomic": True,
        },
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if manifest_path.exists():
        if not resume:
            raise FileExistsError(f"parallel manifest already exists: {manifest_path}")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = (
            "schema_version",
            "launcher_id",
            "worker_count",
            "config_hash",
            "original_manifest",
            "entries",
            "checkpoint",
            "partition",
        )
        if any(existing.get(field) != manifest[field] for field in identity):
            raise ValueError("parallel manifest identity mismatch on resume")
        return existing
    parallel_root.mkdir(parents=True, exist_ok=False)
    for child in ("claims", "completions", "workers", "logs"):
        (parallel_root / child).mkdir()
    _exclusive_json(manifest_path, manifest)
    return manifest


def _verify_checkpoint_sizes(checkpoint: Mapping[str, Any]) -> None:
    root = Path(str(checkpoint["path"]))
    for shard in checkpoint["weight_shards"]:
        path = root / str(shard["name"])
        if not path.is_file() or path.stat().st_size != int(shard["bytes"]):
            raise ValueError(f"worker checkpoint shard mismatch: {path}")


def worker(
    *,
    parallel_root: Path,
    worker_id: int,
    resume: bool,
) -> dict[str, Any]:
    manifest = json.loads(
        (parallel_root / "parallel_manifest.json").read_text(encoding="utf-8")
    )
    if int(manifest["worker_count"]) != WORKER_COUNT:
        raise ValueError("parallel worker_count mismatch")
    if worker_id < 0 or worker_id >= WORKER_COUNT:
        raise ValueError("invalid worker_id")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible or "," in visible:
        raise RuntimeError("each worker requires exactly one CUDA_VISIBLE_DEVICES entry")
    config_path = Path(str(manifest["config_path"]))
    config = _load_yaml(config_path)
    config_hash = canonical_hash(config)
    if config_hash != manifest["config_hash"]:
        raise ValueError("worker config hash mismatch")
    checkpoint = dict(manifest["checkpoint"])
    _verify_checkpoint_sizes(checkpoint)
    entries = tuple(dict(entry) for entry in manifest["entries"])
    assigned = partition_entries(
        entries,
        worker_id=worker_id,
        worker_count=WORKER_COUNT,
    )
    original_root = Path(str(manifest["original_root"]))
    worker_root = parallel_root / "workers" / f"gpu{worker_id}"
    worker_root.mkdir(parents=True, exist_ok=True)
    initial_audit = audit_terminal_records(
        entries=entries,
        episode_roots=_episode_roots(parallel_root, original_root),
        config_hash=config_hash,
        checkpoint_revision=str(checkpoint["revision"]),
    )
    terminal_ids = {str(record["episode_id"]) for record in initial_audit["terminals"]}
    pending = [entry for entry in assigned if str(entry["episode_id"]) not in terminal_ids]
    processed: list[str] = []
    if not pending:
        result = {
            "worker_id": worker_id,
            "physical_gpu": visible,
            "model_load_count": 0,
            "processed_episode_ids": [],
            "complete": True,
        }
        _atomic_json(worker_root / "worker_summary.json", result)
        return result
    loader_entry = pending[0]
    loader_cfg = _model_cfg(
        config,
        task_id=int(loader_entry["task_id"]),
        state_id=int(loader_entry["initial_state_id"]),
        seed=int(loader_entry["seed"]),
    )
    load_started = time.monotonic()
    model, processor, runtime_model_cfg, resolved_unnorm_key = load_model_and_processor(
        loader_cfg
    )
    model_load_seconds = time.monotonic() - load_started
    for entry in pending:
        episode_id = str(entry["episode_id"])
        current_audit = audit_terminal_records(
            entries=entries,
            episode_roots=_episode_roots(parallel_root, original_root),
            config_hash=config_hash,
            checkpoint_revision=str(checkpoint["revision"]),
        )
        matches = [
            record
            for record in current_audit["terminals"]
            if str(record["episode_id"]) == episode_id
        ]
        if matches:
            continue
        claim = atomic_episode_claim(
            parallel_root / "claims" / f"{episode_id}.json",
            episode_id=episode_id,
            worker_id=worker_id,
            worker_count=WORKER_COUNT,
            config_hash=config_hash,
            launcher_id=str(manifest["launcher_id"]),
            resume=resume,
        )
        local_partial = _partial_trace(worker_root / "episodes" / episode_id)
        source = local_partial
        if source is None:
            registered = (manifest.get("resume_traces") or {}).get(episode_id)
            source = Path(str(registered["path"])) if registered else None
        record = _run_clean_episode(
            entry=entry,
            config=config,
            config_hash=config_hash,
            output_dir=worker_root,
            model=model,
            processor=processor,
            runtime_model_cfg=runtime_model_cfg,
            resolved_unnorm_key=resolved_unnorm_key,
            checkpoint_identity=checkpoint,
            resume_trace_path=source,
        )
        completion = {
            "schema_version": "openvla-libero-calibration-completion-v1",
            "episode_id": episode_id,
            "worker_id": worker_id,
            "physical_gpu": visible,
            "claim": claim,
            "terminal_path": record["artifacts"]["episode"],
            "success": record["success"],
            "termination_reason": record["termination_reason"],
        }
        completion_path = parallel_root / "completions" / f"{episode_id}.json"
        if completion_path.exists():
            existing = json.loads(completion_path.read_text(encoding="utf-8"))
            if existing != completion:
                raise ValueError(f"completion identity mismatch: {episode_id}")
        else:
            _exclusive_json(completion_path, completion)
        processed.append(episode_id)
        print(
            json.dumps(
                {
                    "worker_id": worker_id,
                    "physical_gpu": visible,
                    "episode_id": episode_id,
                    "success": record["success"],
                    "termination_reason": record["termination_reason"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
    result = {
        "worker_id": worker_id,
        "physical_gpu": visible,
        "model_load_count": 1,
        "model_load_seconds": model_load_seconds,
        "processor_loader": getattr(runtime_model_cfg, "processor_loader", "unrecorded"),
        "processed_episode_ids": processed,
        "complete": True,
    }
    _atomic_json(worker_root / "worker_summary.json", result)
    return result


def audit(*, parallel_root: Path) -> dict[str, Any]:
    manifest = json.loads(
        (parallel_root / "parallel_manifest.json").read_text(encoding="utf-8")
    )
    config = _load_yaml(Path(str(manifest["config_path"])))
    config_hash = canonical_hash(config)
    entries = tuple(dict(entry) for entry in manifest["entries"])
    original_root = Path(str(manifest["original_root"]))
    terminal_audit = audit_terminal_records(
        entries=entries,
        episode_roots=_episode_roots(parallel_root, original_root),
        config_hash=config_hash,
        checkpoint_revision=str(manifest["checkpoint"]["revision"]),
    )
    original_ids = set(manifest["original_terminal_episode_ids"])
    claim_errors: list[str] = []
    claims: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        episode_id = str(entry["episode_id"])
        claim_path = parallel_root / "claims" / f"{episode_id}.json"
        if episode_id in original_ids:
            if claim_path.exists():
                claim_errors.append(f"{episode_id}: original terminal must not be claimed")
            continue
        if not claim_path.is_file():
            claim_errors.append(f"{episode_id}: missing atomic claim")
            continue
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        expected_worker = index % WORKER_COUNT
        if int(claim.get("worker_id", -1)) != expected_worker:
            claim_errors.append(f"{episode_id}: worker partition mismatch")
        if claim.get("config_hash") != config_hash:
            claim_errors.append(f"{episode_id}: claim config hash mismatch")
        claims.append(claim)
    worker_errors: list[str] = []
    for worker_id in range(WORKER_COUNT):
        summary_path = (
            parallel_root / "workers" / f"gpu{worker_id}" / "worker_summary.json"
        )
        if not summary_path.is_file():
            worker_errors.append(f"gpu{worker_id}: missing worker summary")
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("complete") is not True:
            worker_errors.append(f"gpu{worker_id}: worker incomplete")
        if int(summary.get("model_load_count", -1)) != 1:
            worker_errors.append(f"gpu{worker_id}: expected exactly one model load")
        if str(summary.get("physical_gpu")) != str(worker_id):
            worker_errors.append(f"gpu{worker_id}: CUDA mapping mismatch")
    resume_errors: list[str] = []
    terminals = terminal_audit["terminals"]
    by_id = {str(record["episode_id"]): record for record in terminals}
    for episode_id, resume in (manifest.get("resume_traces") or {}).items():
        terminal = by_id.get(str(episode_id))
        if terminal is None:
            resume_errors.append(f"{episode_id}: resumed episode has no terminal")
            continue
        record_resume = terminal.get("resume") or {}
        if (
            terminal.get("resumed_from_interrupted_trace") is not True
            or record_resume.get("source_trace_sha256") != resume["sha256"]
            or record_resume.get("model_inference_replayed") is not False
        ):
            resume_errors.append(f"{episode_id}: resume provenance mismatch")
    summary = _summarize_calibration(terminals, config)
    errors = (
        list(terminal_audit["errors"])
        + claim_errors
        + worker_errors
        + resume_errors
    )
    result = {
        **summary,
        "schema_version": "openvla-libero-clean-calibration-parallel-summary-v1",
        "passed": not errors and summary["complete"],
        "errors": errors,
        "terminal_audit": {
            key: value for key, value in terminal_audit.items() if key != "terminals"
        },
        "atomic_claim_count": len(claims),
        "original_terminal_count": len(original_ids),
        "worker_count": WORKER_COUNT,
        "independent_worker_output_directories": [
            str(
                (
                    parallel_root / "workers" / f"gpu{worker_id}" / "episodes"
                ).resolve()
            )
            for worker_id in range(WORKER_COUNT)
        ],
        "terminal_paths": {
            str(record["episode_id"]): record["_terminal_path"] for record in terminals
        },
        "parallel_manifest": str(
            (parallel_root / "parallel_manifest.json").resolve()
        ),
    }
    _atomic_json(parallel_root / "calibration_summary_parallel.json", result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "worker", "audit"), required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/openvla_libero_10_calibration_v1.yaml"),
    )
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--parallel-root", type=Path, required=True)
    parser.add_argument("--worker-id", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    parallel_root = args.parallel_root.resolve()
    if args.mode == "prepare":
        if args.smoke_report is None or args.original_root is None:
            raise ValueError("prepare requires --smoke-report and --original-root")
        config_path = args.config if args.config.is_absolute() else ROOT / args.config
        result = prepare(
            config_path=config_path.resolve(),
            smoke_report=args.smoke_report.resolve(),
            original_root=args.original_root.resolve(),
            parallel_root=parallel_root,
            resume=args.resume,
        )
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return 0
    if args.mode == "worker":
        if args.worker_id is None:
            raise ValueError("worker requires --worker-id")
        result = worker(
            parallel_root=parallel_root,
            worker_id=args.worker_id,
            resume=args.resume,
        )
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return 0
    result = audit(parallel_root=parallel_root)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
