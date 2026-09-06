#!/usr/bin/env python3
"""Measure exact development-set serialization capacity; optionally freeze R4.

No model/server calls occur here. The tokenizer must already exist locally.
Reference state transitions use the independent specification implementation.
"""

from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cope.lineage_benchmark.models import ModelPacket, ScenarioSpec, canonical_json  # noqa: E402
from cope.lineage_benchmark.prompts import system_prompt, user_prompt  # noqa: E402
from cope.lineage_benchmark.reference import reference_transition  # noqa: E402
from cope.lineage_benchmark.task import build_scenario  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def round_up(value: float, quantum: int) -> int:
    if not math.isfinite(value) or value <= 0 or quantum <= 0:
        raise ValueError("rounding requires positive finite value and quantum")
    return int(math.ceil(value / quantum) * quantum)


def reference_patch(state: Any, event: Any) -> dict[str, Any]:
    """Hand-written reference output; never execute the CoPE updater here."""
    names = {
        "suspend_current": "suspend", "restore_current": "restore",
        "override_current": "override", "restore_root": "restore_root",
    }
    operation = {"op": names[event.kind]}
    operation["from_slot_id" if event.kind == "restore_root" else "slot_id"] = event.current_slot_id
    if event.kind == "override_current":
        operation["new_slot"] = copy.deepcopy(event.new_slot)
    return {
        "schema_version": "cope-lineage-patch-v1", "event_id": event.event_id,
        "base_revision": state.revision, "ops": [operation],
    }


def development_rows(config: dict[str, Any], tokenizer: Any, budget: dict[str, Any],
                     condition: str, max_context: int) -> list[dict[str, Any]]:
    rows = []
    for profile, dimensions in config["profiles"].items():
        for seed in config["development_seeds"]:
            scenario = build_scenario(ScenarioSpec(
                seed=int(seed), profile=profile,
                initial_slots=int(dimensions["initial_slots"]),
                lineage_depth=int(dimensions["lineage_depth"]),
                max_output_tokens=int(budget["max_output_tokens"]),
                model_timeout_s=float(budget["timeout_s"]),
            ))
            state = scenario.initial_state
            history = []
            for event in scenario.events:
                next_state = reference_transition(state, event, scenario.critical_logical_id)
                packet = ModelPacket(
                    task_contract=scenario.task_contract, current_state=state, event=event,
                    event_history=tuple(history), completed_actions=(),
                    world_state={
                        "available_targets": ["basket_A", "basket_B", "basket_C"],
                        "robot_holding": None,
                        "physical_execution_deferred_until_final_state": True,
                    },
                    compute_budget={
                        "max_model_calls": 1,
                        "max_output_tokens": int(budget["max_output_tokens"]),
                        "timeout_s": float(budget["timeout_s"]),
                    },
                )
                for method in config["methods"]:
                    document = reference_patch(state, event) if method == "CoPE" else next_state.to_dict()
                    if method not in {"CoPE", "FSR-PC"}:
                        raise ValueError(f"no independent capacity reference for {method}")
                    messages = [
                        {"role": "system", "content": system_prompt(method)},
                        {"role": "user", "content": user_prompt(packet)},
                    ]
                    prompt_ids = tokenizer.apply_chat_template(
                        messages, tokenize=True, add_generation_prompt=True, enable_thinking=False,
                    )
                    rendered = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
                    )
                    pretty = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
                    compact = canonical_json(document)
                    pretty_tokens = len(tokenizer.encode(pretty, add_special_tokens=False))
                    compact_tokens = len(tokenizer.encode(compact, add_special_tokens=False))
                    prompt_tokens = len(prompt_ids)
                    rows.append({
                        "budget_condition": condition, "split": "development", "profile": profile,
                        "seed": int(seed), "method": method, "event_ordinal": event.ordinal,
                        "event_kind": event.kind, "event_id": event.event_id,
                        "initial_slots": scenario.spec.initial_slots,
                        "lineage_depth": scenario.spec.lineage_depth,
                        "current_slots": len(state.slots), "reference_slots": len(next_state.slots),
                        "prompt_tokens": prompt_tokens,
                        "reference_pretty_output_tokens": pretty_tokens,
                        "reference_compact_output_tokens": compact_tokens,
                        "reference_pretty_fits_original4096": pretty_tokens <= 4096,
                        "reference_compact_fits_original4096": compact_tokens <= 4096,
                        "required_context_pretty": prompt_tokens + pretty_tokens,
                        "required_context_compact": prompt_tokens + compact_tokens,
                        "server_max_context_tokens": max_context,
                        "reference_pretty_fits_context": prompt_tokens + pretty_tokens <= max_context,
                        "reference_compact_fits_context": prompt_tokens + compact_tokens <= max_context,
                        "requested_max_output_tokens": int(budget["max_output_tokens"]),
                        "request_reservation_context_tokens": prompt_tokens + int(budget["max_output_tokens"]),
                        "request_reservation_fits_context": prompt_tokens + int(budget["max_output_tokens"]) <= max_context,
                        "configured_timeout_s": float(budget["timeout_s"]),
                        "rendered_prompt_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                        "reference_document_sha256": hashlib.sha256(compact.encode()).hexdigest(),
                        "reference_source": "independent_reference_transition",
                    })
                history.append({
                    "event_id": event.event_id, "ordinal": event.ordinal, "kind": event.kind,
                    "current_slot_id": event.current_slot_id, "user_request": event.user_request,
                    "reason": event.reason, "new_slot": event.new_slot,
                })
                state = next_state
    return rows


