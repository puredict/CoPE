"""Fail-closed experiment assembly and immutable exports of durable runtime data.

Factories return lazy clients: constructing an assembly must neither infer nor
step a simulator. Production CLI execution always requires authentic catalog
preflight. The explicit Python-only qualification path is for mocked tests.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import gzip
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence
import uuid
import weakref

from .journal import DurableJournal, JournalError, reject_credentials, stable_hash
from .runner import EpisodeRunner, RuntimeBlocked, RuntimeConfig, json_value, load_runtime_factory


@dataclass(frozen=True)
class EpisodeInputs:
    """Public task plus harness-owned initial records; no method factory sees truth."""
    task: Mapping[str, Any]
    initial_ledger: Any
    initial_context: Any


@dataclass(frozen=True)
class RuntimeAssembly:
    """Versioned integration seam for installed production dependencies.

    ``episode_inputs(*, manifest, task)`` returns EpisodeInputs. The task argument
    is a catalog record for the trusted harness; EpisodeInputs.task is the public
    instruction/skill description passed to methods. Factories below take no
    harness object or canonical ledger. ``method_factory`` takes method_name and
    information_condition keyword arguments. Every call creates independent
    mutable state; model weights may be shared behind independently owned clients.

    ``identity`` is credential-free provenance. ``current_identity`` performs a
    live identity read without inference; in formal mode it returns the exact
    component mapping consumed by phase 4's validate_frozen_bundle.
    """
    episode_inputs: Callable[..., EpisodeInputs]
    environment_factory: Callable[[], Any]
    planner_factory: Callable[[], Any]
    method_factory: Callable[..., Any]
    identity: Mapping[str, Any]
    policy_factory: Callable[[], Any] | None = None
    current_identity: Callable[[], Mapping[str, Any]] | None = None
    frozen_bundle: Mapping[str, Any] | None = None
    fixture: bool = False
    version: str = "runtime_assembly_v2.1"
    public_evidence_builder_factory: Callable[[], Any] | None = None
    public_verifier_factory: Callable[[], Any] | None = None
    nominal_planner_factory: Callable[[], Any] | None = None
    continuation_backend_factory: Callable[[], Any] | None = None
    vla_asset_preflight: Callable[[], Mapping[str, Any]] | None = None
    sealed_evaluator_provider_id: str | None = None


def _encoded(value: Any) -> bytes:
    reject_credentials(json_value(value))
    return (json.dumps(json_value(value), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _read_json(path: Path) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _publish(path: Path, data: bytes, *, resume: bool) -> None:
    """Atomic exclusive publication; interrupted exports resume only byte-identically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if resume and path.read_bytes() == data:
            return
        raise RuntimeBlocked("INVALID_ARTIFACT_OVERWRITE", "existing artifact differs or --resume was omitted")
    temporary = path.parent / (".pending-export-" + uuid.uuid4().hex)
    with temporary.open("xb") as handle:
        os.chmod(temporary, 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    except FileExistsError:
        if not resume or path.read_bytes() != data:
            raise RuntimeBlocked("INVALID_ARTIFACT_OVERWRITE", "artifact was concurrently published")
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    temporary.unlink()


def _jsonl(rows: Sequence[Mapping]) -> bytes:
    return b"".join(_encoded(row) for row in rows)


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(root))):
        if path.is_symlink():
            raise RuntimeBlocked("INVALID_JOURNAL", "journal files must not be symlinks")
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def dependency_report(config: Mapping, *, phase: str, protocol: str,
                      environ: Mapping[str, str] | None = None) -> dict:
    """Read-only availability checks; no provider import, client creation or GPU use."""
    env = os.environ if environ is None else environ
    blockers = []
    required = [("COPE_RUNTIME_FACTORY", "BLOCKED_RUNTIME_ENVIRONMENT_UNAVAILABLE"),
                (config["reasoner"]["provider_factory_env"], "BLOCKED_REASONER_ADAPTER_UNAVAILABLE"),
                (config["reasoner"]["model_env"], "BLOCKED_REASONER_MODEL_UNAVAILABLE")]
    if protocol == "end_to_end":
        required.extend([(config["vla"]["factory_env"], "BLOCKED_VLA_ADAPTER_UNAVAILABLE"),
                         (config["vla"]["checkpoint_env"], "BLOCKED_VLA_CHECKPOINT_UNAVAILABLE")])
    if phase == "formal":
        required.append(("COPE_FREEZE_BUNDLE", "BLOCKED_FREEZE_REQUIRED"))
    for variable, status in required:
        if not str(env.get(variable, "")).strip():
            blockers.append({"status": status, "detail": f"{variable} is not configured"})
    if protocol == "end_to_end":
        checkpoint = env.get(config["vla"]["checkpoint_env"])
        if checkpoint and not Path(checkpoint).expanduser().exists():
            blockers.append({"status": "BLOCKED_VLA_CHECKPOINT_UNAVAILABLE",
                             "detail": "configured checkpoint is not present locally; downloads are disabled"})
    freeze = env.get("COPE_FREEZE_BUNDLE")
    if phase == "formal" and freeze and not Path(freeze).is_file():
        blockers.append({"status": "BLOCKED_FREEZE_REQUIRED", "detail": "frozen bundle file is unavailable"})
    return {"passed": not blockers, "blockers": blockers,
            "provider_calls": 0, "vla_calls": 0, "runtime_factory_calls": 0}


def _freeze_validator():
    try:
        return importlib.import_module("cope_benchmark.repeated_v2.freeze").validate_frozen_bundle
    except (ImportError, AttributeError) as exc:
        raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "phase-4 freeze validator is unavailable") from exc


def _load_freeze(path: str) -> Mapping:
    bundle = _read_json(Path(path))
    if not isinstance(bundle, dict):
        raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "freeze bundle must be an object")
    unsigned = dict(bundle)
    claimed = unsigned.pop("bundle_sha256", None)
    if bundle.get("status") != "FROZEN" or stable_hash(unsigned) != claimed:
        raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "freeze bundle status or content hash is invalid")
    _freeze_validator()  # Require the implementation before runtime factory import.
    return bundle


