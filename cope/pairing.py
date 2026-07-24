from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from cope.types import stable_hash


PAIR_KEY_PREFIX = "cope-pair-v1:"
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class DisturbanceSpec:
    event_type: str
    affected_object: str
    target_joint: str
    policy_step: int
    phase: str
    displacement_category: str
    delta_xyz: tuple[float, float, float]

    @classmethod
    def from_mapping(cls, value: Any) -> "DisturbanceSpec":
        if not isinstance(value, dict):
            raise ValueError("disturbance must be an object")
        delta = value.get("delta_xyz")
        if not isinstance(delta, list) or len(delta) != 3:
            raise ValueError("disturbance.delta_xyz must contain exactly three values")
        policy_step = int(value.get("policy_step", -1))
        if policy_step < 0:
            raise ValueError("disturbance.policy_step must be >= 0")
        result = cls(
            event_type=str(value.get("event_type", "")),
            affected_object=str(value.get("affected_object", "")),
            target_joint=str(value.get("target_joint", "")),
            policy_step=policy_step,
            phase=str(value.get("phase", "")),
            displacement_category=str(value.get("displacement_category", "")),
            delta_xyz=tuple(float(item) for item in delta),
        )
        for field in ("event_type", "affected_object", "target_joint", "phase", "displacement_category"):
            if not getattr(result, field):
                raise ValueError(f"disturbance.{field} must be non-empty")
        return result

    def oracle_event_packet(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "affected_object": self.affected_object,
            "event_time": {"policy_step": self.policy_step, "phase": self.phase},
            "displacement_category": self.displacement_category,
        }


@dataclass(frozen=True)
class PairSpec:
    schema_version: str
    pair_key: str
    task_id: int
    initial_state_id: int
    seed: int
    initial_state_digest: str
    geometry_audit_digest: str
    disturbance: DisturbanceSpec
    atlas_commit: str
    fixture: bool = False

    @property
    def key_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "initial_state_id": self.initial_state_id,
            "seed": self.seed,
            "initial_state_digest": self.initial_state_digest,
            "geometry_audit_digest": self.geometry_audit_digest,
            "disturbance": asdict(self.disturbance),
        }

    @property
    def expected_pair_key(self) -> str:
        return PAIR_KEY_PREFIX + stable_hash(self.key_payload)

    def event_packet(self, event_source: str) -> dict[str, Any]:
        if event_source == "oracle":
            return self.disturbance.oracle_event_packet()
        if event_source == "detected":
            return {
                **self.disturbance.oracle_event_packet(),
                "detector_output_required": True,
                "event_source": "detected",
            }
        raise ValueError(f"unsupported event_source {event_source!r}")

    @classmethod
    def from_mapping(cls, value: Any, *, default_commit: str = "") -> "PairSpec":
        if not isinstance(value, dict):
            raise ValueError("pair record must be an object")
        if value.get("record_type", "pair") != "pair":
            raise ValueError("record_type must be pair")
        pair = cls(
            schema_version=str(value.get("schema_version", "")),
            pair_key=str(value.get("pair_key", "")),
            task_id=int(value.get("task_id", -1)),
            initial_state_id=int(value.get("initial_state_id", -1)),
            seed=int(value.get("seed", -1)),
            initial_state_digest=str(value.get("initial_state_digest", "")),
            geometry_audit_digest=str(value.get("geometry_audit_digest", "")),
            disturbance=DisturbanceSpec.from_mapping(value.get("disturbance")),
            atlas_commit=str(value.get("atlas_commit") or default_commit),
            fixture=bool(value.get("fixture", False)),
        )
        if not pair.schema_version:
            raise ValueError("schema_version must be non-empty")
        if pair.task_id < 0 or pair.initial_state_id < 0 or pair.seed < 0:
            raise ValueError("task_id, initial_state_id, and seed must be >= 0")
        if not pair.initial_state_digest or not pair.geometry_audit_digest:
            raise ValueError("initial_state_digest and geometry_audit_digest are required")
        if pair.pair_key != pair.expected_pair_key:
            raise ValueError(
                f"unstable pair key {pair.pair_key!r}; expected deterministic key {pair.expected_pair_key!r}"
            )
        return pair


@dataclass(frozen=True)
class AtlasManifest:
    schema_version: str
    atlas_commit: str
    source_branch: str
    fixture: bool
    pairs: tuple[PairSpec, ...]
    path: str
    digest: str


def load_atlas(path: str | Path) -> AtlasManifest:
    manifest_path = Path(path)
    records: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{manifest_path}:{line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{manifest_path}:{line_number}: expected object")
            records.append(record)
    if not records or records[0].get("record_type") != "manifest_metadata":
        raise ValueError("atlas first record must be manifest_metadata")
    metadata = records[0]
    atlas_commit = str(metadata.get("atlas_commit", ""))
    pairs = tuple(PairSpec.from_mapping(record, default_commit=atlas_commit) for record in records[1:])
    keys = [pair.pair_key for pair in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("atlas contains duplicate pair keys")
    if any(pair.atlas_commit != atlas_commit for pair in pairs):
        raise ValueError("pair atlas_commit does not match manifest metadata")
    return AtlasManifest(
        schema_version=str(metadata.get("schema_version", "")),
        atlas_commit=atlas_commit,
        source_branch=str(metadata.get("source_branch", "")),
        fixture=bool(metadata.get("fixture", False)),
        pairs=pairs,
        path=str(manifest_path),
        digest=stable_hash(records),
    )


def select_pairs(
    pairs: Iterable[PairSpec],
    *,
    task_ids: Iterable[int],
    initial_state_ids: Iterable[int],
    seeds: Iterable[int],
) -> tuple[PairSpec, ...]:
    task_set = set(task_ids)
    state_set = set(initial_state_ids)
    seed_set = set(seeds)
    selected = tuple(
        pair
        for pair in pairs
        if pair.task_id in task_set
        and pair.initial_state_id in state_set
        and pair.seed in seed_set
    )
    expected = {
        (task_id, initial_state_id, seed)
        for task_id in task_set
        for initial_state_id in state_set
        for seed in seed_set
    }
    actual = {(pair.task_id, pair.initial_state_id, pair.seed) for pair in selected}
    missing = sorted(expected - actual)
    extras = sorted(actual - expected)
    if missing or extras or len(selected) != len(expected):
        raise ValueError(
            f"pair selection is not a complete Cartesian preregistration: "
            f"expected={len(expected)} actual={len(selected)} missing={missing[:10]} extras={extras[:10]}"
        )
    return tuple(sorted(selected, key=lambda pair: (pair.task_id, pair.initial_state_id, pair.seed)))


def validate_formal_atlas(manifest: AtlasManifest) -> list[str]:
    errors: list[str] = []
    if manifest.fixture or any(pair.fixture for pair in manifest.pairs):
        errors.append("formal atlas cannot contain fixtures")
    if manifest.source_branch != "exp/disturbance-causal-atlas":
        errors.append("formal atlas must identify source_branch=exp/disturbance-causal-atlas")
    if not GIT_SHA_PATTERN.fullmatch(manifest.atlas_commit):
        errors.append("formal atlas must record a real git commit SHA")
    if manifest.schema_version != "disturbance_atlas_v1":
        errors.append("formal atlas schema_version must be disturbance_atlas_v1")
    return errors
