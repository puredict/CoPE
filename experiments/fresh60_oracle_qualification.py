#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from cope.compact_tx import execute_compact_transaction, parse_proposal
from cope.native_fresh_cases import load_fresh_manifest
from cope.native_ntrack import (
    derive_post_state,
    expected_patch,
    materialize_patch,
    parse_full_state,
    parse_patch,
    state_without_history,
    validate_and_compile,
)
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider, normalized_raw_request_hash
from cope.tx_exec import execute_transaction
from cope.compact_tx import proposal_from_verbose_carrier
from cope.types import canonical_json, stable_hash


ARMS = ("cope", "compact_tx", "fsr_pc")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    cases = load_fresh_manifest(args.manifest)
    provider = OpenAICompatibleRecoveryProvider({
        "provider": "openrouter", "model": "qwen/qwen3.5-flash-02-23",
        "reasoning_effort": "none", "temperature": 0.0, "seed": 20260802,
        "max_completion_tokens": 4096, "max_prompt_tokens": 12000,
        "max_retries": 0, "timeout_seconds": 90.0,
    })
    rows = []
    for case_index, case in enumerate(cases):
        oracle = state_without_history(derive_post_state(case.pre_state, case.event))
        patch = expected_patch(case.pre_state, case.event)
        verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
        compact = proposal_from_verbose_carrier(verbose.carrier)
        full = oracle
        candidates = {
            "cope": materialize_patch(parse_patch(patch), case.pre_state, case.event),
            "compact_tx": execute_compact_transaction(
                parse_proposal(compact, case.pre_state, case.event),
                case.pre_state, case.event, validate_and_compile,
            ).post_state,
            "fsr_pc": parse_full_state(full),
        }
        requests = {
            "cope": provider.build_audited_request("patch", case.recovery_input, provider.patch_contract),
            "compact_tx": provider.build_audited_request("compact", case.recovery_input, provider.compact_contract),
            "fsr_pc": provider.build_audited_request("regenerate", case.recovery_input, provider.full_contract),
        }
        common_hashes = {request["common_input_message_sha256"] for request in requests.values()}
        normalized = {normalized_raw_request_hash(request) for request in requests.values()}
        for arm in ARMS:
            directive = validate_and_compile(candidates[arm], case.pre_state, case.event)
            rows.append({
                "case_id": case.case_id,
                "base_case_id": case.case_id.rsplit("_v", 1)[0].removeprefix("fresh_"),
                "variant_index": case.case_id.rsplit("_v", 1)[1],
                "phase": case.phase,
                "arm": arm,
                "input_hash": case.recovery_input.input_hash,
                "common_input_bytes": len(canonical_json(case.recovery_input.as_payload()).encode("utf-8")),
                "common_hash_equal": len(common_hashes) == 1,
                "normalized_request_equal": len(normalized) == 1,
                "oracle_state_equal": canonical_json(candidates[arm]) == canonical_json(oracle),
                "validator_pass": bool(directive),
                "reasoning_effort": provider.reasoning_effort,
                "call_order_position": (ARMS.index(arm) - case_index) % 3,
                "candidate_sha256": stable_hash(candidates[arm]),
            })
    with (args.output_dir / "02_ORACLE_QUALIFICATION.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    input_hashes = {row["input_hash"] for row in rows}
    first_positions = Counter(row["arm"] for row in rows if row["call_order_position"] == 0)
    smoke_first = Counter(
        row["arm"] for row in rows if row["phase"] == "smoke" and row["call_order_position"] == 0
    )
    maximum_common = max(int(row["common_input_bytes"]) for row in rows)
    passed = bool(
        len(rows) == 180 and len(input_hashes) == 60
        and all(row["common_hash_equal"] and row["normalized_request_equal"] for row in rows)
        and all(row["oracle_state_equal"] and row["validator_pass"] for row in rows)
        and first_positions == Counter({arm: 20 for arm in ARMS})
        and smoke_first == Counter({arm: 2 for arm in ARMS})
        and maximum_common < 12000
    )
    status = [
        "schema_version=x14-fresh60-oracle-qualification-v1",
        f"cases={len(cases)}",
        f"arm_cells={len(rows)}",
        f"unique_input_hashes={len(input_hashes)}/60",
        f"oracle_state_equal={sum(bool(row['oracle_state_equal']) for row in rows)}/180",
        f"validator_pass={sum(bool(row['validator_pass']) for row in rows)}/180",
        f"fairness_pass={sum(bool(row['common_hash_equal']) and bool(row['normalized_request_equal']) for row in rows)}/180",
        f"first_position_counts={dict(first_positions)}",
        f"smoke_first_position_counts={dict(smoke_first)}",
        f"maximum_common_input_bytes={maximum_common}",
        f"decision={'PASS' if passed else 'FAIL'}",
        "provider_calls=0",
        "gpu_robot_simulator_used=false",
        "reserved_states_27_49_read=false",
    ]
    (args.output_dir / "03_STATUS.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    print("\n".join(status))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
