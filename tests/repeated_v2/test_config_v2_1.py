from pathlib import Path

from cope_benchmark.repeated_v2.calibration_v2_1 import (
    CALIBRATION_STATE_IDS,
    CALIBRATION_TECHNICAL_SEED,
    FORMAL_STATE_IDS,
    FORMAL_TECHNICAL_SEED,
)
from cope_benchmark.repeated_v2.config import ROOT, load_config, validate_config


def test_v2_1_config_binds_the_frozen_disjoint_split_and_budget_cap() -> None:
    config = load_config(ROOT / "configs/repeated_interruptions_v2_1_pilot.yaml")
    selection = config["task_selection"]
    assert tuple(selection["calibration_state_ids"]) == CALIBRATION_STATE_IDS
    assert selection["calibration_policy_seeds"] == [CALIBRATION_TECHNICAL_SEED]
    assert tuple(selection["formal_state_ids"]) == FORMAL_STATE_IDS
    assert selection["formal_policy_seeds"] == [FORMAL_TECHNICAL_SEED]
    assert not set(selection["calibration_state_ids"]) & set(selection["formal_state_ids"])
    assert config["vla"]["max_policy_steps"] == 1040
    assert validate_config(config) == ()


def test_original_v2_config_remains_frozen_and_valid() -> None:
    original = load_config(ROOT / "configs/repeated_interruptions_v2_pilot.yaml")
    assert original["schema_version"] == "repeated_interruptions_v2_config_v1"
    assert original["vla"]["max_policy_steps"] == 260
    assert validate_config(original) == ()


def test_v2_1_pilot_and_formal_configs_are_byte_identical() -> None:
    pilot = Path(ROOT / "configs/repeated_interruptions_v2_1_pilot.yaml").read_bytes()
    formal = Path(ROOT / "configs/repeated_interruptions_v2_1_formal.yaml").read_bytes()
    assert pilot == formal
