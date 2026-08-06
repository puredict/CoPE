#!/usr/bin/env python3
"""Run the frozen occurrence analysis on the locked v3 manifest."""

from __future__ import annotations

from experiments.occurrence_confirmatory_runner_v3 import EXPECTED_MANIFEST_SHA256_V3
from tools import analyze_occurrence_formal as frozen


def main() -> int:
    frozen.EXPECTED_MANIFEST_SHA256 = EXPECTED_MANIFEST_SHA256_V3
    return frozen.main()


if __name__ == "__main__":
    raise SystemExit(main())
