#!/usr/bin/env python3
"""Launch one detached command with a secret read silently from the terminal."""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-name", required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    secret = getpass.getpass("")
    if not secret:
        raise SystemExit("empty secret")
    environment = os.environ.copy()
    environment[args.env_name] = secret
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("xb") as log:
        process = subprocess.Popen(
            command,
            cwd=args.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    environment.pop(args.env_name, None)
    secret = ""
    print(f"DETACHED_PID={process.pid}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