def _select_formal_shard(full_manifest: Sequence[Mapping], bundle: Mapping,
                         shard_index: int | None, num_shards: int) -> list[dict]:
    """Validate the entire deterministic partition, including empty ownership."""
    if num_shards != 8 or type(shard_index) is not int or not 0 <= shard_index < 8:
        raise RuntimeBlocked("INVALID_SHARD", "formal execution requires --shard-index 0..7 and --num-shards 8")
    ids = [row["master_episode_id"] for row in full_manifest]
    if not ids or len(ids) != len(set(ids)):
        raise RuntimeBlocked("INVALID_MANIFEST", "full formal manifest must be nonempty and unique")
    partitions = [[] for _ in range(8)]
    for row in full_manifest:
        owner = int(hashlib.sha256(row["master_episode_id"].encode()).hexdigest(), 16) % 8
        partitions[owner].append(deepcopy(dict(row)))
    for partition in partitions:
        partition.sort(key=lambda row: (row["master_episode_id"], _encoded(row)))
    expected = [{"shard_id": index, "master_episode_ids": [row["master_episode_id"] for row in partition],
                 "manifest_sha256": stable_hash(partition)} for index, partition in enumerate(partitions)]
    if bundle.get("shard_count") != 8 or bundle.get("shards") != expected:
        raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "full formal partition differs from frozen ownership")
    return partitions[shard_index]


def _validate_empty_freeze(bundle: Mapping) -> None:
    """Validate bound evidence without claiming a live identity read for zero jobs.

    All byte, protocol, eligibility, git and shard checks use phase 4's public
    static validator. No runtime/model exists on this path, so the live
    identity callback used before actual external calls is intentionally absent.
    """
    try:
        validator = importlib.import_module("cope_benchmark.repeated_v2.freeze").validate_static_frozen_bundle
    except (ImportError, AttributeError) as exc:
        raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "phase-4 static freeze validators are unavailable") from exc
    validator(bundle)


def _validate_empty_formal_inputs(*, config: Mapping, catalog_data: Mapping | None,
                                 full_manifest: Sequence[Mapping] | None, bundle: Mapping,
                                 shard_index: int | None, num_shards: int) -> None:
    from .preflight import run_preflight
    from .task_catalog import TaskCatalog
    if not catalog_data or not full_manifest:
        raise RuntimeBlocked("INVALID_MANIFEST", "empty shard still requires authentic catalog and full manifest")
    revisions = {row.get("source_commit") for row in full_manifest}
    if len(revisions) != 1:
        raise RuntimeBlocked("INVALID_MANIFEST", "full manifest requires one producer commit")
    report = run_preflight(config, TaskCatalog.from_dict(catalog_data),
                          source_commit=next(iter(revisions)), manifest=list(full_manifest))
    if not report.get("passed"):
        raise RuntimeBlocked(report.get("status", "BLOCKED_PHASE1_PREFLIGHT"), "empty shard full-manifest preflight failed")
    if _select_formal_shard(full_manifest, bundle, shard_index, num_shards):
        raise RuntimeBlocked("INVALID_SHARD", "selected frozen shard owns episodes and cannot be omitted")
    _validate_empty_freeze(bundle)


def pilot_manifest(config: Mapping, catalog: Any, *, source_commit: str, phase: str = "pilot") -> list[dict]:
    """Build the frozen qualification grid without consulting method outcomes."""
    from .scheduler import build_balanced_master_schedules
    from .task_catalog import CATALOG_SCHEMA_VERSION_V2_1, select_eligible_tasks, select_pilot_tasks
    if phase not in {"pilot", "development"}:
        raise ValueError("qualification manifest requires pilot or development phase")
    v2_1 = catalog.schema_version == CATALOG_SCHEMA_VERSION_V2_1
    if v2_1 and phase == "pilot":
        # v2.1 explicitly registers the smallest end-to-end pilot on two of the
        # frozen formal-design state IDs.  It remains pipeline evidence only.
        tasks = select_pilot_tasks(catalog)
        states = tuple(config["task_selection"]["formal_state_ids"][:2])
        seed = config["task_selection"]["formal_policy_seeds"][0]
        if len(states) != 2 or len(set(states)) != 2:
            raise RuntimeBlocked("INVALID_PILOT_DESIGN", "v2.1 pilot requires two unique initial states")
    else:
        tasks = select_eligible_tasks(catalog)
        states = (config["task_selection"]["calibration_state_ids"][0],)
        seed = config["task_selection"]["calibration_policy_seeds"][0 if phase == "pilot" else 1]
        if seed in config["task_selection"]["formal_policy_seeds"]:
            raise RuntimeBlocked("INVALID_PILOT_FORMAL_OVERLAP", "pilot seed occurs in formal design")
    specs, rows = [], []
    for task in tasks:
        for state in states:
            pair = {"task_suite": config["task_suite"], "task_id": task.task_id,
                    "initial_state_id": state, "policy_seed": seed,
                    "initial_state_sha256": task.initial_state_digests[str(state)],
                    "master_seed": config["events"]["master_seed"]}
            episode = "rv2-" + phase + "-" + stable_hash(pair)[:24]
            specs.append({"master_episode_id": episode,
                          "semantic_triggers": json_value(task.semantic_triggers),
                          "supported_event_families": task.supported_event_families})
            rows.append({
                "schema_version": ("cope-repeated-v2.1/pilot-manifest-1" if v2_1
                                   else "cope-repeated-v2/pilot-manifest-1"),
                "master_episode_id": episode, "pair_fields": pair,
                "source_commit": source_commit, "phase": phase,
                "config_sha256": stable_hash(config),
                "task_catalog_sha256": stable_hash(catalog.to_dict()),
                "pipeline_evidence_only": bool(v2_1 and phase == "pilot"),
            })
    schedules = build_balanced_master_schedules(specs, seed=config["events"]["master_seed"])
    by_id = {schedule.master_episode_id: schedule for schedule in schedules}
    for row in rows:
        row["master_schedule"] = by_id[row["master_episode_id"]].to_dict()
        row["master_schedule_sha256"] = stable_hash(row["master_schedule"])
        row["row_sha256"] = stable_hash(row)
    return rows


def _component_identity(component: Any) -> dict:
    return {"class": type(component).__module__ + "." + type(component).__qualname__,
            "provider_id": getattr(component, "provider_id", None),
            "version": getattr(component, "version", None),
            "identity": json_value(getattr(component, "identity", {}))}


def _retain_unique(component: Any, references: list) -> None:
    if any(reference() is component for reference in references):
        raise RuntimeBlocked("INVALID_SHARED_METHOD_STATE", "factories reused mutable state")
    try:
        references.append(weakref.ref(component))
    except TypeError:
        # Some extension objects are not weak-referenceable. Keep only these alive.
        references.append(lambda: component)


