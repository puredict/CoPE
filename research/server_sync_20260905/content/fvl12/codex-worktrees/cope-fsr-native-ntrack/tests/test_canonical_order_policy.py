from pathlib import Path

from experiments.canonical_order_policy import (
    clean_controls,
    fault_controls,
    load_order_rows,
    reorder_controls,
)
from cope.native_ntrack import load_manifest


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "research/native_output_tritrack_2026-08-02/01_CASE_MANIFEST.csv"
X18 = ROOT / "research/structure_mutation_falsifier_2026-08-03/run_v2/03_MUTATION_RESULTS.csv"
FAULTS = ROOT / "research/canonical_order_policy_2026-08-03/01_FAULT_MANIFEST.csv"


def test_clean_and_reorder_policy_controls():
    cases = load_manifest(CASES)
    clean, cache = clean_controls(cases)
    reorder = reorder_controls(load_order_rows(X18), {case.case_id: case for case in cases}, cache)
    assert len(clean) == 12 and all(row["pass"] for row in clean)
    assert len(reorder) == 14 and all(row["pass"] for row in reorder)


def test_key_faults_fail_closed():
    case = next(item for item in load_manifest(CASES) if item.case_id == "replace_pending_target")
    faults = fault_controls(case, FAULTS)
    assert len(faults) == 7
    assert all(row["pass"] for row in faults)
