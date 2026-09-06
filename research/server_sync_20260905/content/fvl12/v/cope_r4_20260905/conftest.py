"""Puts `code/` on sys.path so `cope` and `rekep_repair.benchmark.
statistics` import without installation. Collected automatically by
pytest; imported explicitly by the scripts."""
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent / 'code'
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))
