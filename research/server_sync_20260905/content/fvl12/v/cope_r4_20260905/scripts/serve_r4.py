#!/usr/bin/env python3
"""Start the existing offline model on verified idle GPUs; preserve every attempt."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

BASE = Path("/mnt/data_new/lijingsu_cope_r4_20260905")
RUNTIME = Path("/mnt/data_new/lijingsu_cope_r3_20260905_v2")
SNAPSHOT = RUNTIME / "hf_cache/hub/models--Qwen--Qwen3-32B/snapshots/9216db5781bf21249d130ec9da846c4624c16137"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--attempt", type=int, required=True)
parser.add_argument("--backend", choices=("xgrammar", "guidance"), default="guidance")
args = parser.parse_args()
attempt = BASE / f"server_attempt{args.attempt}"
if attempt.exists():
    raise FileExistsError(attempt)
gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True)
print(gpu)
selected = {0, 1, 2, 3}
for line in gpu.strip().splitlines():
    index, memory, utilization = map(int, line.split(","))
    if index in selected and (memory > 100 or utilization != 0):
        raise RuntimeError(f"GPU {index} is not idle; will not start")
attempt.mkdir(parents=True)
env = dict(os.environ, CUDA_VISIBLE_DEVICES="0,1,2,3", HF_HUB_OFFLINE="1",
           TRANSFORMERS_OFFLINE="1", HF_HOME=str(RUNTIME / "hf_cache"),
           PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
command = [str(RUNTIME / "conda_vllm/bin/python"), "-m", "vllm.entrypoints.openai.api_server",
           "--model", str(SNAPSHOT), "--served-model-name", "Qwen/Qwen3-32B",
           "--host", "127.0.0.1", "--port", "8000", "--tensor-parallel-size", "4",
           "--dtype", "bfloat16", "--max-model-len", "40960",
           "--gpu-memory-utilization", "0.88", "--max-num-seqs", "1",
           "--guided-decoding-backend", args.backend,
           "--compilation-config", '{"cudagraph_capture_sizes":[1]}']
with (attempt / "server.log").open("x") as output:
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
        stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
identity = {"utc": datetime.now(timezone.utc).isoformat(), "pid": process.pid,
            "command": command, "gpu_before": gpu, "model": "Qwen/Qwen3-32B",
            "model_revision": SNAPSHOT.name, "tensor_parallel_size": 4, "dtype": "bfloat16",
            "enforce_eager": False, "max_model_len": 40960, "concurrency": 1,
            "gpu_indices": sorted(selected), "vllm_version": "0.8.5"}
identity["guided_decoding_backend"] = args.backend
(attempt / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
print(json.dumps(identity, indent=2))
