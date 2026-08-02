#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from unittest.mock import patch

from cope.compact_tx import proposal_from_verbose_carrier
from cope.native_ntrack import (
    derive_post_state,
    expected_patch,
    load_manifest,
    state_without_history,
    validate_and_compile,
)
from cope.providers.openai_compatible import OpenAICompatibleRecoveryProvider
from cope.tx_exec import execute_transaction
from cope.types import canonical_json
from experiments.native_output_tritrack import run_triplet


class _Response:
    def __init__(self, output: dict) -> None:
        self.output = output

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "id": "mocked-oracle-transport",
                "choices": [{"message": {"content": json.dumps(self.output)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        ).encode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_manifest(args.manifest)
    os.environ["TRITRACK_ORACLE_CONTROL_KEY"] = "test-only-not-logged"
    provider = OpenAICompatibleRecoveryProvider(
        {
            "provider": "mocked_oracle_transport_control",
            "model": "canonical-injection-not-a-model",
            "endpoint": "https://invalid.test/v1/chat/completions",
            "api_key_env": "TRITRACK_ORACLE_CONTROL_KEY",
            "temperature": 0.0,
            "seed": 20260802,
            "max_retries": 0,
        }
    )
    selected_fields = [
        "case_id", "phase", "family", "arm", "call_order_position",
        "fairness_pass", "parser_valid", "semantic_valid", "first_pass_valid",
        "semantic_correct", "validator_calls", "compiled_directive",
        "prompt_tokens", "completion_tokens", "proposal_bytes", "evidence_class",
        "test_only", "provider_calls", "gpu_used", "simulator_used",
        "reserved_states_read",
    ]
    result_rows = []
    for index, case in enumerate(cases):
        verbose = execute_transaction(case.pre_state, case.event, validate_and_compile)
        outputs = {
            "cope": expected_patch(case.pre_state, case.event),
            "compact_tx": proposal_from_verbose_carrier(verbose.carrier),
            "fsr_pc": state_without_history(derive_post_state(case.pre_state, case.event)),
        }
        arms = ["cope", "compact_tx", "fsr_pc"]
        offset = index % 3
        call_order = arms[offset:] + arms[:offset]
        queue = [outputs[arm] for arm in call_order]

        def fake_urlopen(req, timeout):
            return _Response(queue.pop(0))

        with patch("cope.providers.openai_compatible.request.urlopen", fake_urlopen):
            rows = run_triplet(case, provider, order_index=index)
        for row in rows:
            result_rows.append(
                {
                    "case_id": row["case_id"],
                    "phase": row["phase"],
                    "family": row["family"],
                    "arm": row["arm"],
                    "call_order_position": row["call_order_position"],
                    "fairness_pass": row["fairness_pass"],
                    "parser_valid": row["parser_valid"],
                    "semantic_valid": row["semantic_valid"],
                    "first_pass_valid": row["first_pass_valid"],
                    "semantic_correct": row["semantic_correct"],
                    "validator_calls": row["validator_calls"],
                    "compiled_directive": row["compiled_directive"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "proposal_bytes": row["proposal_bytes"],
                    "evidence_class": "mocked_canonical_transport_control",
                    "test_only": True,
                    "provider_calls": 1,
                    "gpu_used": False,
                    "simulator_used": False,
                    "reserved_states_read": False,
                }
            )
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=selected_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result_rows)
    passed = bool(
        len(result_rows) == 36
        and all(row["fairness_pass"] for row in result_rows)
        and all(row["first_pass_valid"] for row in result_rows)
        and all(row["semantic_correct"] for row in result_rows)
        and all(row["validator_calls"] == 1 for row in result_rows)
    )
    first_counts = {
        arm: sum(row["arm"] == arm and row["call_order_position"] == 0 for row in result_rows)
        for arm in ("cope", "compact_tx", "fsr_pc")
    }
    status = {
        "schema_version": "tri-arm-oracle-transport-control-v1",
        "assigned_triplets": len(cases),
        "assigned_cells": len(result_rows),
        "passed_cells": sum(bool(row["first_pass_valid"]) for row in result_rows),
        "first_position_counts": first_counts,
        "test_only": True,
        "learned_provider_calls": 0,
        "mocked_transport_calls": len(result_rows),
        "credential_logged": False,
        "gpu_used": False,
        "simulator_used": False,
        "reserved_states_read": False,
        "decision": "PASS" if passed and set(first_counts.values()) == {4} else "FAIL",
    }
    args.status.write_text(canonical_json(status) + "\n", encoding="utf-8")
    print(canonical_json(status))
    return 0 if status["decision"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

