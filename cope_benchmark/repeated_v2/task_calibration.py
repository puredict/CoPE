"""Offline, fail-closed calibration evidence validation for repeated v2.

This module imports no policy, simulator, or provider. Missing episodes are not
failures or zeroes: an incomplete preregistered grid blocks task selection.
References, digests, and measured-policy declarations are audit attestations,
not proof that a physical rollout happened. Before ingestion, the evidence
custodian must inspect the referenced terminal records, hash their exact bytes,
and verify the recorded checkpoint, observation privilege, and protocol. This
pure validator does not fetch evidence or silently trust a known fake adapter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
import math
import re
from typing import Any, Iterable, Mapping


CALIBRATION_STATE_IDS = (0, 1, 2, 3, 4)
CALIBRATION_POLICY_SEEDS = (101, 131)
FORMAL_STATE_IDS = (0, 1, 2, 3, 4)
FORMAL_POLICY_SEEDS = (11, 29, 47)
CLEAN_SUCCESS_INTERVAL = (0.40, 0.95)
CALIBRATION_SCHEMA_VERSION = "repeated_v2_clean_calibration_episode_v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class CalibrationBlockedError(ValueError):
    def __init__(self, reasons: Iterable[str], status: str = "BLOCKED_CALIBRATION_EVIDENCE"):
        self.status = status
        self.reasons = tuple(sorted(set(reasons)))
        super().__init__(f"{status}: {'; '.join(self.reasons)}")


def validate_calibration_split(
    state_ids: Iterable[int] = CALIBRATION_STATE_IDS,
    policy_seeds: Iterable[int] = CALIBRATION_POLICY_SEEDS,
    formal_policy_seeds: Iterable[int] = FORMAL_POLICY_SEEDS,
) -> None:
    states, seeds, formal = tuple(state_ids), tuple(policy_seeds), tuple(formal_policy_seeds)
    if set(seeds) & set(formal):
        raise CalibrationBlockedError(("calibration and formal policy seeds overlap",))
    if states != CALIBRATION_STATE_IDS or seeds != CALIBRATION_POLICY_SEEDS or formal != FORMAL_POLICY_SEEDS:
        raise CalibrationBlockedError(("calibration/formal split differs from the frozen configuration",))


def calibration_grid(task_ids: Iterable[int] = range(10)) -> tuple[dict[str, int], ...]:
    """Exactly ten disjoint-policy-seed calibration cells for each task."""
    validate_calibration_split()
    ids = tuple(task_ids)
    if any(type(task_id) is not int or not 0 <= task_id < 10 for task_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("task IDs must be distinct integers in 0..9")
    return tuple(
        {"task_id": task_id, "initial_state_id": state_id, "policy_seed": seed}
        for task_id, state_id, seed in product(sorted(ids), CALIBRATION_STATE_IDS, CALIBRATION_POLICY_SEEDS)
    )


@dataclass(frozen=True)
class CalibrationEpisode:
    schema_version: str
    task_id: int
    initial_state_id: int
    policy_seed: int
    success: bool
    status: str
    learned_policy: bool
    privileged_policy_state: bool
    clean_episode: bool
    policy_id: str
    checkpoint_sha256: str
    protocol_sha256: str
    initial_state_sha256: str
    evidence_ref: str
    evidence_sha256: str
    provenance_kind: str
    max_policy_steps: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CalibrationEpisode":
        try:
            record = cls(**dict(value))
        except (TypeError, ValueError) as exc:
            raise CalibrationBlockedError((f"invalid calibration record schema: {exc}",)) from exc
        record.validate()
        return record

    def validate(self) -> None:
        errors = []
        if self.schema_version != CALIBRATION_SCHEMA_VERSION:
            errors.append("calibration schema is not repeated v2")
        if type(self.task_id) is not int or not 0 <= self.task_id < 10:
            errors.append("invalid task_id")
        if type(self.initial_state_id) is not int or self.initial_state_id not in CALIBRATION_STATE_IDS:
            errors.append("initial_state_id outside preregistered grid")
        if type(self.policy_seed) is not int or self.policy_seed not in CALIBRATION_POLICY_SEEDS:
            errors.append("policy_seed outside preregistered calibration split")
        for name in ("success", "learned_policy", "privileged_policy_state", "clean_episode"):
            if type(getattr(self, name)) is not bool:
                errors.append(f"{name} must be an explicit boolean")
        if self.learned_policy is not True or self.privileged_policy_state is not False:
            errors.append("clean calibration requires a learned non-privileged policy")
        if self.clean_episode is not True:
            errors.append("calibration must contain zero interruption events")
        if self.status not in ("completed", "timeout", "manual_intervention"):
            errors.append("calibration is missing a valid terminal outcome")
        if self.status != "completed" and self.success is not False:
            errors.append("timeout/manual intervention must count as failure")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            errors.append("policy_id is required")
        elif self.provenance_kind == "measured" and re.search(
            r"(?:^|[^a-z])(fake|mock|scripted|oracle|synthetic|controlled)(?:$|[^a-z])", self.policy_id.lower()
        ):
            errors.append("formal calibration forbids fake/scripted/oracle/controlled policy identifiers")
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
            errors.append("evidence_ref is required")
        if self.provenance_kind not in ("measured", "synthetic_test_fixture"):
            errors.append("unsupported calibration provenance")
        for name in ("checkpoint_sha256", "protocol_sha256", "initial_state_sha256", "evidence_sha256"):
            if not isinstance(getattr(self, name), str) or not _SHA256.fullmatch(getattr(self, name)):
                errors.append(f"{name} must be a SHA256 digest")
        if type(self.max_policy_steps) is not int or self.max_policy_steps != 260:
            errors.append("calibration policy horizon differs from frozen v2 horizon 260")
        if errors:
            raise CalibrationBlockedError(errors)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationSummary:
    task_id: int
    total: int
    successes: int
    clean_success_rate: float
    eligible_success_rate: bool
    policy_id: str
    checkpoint_sha256: str
    protocol_sha256: str
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_calibration(
    task_id: int,
    records: Iterable[CalibrationEpisode | Mapping[str, Any]],
    *,
    initial_state_digests: Mapping[str, str] | None = None,
    allow_synthetic: bool = False,
) -> CalibrationSummary:
    """Validate the exact grid before computing a rate (no case deletion)."""
    parsed = tuple(r if isinstance(r, CalibrationEpisode) else CalibrationEpisode.from_dict(r) for r in records)
    expected = {(state, seed) for state, seed in product(CALIBRATION_STATE_IDS, CALIBRATION_POLICY_SEEDS)}
    actual: set[tuple[int, int]] = set()
    errors = []
    for record in parsed:
        record.validate()
        if record.task_id != task_id:
            errors.append("calibration record belongs to another task")
        key = (record.initial_state_id, record.policy_seed)
        if key in actual:
            errors.append(f"duplicate calibration cell {key}")
        actual.add(key)
        if record.provenance_kind != "measured" and not allow_synthetic:
            errors.append("synthetic calibration is forbidden in formal catalogs")
        if initial_state_digests is not None and initial_state_digests.get(str(record.initial_state_id)) != record.initial_state_sha256:
            errors.append(f"initial state digest mismatch for state {record.initial_state_id}")
    if actual != expected:
        errors.append(f"incomplete calibration grid: expected 10 cells, missing {sorted(expected - actual)}, unexpected {sorted(actual - expected)}")
    for field in ("policy_id", "checkpoint_sha256", "protocol_sha256", "provenance_kind"):
        if len({getattr(record, field) for record in parsed}) != 1:
            errors.append(f"calibration must use one {field}")
    if len({record.evidence_ref for record in parsed}) != len(parsed):
        errors.append("each calibration cell requires a distinct evidence record")
    if errors:
        raise CalibrationBlockedError(errors)
    successes = sum(record.success for record in parsed)
    rate = successes / len(expected)
    assert math.isfinite(rate)
    first = parsed[0]
    return CalibrationSummary(task_id, len(expected), successes, rate,
                              CLEAN_SUCCESS_INTERVAL[0] <= rate <= CLEAN_SUCCESS_INTERVAL[1],
                              first.policy_id, first.checkpoint_sha256, first.protocol_sha256,
                              tuple(sorted(record.evidence_ref for record in parsed)))
