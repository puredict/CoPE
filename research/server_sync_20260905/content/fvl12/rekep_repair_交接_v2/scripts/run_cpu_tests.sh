#!/usr/bin/env bash
# CPU test runner -- safe on any machine. No GPU imports.
set -euo pipefail
cd "$(dirname "$0")/../code"
echo "=== pytest (expect 71 passed) ==="
python -m pytest -q
