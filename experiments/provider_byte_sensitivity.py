#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from cope.native_ntrack import load_manifest
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import canonical_json


ARMS = ("cope", "compact_tx", "fsr_pc")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--x19-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with args.x19_results.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "openrouter", "model": "qwen/qwen3.5-flash-02-23",
        "temperature": 0.0, "seed": 20260802, "max_completion_tokens": 4096,
        "max_prompt_tokens": 12000, "max_retries": 0, "timeout_seconds": 90.0,
    })
    empty_request_bytes = {}
    for case in load_manifest(args.manifest):
        request = provider.build_audited_request("sensitivity", case.recovery_input, "")
        empty_request_bytes[case.case_id] = len(canonical_json(request["wire_payload"]).encode("utf-8"))
    by_arm = defaultdict(list)
    for row in rows:
        row = dict(row)
        row["wire_request_bytes"] = int(row["wire_request_bytes"])
        row["oracle_proposal_bytes"] = int(row["oracle_proposal_bytes"])
        by_arm[row["arm"]].append(row)
    summary = []
    for arm in ARMS:
        selected = by_arm[arm]
        repeated = sum(r["wire_request_bytes"] + r["oracle_proposal_bytes"] for r in selected)
        proposal_only = sum(r["oracle_proposal_bytes"] for r in selected)
        overheads = {
            r["wire_request_bytes"] - empty_request_bytes[r["case_id"]] for r in selected
        }
        if len(overheads) != 1:
            raise AssertionError(f"contract wire overhead is not constant for {arm}: {overheads}")
        one_time_overhead = next(iter(overheads))
        cached = sum(empty_request_bytes[r["case_id"]] + r["oracle_proposal_bytes"] for r in selected) + one_time_overhead
        output_wins = 0
        for row in selected:
            case_rows = [item for item in rows if item["case_id"] == row["case_id"]]
            minimum = min(int(item["oracle_proposal_bytes"]) for item in case_rows)
            output_wins += int(row["oracle_proposal_bytes"] == minimum)
        summary.extend([
            {"scenario": "actual_contract_every_call", "arm": arm, "total_bytes": repeated, "per_case_output_only_wins": ""},
            {"scenario": "hypothetical_contract_cached_once", "arm": arm, "total_bytes": cached, "per_case_output_only_wins": ""},
            {"scenario": "proposal_only", "arm": arm, "total_bytes": proposal_only, "per_case_output_only_wins": output_wins},
        ])
    with (args.output_dir / "02_SENSITIVITY.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    winners = {}
    for scenario in ("actual_contract_every_call", "hypothetical_contract_cached_once", "proposal_only"):
        selected = [row for row in summary if row["scenario"] == scenario]
        winners[scenario] = min(selected, key=lambda row: int(row["total_bytes"]))["arm"]
    passed = all(winner == "cope" for winner in winners.values())
    status = [
        "schema_version=provider-byte-sensitivity-v1",
        *(f"winner_{scenario}={winner}" for scenario, winner in winners.items()),
        f"decision={'PASS' if passed else 'FAIL'}",
        "claim_scope=corpus_total_utf8_bytes_not_per_case_dominance",
        "provider_calls=0",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "03_STATUS.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    print("\n".join(status))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
