#!/usr/bin/env python3
"""Stop only the recorded, same-owner idle R4 model server; never match broadly."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
from urllib.request import urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--identity", required=True, type=Path)
args = parser.parse_args()
identity = json.loads(args.identity.read_text())
pid = int(identity["pid"])
proc = Path(f"/proc/{pid}")
if not proc.exists():
    print("recorded server already stopped")
    raise SystemExit(0)
if proc.stat().st_uid != os.getuid():
    raise RuntimeError("refusing to signal another user's process")
observed = (proc / "cmdline").read_bytes().decode().rstrip("\0").split("\0")
if observed != identity["command"] or "vllm.entrypoints.openai.api_server" not in observed:
    raise RuntimeError("recorded PID no longer matches the exact R4 server command")
with urlopen("http://127.0.0.1:8000/metrics", timeout=5) as response:
    metrics = response.read().decode()
queues = [float(v) for v in re.findall(
    r'^vllm:num_requests_(?:running|waiting)(?:\{[^\n]*\})?\s+([0-9.eE+-]+)', metrics, re.MULTILINE)]
if len(queues) < 2 or sum(queues) != 0:
    raise RuntimeError("refusing to stop a server with unconfirmed or nonempty request queues")
os.kill(pid, signal.SIGTERM)
print(f"sent SIGTERM only to verified idle R4 server PID {pid}")
