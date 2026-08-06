#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
from pathlib import Path

from cope.providers.base import load_object
from cope.types import stable_hash


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    with args.config_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError("semantic pilot config must contain exactly one row")
    row = rows[0]
    checks: dict[str, bool] = {}
    checks["schema"] = row["schema_version"] == "cope-semantic-task1-pilot-config-v1"
    checks["task"] = row["task_suite"] == "libero_10" and row["task_id"] == "1"
    checks["checkpoint_identity"] = (
        row["checkpoint_id"] == "openvla-7b-finetuned-libero-10"
        and row["checkpoint_unnorm_key"] == "libero_10"
    )
    checkpoint = Path(row["checkpoint_path"])
    checks["checkpoint_path"] = checkpoint.is_dir()
    checks["weight_file_count"] = (
        len(list(checkpoint.glob("model-*-of-*.safetensors")))
        == int(row["expected_weight_files"])
    )
    bddl = Path(row["bddl_path"])
    init_states = Path(row["init_states_path"])
    checks["bddl_hash"] = bddl.is_file() and sha256_file(bddl) == row["bddl_sha256"]
    checks["init_states_hash"] = (
        init_states.is_file() and sha256_file(init_states) == row["init_states_sha256"]
    )
    factory = load_object(row["predicate_factory"])
    checks["predicate_factory"] = callable(factory)
    commit_check = subprocess.run(
        ["git", "cat-file", "-e", f"{row['predicate_producer_commit']}^{{commit}}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    checks["predicate_commit"] = commit_check.returncode == 0
    checks["predicate_budget"] = (
        "predicate_snapshot" in row["observation_fields"].split(";")
    )
    checks["event_families"] = set(row["event_types"].split(";")) == {
        "replace_pending_goal",
        "cancel_pending_goal",
    }

    manifest_path = repo_root / row["pilot_manifest_path"]
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    checks["reserved_manifest"] = (
        len(manifest) == 2
        and {item["state_id"] for item in manifest} == set(row["reserved_state_ids"].split(";"))
        and {item["event_type"] for item in manifest}
        == {"replace_pending_goal", "cancel_pending_goal"}
        and all(item["status"] == "reserved_uninspected" for item in manifest)
    )
    checks["rollout_locked"] = row["rollout_authorized"].lower() == "false"
    passed = all(checks.values())
    result = {
        "schema_version": row["schema_version"],
        "config_sha256": stable_hash(row),
        **checks,
        "reserved_state_packets_read": 0,
        "gpu_used": False,
        "rollout_authorized": False,
        "passed": passed,
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result), lineterminator="\n")
        writer.writeheader()
        writer.writerow(result)
    print(
        f"checks={len(checks)} passed={sum(checks.values())} "
        "reserved_state_packets_read=0 rollout_authorized=false"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
