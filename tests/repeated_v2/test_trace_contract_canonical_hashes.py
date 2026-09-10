import hashlib
import json
from pathlib import Path

from cope_benchmark.repeated_v2.canonical import canonical_json, canonical_sha256
from cope_benchmark.repeated_v2.trace_contract_validation_v1 import load_canonical_record


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "frozen/repeated_v2_trace_contract_v1/fixtures"


def test_all_fixtures_are_canonical_and_hash_stable():
    for path in sorted(FIXTURES.glob("*.json")):
        value = load_canonical_record(path)
        assert path.read_text() == canonical_json(value) + "\n"
        assert canonical_sha256(value) == hashlib.sha256(canonical_json(value).encode()).hexdigest()


def test_reordered_object_keys_have_same_hash_but_array_order_does_not():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
    assert canonical_sha256(["event-1", "event-2"]) != canonical_sha256(["event-2", "event-1"])


def test_frozen_manifest_matches_every_listed_byte():
    manifest_path = ROOT / "frozen/repeated_v2_trace_contract_v1/HASH_MANIFEST.json"
    manifest = load_canonical_record(manifest_path)
    assert manifest["schema_version"] == "exp1-trace-contract-v1"
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert canonical_sha256(manifest["files"]) == manifest["files_sha256"]
