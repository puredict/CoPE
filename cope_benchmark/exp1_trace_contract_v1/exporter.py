"""Read-only source exporter for already-normalized public trace bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .canonical import canonical_json, strict_loads
from .contract import RuntimeTraceBundleV1


class ExportBoundaryError(ValueError):
    pass


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def export_public_bundle(
    source: str | Path,
    destination: str | Path,
    *,
    read_only_roots: Iterable[str | Path] = (),
) -> str:
    """Validate and copy canonical public bytes without editing any source tree.

    Destination creation is exclusive, and callers can protect one or more
    Experiment-1 roots against accidental output writes.
    """
    source_path = Path(source).expanduser().resolve(strict=True)
    destination_path = Path(destination).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise ExportBoundaryError("source must be a file")
    if source_path == destination_path:
        raise ExportBoundaryError("source and destination must differ")
    for root in read_only_roots:
        root_path = Path(root).expanduser().resolve(strict=True)
        if _inside(destination_path, root_path):
            raise ExportBoundaryError("destination is inside a read-only Experiment-1 root")
    record = RuntimeTraceBundleV1.from_dict(strict_loads(source_path.read_text(encoding="utf-8")))
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with destination_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(record))
        handle.write("\n")
    return record.sha256
