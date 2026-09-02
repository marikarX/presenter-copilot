"""Shared records and filter types for lexical and semantic retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalFilters:
    project_id: str
    document_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    chunk_text: str
    lexical_text: str
    chunk_index: int
    source_unit_id: str
    unit_type: str
    ordinal: int | None
    document_id: str
    original_name: str
    source_type: str