def _production_components(method: Any, planner: Any, environment: Any) -> None:
    markers = ("oracle", "fixture", "fake", "mock", "scripted", "dummy", "noop")
    for label, component in (("planner", planner), ("environment", environment)):
        values = (type(component).__name__, getattr(component, "provider_id", ""))
        if not getattr(component, "provider_id", None) or any(
                marker in str(value).lower() for marker in markers for value in values):
            raise RuntimeBlocked("INVALID_PRODUCTION_RUNTIME", f"{label} is not a production component")
    if getattr(planner, "uses_hidden_truth", None) is not False:
        raise RuntimeBlocked("INVALID_PRIVILEGED_PLANNER", "planner must declare uses_hidden_truth=False")
    gateway = getattr(method, "gateway", None)
    name = str(getattr(method.method, "value", method.method))
    if gateway is None and name not in {"classical_execution_monitor", "oracle_persistent_update"}:
        raise RuntimeBlocked("BLOCKED_REASONER_ADAPTER_UNAVAILABLE", "generative method has no reasoner gateway")
    if gateway is not None:
        values = (type(gateway.reasoner).__name__, gateway.config.provider, gateway.config.model)
        if any(marker in str(value).lower() for marker in markers for value in values):
            raise RuntimeBlocked("INVALID_PRODUCTION_REASONER", "fixture or privileged reasoner cannot run a pilot")
        _strict_public_identity(gateway.reasoner, "reasoner")


_STRICT_PUBLIC_IDENTITY_FIELDS = frozenset({
    "provider_id", "version", "uses_hidden_canonical_state",
    "uses_privileged_simulator_state", "input_schema_hash", "output_schema_hash",
})
_NON_PRODUCTION_MARKERS = ("oracle", "fixture", "fake", "mock", "scripted", "dummy", "noop")


def _strict_public_identity(component: Any, label: str) -> dict[str, Any]:
    identity = json_value(getattr(component, "identity", {}))
    missing = sorted(_STRICT_PUBLIC_IDENTITY_FIELDS - set(identity))
    if missing:
        raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY",
                             f"{label} identity is missing {missing}")
    if identity["provider_id"] != getattr(component, "provider_id", None):
        raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY",
                             f"{label} provider identity differs from its implementation")
    if identity["version"] != getattr(component, "version", None):
        raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY",
                             f"{label} version differs from its implementation")
    for field in ("uses_hidden_canonical_state", "uses_privileged_simulator_state"):
        if identity[field] is not False or getattr(component, field, None) is not False:
            raise RuntimeBlocked("INVALID_PRIVILEGED_RUNTIME_COMPONENT",
                                 f"{label} must declare {field}=false")
    for field in ("input_schema_hash", "output_schema_hash"):
        value = identity[field]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY",
                                 f"{label} has an invalid {field}")
    names = (type(component).__module__, type(component).__qualname__, identity["provider_id"], identity["version"])
    if any(marker in str(value).lower() for marker in _NON_PRODUCTION_MARKERS for value in names):
        raise RuntimeBlocked("INVALID_PRODUCTION_RUNTIME", f"{label} is not a production component")
    return identity


def _journal_resume_self_check() -> dict[str, Any]:
    """Exercise durable intent/response/result replay without an external call."""
    invocations = 0
    key = ("end_to_end", "runtime-gate", "journal-contract", 1)
    metadata = {"schema": "runtime_gate_journal_v1", "external_calls": 0}

    def invoke(_request):
        nonlocal invocations
        invocations += 1
        return {"ok": True}

    with tempfile.TemporaryDirectory(prefix="cope-runtime-gate-") as directory:
        root = Path(directory) / "journal"
        with DurableJournal(root) as journal:
            journal.freeze_metadata(metadata)
            first = journal.call_once(key, {"probe": 1}, invoke)
            journal.save_snapshot(key, {"boundary": 1}, label="completed")
            journal.record_result(key, {"status": "COMPLETED", "provider_called": True})
        with DurableJournal(root, frozen_metadata=metadata) as journal:
            second = journal.call_once(key, {"probe": 1},
                                       lambda _: (_ for _ in ()).throw(AssertionError("duplicate invocation")))
            report = journal.inspect_integrity([key], snapshot_label="completed")
        if first != second or invocations != 1 or not report.valid:
            raise RuntimeBlocked("INVALID_DURABLE_JOURNAL", "at-most-once resume self-check failed")
    return {"status": "PASS", "logical_calls": 2, "actual_invocations": invocations,
            "duplicate_provider_calls": 0, "integrity_status": report.status}


