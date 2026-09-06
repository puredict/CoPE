#!/usr/bin/env bash
# Forwarding wrapper -> code/scripts/launch_gpu_workers.sh (single source of truth).
# REMOTE GPU SERVER ONLY (except DRY_RUN=1).
set -euo pipefail
cd "$(dirname "$0")/../code"
exec bash scripts/launch_gpu_workers.sh "$@"
