#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
exec "${COPE_PYTHON:-python3}" -m cope_benchmark.repeated_v2.formal_launch "$@"
