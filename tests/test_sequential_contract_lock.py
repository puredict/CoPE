from __future__ import annotations

import csv
from pathlib import Path

from cope.sequential_prompting import ARMS, CONTRACTS
from cope.types import stable_hash
from experiments.sequential_formal_runner import EXPECTED_CONTRACT_HASHES


ROOT = Path(__file__).resolve().parents[1]


def test_contract_text_matches_both_companion_manifest_and_runner_lock():
    with (ROOT / "manifests" / "sequential_formal_contract_hashes_v1.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    companion = {row["arm"]: row["contract_sha256"] for row in rows}
    actual = {arm: stable_hash(CONTRACTS[arm]) for arm in ARMS}
    assert companion == EXPECTED_CONTRACT_HASHES == actual
