from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import uuid
import importlib.util
from importlib import metadata as importlib_metadata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from cope.config import ComparisonConfig
from cope.engine import EngineFactory, validate_engine
from cope.methods import build_method
from cope.methods.base import RecoveryMethod
from cope.pairing import AtlasManifest, PairSpec, select_pairs, validate_formal_atlas
from cope.providers.base import HighLevelRecoveryProvider
from cope.types import METHOD_NAMES
from cope.validation import read_jsonl, validate_episode_record, validate_run_records


@dataclass(frozen=True)
class RunContext:
    run_id: str
    phase: str
    event_source: str
    git_commit: str
    config_hash: str
    atlas_commit: str
    engine_commit: str
    output_dir: str


class ComparisonBackend(Protocol):
    name: str
    formal_capable: bool

    def readiness_errors(self, config: ComparisonConfig, *, formal: bool) -> list[str]: ...

    def run_episode(
        self,
        *,
        pair: PairSpec,
        method: RecoveryMethod,
        method_name: str,
        context: RunContext,
        episode_dir: Path,
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


def git_commit_and_clean(repo_root: str | Path) -> tuple[str, bool, str]:
    root = Path(repo_root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    return commit, not bool(status.strip()), status


def environment_manifest() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ("numpy", "torch", "transformers", "libero", "robosuite", "mujoco", "statsmodels"):
        try:
            packages[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "hostname": platform.node(),
        "packages": packages,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def _engine_commit(engine_factory: EngineFactory | None, engine_config: dict[str, Any], formal: bool) -> tuple[str, list[str]]:
    if engine_factory is None:
        return "", ["CoPE engine factory is not configured"]
    try:
        engine = engine_factory(engine_config)
        validate_engine(engine, formal=formal)
        return str(engine.metadata.get("engine_commit", "")), []
    except Exception as exc:
        return "", [f"CoPE engine readiness failed: {type(exc).__name__}: {exc}"]


def readiness_report(
    *,
    config: ComparisonConfig,
    phase: str,
    event_source: str,
    manifest: AtlasManifest,
    provider: HighLevelRecoveryProvider | None,
    engine_factory: EngineFactory | None,
    backend: ComparisonBackend | None,
    repo_root: str | Path,
    allow_test_fixtures: bool,
) -> dict[str, Any]:
    formal = phase in {"formal", "detected"}
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    commit, clean, status = git_commit_and_clean(repo_root)
    check("git_commit_recorded", bool(commit), commit)
    check("git_worktree_clean", clean or not formal, "clean" if clean else status.strip())
    check("six_condition_order", config.methods == METHOD_NAMES, repr(config.methods))
    check(
        "ranked_privileges_forbidden",
        not config.manual_intervention_allowed and not config.reset_allowed and not config.rollback_allowed,
        "manual=false reset=false rollback=false",
    )
    check("primary_oracle_event", event_source == ("detected" if phase == "detected" else "oracle"), event_source)
    selection = config.selection(phase)
    try:
        selected = select_pairs(
            manifest.pairs,
            task_ids=selection.task_ids,
            initial_state_ids=selection.initial_state_ids,
            seeds=selection.seeds,
        )
        selection_error = ""
    except Exception as exc:
        selected = ()
        selection_error = str(exc)
    check("complete_preregistered_pairs", len(selected) == selection.pair_count, selection_error or str(len(selected)))
    expected_episodes = selection.pair_count * len(METHOD_NAMES)
    check(
        "episode_count",
        expected_episodes == (24 if phase == "pilot" else 720 if phase == "formal" else selection.pair_count * 6),
        str(expected_episodes),
    )

    atlas_errors = validate_formal_atlas(manifest) if formal else []
    if manifest.fixture and not allow_test_fixtures:
        atlas_errors.append("test atlas requires --allow-test-fixtures")
    check("disturbance_atlas", not atlas_errors, "; ".join(atlas_errors) or manifest.digest)

    provider_errors: list[str] = []
    if provider is None:
        provider_errors.append("high-level provider is not configured")
    else:
        metadata = provider.metadata
        if formal and metadata.is_fake:
            provider_errors.append("fake provider is forbidden for formal/detected runs")
        if formal and (not metadata.provider or not metadata.model):
            provider_errors.append("formal provider must record provider and model identifiers")
        if metadata.max_prompt_tokens != config.information_budget.max_prompt_tokens:
            provider_errors.append("provider/config prompt token ceiling mismatch")
        if metadata.max_completion_tokens != config.information_budget.max_completion_tokens:
            provider_errors.append("provider/config completion token ceiling mismatch")
        configured_temperature = float(config.provider.get("temperature", metadata.temperature))
        if metadata.temperature != configured_temperature:
            provider_errors.append("provider/config temperature mismatch")
        configured_retries = int(config.provider.get("max_retries", metadata.max_retries))
        if metadata.max_retries != configured_retries:
            provider_errors.append("provider/config retry policy mismatch")
    check("high_level_provider", not provider_errors, "; ".join(provider_errors) or provider.metadata.fairness_fingerprint)

    engine_commit, engine_errors = _engine_commit(engine_factory, config.engine, formal)
    check("cope_engine", not engine_errors, "; ".join(engine_errors) or engine_commit)

    backend_errors: list[str] = []
    if backend is None:
        backend_errors.append("rollout backend is not configured")
    else:
        if formal and not backend.formal_capable:
            backend_errors.append("backend is not formal-capable")
        backend_errors.extend(backend.readiness_errors(config, formal=formal))
    check("rollout_backend", not backend_errors, "; ".join(backend_errors) or backend.name)

    checkpoint_exists = Path(config.checkpoint_path).exists()
    check("checkpoint", checkpoint_exists or not formal, config.checkpoint_path)
    check(
        "checkpoint_digest",
        bool(config.checkpoint_sha256) or not formal,
        config.checkpoint_sha256 or "missing checkpoint.sha256",
    )
    check(
        "external_dependency_commits",
        bool(manifest.atlas_commit and engine_commit) or not formal,
        f"atlas={manifest.atlas_commit or 'missing'} engine={engine_commit or 'missing'}",
    )
    analysis_missing = [
        module for module in ("numpy", "pandas", "statsmodels") if importlib.util.find_spec(module) is None
    ]
    check(
        "analysis_stack",
        not analysis_missing or not formal,
        "available" if not analysis_missing else f"missing {analysis_missing}",
    )
    blockers = [item["detail"] for item in checks if not item["passed"]]
    test_only = bool(
        manifest.fixture
        or (provider is not None and provider.metadata.is_fake)
        or (engine_factory is not None and engine_commit == "fixture-engine")
    )
    return {
        "schema_version": "cope-main-readiness-v1",
        "ready": not blockers,
        "phase": phase,
        "event_source": event_source,
        "git_commit": commit,
        "config_hash": config.config_hash,
        "manifest": {
            "path": manifest.path,
            "digest": manifest.digest,
            "atlas_commit": manifest.atlas_commit,
            "fixture": manifest.fixture,
        },
        "selected_pair_count": len(selected),
        "scheduled_episode_count": len(selected) * len(METHOD_NAMES),
        "engine_commit": engine_commit,
        "test_only": test_only,
        "rollout_authorized": not blockers and not test_only,
        "formal_evidence_eligible": formal and not blockers and not test_only,
        "checks": checks,
        "blockers": blockers,
    }


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


class ComparisonRunner:
    def __init__(
        self,
        *,
        config: ComparisonConfig,
        phase: str,
        event_source: str,
        manifest: AtlasManifest,
        provider: HighLevelRecoveryProvider,
        engine_factory: EngineFactory,
        backend: ComparisonBackend,
        repo_root: str | Path,
        output_dir: str | Path,
    ) -> None:
        self.config = config
        self.phase = phase
        self.event_source = event_source
        self.manifest = manifest
        self.provider = provider
        self.engine_factory = engine_factory
        self.backend = backend
        self.repo_root = Path(repo_root)
        self.output_dir = Path(output_dir)

    def run(self, *, resume: bool = False) -> dict[str, Any]:
        selection = self.config.selection(self.phase)
        pairs = select_pairs(
            self.manifest.pairs,
            task_ids=selection.task_ids,
            initial_state_ids=selection.initial_state_ids,
            seeds=selection.seeds,
        )
        commit, _, _ = git_commit_and_clean(self.repo_root)
        probe_engine = self.engine_factory(self.config.engine)
        engine_commit = str(probe_engine.metadata.get("engine_commit", ""))
        run_manifest_path = self.output_dir / "run_manifest.json"
        episodes_path = self.output_dir / "episodes.jsonl"
        if run_manifest_path.exists():
            if not resume:
                raise FileExistsError(f"run directory already exists; pass resume: {self.output_dir}")
            existing_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
            run_id = str(existing_manifest["run_id"])
            expected_identity = {
                "phase": self.phase,
                "event_source": self.event_source,
                "git_commit": commit,
                "config_hash": self.config.config_hash,
                "atlas_digest": self.manifest.digest,
                "engine_commit": engine_commit,
            }
            actual_identity = {key: existing_manifest.get(key) for key in expected_identity}
            if actual_identity != expected_identity:
                raise ValueError(f"resume identity mismatch: expected={expected_identity} actual={actual_identity}")
        else:
            self.output_dir.mkdir(parents=True, exist_ok=False)
            run_id = f"{self.phase}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
            run_manifest = {
                "schema_version": "cope-main-run-v1",
                "run_id": run_id,
                "phase": self.phase,
                "event_source": self.event_source,
                "git_commit": commit,
                "config_hash": self.config.config_hash,
                "atlas_digest": self.manifest.digest,
                "atlas_commit": self.manifest.atlas_commit,
                "engine_commit": engine_commit,
                "checkpoint_id": self.config.checkpoint_id,
                "checkpoint_path": self.config.checkpoint_path,
                "methods": METHOD_NAMES,
                "pair_count": len(pairs),
                "episode_count": len(pairs) * len(METHOD_NAMES),
                "provider_metadata": asdict(self.provider.metadata),
                "environment": environment_manifest(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            run_manifest_path.write_text(
                json.dumps(run_manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

        existing = read_jsonl(episodes_path) if episodes_path.exists() else []
        completed: dict[tuple[str, str], dict[str, Any]] = {}
        for record in existing:
            key = (str(record.get("pair_key")), str(record.get("method")))
            if key in completed:
                raise ValueError(f"resume ledger contains duplicate {key}")
            completed[key] = record

        context = RunContext(
            run_id=run_id,
            phase=self.phase,
            event_source=self.event_source,
            git_commit=commit,
            config_hash=self.config.config_hash,
            atlas_commit=self.manifest.atlas_commit,
            engine_commit=engine_commit,
            output_dir=str(self.output_dir),
        )
        try:
            for pair in pairs:
                for method_name in METHOD_NAMES:
                    key = (pair.pair_key, method_name)
                    if key in completed:
                        continue
                    method = build_method(
                        method_name,
                        provider=self.provider,
                        engine_factory=self.engine_factory,
                        engine_config=self.config.engine,
                        formal=self.phase in {"formal", "detected"},
                    )
                    episode_dir = self.output_dir / "episodes" / pair.pair_key.split(":")[-1][:16] / method_name
                    record = self.backend.run_episode(
                        pair=pair,
                        method=method,
                        method_name=method_name,
                        context=context,
                        episode_dir=episode_dir,
                    )
                    if record.get("pair_key") != pair.pair_key or record.get("method") != method_name:
                        raise ValueError("backend returned wrong pair key or method")
                    record_errors = validate_episode_record(record, check_artifacts=True)
                    if record_errors:
                        raise ValueError(f"invalid episode record {key}: {record_errors}")
                    _append_jsonl(episodes_path, record)
                    completed[key] = record
        finally:
            self.backend.close()

        records = read_jsonl(episodes_path)
        validation = validate_run_records(records, check_artifacts=True)
        summary = {
            "schema_version": "cope-main-summary-v1",
            "run_id": run_id,
            "phase": self.phase,
            "event_source": self.event_source,
            "pair_count": len(pairs),
            "episode_count": len(records),
            "expected_episode_count": len(pairs) * len(METHOD_NAMES),
            "complete": len(records) == len(pairs) * len(METHOD_NAMES) and validation["passed"],
            "validation": validation,
            "episodes_path": str(episodes_path),
        }
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return summary
