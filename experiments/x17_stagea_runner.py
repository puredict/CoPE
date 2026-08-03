#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from cope.types import ProviderInvocation, canonical_json, stable_hash
from x16_provider_runner import (
    ARMS as X16_ARMS,
    MODES,
    X16Input,
    X16Provider,
    load_qualification,
    provider_status,
    response_hash,
    unsafe_mutation_attempt,
    verify_freeze,
)


MODEL = "qwen/qwen3.5-flash-02-23"
SEED = 20260803
ARMS = ("cope", "neutral_typed", "compact_tx", "fsr_pc")
MODES_X17 = {"cope": "patch", "neutral_typed": "patch", "compact_tx": "compact", "fsr_pc": "regenerate"}
FIELDS = (
    "case_id", "family", "mode", "arm", "call_order_position",
    "provider_status", "provider_error", "parser_valid", "semantic_correct",
    "unsafe_mutation_attempt", "input_hash", "common_input_bytes_sha256",
    "normalized_request_sha256", "fairness_pass", "response_sha256",
    "prompt_tokens", "completion_tokens", "proposal_bytes", "latency_seconds",
    "retry_count", "parse_or_validation_error", "model", "reasoning_effort",
    "temperature", "seed", "max_completion_tokens", "timeout_seconds",
    "retry_budget", "repair_budget", "fallback_used", "oracle_substitution",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="X17 structured-interface Stage A")
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args()


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(type(value).__name__)


def infer_schema(values: Iterable[Any], *, key: str = "") -> dict[str, Any]:
    values = list(values)
    types = sorted({json_type(value) for value in values})
    if types == ["integer", "number"]:
        types = ["number"]
    if len(types) != 1:
        return {"type": types}
    kind = types[0]
    if kind == "object":
        objects = [value for value in values if isinstance(value, dict)]
        keys = sorted(set().union(*(obj.keys() for obj in objects)))
        required = sorted(set.intersection(*(set(obj) for obj in objects))) if objects else []
        return {
            "type": "object",
            "properties": {
                child: infer_schema([obj[child] for obj in objects if child in obj], key=child)
                for child in keys
            },
            "required": required,
            "additionalProperties": False,
        }
    if kind == "array":
        items = [item for value in values for item in value]
        item_schema = infer_schema(items, key=f"{key}_item") if items else {
            "type": ["object", "array", "string", "number", "boolean", "null"]
        }
        return {"type": "array", "items": item_schema}
    schema: dict[str, Any] = {"type": kind}
    if kind == "string" and key in {"schema_version", "disposition", "op"}:
        schema["enum"] = sorted(set(values))
    return schema


def replace_op_enum(schema: dict[str, Any], mapping: Mapping[str, str]) -> None:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict) and "op" in properties:
            op_schema = properties["op"]
            if isinstance(op_schema, dict) and "enum" in op_schema:
                op_schema["enum"] = [mapping[value] for value in op_schema["enum"]]
        for value in schema.values():
            if isinstance(value, dict):
                replace_op_enum(value, mapping)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        replace_op_enum(item, mapping)


def schemas_and_mapping(module: Any) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    representations = [module.representations(case) for case in module.CASES]
    schemas = {
        arm: infer_schema([reps[arm] for reps in representations])
        for arm in X16_ARMS
    }
    op_names = sorted({
        op["op"]
        for reps in representations
        for op in reps["cope"]["operations"]
    })
    semantic_to_neutral = {name: f"N{index:02d}" for index, name in enumerate(op_names, start=1)}
    neutral = copy.deepcopy(schemas["cope"])
    neutral["properties"]["schema_version"]["enum"] = ["x17-neutral-patch-v1"]
    replace_op_enum(neutral, semantic_to_neutral)
    schemas["neutral_typed"] = neutral
    return schemas, semantic_to_neutral


