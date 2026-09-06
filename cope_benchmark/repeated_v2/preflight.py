"""Zero-call phase-1 validation. No provider discovery, imports, or inference."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json, canonical_sha256
from .config import validate_config
from .manifest import build_manifest, event_cell_keys, expected_counts, validate_manifest
from .task_catalog import CatalogBlockedError, select_eligible_tasks, task_catalog_gaps
from .scheduler import MasterSchedule
from .enums import EventFamily
from .task_calibration import validate_calibration_split


def run_preflight(config: Mapping[str, Any], catalog: Any, *, source_commit: str,
                  manifest: list[dict[str, Any]] | None = None,
                  allow_synthetic: bool = False) -> dict[str, Any]:
    """Deterministic report given fixed inputs; no timestamps or process state.

    Synthetic opt-in exists only at this pure unit-test boundary. CLI never
    enables it. Missing real task evidence blocks a formal-ready manifest.
    """
    from .events import phase1_contract_self_check
    checks = phase1_contract_self_check()
    validate_calibration_split()
    checks["calibration_formal_seeds_disjoint"] = True
    config_errors = validate_config(config)
    checks["frozen_config"] = not config_errors
    errors = list(config_errors)
    gaps = task_catalog_gaps(catalog, allow_synthetic=allow_synthetic)
    checks["catalog_complete"] = not gaps
    errors.extend(gaps)
    selected = ()
    selection_status = None
    try:
        selected = select_eligible_tasks(catalog, allow_synthetic=allow_synthetic)
    except CatalogBlockedError as exc:
        selection_status = exc.status
        errors.extend(exc.reasons)
    checks["at_least_eight_eligible_tasks"] = len(selected) >= 8
    rows = None
    validation = None
    if not errors and selected:
        try:
            rows = build_manifest(config, catalog, source_commit=source_commit, allow_synthetic=allow_synthetic)
            checks["manifest_deterministic"] = canonical_json(rows) == canonical_json(
                build_manifest(config, catalog, source_commit=source_commit, allow_synthetic=allow_synthetic))
            validation = validate_manifest(rows if manifest is None else manifest, config, catalog,
                                           source_commit=source_commit, allow_synthetic=allow_synthetic)
            checks["manifest_integrity"] = validation["passed"]
            errors.extend(validation["errors"])
            keys = list(event_cell_keys(rows))
            counts = expected_counts(len(selected), config)
            checks["exact_event_cells_and_unique_keys"] = len(keys) == len(set(keys)) == counts["all_conditions"]["event_cells"]
            checks["exact_master_sessions"] = len(rows) == counts["unique_master_sessions"]
            schedules = [MasterSchedule.from_dict(row["master_schedule"]) for row in rows]
            checks["legal_schedule_prefixes"] = all(
                schedule.prefix(k) == schedule.events[:k]
                for schedule in schedules for k in (0, 1, 2, 4, 8))
            checks["all_event_families_covered"] = {event.family for schedule in schedules
                                                         for event in schedule.events} == set(EventFamily)
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(str(exc))
            checks["manifest_integrity"] = False
    else:
        checks["manifest_integrity"] = False
    for name, passed in checks.items():
        if not passed:
            errors.append(f"check failed: {name}")
    ready = not errors and all(checks.values())
    status = "PHASE1_PREFLIGHT_PASSED" if ready else (
        "INVALID_PROTOCOL_CONFIG" if config_errors else selection_status or "BLOCKED_PHASE1_PREFLIGHT")
    if allow_synthetic and ready:
        status = "SYNTHETIC_PHASE1_CHECKS_PASSED_NOT_FORMAL_EVIDENCE"
    return {
        "schema_version": "cope-repeated-v2/preflight-1",
        "scope": "phase1_contracts_catalog_schedules_manifest",
        "status": status,
        "passed": ready,
        "formal_execution_authorized": False,
        "provider_calls": 0,
        "vla_calls": 0,
        "source_commit": source_commit,
        "config_sha256": canonical_sha256(config),
        "task_catalog_sha256": canonical_sha256(catalog.to_dict()),
        "manifest_sha256": canonical_sha256(rows) if rows is not None else None,
        "eligible_task_ids": [t.task_id for t in selected],
        "catalog_gap_count": len(gaps),
        "checks": dict(sorted(checks.items())),
        "errors": sorted(set(errors)),
        "manifest_validation": validation,
        "expected_counts": expected_counts(len(selected), config) if not config_errors else None,
        "planned_counts_if_eight_eligible": expected_counts(8, config) if not config_errors else None,
        "planned_counts_if_ten_eligible": expected_counts(10, config) if not config_errors else None,
        "deferred_gates": [
            "phase2_method_parsers_and_semantic_information_parity",
            "phase2_atomic_state_engines_and_pure_compiler",
            "phase3_dynamic_evaluator_and_real_simulator_injection",
            "phase3_durable_journal_and_resume",
            "phase3_formal_provider_and_learned_VLA_adapters",
            "phase4_statistics_claims_and_formal_freeze",
        ],
    }
