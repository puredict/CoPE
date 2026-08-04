#!/usr/bin/env python3
"""Run the separate post-outcome contract-explicit occurrence diagnostic."""

from __future__ import annotations

from cope.occurrence_prompting_contract_explicit_v2 import (
    CONTRACTS_V2,
    EXPECTED_CONTRACT_HASHES_V2,
)
from experiments import occurrence_formal_runner as frozen


def main() -> int:
    frozen.CONTRACTS = CONTRACTS_V2
    frozen.EXPECTED_CONTRACT_HASHES = EXPECTED_CONTRACT_HASHES_V2
    return frozen.main()


if __name__ == "__main__":
    raise SystemExit(main())