def validate_runtime_assembly(assembly: RuntimeAssembly) -> dict[str, Any]:
    """Zero-call formal gate for the complete public runtime graph.

    This runs before output publication, provider construction, model loading,
    simulator reset, or learned-policy inference.  Factories inspected here may
    load the local CPU continuation package, but may not own runtime state.
    """
    factories = {
        "public_evidence_builder": assembly.public_evidence_builder_factory,
        "public_runtime_verifier": assembly.public_verifier_factory,
        "nominal_planner": assembly.nominal_planner_factory,
        "continuation_backend": assembly.continuation_backend_factory,
    }
    missing = sorted(name for name, factory in factories.items() if not callable(factory))
    if missing:
        raise RuntimeBlocked("INVALID_RUNTIME_ASSEMBLY", f"missing public component factories: {missing}")
    if not callable(assembly.policy_factory) or not callable(assembly.vla_asset_preflight):
        raise RuntimeBlocked("BLOCKED_VLA_ADAPTER_UNAVAILABLE",
                             "production assembly requires learned-policy and asset-preflight factories")
    try:
        vla_assets = json_value(assembly.vla_asset_preflight())
    except Exception as exc:
        status = getattr(exc, "status", "BLOCKED_VLA_ADAPTER_UNAVAILABLE")
        raise RuntimeBlocked(status, "VLA asset verification failed during zero-call gate") from exc
    declared_vla = json_value(assembly.identity.get("vla", {}))
    missing_vla_identity = sorted(_STRICT_PUBLIC_IDENTITY_FIELDS - set(declared_vla))
    if (vla_assets.get("provider_id") != declared_vla.get("provider_id") or
            vla_assets.get("checkpoint_sha256") != declared_vla.get("checkpoint_sha256") or
            vla_assets.get("learned_policy") is not True or
            vla_assets.get("uses_privileged_state") is not False or
            vla_assets.get("action_dim") != 7 or
            not 1 <= vla_assets.get("max_chunk_horizon", 0) <= 8 or
            missing_vla_identity or
            declared_vla.get("uses_hidden_canonical_state") is not False or
            declared_vla.get("uses_privileged_simulator_state") is not False or
            any(vla_assets.get(field) != declared_vla.get(field)
                for field in _STRICT_PUBLIC_IDENTITY_FIELDS)):
        raise RuntimeBlocked("INVALID_VLA_CONTRACT", "verified VLA assets differ from assembly identity")
    components = {}
    for name, factory in factories.items():
        try:
            components[name] = factory()
        except Exception as exc:
            status = getattr(exc, "status", "BLOCKED_RUNTIME_COMPONENT_UNAVAILABLE")
            raise RuntimeBlocked(status, f"{name} construction failed during zero-call gate") from exc
    identities = {name: _strict_public_identity(component, name)
                  for name, component in components.items()}
    if not isinstance(assembly.sealed_evaluator_provider_id, str) or not assembly.sealed_evaluator_provider_id:
        raise RuntimeBlocked("INVALID_RUNTIME_ASSEMBLY", "sealed evaluator identity is required")
    verifier = components["public_runtime_verifier"]
    if (assembly.sealed_evaluator_provider_id == verifier.provider_id or
            assembly.sealed_evaluator_provider_id in {
                type(verifier).__name__, type(verifier).__module__ + "." + type(verifier).__qualname__}):
        raise RuntimeBlocked("INVALID_EVALUATOR_ALIAS", "public verifier aliases the sealed evaluator")
    nominal = components["nominal_planner"]
    signature = inspect.signature(nominal.solve)
    if tuple(signature.parameters) != ("problem", "context") or any(
            parameter.kind is not inspect.Parameter.KEYWORD_ONLY
            for parameter in signature.parameters.values()):
        raise RuntimeBlocked("INVALID_PRIVILEGED_PLANNER",
                             "nominal planner must consume only keyword-only problem and context")
    backend = components["continuation_backend"]
    if getattr(backend, "nominal_backend", None) is None or getattr(backend, "verifier", None) is None:
        raise RuntimeBlocked("INVALID_COMMON_BACKEND", "continuation backend lacks public dependencies")
    if (json_value(backend.nominal_backend.identity) != identities["nominal_planner"] or
            json_value(backend.verifier.identity) != identities["public_runtime_verifier"]):
        raise RuntimeBlocked("INVALID_COMMON_BACKEND",
                             "continuation backend dependencies differ from common public identities")
    exposed = vars(backend)
    if any(name in exposed for name in ("environment", "env", "sim", "canonical", "canonical_state",
                                        "sealed_evaluator", "hidden_effect")):
        raise RuntimeBlocked("INVALID_PUBLIC_INPUT_LEAKAGE",
                             "continuation backend retains privileged runtime state")
    # Repeat every factory once.  Identity equality is the zero-call proof that
    # all method arms are wired to the same implementation/configuration.
    repeated = {}
    for name, factory in factories.items():
        try:
            repeated[name] = _strict_public_identity(factory(), name)
        except RuntimeBlocked:
            raise
        except Exception as exc:
            status = getattr(exc, "status", "BLOCKED_RUNTIME_COMPONENT_UNAVAILABLE")
            raise RuntimeBlocked(status, f"{name} repeat construction failed during zero-call gate") from exc
    if repeated != identities:
        raise RuntimeBlocked("INVALID_COMMON_BACKEND", "public component identity is not factory-stable")
    declared = json_value(assembly.identity.get("components", {}))
    expected_declared = {
        "public_evidence_builder": identities["public_evidence_builder"],
        "public_runtime_verifier": identities["public_runtime_verifier"],
        "nominal_planner": identities["nominal_planner"],
        "continuation_backend": identities["continuation_backend"],
    }
    for name, identity in expected_declared.items():
        declared_identity = declared.get(name, {})
        for field in _STRICT_PUBLIC_IDENTITY_FIELDS:
            if declared_identity.get(field) != identity[field]:
                raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY",
                                     f"declared {name} identity differs from constructed component")
    backend_declared = declared["continuation_backend"]
    for field in ("package_sha256", "config_sha256", "nominal_planner_identity",
                  "public_verifier_identity"):
        if backend_declared.get(field) != identities["continuation_backend"].get(field):
            raise RuntimeBlocked("INVALID_COMMON_BACKEND",
                                 f"declared continuation backend {field} differs from the loaded package")
    compiler = declared.get("compiler", {})
    missing_compiler = sorted(_STRICT_PUBLIC_IDENTITY_FIELDS - set(compiler))
    if missing_compiler or compiler.get("uses_hidden_canonical_state") is not False or \
            compiler.get("uses_privileged_simulator_state") is not False:
        raise RuntimeBlocked("INVALID_PRIVILEGED_COMPILER", "pure compiler identity is incomplete or privileged")
    from .compiler import compile_ledger
    compiler_signature = inspect.signature(compile_ledger)
    forbidden_parameters = {"task_id", "catalog", "canonical_state", "environment", "simulator",
                            "hidden_effect", "sealed_evaluator"}
    if forbidden_parameters & set(compiler_signature.parameters):
        raise RuntimeBlocked("INVALID_PRIVILEGED_COMPILER", "compiler accepts a privileged reconstruction input")
    source_path = Path(inspect.getsourcefile(compile_ledger) or "")
    if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != compiler.get("source_sha256"):
        raise RuntimeBlocked("INVALID_RUNTIME_COMPONENT_IDENTITY", "compiler source hash differs from assembly")
    journal_gate = _journal_resume_self_check()
    return {
        "status": "PASS", "provider_calls": 0, "vla_calls": 0,
        "simulator_resets": 0, "components": identities,
        "compiler": compiler, "vla_assets": vla_assets, "durable_journal": journal_gate,
        "sealed_evaluator_provider_id": assembly.sealed_evaluator_provider_id,
        "public_sealed_separation": True, "same_components_across_methods": True,
    }


