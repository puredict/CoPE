#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from cope.native_ntrack import load_manifest
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.types import canonical_json, stable_hash
from experiments.typed_assurance_falsification import canonical_outputs


ARMS = ("cope", "compact_tx", "fsr_pc")


def byte_len(value) -> int:
    return len(canonical_json(value).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "openrouter",
        "model": "qwen/qwen3.5-flash-02-23",
        "temperature": 0.0,
        "seed": 20260802,
        "max_completion_tokens": 4096,
        "max_prompt_tokens": 12000,
        "max_retries": 0,
        "timeout_seconds": 90.0,
    })
    contracts = {
        "cope": ("patch", provider.patch_contract),
        "compact_tx": ("compact", provider.compact_contract),
        "fsr_pc": ("regenerate", provider.full_contract),
    }
    rows = []
    for case in load_manifest(args.manifest):
        outputs = canonical_outputs(case)
        for arm in ARMS:
            mode, contract = contracts[arm]
            request = provider.build_audited_request(mode, case.recovery_input, contract)
            wire_bytes = byte_len(request["wire_payload"])
            proposal_bytes = byte_len(outputs[arm])
            common_bytes = len(request["wire_payload"]["messages"][1]["content"].encode("utf-8"))
            contract_bytes = len(contract.encode("utf-8"))
            rows.append({
                "case_id": case.case_id,
                "family": case.family,
                "arm": arm,
                "common_input_bytes": common_bytes,
                "contract_bytes": contract_bytes,
                "wire_request_bytes": wire_bytes,
                "oracle_proposal_bytes": proposal_bytes,
                "request_plus_oracle_proposal_bytes": wire_bytes + proposal_bytes,
                "common_input_sha256": stable_hash(request["wire_payload"]["messages"][1]["content"]),
                "contract_sha256": stable_hash(contract),
                "provider_calls": 0,
            })
    with (args.output_dir / "02_PER_CASE.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    aggregate = []
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        aggregate.append({
            "arm": arm,
            "cases": len(selected),
            "contract_bytes": selected[0]["contract_bytes"],
            "median_wire_request_bytes": statistics.median(row["wire_request_bytes"] for row in selected),
            "median_oracle_proposal_bytes": statistics.median(row["oracle_proposal_bytes"] for row in selected),
            "median_request_plus_oracle_bytes": statistics.median(
                row["request_plus_oracle_proposal_bytes"] for row in selected
            ),
            "sum_wire_request_bytes": sum(row["wire_request_bytes"] for row in selected),
            "sum_oracle_proposal_bytes": sum(row["oracle_proposal_bytes"] for row in selected),
            "sum_request_plus_oracle_bytes": sum(
                row["request_plus_oracle_proposal_bytes"] for row in selected
            ),
        })
    with (args.output_dir / "03_AGGREGATE.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(aggregate[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(aggregate)
    common_equal = all(
        len({row["common_input_sha256"] for row in rows if row["case_id"] == case.case_id}) == 1
        for case in load_manifest(args.manifest)
    )
    status = [
        "schema_version=provider-byte-budget-v1",
        f"assigned_cells={len(rows)}",
        f"common_input_hash_equal={common_equal}",
        "provider_calls=0",
        "tokenizer_used=false",
        "decision=PASS" if len(rows) == 36 and common_equal else "decision=FAIL",
        "evidence_class=deterministic_provider_visible_byte_accounting",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "04_STATUS.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    print("\n".join(status))
    return 0 if len(rows) == 36 and common_equal else 2


if __name__ == "__main__":
    raise SystemExit(main())
