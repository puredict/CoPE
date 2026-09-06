"""In-memory shard fixtures; no synthetic experiment artifacts are written."""
import copy
import hashlib
import json

import pytest

from cope_benchmark.repeated_v2.analysis_shards import ShardIntegrityError, group_formal_shards


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fixture(protocol="controlled", condition="evidence_matched"):
    # Few masters intentionally leave some shards empty. All eight must still
    # be submitted to demonstrate completion of the entire frozen assignment.
    manifest = [dict(master_episode_id=f"unit-master-{i}", pair_fields={"task_id": i},
                     information_conditions=["evidence_matched", "token_matched"],
                     protocol_prefixes={"controlled": {}, "end_to_end": {}}) for i in range(3)]
    ownership = {i: [] for i in range(8)}
    for row in manifest:
        owner = int(hashlib.sha256(row["master_episode_id"].encode()).hexdigest(), 16) % 8
        ownership[owner].append(row)
    bundle = dict(status="FROZEN", bundle_sha256="a" * 64, shard_count=8, shards=[],
                  git={"sha": "1" * 40}, identities={"reasoner": {"model_id": "unit-model"}})
    submitted = []
    for index, rows in ownership.items():
        rows.sort(key=lambda row: row["master_episode_id"])
        bundle["shards"].append(dict(shard_id=index,
            master_episode_ids=[r["master_episode_id"] for r in rows], manifest_sha256=digest(rows)))
        records = [dict(protocol=protocol, information_condition=condition,
                        master_episode_id=r["master_episode_id"], method="cope_typed_edit", event_index=0)
                   for r in rows]
        submitted.append(dict(metadata=dict(freeze_sha256=bundle["bundle_sha256"], phase="formal",
            fixture=False, shard_id=index, shard_count=8, protocol=protocol,
            source_commit=bundle["git"]["sha"], runtime_identities=copy.deepcopy(bundle["identities"]),
            manifest_sha256=digest(rows),
            information_condition=condition), records=records))
    return bundle, manifest, submitted


def nonempty(shards):
    return next(shard for shard in shards if shard["records"])


def test_complete_controlled_only_including_empty_shards_is_deterministic_and_pure():
    bundle, manifest, shards = fixture()
    before = copy.deepcopy((bundle, manifest, shards))
    groups = group_formal_shards(bundle, manifest, shards)
    assert set(groups) == {("controlled", "evidence_matched")}
    assert len(groups[("controlled", "evidence_matched")]["records"]) == 3
    assert group_formal_shards(bundle, list(reversed(manifest)), list(reversed(shards))) == groups
    assert (bundle, manifest, shards) == before
    groups[("controlled", "evidence_matched")]["records"][0]["method"] = "changed-return-copy"
    groups[("controlled", "evidence_matched")]["manifest"][0]["pair_fields"]["task_id"] = "changed"
    assert (bundle, manifest, shards) == before


def test_protocols_and_conditions_remain_separate():
    bundle, manifest, shards = fixture()
    _, _, other_protocol = fixture(protocol="end_to_end")
    _, _, other_condition = fixture(condition="token_matched")
    groups = group_formal_shards(bundle, manifest, shards + other_protocol + other_condition)
    assert len(groups) == 3
    assert all(len(group["records"]) == 3 for group in groups.values())


@pytest.mark.parametrize("mutation", ["omit_empty", "omit_nonempty", "duplicate_shard", "empty_nonempty",
    "foreign_master", "cross_shard_master", "duplicate_cell", "row_protocol", "row_condition",
    "row_alias", "metadata_alias", "manifest_bytes", "manifest_duplicate", "manifest_omission",
    "frozen_ownership", "frozen_digest", "frozen_duplicate", "no_submissions"])
