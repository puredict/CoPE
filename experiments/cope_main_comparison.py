from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope.config import load_comparison_config
from cope.detector import load_detector_factory
from cope.engine import load_engine_factory
from cope.libero_backend import LiberoComparisonBackend
from cope.pairing import load_atlas, select_pairs
from cope.providers.base import load_provider_factory
from cope.runner import ComparisonRunner, readiness_report
from cope.types import METHOD_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strictly paired CoPE versus full-regeneration experiment.")
    parser.add_argument("--config", default="configs/cope_main_comparison_v1.yaml")
    parser.add_argument("--manifest", default=None, help="Override disturbance manifest path.")
    parser.add_argument("--phase", choices=("pilot", "formal", "detected"), required=True)
    parser.add_argument("--event-source", choices=("oracle", "detected"), default=None)
    parser.add_argument("--provider-factory", default=None, help="module:factory provider adapter")
    parser.add_argument("--engine-factory", default=None, help="module:factory CoPE engine adapter")
    parser.add_argument("--detector-factory", default=None, help="module:factory event detector adapter")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--readiness-report", default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--emit-schedule", action="store_true")
    parser.add_argument("--allow-test-fixtures", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_schedule(path: Path, pairs: tuple[Any, ...], phase: str, event_source: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for pair in pairs:
            for method in METHOD_NAMES:
                handle.write(
                    json.dumps(
                        {
                            "phase": phase,
                            "event_source": event_source,
                            "pair_key": pair.pair_key,
                            "task_id": pair.task_id,
                            "initial_state_id": pair.initial_state_id,
                            "seed": pair.seed,
                            "method": method,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    config = load_comparison_config(config_path)
    event_source = args.event_source or ("detected" if args.phase == "detected" else config.event_source)
    config = replace(config, event_source=event_source)
    manifest_path = Path(args.manifest or config.disturbance_manifest)
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path
    manifest = load_atlas(manifest_path)

    provider_spec = args.provider_factory or config.provider.get("factory")
    engine_spec = args.engine_factory or config.engine.get("factory")
    detector_spec = args.detector_factory or (config.provider.get("detector") or {}).get("factory")
    provider = None
    engine_factory = None
    detector_factory = None
    factory_errors: list[str] = []
    if provider_spec:
        try:
            provider = load_provider_factory(str(provider_spec))(config.provider)
        except Exception as exc:
            factory_errors.append(f"provider factory failed: {type(exc).__name__}: {exc}")
    if engine_spec:
        try:
            engine_factory = load_engine_factory(str(engine_spec))
        except Exception as exc:
            factory_errors.append(f"engine factory failed: {type(exc).__name__}: {exc}")
    if detector_spec:
        try:
            detector_factory = load_detector_factory(str(detector_spec))
        except Exception as exc:
            factory_errors.append(f"detector factory failed: {type(exc).__name__}: {exc}")

    backend = None
    if provider is not None:
        backend = LiberoComparisonBackend(
            config=config,
            provider=provider,
            detector_factory=detector_factory,
            detector_config=dict(config.provider.get("detector") or {}),
        )
    report = readiness_report(
        config=config,
        phase=args.phase,
        event_source=event_source,
        manifest=manifest,
        provider=provider,
        engine_factory=engine_factory,
        backend=backend,
        repo_root=repo_root,
        allow_test_fixtures=args.allow_test_fixtures,
    )
    if factory_errors:
        report["ready"] = False
        report["blockers"].extend(factory_errors)
        report["checks"].append(
            {"name": "factory_loading", "passed": False, "detail": "; ".join(factory_errors)}
        )

    default_report = repo_root / "docs" / "audit" / f"cope_main_{args.phase}_readiness.json"
    report_path = Path(args.readiness_report) if args.readiness_report else default_report
    if not report_path.is_absolute():
        report_path = repo_root / report_path
    _write_json(report_path, report)

    if args.emit_schedule:
        selection = config.selection(args.phase)
        try:
            pairs = select_pairs(
                manifest.pairs,
                task_ids=selection.task_ids,
                initial_state_ids=selection.initial_state_ids,
                seeds=selection.seeds,
            )
        except ValueError as exc:
            report["schedule_error"] = str(exc)
        else:
            schedule_path = report_path.with_name(f"cope_main_{args.phase}_schedule.jsonl")
            _write_schedule(schedule_path, pairs, args.phase, event_source)
            report["schedule_path"] = str(schedule_path)
        _write_json(report_path, report)
    print(json.dumps({"readiness_report": str(report_path), **report}, indent=2), flush=True)

    if args.validate_only:
        raise SystemExit(0 if report["ready"] else 2)
    if not report["ready"]:
        raise SystemExit("refusing to run: readiness report has blockers")
    if provider is None or engine_factory is None or backend is None:
        raise SystemExit("refusing to run: provider, engine, and backend are required")
    if provider.metadata.is_fake:
        raise SystemExit("refusing to run rollouts with deterministic fake provider")

    output_dir = Path(args.out_dir) if args.out_dir else (
        Path(config.output_root) / f"{args.phase}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    )
    runner = ComparisonRunner(
        config=config,
        phase=args.phase,
        event_source=event_source,
        manifest=manifest,
        provider=provider,
        engine_factory=engine_factory,
        backend=backend,
        repo_root=repo_root,
        output_dir=output_dir,
    )
    summary = runner.run(resume=args.resume)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    if not summary["complete"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