def export_journal(journal: DurableJournal, *, output_dir: Path, expected_cells: Sequence,
                   condition: str, resume: bool) -> dict:
    """Publish complete raw records and trace/snapshot provenance without imputation."""
    report = journal.inspect_integrity(expected_cells, snapshot_label="completed").as_dict()
    report["information_condition"] = condition
    if not report["valid"]:
        raise RuntimeBlocked("INVALID_RUN", "journal is incomplete or has ambiguous/invalid cells")
    artifacts = {}
    records = {}
    for name, kind in (("04_CALL_INTENTS.jsonl", "intents"),
                       ("05_PROVIDER_RESPONSES.jsonl", "responses"),
                       ("06_EVENT_RESULTS.jsonl", "results"),
                       ("07_EPISODE_RESULTS.jsonl", "episodes")):
        collection = journal.read_records(kind)
        records[kind] = collection
        rows = [{"protocol": key[0], "master_episode_id": key[1], "method": key[2],
                 "event_index": key[3], **payload, "information_condition": condition}
                for key, payload in sorted(collection.items())]
        data = _jsonl(rows)
        _publish(output_dir / name, data, resume=resume)
        artifacts[name] = hashlib.sha256(data).hexdigest()
    snapshots, problems = [], []
    for key in sorted(expected_cells):
        for label in ("initial", "pre", "completed"):
            if not journal.snapshot_exists(key, label=label):
                continue
            payload = journal.load_snapshot(key, label=label)
            provenance = {"protocol": key[0], "master_episode_id": key[1], "method": key[2],
                          "event_index": key[3], "information_condition": condition, "label": label}
            snapshots.append({**provenance, "snapshot_sha256": stable_hash(payload), "snapshot": payload})
            if "planning_problem" in payload:
                problems.append({**provenance, "planning_problem": payload["planning_problem"],
                                 "planning_problem_sha256": stable_hash(payload["planning_problem"])})
    for name, rows in (("08_STATE_SNAPSHOTS.jsonl", snapshots), ("09_PLANNING_PROBLEMS.jsonl", problems)):
        data = _jsonl(rows)
        _publish(output_dir / name, data, resume=resume)
        artifacts[name] = hashlib.sha256(data).hexdigest()
    (output_dir / "10_ACTION_TRACES").mkdir(parents=True, exist_ok=True)
    for key, episode in sorted(records["episodes"].items()):
        trace = episode.get("action_trace")
        if trace is None or stable_hash(trace) != episode.get("action_trace_sha256"):
            raise RuntimeBlocked("INVALID_ACTION_TRACE", "episode has no hash-verified action trace")
        name = "10_ACTION_TRACES/" + stable_hash(list(key)) + ".jsonl.gz"
        data = gzip.compress(_jsonl(trace), mtime=0)
        _publish(output_dir / name, data, resume=resume)
        artifacts[name] = hashlib.sha256(data).hexdigest()
    _publish(output_dir / "INTEGRITY.json", _encoded(report), resume=resume)
    return {"integrity": report, "artifact_sha256": artifacts}


