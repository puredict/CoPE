from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from .interruptions import AxisAlignedBox


METRICS_VERSION = "repeated_metrics_v1"


@dataclass(frozen=True)
class ProgressPreservationMetrics:
    progress_preservation: float
    completed_before: int
    retained_after: int
    regressions: tuple[str, ...]
    silent_commitment_loss: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_progress_preservation(
    before: Mapping[str, bool],
    after: Mapping[str, bool],
    *,
    commitment_names: Iterable[str],
    declared_modified_slots: Iterable[str] = (),
) -> ProgressPreservationMetrics:
    commitments = tuple(sorted(set(str(name) for name in commitment_names)))
    completed = tuple(name for name in commitments if bool(before.get(name, False)))
    retained = tuple(name for name in completed if bool(after.get(name, False)))
    regressions = tuple(name for name in completed if not bool(after.get(name, False)))
    declared = set(str(name) for name in declared_modified_slots)
    silent = tuple(name for name in regressions if name not in declared and f"progress:{name}" not in declared)
    score = 1.0 if not completed else len(retained) / len(completed)
    return ProgressPreservationMetrics(
        progress_preservation=float(score),
        completed_before=len(completed),
        retained_after=len(retained),
        regressions=regressions,
        silent_commitment_loss=silent,
    )


@dataclass(frozen=True)
class ConstraintSurvivalMetrics:
    unaffected_constraint_survival: float
    unaffected_total: int
    unaffected_survived: int
    lost_unaffected_slots: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_unaffected_constraint_survival(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    affected_slots: Iterable[str] = (),
) -> ConstraintSurvivalMetrics:
    affected = set(str(value) for value in affected_slots)
    candidates = tuple(sorted(key for key in before if key not in affected))
    lost = tuple(key for key in candidates if key not in after or after[key] != before[key])
    survived = len(candidates) - len(lost)
    score = 1.0 if not candidates else survived / len(candidates)
    return ConstraintSurvivalMetrics(
        unaffected_constraint_survival=float(score),
        unaffected_total=len(candidates),
        unaffected_survived=survived,
        lost_unaffected_slots=lost,
    )


@dataclass(frozen=True)
class StepViolationMetrics:
    translation_magnitude: float
    eef_speed: float | None
    contact_impulse_proxy: float | None
    gentle_translation_violation: bool
    gentle_speed_violation: bool
    gentle_contact_violation: bool
    no_go_violation_zone_ids: tuple[str, ...]
    safety_shield_intervened: bool
    raw_action: tuple[float, ...]
    executed_action: tuple[float, ...]

    @property
    def preference_violation(self) -> bool:
        return bool(
            self.gentle_translation_violation
            or self.gentle_speed_violation
            or self.gentle_contact_violation
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["preference_violation"] = self.preference_violation
        return value


def score_step_constraints(
    *,
    raw_action: Sequence[float],
    executed_action: Sequence[float] | None,
    eef_position_before: Sequence[float] | None,
    eef_position_after: Sequence[float] | None,
    dt_seconds: float | None,
    contact_impulse_proxy: float | None,
    gentle_preferences: Mapping[str, Mapping[str, Any]],
    active_no_go_zones: Mapping[str, AxisAlignedBox],
    safety_shield_intervened: bool,
) -> StepViolationMetrics:
    import math

    raw = tuple(float(value) for value in raw_action)
    executed = tuple(float(value) for value in (executed_action if executed_action is not None else raw))
    translation = math.sqrt(sum(value * value for value in raw[:3])) if len(raw) >= 3 else 0.0
    speed: float | None = None
    if (
        eef_position_before is not None
        and eef_position_after is not None
        and dt_seconds is not None
        and dt_seconds > 0
    ):
        speed = math.sqrt(
            sum(
                (float(after) - float(before)) ** 2
                for before, after in zip(eef_position_before[:3], eef_position_after[:3])
            )
        ) / float(dt_seconds)

    translation_violation = False
    speed_violation = False
    contact_violation = False
    for preference in gentle_preferences.values():
        translation_violation |= translation > float(preference["translation_ceiling"])
        if speed is not None:
            speed_violation |= speed > float(preference["eef_speed_ceiling"])
        if contact_impulse_proxy is not None:
            contact_violation |= contact_impulse_proxy > float(
                preference["contact_impulse_proxy_ceiling"]
            )

    no_go: list[str] = []
    if eef_position_after is not None:
        for zone_id, zone in active_no_go_zones.items():
            if zone.contains(eef_position_after) or (
                eef_position_before is not None
                and zone.segment_intersects(eef_position_before, eef_position_after)
            ):
                no_go.append(str(zone_id))

    return StepViolationMetrics(
        translation_magnitude=float(translation),
        eef_speed=speed,
        contact_impulse_proxy=(
            None if contact_impulse_proxy is None else float(contact_impulse_proxy)
        ),
        gentle_translation_violation=translation_violation,
        gentle_speed_violation=speed_violation,
        gentle_contact_violation=contact_violation,
        no_go_violation_zone_ids=tuple(sorted(no_go)),
        safety_shield_intervened=bool(safety_shield_intervened),
        raw_action=raw,
        executed_action=executed,
    )


def detect_invalid_restore(
    patch_operations: Iterable[Mapping[str, Any]],
    *,
    current_slot_versions: Mapping[str, int],
) -> tuple[str, ...]:
    """Return restore operations lacking valid lineage/version evidence."""

    invalid: list[str] = []
    for index, operation in enumerate(patch_operations):
        if str(operation.get("op")) != "restore":
            continue
        slot = str(operation.get("slot", ""))
        expected = operation.get("expected_version")
        source_event = operation.get("source_event_id")
        reason: str | None = None
        if not slot or slot not in current_slot_versions:
            reason = "unknown_slot"
        elif expected is None or int(expected) != int(current_slot_versions[slot]):
            reason = "version_mismatch"
        elif not source_event:
            reason = "missing_lineage"
        if reason:
            invalid.append(f"operation[{index}]/{slot or '<missing>'}:{reason}")
    return tuple(invalid)
