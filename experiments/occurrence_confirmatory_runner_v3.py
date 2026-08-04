#!/usr/bin/env python3
"""Run the outcome-locked held-out occurrence confirmation."""

from __future__ import annotations

from cope.occurrence_prompting_confirmatory_v3 import (
    CONTRACTS_V3,
    EXPECTED_CONTRACT_HASHES_V3,
)
from experiments import occurrence_formal_runner as frozen


EXPECTED_MANIFEST_SHA256_V3 = "fa76ee03d207eb7a1959143881a0886b06965e6ebc0900ecde5631307a065bc5"


def main() -> int:
    frozen.CONTRACTS = CONTRACTS_V3
    frozen.EXPECTED_CONTRACT_HASHES = EXPECTED_CONTRACT_HASHES_V3
    frozen.EXPECTED_MANIFEST_SHA256 = EXPECTED_MANIFEST_SHA256_V3
    return frozen.main()


if __name__ == "__main__":
    raise SystemExit(main())
