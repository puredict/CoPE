#!/usr/bin/env python3
"""Credential-free cold preflight for occurrence confirmation v3."""

from __future__ import annotations

from cope.occurrence_prompting_confirmatory_v3 import CONTRACTS_V3
from experiments import occurrence_formal_preflight as frozen
from experiments.occurrence_confirmatory_runner_v3 import EXPECTED_MANIFEST_SHA256_V3


def main() -> int:
    frozen.CONTRACTS = CONTRACTS_V3
    frozen.EXPECTED_MANIFEST_SHA256 = EXPECTED_MANIFEST_SHA256_V3
    return frozen.main()


if __name__ == "__main__":
    raise SystemExit(main())
