"""Pure, fail-closed grouping of the eight frozen formal output shards.

The caller verifies the freeze itself and each immutable journal before calling
this helper. Grouping never fills a missing cell or changes a source record.
Complete protocol/condition groups can be submitted independently; every such
group must include all eight shards, including explicitly empty shard outputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


class ShardIntegrityError(ValueError):
    """Submitted shards cannot be established as one frozen complete group."""


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ShardIntegrityError(detail)


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShardIntegrityError("manifest contains noncanonical values") from exc
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any, name: str) -> None:
    _require(isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
             f"{name} must be a sequence")


def group_formal_shards(bundle: Mapping[str, Any], manifest: Sequence[Mapping[str, Any]],
                        shards: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, list]]:
    """Verify frozen ownership and combine records without discarding any cells.

    Each input shard provides ``metadata`` and ``records``. Metadata binds
    ``freeze_sha256``, ``phase``, ``fixture``, ``shard_id``, ``shard_count``,
    ``protocol``, ``information_condition``, ``source_commit``,
    ``runtime_identities``, and the owned shard's ``manifest_sha256``. Additional
    input fields are permitted for the caller's journal audit. Returned groups
    own deep copies.
    """
    _require(isinstance(bundle, Mapping), "freeze must be a mapping")
    _require(bundle.get("status") == "FROZEN", "freeze is not FROZEN")
    frozen_hash = bundle.get("bundle_sha256")
    _require(isinstance(frozen_hash, str) and bool(re.fullmatch(r"[0-9a-f]{64}", frozen_hash)),
             "missing frozen bundle digest")
    _require(type(bundle.get("shard_count")) is int and bundle["shard_count"] == 8,
             "freeze requires exactly eight shards")
    git_identity = bundle.get("git")
    _require(isinstance(git_identity, Mapping), "missing frozen git identity")
    source_commit = git_identity.get("sha")
    _require(isinstance(source_commit, str) and bool(re.fullmatch(r"[0-9a-f]{40}", source_commit)),
             "missing frozen source commit")
    identities = bundle.get("identities")
    _require(isinstance(identities, Mapping), "missing frozen runtime identities")
    _sequence(manifest, "manifest")
    _require(bool(manifest), "empty formal manifest")
    masters: dict[str, Mapping[str, Any]] = {}
    owned: dict[int, list[str]] = {index: [] for index in range(8)}
    for row in manifest:
        _require(isinstance(row, Mapping), "manifest row must be a mapping")
        master = row.get("master_episode_id")
        _require(isinstance(master, str) and bool(master.strip()), "missing manifest master identity")
        _require(master not in masters, f"duplicate manifest master: {master}")
        masters[master] = row
        owner = int(hashlib.sha256(master.encode("utf-8")).hexdigest(), 16) % 8
        owned[owner].append(master)
    for values in owned.values():
        values.sort()
    frozen_shards = bundle.get("shards")
    _sequence(frozen_shards, "frozen shards")
    _require(len(frozen_shards) == 8, "freeze lacks all eight shard ownership records")
    frozen_seen = set()
    manifest_digests = {}
    for shard in frozen_shards:
        _require(isinstance(shard, Mapping), "frozen shard must be a mapping")
        index = shard.get("shard_id")
        _require(type(index) is int and 0 <= index < 8, "invalid frozen shard ID")
        _require(index not in frozen_seen, "duplicate frozen shard ID")
        frozen_seen.add(index)
        _require(shard.get("master_episode_ids") == owned[index],
                 f"frozen master ownership differs from manifest for shard {index}")
        expected_digest = _digest([dict(masters[mid]) for mid in owned[index]])
        _require(shard.get("manifest_sha256") == expected_digest,
                 f"manifest identity differs from freeze for shard {index}")
        manifest_digests[index] = expected_digest

    _sequence(shards, "submitted shards")
    _require(bool(shards), "no formal shards submitted")
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for submitted in shards:
        _require(isinstance(submitted, Mapping), "submitted shard must be a mapping")
        metadata = submitted.get("metadata")
        _require(isinstance(metadata, Mapping), "missing shard metadata")
        _require(metadata.get("freeze_sha256") == frozen_hash, "shard frozen identity mismatch")
        _require(metadata.get("source_commit") == source_commit, "shard source commit differs from freeze")
        runtime = metadata.get("runtime_identities")
        _require(isinstance(runtime, Mapping) and _digest(dict(runtime)) == _digest(dict(identities)),
                 "shard runtime identities differ from freeze")
        _require(metadata.get("phase") == "formal" and metadata.get("fixture") is False,
                 "shard phase or fixture is not admissible formal evidence")
        index = metadata.get("shard_id")
        _require(type(index) is int and 0 <= index < 8, "invalid submitted shard ID")
        _require(metadata.get("manifest_sha256") == manifest_digests[index],
                 f"shard {index} metadata manifest digest differs from frozen ownership")
        _require(type(metadata.get("shard_count")) is int and metadata["shard_count"] == 8,
                 "submitted shard count must be eight")
        protocol, condition = metadata.get("protocol"), metadata.get("information_condition")
        _require(protocol in ("controlled", "end_to_end"), "unknown shard protocol")
        _require(condition in ("evidence_matched", "token_matched"), "unknown information condition")
        _require("condition" not in metadata or metadata["condition"] == condition,
                 "contradictory shard information condition")
        group_key = (protocol, condition)
        group = grouped.setdefault(group_key, {"records": [], "shards": set(), "cells": set()})
        _require(index not in group["shards"], f"duplicate shard {index} in {group_key}")
        group["shards"].add(index)
        rows = submitted.get("records")
        _sequence(rows, "shard records")
        actual_masters: set[str] = set()
        for row in rows:
            _require(isinstance(row, Mapping), "result row must be a mapping")
            _require(row.get("protocol") == protocol and row.get("information_condition") == condition,
                     "result protocol/condition differs from its shard")
            _require("condition" not in row or row["condition"] == condition,
                     "contradictory result information condition")
            master = row.get("master_episode_id")
            _require(isinstance(master, str) and master in owned[index],
                     f"result master is not owned by shard {index}")
            _require(condition in masters[master].get("information_conditions", ()),
                     "result condition is absent from the frozen manifest")
            _require(protocol in masters[master].get("protocol_prefixes", {}),
                     "result protocol is absent from the frozen manifest")
            method, event = row.get("method"), row.get("event_index")
            _require(isinstance(method, str) and bool(method) and type(event) is int,
                     "malformed result cell identity")
            cell = (master, method, event)
            _require(cell not in group["cells"], f"duplicate result cell in {group_key}: {cell}")
            group["cells"].add(cell)
            actual_masters.add(master)
            group["records"].append(copy.deepcopy(dict(row)))
        _require(actual_masters == set(owned[index]),
                 f"missing or unexpected master sessions in shard {index}")

    output = {}
    for key in sorted(grouped):
        group = grouped[key]
        _require(group["shards"] == set(range(8)), f"missing formal shards in {key}")
        output[key] = {
            "records": sorted(group["records"], key=lambda r: (
                r["master_episode_id"], r["method"], r["event_index"])),
            "manifest": [copy.deepcopy(dict(masters[mid])) for mid in sorted(masters)],
        }
    return output
