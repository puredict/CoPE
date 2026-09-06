#!/usr/bin/env python3
"""Collect real R4 development call telemetry without estimating missing values.

Only completed episode result.json files are read. Warmup is determined from
the chronological serial call order, after one successful completed generation
for each method. This script never invokes a model or changes experiment data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label}: timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timezone must be explicit")
    return parsed.astimezone(timezone.utc)


def valid_count(value: Any, *, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def completed_success(generation: dict[str, Any]) -> bool:
    return (
        generation.get("ok") is True
        and generation.get("status") == "ok"
        and generation.get("request_completed") is True
        and generation.get("finish_reason") == "stop"
        and generation.get("telemetry", {}).get("received_done") is True
        and generation.get("telemetry", {}).get("generation_completed_before_client_deadline") is True
    )


def measurement_errors(generation: dict[str, Any]) -> list[str]:
    errors = []
    if not valid_count(generation.get("prompt_tokens"), minimum=1):
        errors.append("missing_or_invalid_actual_prompt_tokens")
    if not valid_count(generation.get("completion_tokens"), minimum=2):
        errors.append("missing_or_insufficient_actual_completion_tokens")
    if generation.get("observed_token_count_kind") != "server_usage_cumulative":
        errors.append("token_counts_not_confirmed_as_server_usage")
    elapsed, first = generation.get("latency_s"), generation.get("ttft_s")
    numeric = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not numeric(elapsed) or not numeric(first) or not (0 <= first < elapsed):
        errors.append("missing_or_invalid_measured_ttft_or_elapsed_time")
    return errors


def load_run(path: Path, server: dict[str, Any]) -> dict[str, Any]:
    config_path = path / "config_resolved.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    run = config.get("run", {})
    if config.get("schema_version") != "cope-fsrpc-r4-config-v1":
        raise ValueError(f"not an R4 run: {path}")
    if run.get("client") != "openai" or run.get("split") != "development":
        raise ValueError(f"only real-model development runs may calibrate throughput: {path}")
    if (config["model"]["name"] != server["model"]
            or config["model"].get("revision") != server["model_revision"]):
        raise ValueError(f"run model/revision differs from supplied server identity: {path}")
    if config["model"].get("guided_decoding_backend", "xgrammar") != server.get("guided_decoding_backend", "xgrammar"):
        raise ValueError(f"run decoding backend differs from server identity: {path}")
    registered_seeds = set(config["development_seeds"])
    if registered_seeds & set(config["test_seeds"]):
        raise ValueError(f"development/test seed overlap: {path}")
    start = utc_time(run.get("utc"), str(config_path))
    episodes = []
    for result_path in sorted(path.rglob("result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("schema_version") != "cope-fsrpc-r4-episode-v1":
            continue
        if result.get("model") != server["model"]:
            raise ValueError(f"nonregistered model result: {result_path}")
        if result.get("seed") not in registered_seeds or result.get("seed") not in run["seeds"]:
            raise ValueError(f"result seed is outside this development run: {result_path}")
        if result.get("method") not in config["methods"] or result.get("profile") not in config["profiles"]:
            raise ValueError(f"result method/profile is unregistered: {result_path}")
        calls = result.get("model_calls")
        if not isinstance(calls, list) or not calls:
            raise ValueError(f"completed result lacks model calls: {result_path}")
        ordinals = [row.get("ordinal") for row in calls]
        if any(not valid_count(value, minimum=1) for value in ordinals) or ordinals != sorted(set(ordinals)):
            raise ValueError(f"model call sequence is ambiguous: {result_path}")
        finish = utc_time(result.get("utc"), str(result_path))
        if finish < start:
            raise ValueError(f"result predates declared run start: {result_path}")
        episodes.append({"path": result_path, "result": result, "finish": finish})
    if not episodes:
        raise ValueError(f"no completed R4 result files under {path}")
    episodes.sort(key=lambda item: item["finish"])
    times = [item["finish"] for item in episodes]
    if len(set(times)) != len(times):
        raise ValueError(f"episode ordering cannot be resolved from completion UTC: {path}")
    return {
        "path": path, "config_path": config_path, "config": config,
        "start": start, "finish": times[-1], "episodes": episodes,
    }


def collect(run_paths: list[Path], identity_path: Path) -> dict[str, Any]:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    server = identity.get("server", identity)
    required = {"model", "model_revision", "tensor_parallel_size", "dtype", "enforce_eager",
                "max_model_len", "concurrency"}
    if not isinstance(server, dict) or not required <= server.keys():
        raise ValueError("server identity missing fields required by audit_r4_capacity.py")
    if server["concurrency"] != 1:
        raise ValueError("collector requires measured serial service concurrency=1")
    if len(set(run_paths)) != len(run_paths):
        raise ValueError("duplicate --run paths are not permitted")
    runs = sorted((load_run(path, server) for path in run_paths), key=lambda item: item["start"])
    for previous, current in zip(runs, runs[1:]):
        if current["start"] < previous["finish"]:
            raise ValueError("overlapping run intervals make exact serial warmup ordering ambiguous")
    warmed_by: dict[str, str] = {}
    samples = []
    request_ids = set()
    unknown_drain = None
    sources = []
    for run in runs:
        sources.append({
            "run_directory": str(run["path"]), "config_file": str(run["config_path"]),
            "config_sha256": file_hash(run["config_path"]),
            "run_start_utc": run["start"].isoformat(),
            "last_completed_episode_utc": run["finish"].isoformat(),
            "completed_episodes": len(run["episodes"]),
            "declared_context_tokens": run["config"]["model"].get("max_context_tokens"),
        })
        for episode in run["episodes"]:
            result, result_path = episode["result"], episode["path"]
            for call in result["model_calls"]:
                if unknown_drain is not None:
                    raise ValueError(f"a later call follows unconfirmed server drain after {unknown_drain}")
                method = result["method"]
                if call.get("method") != method or call.get("model") != server["model"]:
                    raise ValueError(f"call identity differs from completed result: {result_path}")
                generation = call["generation"]
                request_id = generation.get("request_id")
                if not isinstance(request_id, str) or not request_id:
                    raise ValueError(f"real call lacks request id: {result_path}")
                if request_id in request_ids:
                    raise ValueError(f"duplicate request id: {request_id}")
                request_ids.add(request_id)
                success = completed_success(generation)
                errors = measurement_errors(generation)
                status = generation.get("status", "unknown")
                if status == "ok" and not success:
                    status = "generation_completion_unconfirmed"
                elif status == "ok" and errors:
                    status = "measurement_incomplete"
                telemetry = generation.get("telemetry", {})
                if telemetry.get("guided_decoding_backend") != server.get("guided_decoding_backend", "xgrammar"):
                    raise ValueError(f"call decoding backend differs from server identity: {result_path}")
                sample = {
                    "method": method, "profile": result["profile"], "seed": result["seed"],
                    "event_ordinal": call["ordinal"], "event_id": call["event_id"],
                    "prompt_tokens": generation.get("prompt_tokens"),
                    "completion_tokens": generation.get("completion_tokens"),
                    "latency_s": generation.get("latency_s"), "ttft_s": generation.get("ttft_s"),
                    "warmed": method in warmed_by,
                    "warmup_request_id": warmed_by.get(method),
                    "status": status, "generation_status": generation.get("status"),
                    "request_completed": generation.get("request_completed"),
                    "finish_reason": generation.get("finish_reason"),
                    "request_id": request_id, "response_id": generation.get("response_id"),
                    "schema_valid": call.get("output_schema_valid"),
                    "semantic_match": call.get("semantic_match_to_registered_transition"),
                    "cancellation_status": generation.get("cancellation_status"),
                    "server_drain": telemetry.get("server_drain"),
                    "measurement_errors": errors,
                    "source_result": str(result_path), "source_result_sha256": file_hash(result_path),
                    "source_episode_finish_utc": result["utc"],
                    "chronological_call_index": len(samples),
                    "warmup_generation_completed": success,
                }
                samples.append(sample)
                if success and method not in warmed_by:
                    warmed_by[method] = request_id
                if (generation.get("cancellation_status") == "connection_closed_server_status_unknown"
                        and telemetry.get("server_drain", {}).get("confirmed_idle") is not True):
                    unknown_drain = request_id
    return {
        "schema_version": "cope-fsrpc-r4-throughput-measurements-v1",
        "utc": datetime.now(timezone.utc).isoformat(), "server": server,
        "server_identity_source": str(identity_path),
        "server_identity_sha256": file_hash(identity_path),
        "sources": sources, "samples": samples,
        "counts": {
            "completed_episodes": sum(len(run["episodes"]) for run in runs),
            "calls": len(samples),
            "warmed_successful_measurable_calls": sum(
                sample["warmed"] and sample["status"] == "ok" for sample in samples
            ),
            "retained_failed_or_unmeasurable_calls": sum(sample["status"] != "ok" for sample in samples),
        },
        "warmup_policy": "A method becomes warm only after its first successful schema-valid generation completed with finish_reason=stop and SSE DONE before deadline; that first call is not marked warmed. Semantic correctness is not used to select performance samples.",
        "chronology_basis": "Non-overlapping run start/completion UTC, serial completed-episode completion UTC, then recorded model_calls array order. No per-request timestamp is fabricated.",
        "identity_scope": "The supplied identity must describe the same uninterrupted serving instance for all input runs. The collector verifies model/revision and serial chronology but cannot retrospectively inspect server restarts or competing requests.",
        "measurement_scope": "Only recorded server token usage and client TTFT/elapsed time are copied. Missing usage remains null; character counts and stream chunks are never converted into tokens.",
        "last_unconfirmed_server_drain_request_id": unknown_drain,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, nargs="+", action="append", required=True,
                        help="One or more R4 development run roots; may be repeated")
    parser.add_argument("--server-identity", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New measurement JSON path")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    run_paths = [path.resolve() for group in args.run for path in group]
    report = collect(run_paths, args.server_identity.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"out": str(args.out.resolve()), **report["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
