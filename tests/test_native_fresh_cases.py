from pathlib import Path

from cope.native_fresh_cases import load_fresh_manifest
from cope.native_ntrack import derive_post_state, state_without_history, validate_and_compile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "research/native_output_fresh60_2026-08-03/01_MANIFEST.csv"


def test_fresh_manifest_has_unique_inputs_and_exact_family_balance():
    cases = load_fresh_manifest(MANIFEST)
    assert len(cases) == 60
    assert len({case.recovery_input.input_hash for case in cases}) == 60
    assert sum(case.phase == "smoke" for case in cases) == 6


def test_all_fresh_oracle_states_validate():
    for case in load_fresh_manifest(MANIFEST):
        oracle = state_without_history(derive_post_state(case.pre_state, case.event))
        assert validate_and_compile(oracle, case.pre_state, case.event)
