#!/usr/bin/env python3
"""Run or analyse the fixed-LLM persistent-lineage experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "code", ROOT):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from cope.lineage_benchmark.analysis import analyse, load_results  # noqa: E402
from cope.lineage_benchmark.client import (  # noqa: E402
    OpenAICompatibleClient,
    OracleModelClient,
)
from cope.lineage_benchmark.models import ScenarioSpec  # noqa: E402
from cope.lineage_benchmark.runner import run_episode  # noqa: E402
from cope.lineage_benchmark.task import build_scenario  # noqa: E402
from cope.lineage_benchmark.world import make_world  # noqa: E402


def read_config(path: Path) -> Dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "cope-fsrpc-r3-config-v1":
        raise ValueError(f"unsupported config schema in {path}")
    return config


def scenario_spec(config: Dict[str, Any], profile: str, seed: int) -> ScenarioSpec:
    row = config["profiles"][profile]
    budget = config["shared_budget"]
    return ScenarioSpec(
        seed=seed,
        profile=profile,
        initial_slots=int(row["initial_slots"]),
        lineage_depth=int(row["lineage_depth"]),
        max_output_tokens=int(budget["max_output_tokens"]),
        model_timeout_s=float(budget["timeout_s"]),
    )


def make_client(args: argparse.Namespace, config: Dict[str, Any]):
    if args.client == "oracle":
        return OracleModelClient(enforce_budget=False), "local-oracle-unbudgeted"
    if args.client == "budgeted_oracle":
        return OracleModelClient(enforce_budget=True), "local-oracle-budgeted"
    model_cfg = config["model"]
    api_key = os.environ.get(str(model_cfg.get("api_key_env", "")), "EMPTY")
    name = args.model or str(model_cfg["name"])
    return (
        OpenAICompatibleClient(
            base_url=args.base_url or str(model_cfg["base_url"]),
            model=name,
            api_key=api_key,
            seed=int(model_cfg["seed"]),
        ),
        name,
    )


def resolved_backend_config(config_path: Path, config: Dict[str, Any]) -> Path:
    raw = Path(config["physical_backend"]["config"])
    return raw if raw.is_absolute() else (config_path.parent.parent / raw).resolve()


def run_gate(args: argparse.Namespace, config: Dict[str, Any], config_path: Path) -> int:
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    args.out.mkdir(parents=True)
    gate = config["nominal_gate"]
    n = args.seeds if args.seeds is not None else int(gate["seeds"])
    backend_config = resolved_backend_config(config_path, config)
    rows = []
    for seed in range(n):
        scenario = build_scenario(scenario_spec(config, "calibration", seed))
        seed_dir = args.out / f"seed_{seed:03d}"
        seed_dir.mkdir()
        result = make_world(args.backend).execute(
            scenario.expected_plan,
            scenario.expected_plan,
            seed=seed,
            episode_dir=seed_dir,
            backend_config=backend_config if args.backend == "libero_mujoco" else None,
        )
        rows.append({"seed": seed, "physical_success": result["physical_success"], "result": result})
    successes = sum(row["physical_success"] for row in rows)
    required = int(gate["required_successes"])
    report = {
        "schema_version": "cope-fsrpc-r3-gate-v1",
        "backend": args.backend,
        "successes": successes,
        "n": n,
        "required_successes": required,
        "passed": successes >= required,
        "rows": rows,
    }
    (args.out / "gate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"nominal gate: {successes}/{n}; required={required}; passed={report['passed']}")
    return 0 if report["passed"] else 2


def run_main(args: argparse.Namespace, config: Dict[str, Any], config_path: Path) -> int:
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    args.out.mkdir(parents=True)
    client, model_name = make_client(args, config)
    profiles = args.profiles or list(config["profiles"])
    methods = args.methods or list(config["methods"])
    n_seeds = args.seeds if args.seeds is not None else int(config["seeds"])
    backend_config = resolved_backend_config(config_path, config)
    resolved = {
        **config,
        "run": {
            "utc": datetime.now(timezone.utc).isoformat(),
            "client": args.client,
            "model": model_name,
            "backend": args.backend,
            "profiles": profiles,
            "methods": methods,
            "seeds": list(range(n_seeds)),
            "method_order_rule": "even seeds CoPE first; odd seeds FSR-PC first",
        },
    }
    (args.out / "config_resolved.json").write_text(
        json.dumps(resolved, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    rows: List[Dict[str, Any]] = []
    for profile in profiles:
        if profile not in config["profiles"]:
            raise ValueError(f"unknown profile {profile!r}")
        for seed in range(n_seeds):
            scenario = build_scenario(scenario_spec(config, profile, seed))
            ordered = list(methods)
            if seed % 2:
                ordered.reverse()
            for method in ordered:
                episode_dir = args.out / profile / method.replace("/", "_") / f"seed_{seed:03d}"
                print(f"run profile={profile} seed={seed} method={method}", flush=True)
                row = run_episode(
                    scenario,
                    method=method,
                    client=client,
                    episode_dir=episode_dir,
                    backend=args.backend,
                    backend_config=(backend_config if args.backend == "libero_mujoco" else None),
                    model_name=model_name,
                )
                rows.append(row)
                print(
                    f"  completion={row['metrics']['task_completion']} "
                    f"valid={row['metrics']['all_generations_valid']} "
                    f"failure={row['metrics']['first_failure'] or 'none'}",
                    flush=True,
                )

        calibration = config.get("calibration_gate", {})
        if profile == calibration.get("profile"):
            threshold = float(
                calibration.get("minimum_valid_generation_rate_per_method", 0.8)
            )
            rates = {}
            for method in methods:
                method_rows = [
                    row for row in rows
                    if row["profile"] == profile and row["method"] == method
                ]
                rates[method] = (
                    sum(row["metrics"]["all_generations_valid"] for row in method_rows)
                    / len(method_rows)
                    if method_rows else 0.0
                )
            gate_report = {
                "profile": profile,
                "minimum_valid_generation_rate_per_method": threshold,
                "valid_generation_rates": rates,
                "passed": bool(rates and all(rate >= threshold for rate in rates.values())),
            }
            (args.out / "calibration_gate.json").write_text(
                json.dumps(gate_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if not gate_report["passed"]:
                partial = analyse(rows, str(config["primary_profile"]))
                (args.out / "analysis.json").write_text(
                    json.dumps(partial, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8",
                )
                print(
                    "calibration generation gate failed; stopping before later profiles",
                    file=sys.stderr,
                )
                return 3

    report = analyse(rows, str(config["primary_profile"]))
    (args.out / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["primary"].get("task_completion", {}), indent=2))
    return 0


def run_analysis(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    rows = load_results(args.out)
    report = analyse(rows, str(config["primary_profile"]))
    target = args.out / "analysis.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target} from {len(rows)} episodes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("gate", "main", "analyse"), default="main")
    parser.add_argument("--config", type=Path, default=ROOT / "configs_r3" / "experiment.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--client", choices=("openai", "oracle", "budgeted_oracle"), default="openai")
    parser.add_argument("--backend", choices=("symbolic_basket", "libero_mujoco"), default="symbolic_basket")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--seeds", type=int)
    parser.add_argument("--profiles", nargs="+")
    parser.add_argument("--methods", nargs="+", choices=("CoPE", "FSR-PC"))
    args = parser.parse_args()
    config_path = args.config.expanduser().resolve()
    config = read_config(config_path)
    args.out = args.out.expanduser().resolve()
    if args.stage == "gate":
        return run_gate(args, config, config_path)
    if args.stage == "analyse":
        return run_analysis(args, config)
    return run_main(args, config, config_path)


if __name__ == "__main__":
    raise SystemExit(main())
