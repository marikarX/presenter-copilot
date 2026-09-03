"""Shared records and filter types for lexical and semantic retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalFilters:
    project_id: str
    document_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    usage: str = "all"
    allow_private: bool = True
    slide_start: int | None = None
    slide_end: int | None = None


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    chunk_text: str
    lexical_text: str
    chunk_index: int
    source_unit_id: str | None
    unit_type: str
    ordinal: int | None
    document_id: str
    original_name: str
    source_type: str
    entity_type: str = "chunk"
    entity_id: str | None = None
    source_class: str = "document"
    source_id: str | None = None
    knowledge_item_id: str | None = None
    knowledge_kind: str | None = None
    user_statement_id: str | None = None
    private: bool = False
    preferred: bool = False
    use_live: bool = True
    use_rehearsal: bool = True
    document_kind: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    speaker_label: str | None = None
