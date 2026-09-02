"""Deterministic lexical scoring shared by M1 fallback and the M2 hybrid path."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from time import monotonic
from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.ingestion.models import Evidence
from presenter_core.ingestion.parsers.utils import lexical_normalize
from presenter_core.ingestion.service import provenance_label
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .models import ChunkRecord, RetrievalFilters

MAX_QUERY_LENGTH = 500
MAX_RESULTS = 50
LEXICAL_CANDIDATE_LIMIT = 100
LEXICAL_SCAN_BATCH_SIZE = 256

SOURCE_TYPE_MIME = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "markdown": "text/markdown",
}


@dataclass(frozen=True)
class LexicalCandidate:
    """A chunk plus explainable M1 lexical signals."""

    record: ChunkRecord
    raw_score: float
    exact_phrase: bool
    exact_number: bool


def validate_query(value: Any) -> tuple[str, list[str], set[str], str]:
    """Validate and normalize a bounded query for both retrieval modes."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_QUERY_LENGTH:
        raise invalid_request(
            f"query must be between 1 and {MAX_QUERY_LENGTH} characters.",
            field="query",
        )
    normalized_query = lexical_normalize(value)
    query_tokens = normalized_query.split()
    if not query_tokens:
        raise invalid_request("query must contain searchable text.", field="query")
    return value, query_tokens, set(query_tokens), " ".join(query_tokens)


def select_chunk_records(
    connection: sqlite3.Connection,
    filters: RetrievalFilters,
) -> list[ChunkRecord]:
    """Read only current, parsed chunk metadata from the project database."""
    sql, parameters = _chunk_select_sql(filters)
    return [_record_from_row(row) for row in connection.execute(sql, parameters).fetchall()]


def select_retrieval_records(
    connection: sqlite3.Connection,
    filters: RetrievalFilters,
) -> list[ChunkRecord]:
    """Read document chunks and confirmed project knowledge through one contract."""
    records = select_chunk_records(connection, filters)
    if not filters.document_ids and not filters.source_types:
        sql, parameters = _knowledge_select_sql(filters)
        records.extend(
            _record_from_row(row) for row in connection.execute(sql, parameters).fetchall()
        )
    return records


