"""Frozen common input and five-arm contracts for sequential formal v2."""

from __future__ import annotations

from cope.governance_collision_prompting import GOVERNED_DELTA_CONTRACT
from cope.sequential_prompting import (
    CONTRACTS as V1_CONTRACTS,
    MAX_COMPLETION_TOKENS,
    MAX_PROMPT_TOKENS,
    MODEL,
    REASONING_EFFORT,
    SEED_BASE,
    TEMPERATURE,
    TIMEOUT_SECONDS,
    build_sequential_recovery_input,
)


ARMS = (
    "cope",
    "neutral_patch",
    "governed_delta",
    "fsr_pc",
    "full_replan",
)
CONTRACTS = {**V1_CONTRACTS, "governed_delta": GOVERNED_DELTA_CONTRACT}


__all__ = (
    "ARMS",
    "CONTRACTS",
    "MAX_COMPLETION_TOKENS",
    "MAX_PROMPT_TOKENS",
    "MODEL",
    "REASONING_EFFORT",
    "SEED_BASE",
    "TEMPERATURE",
    "TIMEOUT_SECONDS",
    "build_sequential_recovery_input",
)
