"""Forwarding wrapper -> code/scripts/run_rekep_baseline.py (single source of truth).

Duplicating the real script here would break its sys.path assumptions, so this
wrapper simply executes the canonical one with the same arguments.
"""
import runpy, sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "code" / "scripts" / "run_rekep_baseline.py"
if not TARGET.exists():
    sys.exit(f"missing canonical script: {TARGET}")
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