def execute_assembly(*, assembly: RuntimeAssembly | None, config: Mapping, manifest: Sequence[Mapping],
                     catalog: Mapping[int, Mapping], output_dir: str | Path, phase: str,
                     protocol: str, source_commit: str, resume: bool = False,
                     frozen_bundle: Mapping | None = None, qualification: bool = False,
                     information_condition: str | None = None, shard_index: int | None = None,
                     num_shards: int = 8, catalog_data: Mapping | None = None,
                     full_manifest: Sequence[Mapping] | None = None) -> dict:
    """Execute a checked assembly; qualification=True is never exposed by the CLI."""
    empty_formal = phase == "formal" and not manifest
    if not isinstance(assembly, RuntimeAssembly) and not (assembly is None and empty_formal):
        raise RuntimeBlocked("INVALID_RUNTIME_FACTORY", "factory must return RuntimeAssembly")
    if ((assembly is not None and assembly.fixture != qualification) or
            (qualification and phase != "pilot")):
        raise RuntimeBlocked("INVALID_FIXTURE_RUN", "mock qualification must be explicitly identified")
    if not manifest and not empty_formal:
        raise RuntimeBlocked("BLOCKED_EMPTY_MANIFEST", "no episodes are available")
    runtime_gate = None
    if assembly is not None and not qualification:
        runtime_gate = validate_runtime_assembly(assembly)
    if assembly is not None and assembly.frozen_bundle is not None:
        if frozen_bundle is not None and stable_hash(assembly.frozen_bundle) != stable_hash(frozen_bundle):
            raise RuntimeBlocked("INVALID_PROTOCOL_DRIFT", "CLI and assembly freeze bundles differ")
        frozen_bundle = assembly.frozen_bundle
    if empty_formal:
        if not frozen_bundle:
            raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "empty formal shard requires a frozen bundle")
        _validate_empty_formal_inputs(config=config, catalog_data=catalog_data,
            full_manifest=full_manifest, bundle=frozen_bundle, shard_index=shard_index, num_shards=num_shards)
    elif phase == "formal":
        if not frozen_bundle or assembly.current_identity is None:
            raise RuntimeBlocked("BLOCKED_FREEZE_REQUIRED", "formal run requires a bundle and live identities")
        _freeze_validator()(frozen_bundle, current_identity=assembly.current_identity)
    root = Path(output_dir)
    if not resume and root.exists() and any(root.iterdir()):
        raise RuntimeBlocked("INVALID_OUTPUT_DIRECTORY", "output directory is nonempty; use --resume")
    root.mkdir(parents=True, exist_ok=True)
    v2_1_pilot = (phase == "pilot"
                  and config.get("schema_version") == "repeated_interruptions_v2_1_config_v1")
    methods = list(config["methods"]["non_oracle"])
    if not v2_1_pilot:
        methods += list(config["methods"]["oracle"])
    conditions = [config["evidence"]["primary_condition"], config["evidence"]["secondary_condition"]]
    if v2_1_pilot and information_condition is None:
        conditions = [config["evidence"]["primary_condition"]]
    if information_condition is not None:
        if information_condition not in conditions:
            raise RuntimeBlocked("INVALID_INFORMATION_CONDITION", "condition differs from frozen config")
        conditions = [information_condition]
    if len(methods) != len(set(methods)) or len(conditions) != len(set(conditions)):
        raise RuntimeBlocked("INVALID_MANIFEST", "duplicate method or information condition")
    episode_ids = [row["master_episode_id"] for row in manifest]
    if len(episode_ids) != len(set(episode_ids)):
        raise RuntimeBlocked("INVALID_MANIFEST", "duplicate master episode")
    metadata = {"schema_version": assembly.version if assembly is not None else "runtime_assembly_v2.1", "phase": phase, "protocol": protocol,
                "fixture": qualification, "source_commit": source_commit,
                "config_sha256": stable_hash(config), "manifest_sha256": stable_hash(manifest),
                "runtime_identities": json_value(assembly.identity if assembly is not None else frozen_bundle["identities"]),
                "freeze_sha256": (frozen_bundle or {}).get("bundle_sha256"),
                "information_condition": information_condition,
                "shard_id": shard_index, "shard_count": num_shards if phase == "formal" else 1,
                "evidence_admissibility": "mock_qualification" if qualification else phase}
    if runtime_gate is not None:
        metadata["zero_call_runtime_gate"] = runtime_gate
    if empty_formal:
        metadata.update(empty_shard=True, full_manifest_sha256=stable_hash(full_manifest),
                        live_identity_check="not_required_no_external_calls")
    # Own the protocol directory throughout input publication, execution and export.
    with DurableJournal(root / ".run-owner") as owner:
        owner.freeze_metadata(metadata)
        _publish(root / "00_RUN_METADATA.json", _encoded(metadata), resume=resume)
        _publish(root / "01_CONFIG_FROZEN.yaml", _encoded(config), resume=resume)  # JSON is YAML 1.2.
        _publish(root / "02_TASK_CATALOG_FROZEN.json", _encoded(catalog_data or {str(k): v for k, v in catalog.items()}), resume=resume)
        _publish(root / "03_MANIFEST_FROZEN.jsonl", _jsonl(manifest), resume=resume)
        if (root / "12_STATUS.json").exists() and not resume:
            raise RuntimeBlocked("INVALID_DUPLICATE_RUN", "completed run requires --resume")
        if (root / "13_INFRASTRUCTURE_STOP.json").exists():
            stopped = _read_json(root / "13_INFRASTRUCTURE_STOP.json")
            if stopped.get("status") in {"INVALID_PROTOCOL_DRIFT", "BLOCKED_AMBIGUOUS_CALL"}:
                raise RuntimeBlocked(stopped["status"], "run is durably stopped")
        exports = {}
        common = {}
        live_instances = []  # Weak references catch reuse without retaining closed model allocations.
        try:
            from .scheduler import MasterSchedule
            from .provider import assert_same_backbone
            prepared_methods = {}
            # All actual generative gateways are checked before the first reset,
            # model inference or provider call; budget settings match within a condition.
            for condition in conditions:
                gateways = []
                for row in manifest:
                    for name in methods:
                        method = assembly.method_factory(method_name=name, information_condition=condition)
                        _retain_unique(method, live_instances)
                        actual = str(getattr(method.method, "value", method.method))
                        if actual != name:
                            raise RuntimeBlocked("INVALID_METHOD_IDENTITY", "adapter differs from requested method")
                        gateway = getattr(method, "gateway", None)
                        if gateway is not None:
                            _retain_unique(gateway, live_instances)
                            if gateway.config.setting != condition:
                                raise RuntimeBlocked("INVALID_REASONER_PARITY", "gateway information condition differs from run")
                            if not qualification:
                                reasoner_identity = assembly.identity.get("reasoner", {})
                                if (reasoner_identity.get("provider_id") != gateway.config.provider or
                                        reasoner_identity.get("model_id") != gateway.config.model):
                                    raise RuntimeBlocked("INVALID_REASONER_IDENTITY", "actual reasoner differs from assembly provenance")
                                actual_reasoner_identity = _strict_public_identity(
                                    gateway.reasoner, "reasoner")
                                if any(reasoner_identity.get(field) != actual_reasoner_identity.get(field)
                                       for field in _STRICT_PUBLIC_IDENTITY_FIELDS):
                                    raise RuntimeBlocked("INVALID_REASONER_IDENTITY",
                                                         "reasoner component contract differs from assembly provenance")
                                expected_tokens = config["reasoner"]["max_input_tokens_" + condition]
                                if (gateway.config.max_input_tokens != expected_tokens or
                                        gateway.config.max_output_tokens != config["reasoner"]["max_output_tokens"]):
                                    raise RuntimeBlocked("INVALID_REASONER_PARITY", "gateway token limits differ from frozen config")
                            gateways.append(gateway)
                        prepared_methods[(condition, row["master_episode_id"], name)] = method
                try:
                    assert_same_backbone(gateways)
                except ValueError as exc:
                    raise RuntimeBlocked("INVALID_REASONER_PARITY", "generative gateways differ before execution") from exc
                if gateways:
                    _publish(root / "component_identities" / (condition + "_reasoner.json"),
                             _encoded(gateways[0].config.to_dict()), resume=resume)
            for condition in conditions:
                subdir = root if information_condition is not None else root / condition
                with DurableJournal(subdir) as journal:
                    runtime_frozen = frozen_bundle if phase == "formal" else {
                        **metadata, "information_condition": condition}
                    journal.freeze_metadata(runtime_frozen)
                    expected = []
                    for row in manifest:
                        pair = row["pair_fields"]
                        schedule = MasterSchedule.from_dict(row["master_schedule"])
                        if schedule.master_episode_id != row["master_episode_id"] or stable_hash(json_value(schedule)) != row["master_schedule_sha256"]:
                            raise RuntimeBlocked("INVALID_MANIFEST", "master schedule identity/hash mismatch")
                        inputs = assembly.episode_inputs(manifest=deepcopy(dict(row)), task=deepcopy(dict(catalog[pair["task_id"]])))
                        if not isinstance(inputs, EpisodeInputs):
                            raise RuntimeBlocked("INVALID_RUNTIME_FACTORY", "episode_inputs must return EpisodeInputs")
                        input_record = {"task": inputs.task, "initial_ledger": inputs.initial_ledger,
                                        "initial_context": inputs.initial_context}
                        # Freeze the source inputs before any reset or external call.
                        _publish(subdir / "episode_inputs" / (stable_hash(row["master_episode_id"]) + ".json"),
                                 _encoded(input_record), resume=resume)
                        for name in methods:
                            count = config["protocols"][protocol]["event_count"]
                            expected.extend((protocol, row["master_episode_id"], name, i) for i in range(count + 1))
                            environment = planner = policy = runner = None
                            try:
                                if phase == "formal":
                                    _freeze_validator()(frozen_bundle, current_identity=assembly.current_identity)
                                environment = assembly.environment_factory()
                                planner = assembly.planner_factory()
                                method = prepared_methods[(condition, row["master_episode_id"], name)]
                                for value in (environment, planner):
                                    _retain_unique(value, live_instances)
                                actual_name = str(getattr(method.method, "value", method.method))
                                if actual_name != name:
                                    raise RuntimeBlocked("INVALID_METHOD_IDENTITY", "adapter differs from requested method")
                                if not qualification:
                                    _production_components(method, planner, environment)
                                for label, value in (("environment", environment), ("planner", planner)):
                                    identity = _component_identity(value)
                                    if label in common and common[label] != identity:
                                        raise RuntimeBlocked("INVALID_COMMON_BACKEND", f"{label} identity differs across methods")
                                    common[label] = identity
                                    _publish(root / "component_identities" / (label + ".json"), _encoded(identity), resume=True)
                                gateway = getattr(method, "gateway", None)
                                if gateway is not None:
                                    backbone = {"provider": gateway.config.provider, "model": gateway.config.model}
                                    if "reasoner" in common and common["reasoner"] != backbone:
                                        raise RuntimeBlocked("INVALID_REASONER_PARITY", "reasoner backbone differs across methods")
                                    common["reasoner"] = backbone
                                if protocol == "end_to_end":
                                    if assembly.policy_factory is None:
                                        raise RuntimeBlocked("BLOCKED_VLA_ADAPTER_UNAVAILABLE", "assembly has no learned VLA factory")
                                    policy = assembly.policy_factory()
                                    _retain_unique(policy, live_instances)
                                    if not qualification:
                                        _strict_public_identity(policy, "learned_vla")
                                    identity = _component_identity(policy)
                                    if "policy" in common and common["policy"] != identity:
                                        raise RuntimeBlocked("INVALID_COMMON_EXECUTOR", "VLA identity differs across methods")
                                    common["policy"] = identity
                                    _publish(root / "component_identities" / "policy.json", _encoded(identity), resume=True)
                                runtime_config = RuntimeConfig(protocol=protocol, phase=phase,
                                    fixture=qualification, information_condition=condition,
                                    max_policy_steps=config["vla"]["max_policy_steps"],
                                    action_dimension=config["vla"]["action_dimension"],
                                    action_chunk_horizon=config["vla"]["action_chunk_horizon"])
                                runner = EpisodeRunner(config=runtime_config, environment=environment,
                                    method=method, planner=planner, journal=journal, policy=policy,
                                    frozen_identity=runtime_frozen,
                                    current_identity=assembly.current_identity if phase == "formal" else None)
                                runner.run(master_episode_id=row["master_episode_id"], task=deepcopy(inputs.task),
                                    initial_state_id=pair["initial_state_id"], seed=pair["policy_seed"],
                                    initial_ledger=inputs.initial_ledger, initial_context=inputs.initial_context,
                                    schedule=schedule, resume=resume)
                            finally:
                                if runner is not None:
                                    runner.close()
                                else:
                                    if policy is not None:
                                        policy.close()
                                    if environment is not None:
                                        environment.close()
                    exports[condition] = export_journal(journal, output_dir=subdir, expected_cells=expected,
                                                        condition=condition, resume=resume)
                    if phase in {"pilot", "development"}:
                        rows_by_id = {row["master_episode_id"]: row for row in manifest}
                        journal_hash = _tree_hash(journal.root)
                        results = journal.read_records("results")
                        summaries = []
                        for key, episode in sorted(journal.read_records("episodes").items()):
                            # Keep all nine methods in raw records. Pilot gates
                            # summarize all non-oracle arms; comparator selection
                            # summarizes the six preregistered baseline methods.
                            selected_methods = config["methods"]["non_oracle"] if phase == "pilot" else config["methods"]["non_oracle"][2:]
                            if key[2] not in selected_methods:
                                continue
                            pair = rows_by_id[key[1]]["pair_fields"]
                            reached = episode["reached_events"]
                            complete = episode["status"] == "COMPLETED" and reached == episode["required_events"]
                            summary = {"phase": phase, "protocol": protocol,
                                "status": ("MOCK_QUALIFICATION_COMPLETE" if qualification else "COMPLETE") if complete else episode["status"],
                                "fixture": qualification, "master_episode_id": key[1], "method": key[2],
                                "information_condition": condition, "task_id": pair["task_id"],
                                "initial_state_id": pair["initial_state_id"], "policy_seed": pair["policy_seed"],
                                "event_indices": sorted(k[3] for k in results if k[:3] == key[:3] and k[3]),
                                "reached_event_count": reached, "success": episode["success"],
                                "runtime_identities": json_value(assembly.identity),
                                "integrity_status": "VALID", "missing_cells": 0,
                                "duplicate_cells": 0, "unexpected_cells": 0,
                                "journal_sha256": journal_hash, "journal_path": str(journal.root),
                                "evidence_admissibility": "mock_qualification" if qualification else phase}
                            if phase == "development":
                                result = results[(*key[:3], 4)]
                                values = [source["history_corruption"] for source in (result, result.get("metrics", {}), result.get("evaluation", {}))
                                          if isinstance(source, Mapping) and "history_corruption" in source]
                                corruption = values[0] if values and all(value == values[0] for value in values) else None
                                if isinstance(corruption, (list, dict)):
                                    corruption = len(corruption)
                                elif type(corruption) is bool:
                                    corruption = int(corruption)
                                summary.update(checkpoint=4, success=result["success"],
                                               history_corruption=corruption, trace_sha256=journal_hash)
                            summaries.append(summary)
                        name = "PILOT_QUALIFICATION.jsonl" if phase == "pilot" else "DEVELOPMENT_RECORDS.jsonl"
                        _publish(subdir / name, _jsonl(summaries), resume=resume)
            status = {"status": "MOCK_QUALIFICATION_COMPLETE" if qualification else "COMPLETE",
                      "phase": phase, "protocol": protocol, "fixture": qualification,
                      "evidence_admissibility": metadata["evidence_admissibility"],
                      "master_count": len(manifest), "method_count": len(methods),
                      "information_conditions": conditions, "exports": exports,
                      "performance_claims": False}
            if empty_formal:
                status.update(empty_shard=True, provider_calls=0, vla_calls=0, runtime_factory_calls=0,
                              executed_trajectory_count=0, result_rows_generated=0)
            _publish(root / "12_STATUS.json", _encoded(status), resume=resume)
            return status
        except Exception as exc:
            stop = {"status": getattr(exc, "status", "BLOCKED_RUNTIME_DEPENDENCY"),
                    "phase": phase, "protocol": protocol, "exception_type": type(exc).__name__,
                    "detail": "Execution stopped; journal retains exact attempted cells. No result cells were imputed."}
            # A resume may fail for a different transient dependency after an
            # earlier stop receipt was sealed.  Preserve that receipt and the
            # original exception instead of masking the useful failure with an
            # artifact-overwrite error.
            stop_path = root / "13_INFRASTRUCTURE_STOP.json"
            if not stop_path.exists():
                _publish(stop_path, _encoded(stop), resume=True)
            raise


