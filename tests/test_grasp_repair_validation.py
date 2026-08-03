from __future__ import annotations

from dataclasses import asdict

from cope.types import stable_hash
from experiments import grasp_repair_validation as validation


def test_validation_state_set_is_exactly_locked_partition() -> None:
    assert validation.AUTHORIZED_STATE_IDS == tuple(range(15, 25))
    assert max(validation.AUTHORIZED_STATE_IDS) < 25


def test_validation_config_hashes_match_preregistered_values() -> None:
    assert {
        name: stable_hash(asdict(config))
        for name, config in validation.ARM_CONFIGS.items()
    } == validation.EXPECTED_CONFIG_HASHES


def test_exact_two_sided_sign_test() -> None:
    assert validation.exact_two_sided_sign_p(10, 0) == 2 / (2**10)
    assert validation.exact_two_sided_sign_p(5, 5) == 1.0
    assert validation.exact_two_sided_sign_p(0, 0) == 1.0