def measured_timeout(path: Path, config: dict[str, Any], output_tokens: int,
                     max_context: int) -> tuple[int, dict[str, Any]]:
    """Use observed warmed serial service performance, never assume TP throughput."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    server = raw.get("server", {})
    required = {"model", "model_revision", "tensor_parallel_size", "dtype", "enforce_eager",
                "max_model_len", "concurrency"}
    if not required <= server.keys():
        raise ValueError(f"throughput server identity missing {sorted(required - server.keys())}")
    if server["model"] != config["model"]["name"] or server["model_revision"] != config["model"]["revision"]:
        raise ValueError("throughput measurements must use the registered model and revision")
    if int(server["max_model_len"]) != max_context or int(server["concurrency"]) != 1:
        raise ValueError("throughput evidence must match context limit and serial concurrency=1")
    if server.get("guided_decoding_backend") != config["model"].get("guided_decoding_backend"):
        raise ValueError("throughput decoding backend must match the current configured backend")
    samples = raw.get("samples", [])
    usable = []
    for item in samples:
        if item.get("status") != "ok" or item.get("finish_reason") != "stop" or item.get("warmed") is not True:
            continue
        if int(item.get("seed", -1)) not in config["development_seeds"]:
            raise ValueError("test outcomes must not enter throughput calibration")
        if item.get("method") not in config["methods"] or item.get("profile") not in config["profiles"]:
            raise ValueError("unregistered throughput method/profile")
        completion = int(item["completion_tokens"])
        elapsed, first = float(item["latency_s"]), float(item["ttft_s"])
        if completion < 2 or not (0 <= first < elapsed) or not all(map(math.isfinite, [elapsed, first])):
            raise ValueError("invalid throughput timing/count; require actual TTFT and completed call")
        usable.append({**item, "observed_decode_tokens_per_second": (completion - 1) / (elapsed - first)})
    for method in config["methods"]:
        count = sum(item["method"] == method for item in usable)
        if count < (2 if method == "FSR-PC" else 1):
            raise ValueError(f"need warmed successful development measurements for {method}")
    slowest = min(item["observed_decode_tokens_per_second"] for item in usable)
    largest_ttft = max(float(item["ttft_s"]) for item in usable)
    policy = config["budget_freeze_policy"]
    estimate = largest_ttft + (output_tokens - 1) / slowest
    timeout = round_up(estimate * float(policy["timeout_margin_factor"]),
                       int(policy["timeout_round_to_seconds"]))
    return timeout, {
        "source": str(path.resolve()), "source_sha256": sha256_file(path), "server": server,
        "successful_warmed_samples": len(usable), "all_supplied_samples": len(samples),
        "slowest_observed_decode_tokens_per_second": slowest,
        "largest_observed_ttft_s": largest_ttft,
        "largest_measured_prompt_tokens": max(int(item["prompt_tokens"]) for item in usable),
        "largest_completed_output_tokens": max(int(item["completion_tokens"]) for item in usable),
        "extrapolated_full_budget_time_before_margin_s": estimate,
        "timeout_s": timeout,
        "interpretation": "Conservative throughput-based extrapolation, not a guaranteed completion bound.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs_r4" / "experiment.json")
    parser.add_argument("--tokenizer", type=Path, required=True, help="Existing local fixed-model tokenizer snapshot")
    parser.add_argument("--out", type=Path, required=True, help="New directory; existing outputs are never overwritten")
    parser.add_argument("--max-context-tokens", type=int, required=True, help="Actual server max_model_len, not model advertising")
    parser.add_argument("--throughput-measurements", type=Path)
    parser.add_argument("--freeze-config", type=Path, help="New resolved config file; requires measured throughput and capacity fit")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("schema_version") != "cope-fsrpc-r4-config-v1":
        raise ValueError("R4 config required")
    if args.out.exists() or (args.freeze_config and args.freeze_config.exists()):
        raise FileExistsError("refusing to overwrite audit or frozen configuration")
    if not args.tokenizer.is_dir() or args.max_context_tokens < 1:
        raise ValueError("require a local tokenizer directory and positive actual context limit")
    if set(config["development_seeds"]) & set(config["test_seeds"]):
        raise ValueError("development and test seeds must be disjoint")
    if args.freeze_config and not args.throughput_measurements:
        raise ValueError("cannot freeze an adequate timeout without real throughput evidence")
    from transformers import AutoTokenizer, __version__ as transformers_version
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True, trust_remote_code=False)
    template = tokenizer.get_chat_template()
    if "enable_thinking" not in template:
        raise ValueError("registered Qwen tokenizer template must expose enable_thinking")
    rows = development_rows(config, tokenizer, config["budgets"]["fixed"], "fixed", args.max_context_tokens)
    maximum_reference = max(max(row["reference_pretty_output_tokens"], row["reference_compact_output_tokens"]) for row in rows)
    policy = config["budget_freeze_policy"]
    proposed_output = round_up(maximum_reference * (1 + float(policy["output_margin_fraction"])),
                               int(policy["output_round_to_tokens"]))
    proposed_output = max(proposed_output, int(config["budgets"]["fixed"]["max_output_tokens"]))
    throughput = None
    adequate_budget = {"status": "pending_measured_throughput", "max_output_tokens": proposed_output,
                       "timeout_s": None, "calls_per_event": 1}
    frozen = None
    blockers = []
    if args.throughput_measurements:
        timeout, throughput = measured_timeout(args.throughput_measurements, config, proposed_output,
                                              args.max_context_tokens)
        adequate_budget.update({"status": "capacity_checked", "timeout_s": float(timeout)})
        adequate_rows = development_rows(config, tokenizer, adequate_budget, "adequate", args.max_context_tokens)
        rows.extend(adequate_rows)
        if any(not row["request_reservation_fits_context"] for row in adequate_rows):
            blockers.append("actual server context cannot reserve the global adequate output budget for every development prompt")
        max_prompt = max(row["prompt_tokens"] for row in adequate_rows)
        if throughput["largest_measured_prompt_tokens"] < 0.9 * max_prompt:
            blockers.append("throughput measurements lack a representative long prompt (at least 90% of audited maximum)")
        if not blockers and args.freeze_config:
            frozen = copy.deepcopy(config)
            frozen["model"]["max_context_tokens"] = args.max_context_tokens
            frozen["budgets"]["adequate"] = {
                **adequate_budget, "status": "frozen", "provenance": {
                    "capacity_report": str((args.out / "capacity_report.json").resolve()),
                    "throughput_source_sha256": throughput["source_sha256"],
                    "development_seeds": config["development_seeds"],
                    "maximum_reference_output_tokens": maximum_reference,
                    "output_margin_fraction": policy["output_margin_fraction"],
                    "output_round_to_tokens": policy["output_round_to_tokens"],
                    "server": throughput["server"],
                },
            }
            adequate_budget["status"] = "frozen"
    else:
        blockers.append("adequate timeout is pending actual warmed serial throughput measurements")
    token_files = {}
    for filename in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.json", "merges.txt", "config.json"):
        candidate = args.tokenizer / filename
        if candidate.is_file():
            token_files[filename] = sha256_file(candidate)
    report = {
        "schema_version": "cope-fsrpc-r4-capacity-v1", "utc": datetime.now(timezone.utc).isoformat(),
        "config_source": str(args.config.resolve()), "config_sha256": sha256_file(args.config),
        "tokenizer_path": str(args.tokenizer.resolve()), "tokenizer_file_sha256": token_files,
        "transformers_version": transformers_version, "chat_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "enable_thinking": False, "add_generation_prompt": True,
        "server_max_context_tokens": args.max_context_tokens,
        "development_seeds": config["development_seeds"], "profiles": config["profiles"],
        "row_count": len(rows), "maximum_reference_output_tokens": maximum_reference,
        "maximum_prompt_tokens": max(row["prompt_tokens"] for row in rows),
        "maximum_required_context_compact": max(row["required_context_compact"] for row in rows),
        "maximum_required_context_pretty": max(row["required_context_pretty"] for row in rows),
        "proposed_uniform_output_plus_max_fixed_prompt_tokens": proposed_output + max(
            row["prompt_tokens"] for row in rows if row["budget_condition"] == "fixed"
        ),
        "proposed_context_caveat": "Planning estimate using the fixed-budget prompt; frozen adequate prompts are re-tokenized after the measured timeout is known.",
        "adequate_budget_proposal": adequate_budget, "throughput_calibration": throughput,
        "freeze_blockers": blockers, "frozen_config": str(args.freeze_config.resolve()) if frozen else None,
        "measurement_scope": "Reference trajectory with correct independent preceding states; offline capacity diagnostic, not model correctness or performance.",
        "reference_length_caveat": "These are token counts of specific legal pretty/compact serializations, not a mathematical lower bound over all legal answers. JSON completion counts exclude any generated stop token; the global budget includes an explicit margin.",
        "prompt_caveat": "Includes each method's full system prompt, user packet, actual tokenizer chat template and assistant prefix. Guided JSON schema is an external decoding constraint, not serialized prompt text.",
        "row_file": "capacity_rows.csv",
    }
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.out / "capacity_rows.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (args.out / "capacity_report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
    if frozen:
        args.freeze_config.parent.mkdir(parents=True, exist_ok=True)
        with args.freeze_config.open("x", encoding="utf-8") as stream:
            json.dump(frozen, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
    print(json.dumps({key: report[key] for key in ("row_count", "maximum_reference_output_tokens", "adequate_budget_proposal", "freeze_blockers", "frozen_config")}, indent=2))
    return 2 if args.freeze_config and not frozen else 0


if __name__ == "__main__":
    raise SystemExit(main())
