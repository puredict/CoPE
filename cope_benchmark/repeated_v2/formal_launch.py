"""Eight deterministic formal shards; gates precede process creation and calls."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from .analysis import sha256_file
from .freeze import FreezeBlocked, _load, validate_static_frozen_bundle


def idle_gpu_ids(gpu_csv: str, process_csv: str) -> list[str]:
    """Require no compute process, zero utilization and <=100 MiB allocated memory."""
    busy = set()
    for row in csv.reader(io.StringIO(process_csv)):
        if row and row[0].strip():
            if len(row) != 2 or not row[1].strip().isdigit():
                raise FreezeBlocked("BLOCKED_UNRECOGNIZED_GPU_PROCESS_STATUS")
            busy.add(row[0].strip())
    idle = []
    seen = set()
    for row in csv.reader(io.StringIO(gpu_csv)):
        if not row:
            continue
        if len(row) != 4:
            raise FreezeBlocked("BLOCKED_UNRECOGNIZED_GPU_STATUS")
        index, uuid, utilization, memory = (s.strip() for s in row)
        if not index.isdigit() or uuid in seen or not uuid.startswith("GPU-"):
            raise FreezeBlocked("BLOCKED_UNRECOGNIZED_GPU_STATUS")
        seen.add(uuid)
        try:
            utilization, memory = int(utilization), int(memory)
        except ValueError as exc:
            raise FreezeBlocked("BLOCKED_UNRECOGNIZED_GPU_STATUS") from exc
        if not 0 <= utilization <= 100 or memory < 0:
            raise FreezeBlocked("BLOCKED_UNRECOGNIZED_GPU_STATUS")
        if uuid not in busy and utilization == 0 and memory <= 100:
            idle.append((int(index), uuid))
    return [uuid for _,uuid in sorted(idle)]


def inspect_idle_gpus() -> list[str]:
    # Always run the full nvidia-smi inspection before touching a GPU.
    subprocess.run(["nvidia-smi"], check=True)
    gpus = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,utilization.gpu,memory.used",
                                    "--format=csv,noheader,nounits"], text=True)
    processes = subprocess.check_output(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid",
                                         "--format=csv,noheader,nounits"], text=True)
    return idle_gpu_ids(gpus, processes)


def shard_command(*, python: str, repo_root: Path, protocol: str, condition: str,
                  config: str, catalog: str, manifest: str, freeze: str,
                  output_root: Path, shard_id: int, resume: bool = False) -> list[str]:
    if protocol not in ("controlled","end_to_end") or condition not in ("evidence_matched","token_matched"):
        raise ValueError("invalid protocol/condition")
    if type(shard_id) is not int or not 0 <= shard_id < 8:
        raise ValueError("shard must be an integer 0..7")
    command = [python, str(repo_root/"experiments/repeated_interruptions_v2.py"),
        "--phase", "formal", "--protocol", protocol, "--information-condition", condition,
        "--config", config, "--task-catalog", catalog, "--manifest", manifest,
        "--frozen-bundle", freeze, "--shard-index", str(shard_id), "--num-shards", "8",
        "--output-dir", str(output_root/protocol/condition/f"shard_{shard_id:02d}")]
    if resume:
        command.append("--resume")
    return command


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--task-catalog", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--frozen-bundle", required=True)
    parser.add_argument("--protocol", choices=("controlled","end_to_end"),required=True)
    parser.add_argument("--information-condition",choices=("evidence_matched","token_matched"),required=True)
    parser.add_argument("--output-root",required=True)
    parser.add_argument("--workers",type=int,default=1)
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--plan-only",action="store_true")
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[2]
    output=Path(args.output_root).resolve()
    try:
        if not 1 <= args.workers <= 8:
            raise FreezeBlocked("BLOCKED_INVALID_WORKER_COUNT")
        if not any(output.is_relative_to(root/p) for p in ("research","docs")):
            raise FreezeBlocked("BLOCKED_OUTPUT_OUTSIDE_RESEARCH_DOCS")
        bundle=_load(args.frozen_bundle)
        validate_static_frozen_bundle(bundle,repo_root=root)
        for role,path in (("config",args.config),("catalog",args.task_catalog),("manifest",args.manifest)):
            entries=bundle["artifacts"][role]["entries"]
            if len(entries)!=1 or sha256_file(path)!=entries[0]["sha256"]:
                raise FreezeBlocked("BLOCKED_LAUNCH_INPUT_DRIFT")
        commands=[shard_command(python=sys.executable,repo_root=root,protocol=args.protocol,
            condition=args.information_condition,config=str(Path(args.config).resolve()),
            catalog=str(Path(args.task_catalog).resolve()),manifest=str(Path(args.manifest).resolve()),
            freeze=str(Path(args.frozen_bundle).resolve()),output_root=output,shard_id=i,resume=args.resume)
            for i in range(8)]
        if args.plan_only:
            print(json.dumps({"status":"FROZEN_LAUNCH_PLAN_ONLY","formal_calls":0,"commands":commands},indent=2))
            return 0
        if not os.environ.get("COPE_RUNTIME_FACTORY"):
            raise FreezeBlocked("BLOCKED_RUNTIME_FACTORY_UNAVAILABLE")
        gpus=inspect_idle_gpus() if args.protocol=="end_to_end" else []
        if args.protocol=="end_to_end" and not gpus:
            raise FreezeBlocked("BLOCKED_NO_IDLE_GPU")
        width=min(args.workers,len(gpus)) if gpus else args.workers
        group_output=output/args.protocol/args.information_condition
        if group_output.exists() and not args.resume:
            raise FreezeBlocked("BLOCKED_EXISTING_OUTPUT_REQUIRES_VERIFIED_RESUME")
        output.mkdir(parents=True,exist_ok=True)
        for first in range(0,8,width):
            validate_static_frozen_bundle(bundle,repo_root=root)
            available=inspect_idle_gpus() if gpus else []
            if gpus and not set(gpus[:width]).issubset(available):
                raise FreezeBlocked("BLOCKED_GPU_BECAME_BUSY")
            jobs=[]
            try:
                for offset,command in enumerate(commands[first:first+width]):
                    env=dict(os.environ, CUDA_VISIBLE_DEVICES=gpus[offset] if gpus else "")
                    # Child factory supplies live identity checks before every external
                    # call. A frozen string alone never authorizes a model invocation.
                    jobs.append(subprocess.Popen(command,cwd=root,env=env))
            except OSError:
                # A failed spawn cannot orphan an already-started owned shard.
                # Let those children finish their durable records; never kill others.
                for process in jobs:
                    process.wait()
                raise
            failures=[process.wait() for process in jobs]
            if any(code!=0 for code in failures):
                raise FreezeBlocked("BLOCKED_FORMAL_SHARD_FAILED_RETAIN_ALL_ARTIFACTS")
        print(json.dumps({"status":"FORMAL_SHARDS_COMPLETED","shards":8,"protocol":args.protocol,
                          "condition":args.information_condition}))
        return 0
    except (FreezeBlocked,OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":getattr(exc,"status","BLOCKED_FORMAL_LAUNCH"),
                          "reasons":getattr(exc,"reasons",[str(exc)])},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