def test_missing_mixed_tampered_or_duplicate_shards_fail_closed(mutation):
    bundle, manifest, shards = fixture()
    first = nonempty(shards)
    if mutation == "omit_empty": shards.remove(next(s for s in shards if not s["records"]))
    if mutation == "omit_nonempty": shards.remove(first)
    if mutation == "duplicate_shard": shards.append(copy.deepcopy(shards[0]))
    if mutation == "empty_nonempty": first["records"] = []
    if mutation == "foreign_master": first["records"][0]["master_episode_id"] = "foreign"
    if mutation == "cross_shard_master":
        target = next(s for s in shards if s is not first)
        target["records"].append(first["records"].pop())
    if mutation == "duplicate_cell": first["records"].append(copy.deepcopy(first["records"][0]))
    if mutation == "row_protocol": first["records"][0]["protocol"] = "end_to_end"
    if mutation == "row_condition": first["records"][0]["information_condition"] = "token_matched"
    if mutation == "row_alias": first["records"][0]["condition"] = "token_matched"
    if mutation == "metadata_alias": first["metadata"]["condition"] = "token_matched"
    if mutation == "manifest_bytes": manifest[0]["pair_fields"]["task_id"] = 99
    if mutation == "manifest_duplicate": manifest.append(copy.deepcopy(manifest[0]))
    if mutation == "manifest_omission": manifest.pop()
    if mutation == "frozen_ownership": bundle["shards"][0]["master_episode_ids"].append("foreign")
    if mutation == "frozen_digest": bundle["shards"][0]["manifest_sha256"] = "b" * 64
    if mutation == "frozen_duplicate": bundle["shards"][1] = copy.deepcopy(bundle["shards"][0])
    if mutation == "no_submissions": shards = []
    before = copy.deepcopy((bundle, manifest, shards))
    with pytest.raises(ShardIntegrityError): group_formal_shards(bundle, manifest, shards)
    assert (bundle, manifest, shards) == before


@pytest.mark.parametrize("field,value", [
    ("phase", "pilot"), ("phase", None), ("fixture", True), ("fixture", 0),
    ("freeze_sha256", "b" * 64), ("shard_id", True), ("shard_id", -1), ("shard_id", 8),
    ("shard_id", "0"), ("shard_count", 7), ("shard_count", True),
    ("protocol", "oracle"), ("information_condition", "combined"),
    ("source_commit", None), ("source_commit", "2" * 40),
    ("runtime_identities", None), ("runtime_identities", {}),
    ("runtime_identities", {"reasoner": {"model_id": "changed-unit-model"}}),
    ("manifest_sha256", None), ("manifest_sha256", "c" * 64),
])
def test_metadata_requires_exact_formal_bindings(field, value):
    bundle, manifest, shards = fixture()
    shards[0]["metadata"][field] = value
    with pytest.raises(ShardIntegrityError): group_formal_shards(bundle, manifest, shards)


def test_metadata_uses_its_owned_manifest_digest_including_empty_shards():
    bundle, manifest, shards = fixture()
    first = nonempty(shards)
    first["metadata"]["manifest_sha256"] = digest([])
    with pytest.raises(ShardIntegrityError, match="metadata manifest digest"):
        group_formal_shards(bundle, manifest, shards)


def test_runtime_identity_comparison_preserves_boolean_numeric_distinction():
    bundle, manifest, shards = fixture()
    bundle["identities"]["uses_privileged_state"] = False
    for shard in shards:
        shard["metadata"]["runtime_identities"] = copy.deepcopy(bundle["identities"])
    shards[0]["metadata"]["runtime_identities"]["uses_privileged_state"] = 0
    with pytest.raises(ShardIntegrityError, match="runtime identities"):
        group_formal_shards(bundle, manifest, shards)


def test_incomplete_second_group_invalidates_grouping_instead_of_silent_selection():
    bundle, manifest, shards = fixture()
    _, _, other = fixture(protocol="end_to_end")
    with pytest.raises(ShardIntegrityError, match="missing formal shards"):
        group_formal_shards(bundle, manifest, shards + other[:-1])
