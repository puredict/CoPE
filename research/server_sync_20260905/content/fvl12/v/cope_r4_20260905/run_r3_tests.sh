#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/code${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s tests_r3 -p 'test_*.py' -v
python3 scripts/run_r3_causal_gate.py
python3 scripts/preflight_r3.py
