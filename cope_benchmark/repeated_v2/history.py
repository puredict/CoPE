"""Frozen, deterministic retrieval over exclusively public history chunks."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .prompts import primitive, scan_public_input

_WORD = re.compile(r"[\w-]+", re.UNICODE)


@dataclass(frozen=True)
class PublicHistoryChunk:
    chunk_id: str
    sequence: int
    text: str
    sha256: str


@dataclass(frozen=True)
class FrozenRetrieverConfig:
    version: str = "public-lexical-overlap-v1"
    token_budget: int = 2048

    def __post_init__(self) -> None:
        if self.version != "public-lexical-overlap-v1" or self.token_budget <= 0:
            raise ValueError("Unsupported retriever configuration")


class PublicHistoryIndex:
    """Append-only index. Token budget uses a documented conservative byte unit.

    UTF-8 bytes upper-bound common subword token counts; no chunk is partially
    reconstructed or semantically repaired. Ranking and tie breaks are frozen.
    """

    def __init__(self, config: FrozenRetrieverConfig | None = None):
        self.config = config or FrozenRetrieverConfig()
        self.chunks: list[PublicHistoryChunk] = []

    def ingest(self, public_history: Sequence[Mapping[str, Any]]) -> None:
        from .evidence import assert_public_safe

        scan_public_input(public_history, generic=True)
        assert_public_safe(public_history)
        texts = [json.dumps(primitive(record), ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False) for record in public_history]
        if len(texts) < len(self.chunks) or any(chunk.text != texts[i] for i, chunk in enumerate(self.chunks)):
            raise ValueError("Public history must extend its immutable prefix")
        for sequence in range(len(self.chunks), len(texts)):
            text = texts[sequence]
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self.chunks.append(PublicHistoryChunk(f"public-{sequence}-{digest[:12]}", sequence, text, digest))

    def retrieve(self, query: Any) -> list[dict[str, Any]]:
        scan_public_input(query, generic=True)
        query_terms = set(_WORD.findall(json.dumps(primitive(query), ensure_ascii=False).casefold()))
        ranked = sorted(self.chunks, key=lambda chunk: (
            -len(query_terms & set(_WORD.findall(chunk.text.casefold()))), -chunk.sequence, chunk.sha256))
        result: list[dict[str, Any]] = []
        for chunk in ranked:
            candidate = {"chunk_id": chunk.chunk_id, "sequence": chunk.sequence, "text": chunk.text}
            # Include serialized metadata and list punctuation in the budget.
            proposed = json.dumps(result + [candidate], ensure_ascii=False, separators=(",", ":"))
            if len(proposed.encode("utf-8")) <= self.config.token_budget:
                result.append(candidate)
        return result
