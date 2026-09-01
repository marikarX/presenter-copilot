"""Deterministic project-scoped exact/lexical retrieval fallback for M1."""

from __future__ import annotations

import re
from time import monotonic
from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.ingestion.models import Evidence
from presenter_core.ingestion.parsers.utils import lexical_normalize
from presenter_core.ingestion.service import provenance_label
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

MAX_QUERY_LENGTH = 500
MAX_RESULTS = 50


class LexicalRetrievalService:
    """Search persisted chunks without embeddings, providers, or network access."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "query", "limit"})
        project_id = params.get("project_id")
        if not isinstance(project_id, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        project_id = normalize_project_id(project_id)
        query = params.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
            raise invalid_request(
                f"query must be between 1 and {MAX_QUERY_LENGTH} characters.",
                field="query",
            )
        limit = params.get("limit", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
            raise invalid_request(f"limit must be between 1 and {MAX_RESULTS}.", field="limit")

        normalized_query = lexical_normalize(query)
        query_tokens = normalized_query.split()
        if not query_tokens:
            raise invalid_request("query must contain searchable text.", field="query")
        query_set = set(query_tokens)
        phrase = " ".join(query_tokens)
        started = monotonic()
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
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
                    documents.original_name AS original_name
                FROM chunks
                JOIN source_units ON source_units.id = chunks.source_unit_id
                JOIN documents ON documents.id = source_units.document_id
                WHERE documents.project_id = ?
                """,
                (project_id,),
            ).fetchall()

        scored: list[tuple[float, tuple[Any, ...], Evidence]] = []
        for row in rows:
            body = row["lexical_text"]
            body_tokens = set(re.findall(r"[^\s]+", body))
            overlap = query_set.intersection(body_tokens)
            if not overlap:
                continue
            score = len(overlap) / len(query_set)
            if phrase in body:
                score += 2.0
            numeric_matches = sum(
                1
                for token in query_set
                if any(character.isdigit() for character in token) and token in body_tokens
            )
            score += numeric_matches * 0.25
            evidence = Evidence(
                evidence_id=row["chunk_id"],
                source_type="document",
                source_id=row["document_id"],
                source_unit_id=row["source_unit_id"],
                label=provenance_label(row["original_name"], row["unit_type"], row["ordinal"]),
                text=row["chunk_text"],
                score=score,
                fact_safe=True,
            )
            tie_breaker = (
                str(row["original_name"]).casefold(),
                str(row["unit_type"]),
                row["ordinal"] if row["ordinal"] is not None else 2**31,
                row["chunk_index"],
                str(row["chunk_id"]),
            )
            scored.append((score, tie_breaker, evidence))

        scored.sort(key=lambda item: (-item[0], item[1]))
        results: list[dict[str, Any]] = []
        for rank, (_, _, evidence) in enumerate(scored[:limit], start=1):
            results.append(
                Evidence(
                    evidence_id=evidence.evidence_id,
                    source_type=evidence.source_type,
                    source_id=evidence.source_id,
                    source_unit_id=evidence.source_unit_id,
                    label=evidence.label,
                    text=evidence.text,
                    rank=rank,
                    score=evidence.score,
                    fact_safe=evidence.fact_safe,
                ).to_dict()
            )
        return {
            "project_id": project_id,
            "query": query,
            "results": results,
            "latency_ms": max(0, int((monotonic() - started) * 1000)),
        }
