#!/usr/bin/env python3
"""Check files, prompt sizes, server health, and optional live model behavior."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from cope.lineage_benchmark.adapters import ADAPTERS  # noqa: E402
from cope.lineage_benchmark.client import OpenAICompatibleClient, OracleModelClient  # noqa: E402
from cope.lineage_benchmark.models import ModelPacket, ScenarioSpec, canonical_json  # noqa: E402
from cope.lineage_benchmark.prompts import user_prompt  # noqa: E402
from cope.lineage_benchmark.state import apply_patch_document  # noqa: E402
from cope.lineage_benchmark.task import build_scenario, oracle_patch  # noqa: E402


def approx_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def packet_for(scenario, state, event, history):
    return ModelPacket(
        task_contract=scenario.task_contract,
        current_state=state,
        event=event,
        event_history=tuple(history),
        completed_actions=(),
        world_state={
            "available_targets": ["basket_A", "basket_B", "basket_C"],
            "robot_holding": None,
            "physical_execution_deferred_until_final_state": True,
        },
        compute_budget={
            "max_model_calls": 1,
            "max_output_tokens": scenario.spec.max_output_tokens,
            "timeout_s": scenario.spec.model_timeout_s,
        },
    )


def profile_sizes(config):
    rows = {}
    for name, profile in config["profiles"].items():
        spec = ScenarioSpec(
            seed=0,
            profile=name,
            initial_slots=int(profile["initial_slots"]),
            lineage_depth=int(profile["lineage_depth"]),
            max_output_tokens=int(config["shared_budget"]["max_output_tokens"]),
            model_timeout_s=float(config["shared_budget"]["timeout_s"]),
        )
        scenario = build_scenario(spec)
        state = scenario.initial_state
        history = []
        prompts, patches, full_states = [], [], []
        for event in scenario.events:
            packet = packet_for(scenario, state, event, history)
            patch = oracle_patch(state, event)
            next_state = apply_patch_document(
                state, patch, event, scenario.critical_logical_id
            )
            prompts.append(approx_tokens(user_prompt(packet)))
            patches.append(approx_tokens(canonical_json(patch)))
            full_states.append(approx_tokens(canonical_json(next_state.to_dict())))
            history.append(event.to_dict())
            state = next_state
        context_limit = int(config["model"]["max_context_tokens"])
        rows[name] = {
            "events": len(scenario.events),
            "initial_slots": spec.initial_slots,
            "lineage_depth": spec.lineage_depth,
            "approx_prompt_tokens_max": max(prompts),
            "approx_patch_tokens_max": max(patches),
            "approx_full_state_tokens_max": max(full_states),
            "registered_output_budget": spec.max_output_tokens,
            "registered_context_limit": context_limit,
            "prompt_plus_output_fits_char4_estimate": (
                max(prompts) + spec.max_output_tokens <= context_limit
            ),
            "full_state_fits_char4_estimate": max(full_states) <= spec.max_output_tokens,
            "note": "four characters/token is diagnostic only; live tokenizer usage is authoritative",
        }
    return rows


def server_models(base_url: str, timeout_s: float):
    with urlrequest.urlopen(base_url.rstrip("/") + "/v1/models", timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs_r3" / "experiment.json")
    parser.add_argument("--server", action="store_true", help="require /v1/models health")
    parser.add_argument("--live-call", action="store_true", help="make one event call for both methods")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--check-libero", action="store_true")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base_url = args.base_url or config["model"]["base_url"]
    model = args.model or config["model"]["name"]
    report = {
        "schema_version": "cope-fsrpc-r3-preflight-v1",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "config": str(config_path),
        "required_files": {},
        "profile_size_diagnostics": profile_sizes(config),
        "server": {"requested": args.server or args.live_call},
        "libero": {"requested": args.check_libero},
    }
    required = [
        ROOT / "configs_gpu" / "task_assets.yaml",
        ROOT / "configs_gpu" / "cope_basket_sorting.bddl",
        ROOT / "code" / "cope" / "backends" / "libero_mujoco.py",
        ROOT / "code" / "cope" / "lineage_benchmark" / "runner.py",
    ]
    report["required_files"] = {str(path.relative_to(ROOT)): path.is_file() for path in required}
    ok = all(report["required_files"].values())
    if not all(
        row["prompt_plus_output_fits_char4_estimate"]
        for row in report["profile_size_diagnostics"].values()
    ):
        ok = False

    try:
        gpu_text = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        report["gpus"] = [line.strip() for line in gpu_text.splitlines() if line.strip()]
    except Exception as exc:
        report["gpus"] = []
        report["gpu_note"] = str(exc)

    if args.server or args.live_call:
        try:
            models = server_models(base_url, 10.0)
            available = [item.get("id") for item in models.get("data", [])]
            report["server"].update({"healthy": True, "base_url": base_url, "models": available})
            if model not in available:
                report["server"]["warning"] = f"configured model {model!r} not listed"
        except Exception as exc:
            report["server"].update({"healthy": False, "error": str(exc)})
            ok = False

    if args.live_call and ok:
        profile = config["profiles"]["calibration"]
        spec = ScenarioSpec(
            seed=0,
            profile="calibration",
            initial_slots=int(profile["initial_slots"]),
            lineage_depth=int(profile["lineage_depth"]),
            max_output_tokens=int(config["shared_budget"]["max_output_tokens"]),
            model_timeout_s=float(config["shared_budget"]["timeout_s"]),
        )
        scenario = build_scenario(spec)
        packet = packet_for(scenario, scenario.initial_state, scenario.events[0], [])
        client = OpenAICompatibleClient(
            base_url=base_url,
            model=model,
            api_key=os.environ.get(config["model"].get("api_key_env", ""), "EMPTY"),
            seed=int(config["model"]["seed"]),
        )
        live = {}
        for method in ("CoPE", "FSR-PC"):
            result = ADAPTERS[method](client).adapt(packet)
            live[method] = {
                "ok": result.ok,
                "status": result.status,
                "semantic_match": result.semantic_match,
                "generation": result.generation.to_dict(),
                "validation_errors": result.validation_errors,
            }
            ok = ok and result.ok
        report["live_call"] = live

    if args.check_libero:
        try:
            from cope.backends import make_backend

            backend_config = (ROOT / config["physical_backend"]["config"]).resolve()
            meta = make_backend("libero_mujoco").initialize(backend_config)
            report["libero"].update({"available": True, "meta": meta})
        except Exception as exc:
            report["libero"].update({"available": False, "error": f"{type(exc).__name__}: {exc}"})
            ok = False

    report["passed"] = ok
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
