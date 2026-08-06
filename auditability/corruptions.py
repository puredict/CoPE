from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Any, Callable

from auditability import SCHEMA_VERSION
from auditability.common import content_hash, read_jsonl, stable_id, write_json, write_jsonl
from auditability.schema_adapter import adapt_episode, load_episode
from auditability.trace_state import state_hash


Mutation = Callable[[dict[str, Any], random.Random], str | None]


def _patch_op(patch: dict[str, Any]) -> str:
    return str(patch.get("op") or patch.get("operation") or "").lower()


def _missing_revalidate(episode: dict[str, Any], _: random.Random) -> str | None:
    for patch in episode["cope"]["patches"]:
        if _patch_op(patch) == "restore":
            validation_id = patch.get("revalidation_id") or patch.get("validation_id")
            outputs = episode["cope"]["validator_outputs"]
            for index, output in enumerate(outputs):
                if output["id"] == validation_id:
                    del outputs[index]
                    return f"/cope/validator_outputs/{index}"
    return None


def _replace_slot_id(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, patch in enumerate(episode["cope"]["patches"]):
        if patch.get("target_slot_id") or patch.get("slot_id"):
            patch["target_slot_id"] = stable_id("slot", episode["episode_id"], "missing")
            patch.pop("slot_id", None)
            return f"/cope/patches/{index}/target_slot_id"
    return None


def _dangling_lineage(episode: dict[str, Any], _: random.Random) -> str | None:
    slots = episode["cope"]["slots"]
    if not slots:
        return None
    slots[0]["parent_slot_id"] = stable_id("slot", episode["episode_id"], "dangling")
    return "/cope/slots/0/parent_slot_id"


def _priority_conflict(episode: dict[str, Any], _: random.Random) -> str | None:
    slots = episode["cope"]["slots"]
    active = [slot for slot in slots if str(slot.get("status", "active")).lower() == "active"]
    if not active:
        return None
    clone = copy.deepcopy(active[0])
    clone["id"] = stable_id("slot", episode["episode_id"], "priority-conflict")
    clone["value"] = f"conflict:{clone.get('value')}"
    clone["parent_slot_id"] = active[0]["id"]
    slots.append(clone)
    return f"/cope/slots/{len(slots) - 1}"


def _delete_preference(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, slot in enumerate(episode["cope"]["slots"]):
        kind = str(slot.get("kind") or slot.get("type") or "").lower()
        if kind in {"preference", "user_preference"} or str(slot.get("source", "")).lower() == "user":
            removed_id = slot["id"]
            del episode["cope"]["slots"][index]
            for state in episode["cope"]["states"][1:]:
                if isinstance(state.get("slots"), list):
                    state["slots"] = [
                        child for child in state["slots"] if child.get("id") != removed_id
                    ]
            return f"/cope/slots/{index}"
    return None


def _unexplained_restore(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, patch in enumerate(episode["cope"]["patches"]):
        if _patch_op(patch) == "restore":
            patch.pop("revalidation_id", None)
            patch.pop("validation_id", None)
            patch.pop("source_event_id", None)
            patch["evidence_refs"] = []
            return f"/cope/patches/{index}"
    return None


def _expire_to_restore(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, patch in enumerate(episode["cope"]["patches"]):
        if _patch_op(patch) == "expire":
            patch["op"] = "restore"
            patch.pop("operation", None)
            patch.pop("revalidation_id", None)
            return f"/cope/patches/{index}/op"
    return None


def _delete_event_provenance(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, patch in enumerate(episode["cope"]["patches"]):
        if patch.get("source_event_id") or patch.get("evidence_refs"):
            patch.pop("source_event_id", None)
            patch["evidence_refs"] = []
            return f"/cope/patches/{index}"
    return None


def _modify_state_hash(episode: dict[str, Any], _: random.Random) -> str | None:
    for index, state in enumerate(episode["cope"]["states"]):
        if "state_hash" in state:
            state["state_hash"] = "0" * 64
            return f"/cope/states/{index}/state_hash"
    return None


def _shuffle_patch_order(episode: dict[str, Any], rng: random.Random) -> str | None:
    patches = episode["cope"]["patches"]
    if len(patches) < 2:
        return None
    original = [patch["id"] for patch in patches]
    for _ in range(10):
        rng.shuffle(patches)
        if [patch["id"] for patch in patches] != original:
            return "/cope/patches"
    patches.reverse()
    return "/cope/patches"


CORRUPTIONS: dict[str, Mutation] = {
    "missing_revalidate": _missing_revalidate,
    "slot_id_replaced": _replace_slot_id,
    "dangling_lineage": _dangling_lineage,
    "priority_conflict": _priority_conflict,
    "missing_user_preference": _delete_preference,
    "unexplained_restore": _unexplained_restore,
    "expire_to_restore": _expire_to_restore,
    "missing_event_provenance": _delete_event_provenance,
    "state_hash_mismatch": _modify_state_hash,
    "patch_order_shuffled": _shuffle_patch_order,
}


def generate_corruptions(
    episode: dict[str, Any], *, seed: int, include_negative_control: bool = True
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    original_hash = content_hash(episode)
    outputs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for error_type, mutate in CORRUPTIONS.items():
        candidate = copy.deepcopy(episode)
        rng = random.Random(f"{seed}:{episode['episode_id']}:{error_type}")
        location = mutate(candidate, rng)
        if location is None:
            continue
        if error_type != "state_hash_mismatch":
            for state in candidate["cope"]["states"]:
                if "state_hash" in state:
                    state["state_hash"] = state_hash(state)
        corrupted_hash = content_hash(candidate)
        if corrupted_hash == original_hash:
            raise AssertionError(f"corruption {error_type} did not change the trace")
        corruption_id = stable_id(
            "corruption", episode["episode_id"], error_type, seed
        )
        candidate["corruption_id"] = corruption_id
        manifest = {
            "corruption_id": corruption_id,
            "episode_id": episode["episode_id"],
            "error_type": error_type,
            "location": location,
            "negative_control": False,
            "seed": seed,
            "schema_version": SCHEMA_VERSION,
            "original_hash": original_hash,
            "corrupted_hash": corrupted_hash,
        }
        outputs.append((candidate, manifest))
    if include_negative_control:
        candidate = copy.deepcopy(episode)
        corruption_id = stable_id(
            "corruption", episode["episode_id"], "negative-control", seed
        )
        candidate["corruption_id"] = corruption_id
        outputs.append(
            (
                candidate,
                {
                    "corruption_id": corruption_id,
                    "episode_id": episode["episode_id"],
                    "error_type": "none",
                    "location": None,
                    "negative_control": True,
                    "seed": seed,
                    "schema_version": SCHEMA_VERSION,
                    "original_hash": original_hash,
                    "corrupted_hash": original_hash,
                },
            )
        )
    return outputs


def _load_inputs(path: Path) -> list[dict[str, Any]]:
    if path.is_file() and path.suffix == ".jsonl":
        return [
            row if row.get("schema_version") == SCHEMA_VERSION else adapt_episode(row, origin=str(path))
            for row in read_jsonl(path)
        ]
    return [load_episode(path)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic corrupted traces.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {args.schema_version}")
    generated = []
    for episode in _load_inputs(args.input):
        generated.extend(generate_corruptions(episode, seed=args.seed))
    manifests = [manifest for _, manifest in generated]
    config = {
        "input": str(args.input.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "seed": args.seed,
        "schema_version": args.schema_version,
        "corruption_types": list(CORRUPTIONS),
    }
    summary = {
        "config_hash": content_hash(config),
        "trace_count": len(generated),
        "negative_control_count": sum(row["negative_control"] for row in manifests),
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for trace, manifest in generated:
        path = args.output_dir / "traces" / f"{manifest['corruption_id'].replace(':', '_')}.json"
        if path.exists() and args.resume:
            continue
        write_json(path, trace)
    write_jsonl(
        args.output_dir / "corruption_manifest.jsonl",
        manifests,
        resume_key="corruption_id" if args.resume else None,
    )
    write_json(
        args.output_dir / "manifest.json",
        {**summary, "config": config},
        overwrite=args.resume,
    )
    print(json.dumps({**summary, "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
