from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Iterator


ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9_.:/-]+$")
FAILURE_LAYERS = (
    "perception",
    "event_detection",
    "full_regeneration",
    "patch_generation",
    "schema_parsing",
    "validation",
    "planning",
    "low_level_control",
    "termination_accounting",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(namespace: str, *parts: Any, length: int = 20) -> str:
    digest = hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()[:length]
    return f"{namespace}:{digest}"


def is_parseable_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_RE.fullmatch(value))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value


def ensure_output(path: Path, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, value: Any, *, overwrite: bool = False) -> None:
    ensure_output(path, overwrite=overwrite)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def write_jsonl(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    overwrite: bool = False,
    resume_key: str | None = None,
) -> int:
    existing: set[Any] = set()
    mode = "w"
    if path.exists():
        if resume_key is None:
            if not overwrite:
                raise FileExistsError(f"refusing to overwrite existing output: {path}")
        else:
            existing = {row.get(resume_key) for row in iter_jsonl(path)}
            mode = "a"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with path.open(mode, encoding="utf-8") as handle:
        for row in rows:
            if resume_key is not None and row.get(resume_key) in existing:
                continue
            handle.write(canonical_json(row))
            handle.write("\n")
            written += 1
            if resume_key is not None:
                existing.add(row.get(resume_key))
    return written


def numeric_step(record: dict[str, Any]) -> int:
    for key in ("policy_step", "step", "environment_step", "timestamp_step"):
        value = record.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return 0


def ids_in_episode(episode: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if (key == "id" or key.endswith("_id")) and is_parseable_id(child):
                    found.add(child)
                elif key.endswith("_ids") or key in {
                    "supporting_ids",
                    "evidence_refs",
                    "provenance_refs",
                    "lineage",
                }:
                    if isinstance(child, list):
                        found.update(item for item in child if is_parseable_id(item))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(episode)
    return found


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.strip().lower().split())


def token_set(value: Any) -> list[str]:
    return re.findall(r"[\w.-]+", normalize_text(value), flags=re.UNICODE)
