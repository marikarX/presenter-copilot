"""Typed intermediate and provenance models shared by ingestion/retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedSourceUnit:
    """Parser output before it is assigned persistent UUIDs.

    ``text`` is the bounded display text.  Parsers may provide a separate
    index text when useful source material (for example PPTX speaker notes)
    should remain searchable without being duplicated in the preview body.
    """

    unit_type: str
    ordinal: int | None
    title: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    search_text: str | None = None

    @property
    def index_text(self) -> str:
        """Return the text that should be chunked for retrieval."""
        return self.search_text if self.search_text is not None else self.text


@dataclass(frozen=True)
class ChunkDraft:
    """A deterministic chunk that still belongs to one parsed unit."""

    chunk_index: int
    text: str
    lexical_text: str
    token_count: None = None


@dataclass(frozen=True)
class ProvenanceRef:
    """Canonical source location shared by evidence and later retrieval paths."""

    source_type: str
    source_id: str
    source_unit_id: str | None
    label: str
    exact_span: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Evidence:
    """Canonical source-backed evidence returned by core APIs."""

    evidence_id: str
    source_type: str
    source_id: str
    source_unit_id: str | None
    label: str
    text: str
    rank: int = 0
    score: float | None = None
    fact_safe: bool = True

    def provenance_ref(self) -> ProvenanceRef:
        """Return the location portion without changing the flat wire shape."""
        return ProvenanceRef(
            source_type=self.source_type,
            source_id=self.source_id,
            source_unit_id=self.source_unit_id,
            label=self.label,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_unit_id": self.source_unit_id,
            "label": self.label,
            "text": self.text,
            "rank": self.rank,
            "fact_safe": self.fact_safe,
        }
        if self.score is not None:
            result["score"] = round(self.score, 6)
        return result
