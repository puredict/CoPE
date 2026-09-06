#!/usr/bin/env python3
"""R4 development diagnostics and frozen-budget free-running episodes (no retries)."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from cope.lineage_benchmark.client import ModelClient, OpenAICompatibleClient, OracleModelClient
from cope.lineage_benchmark.models import ScenarioSpec
from cope.lineage_benchmark.runner import run_episode
from cope.lineage_benchmark.task import build_scenario


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class DrainCheckedClient(ModelClient):
    """Do not let a timed-out request contaminate the next method's latency."""
    def __init__(self, inner, base_url):
        self.inner, self.base_url = inner, base_url.rstrip("/")

    def generate(self, **kwargs):
        result = self.inner.generate(**kwargs)
        if (result.status in ("timeout", "client_timeout", "transport_or_response_error", "incomplete_stream")
                or result.cancellation_status == "connection_closed_server_status_unknown"):
            samples = []
            for _ in range(15):
                try:
                    with urlopen(self.base_url + "/metrics", timeout=3) as response:
                        metrics = response.read().decode()
                    running = [float(x) for x in re.findall(
                        r'^vllm:num_requests_(?:running|waiting)(?:\{[^\n]*\})?\s+([0-9.eE+-]+)',
                        metrics, re.MULTILINE)]
                    samples.append({"seconds_after_return": len(samples), "queues": running})
                    if len(running) >= 2 and sum(running) == 0:
                        result.telemetry["server_drain"] = {"confirmed_idle": True, "samples": samples}
                        break
                except Exception as exc:
                    samples.append({"error": str(exc)})
                time.sleep(1)
            else:
                result.telemetry["server_drain"] = {"confirmed_idle": False, "samples": samples}
                # Preserve this call's evidence before preventing further requests.
                self.blocked = True
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs_r4/experiment.json")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--budget", required=True)
    parser.add_argument("--mode", choices=("reference_diagnostic", "free_running"), default="free_running")
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--profiles", nargs="+")
    parser.add_argument("--methods", nargs="+", choices=("CoPE", "FSR-PC"))
    parser.add_argument("--client", choices=("openai", "oracle"), default="openai")
    parser.add_argument("--backend", choices=("symbolic_basket", "libero_mujoco"), default="symbolic_basket")
    parser.add_argument("--base-url")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    budget = cfg["budgets"][args.budget]
    if budget.get("max_output_tokens") is None or budget.get("timeout_s") is None:
        raise ValueError("budget pending: freeze with measured development capacity/throughput first")
    if budget.get("status") != "frozen":
        raise ValueError("budget is not frozen; numeric trial values alone are not acceptance")
    registered = cfg[args.split + "_seeds"]
    seeds = args.seeds or registered
    if not set(seeds) <= set(registered):
        raise ValueError("requested seeds are not in the registered split")
    if args.mode == "reference_diagnostic" and (args.split != "development" or args.backend != "symbolic_basket"):
        raise ValueError("reference-fed diagnostics are development-only and never physically executed")
    if args.split == "test" and (
        cfg.get("protocol_phase") != "phase1_frozen_evaluation"
        or cfg["budgets"]["adequate"].get("status") != "frozen"
        or not cfg.get("development_acceptance", {}).get("passed")
    ):
        raise ValueError("test runs require completed development freeze and explicit acceptance")
    profiles = args.profiles or list(cfg["profiles"])
    methods = args.methods or cfg["methods"]
    if not set(methods) <= set(cfg["methods"]):
        raise ValueError("unregistered method")
    args.out.mkdir(parents=True, exist_ok=False)
    model = cfg["model"]
    base_url = args.base_url or model["base_url"]
    client = OracleModelClient() if args.client == "oracle" else DrainCheckedClient(
        OpenAICompatibleClient(base_url=base_url, model=model["name"],
                               api_key=os.environ.get(model.get("api_key_env", ""), "EMPTY"),
                               guided_decoding_backend=model.get("guided_decoding_backend", "xgrammar"),
                               seed=model["seed"]), base_url)
    save(args.out / "config_resolved.json", {**cfg, "run": {
        "utc": datetime.now(timezone.utc).isoformat(), "budget": args.budget,
        "mode": args.mode, "split": args.split, "seeds": seeds, "profiles": profiles,
        "methods": methods, "client": args.client, "backend": args.backend,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in (ROOT / "code/cope/lineage_benchmark", ROOT / "scripts")
            for path in sorted(folder.glob("*.py"))},
        "test_metrics": args.split == "test", "generation_retries": 0,
        "method_order": "reverse on odd seed", "base_url": base_url}})
    rows = []
    backend_config = ROOT / cfg["physical_backend"]["config"]
    for profile in profiles:
        setting = cfg["profiles"][profile]
        for seed in seeds:
            scenario = build_scenario(ScenarioSpec(seed=seed, profile=profile,
                initial_slots=setting["initial_slots"], lineage_depth=setting["lineage_depth"],
                max_output_tokens=budget["max_output_tokens"], model_timeout_s=budget["timeout_s"]))
            ordered = methods if seed % 2 == 0 else list(reversed(methods))
            for method in ordered:
                print(f"run budget={args.budget} mode={args.mode} profile={profile} seed={seed} method={method}", flush=True)
                row = run_episode(scenario, method=method, client=client,
                    episode_dir=args.out / profile / method / f"seed_{seed:04d}",
                    backend=args.backend, backend_config=backend_config,
                    model_name=model["name"] if args.client == "openai" else "local-oracle-not-model-result",
                    diagnostic_reference_inputs=args.mode == "reference_diagnostic")
                rows.append({"profile": profile, "seed": seed, "method": method, "metrics": row["metrics"]})
                save(args.out / "summary.json", rows)
                print(json.dumps(rows[-1]), flush=True)
                if getattr(client, "blocked", False):
                    raise RuntimeError("server idle not confirmed after failure; stop rather than overlap requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