def run_experiment(*, config_path: str | Path, output_dir: str | Path, phase: str,
                   protocol: str, resume: bool = False,
                   environ: Mapping[str, str] | None = None,
                   information_condition: str | None = None, task_catalog_path: str | Path | None = None,
                   manifest_path: str | Path | None = None, frozen_bundle_path: str | Path | None = None,
                   shard_index: int | None = None, num_shards: int = 8) -> dict:
    """Production entry point. A blocked dependency never invokes a runtime factory."""
    from .config import load_config
    from .manifest import build_manifest, read_manifest
    from .preflight import run_pilot_preflight, run_preflight
    from .task_catalog import load_task_catalog
    env = dict(os.environ if environ is None else environ)
    if frozen_bundle_path is not None:
        env["COPE_FREEZE_BUNDLE"] = str(frozen_bundle_path)
    root = Path(output_dir)
    if phase not in {"pilot", "formal", "development"} or protocol not in {"controlled", "end_to_end"}:
        raise ValueError("unsupported phase/protocol")
    if root.exists() and any(root.iterdir()) and not resume:
        raise RuntimeBlocked("INVALID_OUTPUT_DIRECTORY", "output directory is nonempty; use --resume")
    dependencies = None
    preflight = None
    try:
        config = load_config(config_path)
        if phase == "development" and (protocol != "end_to_end" or information_condition != "evidence_matched"):
            raise RuntimeBlocked("INVALID_DEVELOPMENT_DESIGN", "comparator development requires end_to_end and evidence_matched")
        dependencies = dependency_report(config, phase=phase, protocol=protocol, environ=env)
        catalog_path = task_catalog_path or env.get("COPE_TASK_CATALOG")
        catalog = load_task_catalog(catalog_path) if catalog_path else load_task_catalog()
        repo_root = Path(__file__).resolve().parents[2]
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
        loaded_manifest = read_manifest(manifest_path) if manifest_path else None
        manifest_commit = commit
        if loaded_manifest:
            revisions = {row.get("source_commit") for row in loaded_manifest}
            if len(revisions) != 1:
                raise RuntimeBlocked("INVALID_MANIFEST", "manifest contains different producer commits")
            manifest_commit = next(iter(revisions))
        if phase == "pilot":
            preflight = run_pilot_preflight(config, catalog, source_commit=manifest_commit)
        else:
            preflight = run_preflight(config, catalog, source_commit=manifest_commit,
                                      manifest=loaded_manifest if phase == "formal" else None)
        blockers = list(dependencies["blockers"])
        if not preflight["passed"]:
            blockers.insert(0, {"status": preflight["status"], "detail": "authentic catalog/calibration preflight failed"})
        bundle = None
        rows = None
        complete_manifest = None
        # Ownership is decided from the complete authentic design before loading
        # any runtime factory. An empty shard has no model/runtime dependency.
        if (phase == "formal" and preflight["passed"] and
                not any(blocker["status"] == "BLOCKED_FREEZE_REQUIRED" for blocker in blockers)):
            bundle = _load_freeze(env["COPE_FREEZE_BUNDLE"])
            complete_manifest = loaded_manifest if loaded_manifest is not None else build_manifest(config, catalog, source_commit=commit)
            rows = _select_formal_shard(complete_manifest, bundle, shard_index, num_shards)
            if not rows:
                blockers = []  # Static freeze validation still runs before publication.
        if blockers:
            report = {"status": blockers[0]["status"], "phase": phase, "protocol": protocol,
                      "passed": False, "blockers": blockers, "preflight": preflight,
                      "provider_calls": 0, "vla_calls": 0, "runtime_factory_calls": 0,
                      "evidence_admissibility": "blocked_no_execution", "result_rows_generated": 0}
            with DurableJournal(root):
                _publish(root / "13_INFRASTRUCTURE_STOP.json", _encoded(report), resume=resume)
            return report
        if phase != "formal":
            rows = pilot_manifest(config, catalog, source_commit=commit, phase=phase)
        if phase != "formal" and loaded_manifest is not None and stable_hash(loaded_manifest) != stable_hash(rows):
            raise RuntimeBlocked("INVALID_MANIFEST", "supplied pilot manifest differs from deterministic development design")
        if phase != "formal" and shard_index is not None:
            raise RuntimeBlocked("INVALID_SHARD", "pilot manifests are not formally sharded")
        assembly = None if phase == "formal" and not rows else load_runtime_factory(env["COPE_RUNTIME_FACTORY"], config=config)
        return execute_assembly(assembly=assembly, config=config, manifest=rows,
            catalog={task.task_id: task.to_dict() for task in catalog.tasks}, output_dir=root,
            phase=phase, protocol=protocol, source_commit=commit, resume=resume, frozen_bundle=bundle,
            information_condition=information_condition, shard_index=shard_index, num_shards=num_shards,
            catalog_data=catalog.to_dict(), full_manifest=complete_manifest)
    except Exception as exc:
        # Avoid logging arbitrary provider exceptions, which may contain credentials.
        report = {"status": getattr(exc, "status", "BLOCKED_RUNTIME_DEPENDENCY"),
                  "phase": phase, "protocol": protocol, "passed": False,
                  "exception_type": type(exc).__name__, "evidence_admissibility": "blocked_or_incomplete",
                  "detail": "Required input, runtime dependency or integrity gate failed; inspect immutable run artifacts."}
        if not (root / "13_INFRASTRUCTURE_STOP.json").exists():
            with DurableJournal(root):
                _publish(root / "13_INFRASTRUCTURE_STOP.json", _encoded(report), resume=resume)
        return report
