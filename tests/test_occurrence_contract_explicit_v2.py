from cope.occurrence_prompting import ARMS
from cope.occurrence_prompting_contract_explicit_v2 import (
    CONTRACTS_V2,
    EXPECTED_CONTRACT_HASHES_V2,
)
from cope.types import stable_hash


def test_contract_explicit_hashes_are_frozen() -> None:
    assert tuple(CONTRACTS_V2) == ARMS
    assert {arm: stable_hash(CONTRACTS_V2[arm]) for arm in ARMS} == EXPECTED_CONTRACT_HASHES_V2


def test_primary_controls_name_previously_ambiguous_shapes() -> None:
    neutral = CONTRACTS_V2["neutral_patch"]
    governed = CONTRACTS_V2["governed_delta"]
    full = CONTRACTS_V2["full_replan"]
    assert "exactly these\nsix operations" in neutral
    assert 'key is literally "after"' in governed
    assert "occurrence-ID strings only" in full