def contracts(schemas: Mapping[str, Mapping[str, Any]], mapping: Mapping[str, str]) -> dict[str, str]:
    signatures = (
        "Every typed operation uses the exact discriminator key op. Exact field signatures: "
        "SetCommitmentStatus={op,target_id,status}; "
        "SetCommitmentField={op,target_id,field,value}; "
        "InsertCommitment={op,record}; SetAction={op,target_id,fields}; "
        "InsertAction={op,record}; SetProgress={op,target_id,fields}; "
        "InsertProgress={op,record}; AddRestoration={op,record}; "
        "RemoveRestoration={op,target_id}; SetFact={op,key,value}; "
        "CommitEvent={op}."
    )
    mapping_text = "; ".join(f"{neutral} has the behavior of {semantic}" for semantic, neutral in sorted(mapping.items()))
    common = "Return exactly one JSON object matching this JSON Schema. No prose, Markdown, repair, or extra fields.\n"
    return {
        "cope": common + signatures + "\nJSON_SCHEMA\n" + canonical_json(schemas["cope"]),
        "neutral_typed": common + (
            "Use neutral operation labels only. " + mapping_text + ". Field signatures are identical to the corresponding behavior.\n"
            "JSON_SCHEMA\n" + canonical_json(schemas["neutral_typed"])
        ),
        "compact_tx": common + (
            "Each write is exactly {op,path,value}. op is add or replace. Stable-ID paths are "
            "/commitments/<id>/<field>, /commitments/+/<id>, /actions/<id>/<field>, "
            "/actions/+/<id>, /progress/<id>/<field>, /progress/+/<id>, /restorations, "
            "/facts/<key>, /processed_events/+/<event_id>, /state_version, or /evidence_version.\n"
            "JSON_SCHEMA\n" + canonical_json(schemas["compact_tx"])
        ),
        "fsr_pc": common + "state must be the complete canonical post-decision state.\nJSON_SCHEMA\n" + canonical_json(schemas["fsr_pc"]),
    }


class StageAProvider(X16Provider):
    def __init__(
        self, config: Mapping[str, Any], *, system_prompt: str,
        structured: bool, schemas: Mapping[str, Mapping[str, Any]],
        contract_to_arm: Mapping[str, str],
    ) -> None:
        super().__init__(config, system_prompt=system_prompt)
        self.structured = structured
        self.schemas = schemas
        self.contract_to_arm = contract_to_arm

    def build_audited_request(
        self, mode: str, recovery_input: X16Input, output_contract: str
    ) -> dict[str, Any]:
        audited = super().build_audited_request(mode, recovery_input, output_contract)
        if self.structured:
            arm = self.contract_to_arm[stable_hash(output_contract)]
            audited["wire_payload"]["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": f"x17_{arm}_stagea",
                    "strict": True,
                    "schema": copy.deepcopy(self.schemas[arm]),
                },
            }
            audited["wire_payload"]["provider"] = {"require_parameters": True}
        return audited