def _chunk_select_sql(
    filters: RetrievalFilters,
    *,
    lexical_tokens: set[str] | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["documents.project_id = ?", "documents.parse_status = 'ready'"]
    parameters: list[Any] = [filters.project_id]
    if filters.document_ids:
        placeholders = ", ".join("?" for _ in filters.document_ids)
        clauses.append(f"documents.id IN ({placeholders})")
        parameters.extend(filters.document_ids)
    if filters.source_types:
        mime_types = [SOURCE_TYPE_MIME[source_type] for source_type in filters.source_types]
        placeholders = ", ".join("?" for _ in mime_types)
        clauses.append(f"documents.mime_type IN ({placeholders})")
        parameters.extend(mime_types)
    if lexical_tokens:
        token_clauses = " OR ".join(
            "instr(' ' || chunks.lexical_text || ' ', ' ' || ? || ' ') > 0" for _ in lexical_tokens
        )
        clauses.append(f"({token_clauses})")
        parameters.extend(sorted(lexical_tokens))
    sql = (
        """
        SELECT
            chunks.id AS chunk_id,
            chunks.text AS chunk_text,
            chunks.lexical_text AS lexical_text,
            chunks.chunk_index AS chunk_index,
            source_units.id AS source_unit_id,
            source_units.unit_type AS unit_type,
            source_units.ordinal AS ordinal,
            documents.id AS document_id,
            documents.original_name AS original_name,
            documents.mime_type AS mime_type
        FROM chunks
        JOIN source_units ON source_units.id = chunks.source_unit_id
        JOIN documents ON documents.id = source_units.document_id
        WHERE """
        + " AND ".join(clauses)
        + " ORDER BY documents.original_name COLLATE NOCASE, source_units.unit_type, "
        + "source_units.ordinal IS NULL, source_units.ordinal, chunks.chunk_index, chunks.id"
    )
    return sql, parameters


def _knowledge_select_sql(filters: RetrievalFilters) -> tuple[str, list[Any]]:
    clauses = ["k.project_id = ?"]
    parameters: list[Any] = [filters.project_id]
    if not filters.allow_private:
        clauses.append("k.private = 0")
    if filters.usage == "live":
        clauses.append("k.use_live = 1")
    elif filters.usage == "rehearsal":
        clauses.append("k.use_rehearsal = 1")
    sql = (
        """
        SELECT
            k.id AS chunk_id,
            k.text AS chunk_text,
            k.text AS lexical_text,
            0 AS chunk_index,
            NULL AS source_unit_id,
            'knowledge_item' AS unit_type,
            NULL AS ordinal,
            k.project_id AS document_id,
            'Your Teach explanation' AS original_name,
            'user_knowledge' AS mime_type,
            'knowledge_item' AS entity_type,
            'user_knowledge' AS source_class,
            k.id AS knowledge_item_id,
            k.private AS private,
            k.preferred AS preferred,
            k.use_live AS use_live,
            k.use_rehearsal AS use_rehearsal,
            (
                SELECT ke.provenance_id
                FROM knowledge_evidence AS ke
                WHERE ke.knowledge_item_id = k.id
                  AND ke.provenance_type = 'user_statement'
                ORDER BY ke.provenance_id
                LIMIT 1
            ) AS user_statement_id
        FROM knowledge_items AS k
        WHERE """
        + " AND ".join(clauses)
        + " AND EXISTS ("
        + " SELECT 1 FROM knowledge_evidence AS ke"
        + " WHERE ke.knowledge_item_id = k.id"
        + " AND ke.provenance_type = 'user_statement'"
        + " ) ORDER BY k.updated_at DESC, k.id"
    )
    return sql, parameters


def _record_from_row(row: sqlite3.Row | Any) -> ChunkRecord:
    keys = set(row.keys()) if isinstance(row, sqlite3.Row) else set()
    entity_type = str(row["entity_type"]) if "entity_type" in keys else "chunk"
    source_class = str(row["source_class"]) if "source_class" in keys else "document"
    source_id = (
        str(row["user_statement_id"])
        if "user_statement_id" in keys and row["user_statement_id"] is not None
        else str(row["document_id"])
    )
    raw_lexical_text = str(row["lexical_text"])
    normalized_lexical_text = (
        lexical_normalize(raw_lexical_text) if entity_type == "knowledge_item" else raw_lexical_text
    )
    return ChunkRecord(
        chunk_id=str(row["chunk_id"]),
        chunk_text=str(row["chunk_text"]),
        lexical_text=normalized_lexical_text,
        chunk_index=int(row["chunk_index"]),
        source_unit_id=(str(row["source_unit_id"]) if row["source_unit_id"] is not None else None),
        unit_type=str(row["unit_type"]),
        ordinal=int(row["ordinal"]) if row["ordinal"] is not None else None,
        document_id=str(row["document_id"]),
        original_name=str(row["original_name"]),
        source_type=_source_type_from_mime(str(row["mime_type"])),
        entity_type=entity_type,
        entity_id=str(row["chunk_id"]),
        source_class=source_class,
        source_id=source_id,
        knowledge_item_id=(
            str(row["knowledge_item_id"])
            if "knowledge_item_id" in keys and row["knowledge_item_id"] is not None
            else None
        ),
        user_statement_id=(
            str(row["user_statement_id"])
            if "user_statement_id" in keys and row["user_statement_id"] is not None
            else None
        ),
        private=bool(row["private"]) if "private" in keys else False,
        preferred=bool(row["preferred"]) if "preferred" in keys else False,
        use_live=bool(row["use_live"]) if "use_live" in keys else True,
        use_rehearsal=bool(row["use_rehearsal"]) if "use_rehearsal" in keys else True,
    )


def _source_type_from_mime(mime_type: str) -> str:
    if mime_type == "user_knowledge":
        return "user_statement"
    for source_type, known_mime in SOURCE_TYPE_MIME.items():
        if mime_type == known_mime:
            return source_type
    return "unknown"


def score_records(
    records: list[ChunkRecord],
    query_tokens: list[str],
    query_set: set[str],
    phrase: str,
    *,
    limit: int,
) -> list[LexicalCandidate]:
    """Score every bounded metadata row with the original M1 exact behavior."""
    scored: list[tuple[float, tuple[Any, ...], LexicalCandidate]] = []
    for record in records:
        body_tokens = set(record.lexical_text.split())
        overlap = query_set.intersection(body_tokens)
        if not overlap:
            continue
        exact_phrase = phrase in record.lexical_text
        numeric_matches = sum(
            1
            for token in query_tokens
            if any(character.isdigit() for character in token) and token in body_tokens
        )
        score = len(overlap) / len(query_set)
        if exact_phrase:
            score += 2.0
        score += numeric_matches * 0.25
        candidate = LexicalCandidate(
            record=record,
            raw_score=score,
            exact_phrase=exact_phrase,
            exact_number=numeric_matches > 0,
        )
        tie_breaker = (
            record.original_name.casefold(),
            record.unit_type,
            record.ordinal if record.ordinal is not None else 2**31,
            record.chunk_index,
            record.chunk_id,
        )
        scored.append((score, tie_breaker, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _, _, candidate in scored[:limit]]


def bounded_lexical_candidates(
    connection: sqlite3.Connection,
    filters: RetrievalFilters,
    query_tokens: list[str],
    query_set: set[str],
    phrase: str,
    *,
    limit: int = LEXICAL_CANDIDATE_LIMIT,
) -> list[LexicalCandidate]:
    """Scan current document and user-knowledge metadata for lexical matches."""
    document_sql, document_parameters = _chunk_select_sql(filters, lexical_tokens=query_set)
    cursor = connection.execute(document_sql, document_parameters)
    records: list[ChunkRecord] = []
    while True:
        rows = cursor.fetchmany(LEXICAL_SCAN_BATCH_SIZE)
        if not rows:
            break
        records.extend(_record_from_row(row) for row in rows)
    if not filters.document_ids and not filters.source_types:
        knowledge_sql, knowledge_parameters = _knowledge_select_sql(filters)
        knowledge_rows = connection.execute(knowledge_sql, knowledge_parameters).fetchall()
        records.extend(_record_from_row(row) for row in knowledge_rows)
    return _sort_lexical_candidates(
        score_records(records, query_tokens, query_set, phrase, limit=limit)
    )[:limit]


class LexicalRetrievalService:
    """Search persisted chunks without embeddings, providers, or network access."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "query", "limit", "usage"})
        project_id = params.get("project_id")
        if not isinstance(project_id, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        project_id = normalize_project_id(project_id)
        query, query_tokens, query_set, phrase = validate_query(params.get("query"))
        limit = params.get("limit", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
            raise invalid_request(f"limit must be between 1 and {MAX_RESULTS}.", field="limit")
        usage = params.get("usage", "all")
        if usage not in {"all", "live", "rehearsal"}:
            raise invalid_request("usage must be all, live, or rehearsal.", field="usage")

        started = monotonic()
        with self._storage.project_database(project_id) as connection:
            candidates = bounded_lexical_candidates(
                connection,
                RetrievalFilters(project_id=project_id, usage=usage),
                query_tokens,
                query_set,
                phrase,
                limit=limit,
            )
        results = [
            _candidate_evidence(candidate, rank=rank).to_dict()
            for rank, candidate in enumerate(candidates, start=1)
        ]
        return {
            "project_id": project_id,
            "query": query,
            "results": results,
            "latency_ms": max(0, int((monotonic() - started) * 1000)),
        }


def _candidate_evidence(candidate: LexicalCandidate, *, rank: int) -> Evidence:
    record = candidate.record
    return Evidence(
        evidence_id=record.chunk_id,
        source_type="user_statement" if record.entity_type == "knowledge_item" else "document",
        source_id=record.source_id or record.document_id,
        source_unit_id=record.source_unit_id,
        label=(
            "Your Teach explanation"
            if record.entity_type == "knowledge_item"
            else provenance_label(record.original_name, record.unit_type, record.ordinal)
        ),
        text=record.chunk_text,
        rank=rank,
        score=candidate.raw_score,
        fact_safe=True,
    )


def _sort_lexical_candidates(candidates: list[LexicalCandidate]) -> list[LexicalCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.raw_score,
            candidate.record.original_name.casefold(),
            candidate.record.unit_type,
            candidate.record.ordinal if candidate.record.ordinal is not None else 2**31,
            candidate.record.chunk_index,
            candidate.record.chunk_id,
        ),
    )