def normalized_hash(raw_request: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(raw_request["wire_payload"])
    payload["messages"][2]["content"] = "<ARM_OUTPUT_CONTRACT>"
    if payload.get("response_format", {}).get("type") == "json_schema":
        payload["response_format"] = {"type": "json_schema", "json_schema": "<ARM_SCHEMA>"}
    return stable_hash(payload)


def translate_neutral(proposal: Any, mapping: Mapping[str, str]) -> Any:
    if not isinstance(proposal, dict):
        return proposal
    inverse = {neutral: semantic for semantic, neutral in mapping.items()}
    translated = copy.deepcopy(proposal)
    translated["schema_version"] = "x16-cope-patch-v1"
    for operation in translated.get("operations", []):
        if isinstance(operation, dict) and operation.get("op") in inverse:
            operation["op"] = inverse[operation["op"]]
    return translated


def expected_schema_version(arm: str, module: Any) -> str:
    if arm == "neutral_typed":
        return "x17-neutral-patch-v1"
    return module.ARM_CONTRACTS[arm]["schema_version"]


def evaluate(
    module: Any, case: Any, run_mode: str, arm: str, position: int,
    invocation: ProviderInvocation, provider: StageAProvider,
    mapping: Mapping[str, str],
) -> dict[str, Any]:
    status, error = provider_status(invocation, provider)
    proposal = invocation.parsed_output
    parser_valid = bool(
        status == "ok" and isinstance(proposal, dict)
        and proposal.get("schema_version") == expected_schema_version(arm, module)
    )
    validator_arm = "cope" if arm == "neutral_typed" else arm
    candidate_proposal = translate_neutral(proposal, mapping) if arm == "neutral_typed" else proposal
    semantic_correct = False
    validation_error = ""
    if parser_valid:
        try:
            module.validate_representation(case, validator_arm, candidate_proposal)
            semantic_correct = True
        except Exception as exc:
            validation_error = f"{type(exc).__name__}:{exc}"
    elif status == "ok":
        validation_error = "schema_version_or_object_mismatch"
    return {
        "case_id": case["case_id"], "family": case["primary_family"],
        "mode": run_mode, "arm": arm, "call_order_position": position,
        "provider_status": status, "provider_error": error,
        "parser_valid": parser_valid, "semantic_correct": semantic_correct,
        "unsafe_mutation_attempt": unsafe_mutation_attempt(module, case, validator_arm, candidate_proposal),
        "input_hash": stable_hash(module.common_input(case)),
        "common_input_bytes_sha256": invocation.raw_request.get("common_input_message_sha256", ""),
        "normalized_request_sha256": normalized_hash(invocation.raw_request),
        "fairness_pass": False, "response_sha256": response_hash(invocation),
        "prompt_tokens": invocation.usage.prompt_tokens,
        "completion_tokens": invocation.usage.completion_tokens,
        "proposal_bytes": len(canonical_json(proposal).encode("utf-8")) if isinstance(proposal, dict) else 0,
        "latency_seconds": f"{invocation.latency_seconds:.6f}",
        "retry_count": invocation.retry_count,
        "parse_or_validation_error": validation_error,
        "model": provider.metadata.model, "reasoning_effort": provider.reasoning_effort,
        "temperature": provider.metadata.temperature, "seed": provider.seed,
        "max_completion_tokens": provider.metadata.max_completion_tokens,
        "timeout_seconds": provider.metadata.timeout_seconds,
        "retry_budget": provider.metadata.max_retries, "repair_budget": 0,
        "fallback_used": False, "oracle_substitution": False,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Iterable[str]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    freeze_dir = args.freeze_dir.resolve()
    output_dir = args.output_dir.resolve()
    if repo_root / "research" not in output_dir.parents:
        raise RuntimeError("X17 output must be under research/")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout
    if git_status.strip():
        raise RuntimeError("X17 requires a clean committed worktree")
    runtime_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    freeze_hashes = verify_freeze(freeze_dir)
    module = load_qualification(freeze_dir)
    selected = [case for case in module.CASES if case["disposition"] == "APPLY"][:6]
    if len(selected) != 6:
        raise RuntimeError("Stage A selection did not produce six APPLY cases")
    schemas, mapping = schemas_and_mapping(module)
    arm_contracts = contracts(schemas, mapping)
    contract_to_arm = {stable_hash(text): arm for arm, text in arm_contracts.items()}
    providers = {
        mode: StageAProvider(
            {
                "provider": "openrouter", "endpoint": args.endpoint,
                "api_key_env": args.api_key_env, "model": MODEL,
                "reasoning_effort": "none", "temperature": 0.0, "seed": SEED,
                "max_prompt_tokens": 16000, "max_completion_tokens": 8192,
                "max_retries": 0, "timeout_seconds": 90.0,
            },
            system_prompt=module.SYSTEM_PROMPT, structured=(mode == "structured"),
            schemas=schemas, contract_to_arm=contract_to_arm,
        )
        for mode in ("plain", "structured")
    }
    preflight_rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(selected):
        for run_mode, provider in providers.items():
            input_obj = X16Input(module.common_input(case))
            hashes = []
            for arm in ARMS:
                audited = provider.build_audited_request(MODES_X17[arm], input_obj, arm_contracts[arm])
                hashes.append(normalized_hash(audited))
            fairness = len(set(hashes)) == 1
            preflight_rows.append({
                "case_id": case["case_id"], "family": case["primary_family"],
                "mode": run_mode, "arm_cells": 4, "fairness_pass": fairness,
                "normalized_request_sha256": hashes[0] if fairness else "",
                "order": canonical_json(list(ARMS[case_index % 4:] + ARMS[:case_index % 4])),
            })
    if len(preflight_rows) != 12 or not all(row["fairness_pass"] for row in preflight_rows):
        raise RuntimeError("X17 Stage A preflight fairness failed")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_csv(output_dir / "00_PREFLIGHT.csv", preflight_rows, list(preflight_rows[0]))
    (output_dir / "01_INTERFACE_FREEZE.txt").write_text(
        canonical_json({
            "selected_case_ids": [case["case_id"] for case in selected],
            "selected_case_families": [case["primary_family"] for case in selected],
            "schema_sha256": {arm: stable_hash(schema) for arm, schema in schemas.items()},
            "contract_sha256": {arm: stable_hash(text) for arm, text in arm_contracts.items()},
            "semantic_to_neutral": mapping, "freeze_files_verified": len(freeze_hashes),
            "runtime_git_commit": runtime_commit, "provider_calls": 0,
        }) + "\n", encoding="utf-8",
    )
    if args.preflight_only:
        return 0
    if not os.environ.get(args.api_key_env):
        raise RuntimeError(f"credential environment variable {args.api_key_env} is not set")
    rows: list[dict[str, Any]] = []
    with (output_dir / "02_CALL_JOURNAL.txt").open("x", encoding="utf-8") as journal:
        for case_index, case in enumerate(selected):
            order = ARMS[case_index % 4:] + ARMS[:case_index % 4]
            for run_mode, provider in providers.items():
                triplet: list[dict[str, Any]] = []
                for position, arm in enumerate(order, start=1):
                    invocation = provider.call_contract(
                        MODES_X17[arm], X16Input(module.common_input(case)), arm_contracts[arm]
                    )
                    row = evaluate(module, case, run_mode, arm, position, invocation, provider, mapping)
                    triplet.append(row)
                    journal.write(canonical_json({
                        "case_id": case["case_id"], "mode": run_mode,
                        "arm": arm, "row": row, "raw_response": invocation.raw_response,
                    }) + "\n")
                    journal.flush()
                fairness = len({row["input_hash"] for row in triplet}) == 1 and len({
                    row["common_input_bytes_sha256"] for row in triplet
                }) == 1 and len({row["normalized_request_sha256"] for row in triplet}) == 1
                for row in triplet:
                    row["fairness_pass"] = fairness
                rows.extend(triplet)
    write_csv(output_dir / "03_PER_ARM_RESULTS.csv", rows, FIELDS)
    aggregate: list[dict[str, Any]] = []
    for run_mode in ("plain", "structured"):
        for arm in ARMS:
            chosen = [row for row in rows if row["mode"] == run_mode and row["arm"] == arm]
            aggregate.append({
                "mode": run_mode, "arm": arm, "assigned": len(chosen),
                "provider_ok": sum(row["provider_status"] == "ok" for row in chosen),
                "parser_valid": sum(bool(row["parser_valid"]) for row in chosen),
                "semantic_correct": sum(bool(row["semantic_correct"]) for row in chosen),
                "unsafe_mutation_attempts": sum(bool(row["unsafe_mutation_attempt"]) for row in chosen),
                "completion_tokens": sum(int(row["completion_tokens"]) for row in chosen),
                "proposal_bytes": sum(int(row["proposal_bytes"]) for row in chosen),
                "latency_seconds": f"{sum(float(row['latency_seconds']) for row in chosen):.6f}",
            })
    write_csv(output_dir / "04_AGGREGATE.csv", aggregate, list(aggregate[0]))
    structured_sparse = {
        row["arm"]: int(row["semantic_correct"])
        for row in aggregate if row["mode"] == "structured" and row["arm"] in {
            "cope", "neutral_typed", "compact_tx"
        }
    }
    stage_a_pass = all(value >= 4 for value in structured_sparse.values())
    (output_dir / "05_RUN_STATUS.txt").write_text(
        canonical_json({
            "decision": "PASS" if stage_a_pass else "FAIL",
            "stage_a_threshold": "each structured sparse arm >=4/6",
            "structured_sparse_correct": structured_sparse,
            "provider_calls": len(rows), "fair_quadruplets": 12,
            "retry_budget": 0, "repair_budget": 0, "fallback_used": False,
            "oracle_substitution": False, "reserved_states_read": False,
            "runtime_git_commit": runtime_commit,
        }) + "\n", encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
