"""Hybrid semantic/lexical retrieval and generation-based index persistence."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, cast

import numpy as np

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.models import Evidence
from presenter_core.ingestion.service import provenance_label
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .conflicts import detect_conflicts
from .embeddings import EMBEDDING_BATCH_SIZE, EmbeddingAdapter, EmbeddingHealth, normalize_vector
from .index import NumpyEmbeddingIndex
from .lexical import (
    LEXICAL_CANDIDATE_LIMIT,
    MAX_RESULTS,
    SOURCE_TYPE_MIME,
    LexicalCandidate,
    _record_from_row,
    bounded_lexical_candidates,
    validate_query,
)
from .models import ChunkRecord, RetrievalFilters

EventSink = Callable[[str, dict[str, Any]], None]

MAX_DOCUMENT_IDS = 100
MAX_SLIDE = 10_000
MAX_SLIDE_WINDOW = 100
SEMANTIC_CANDIDATE_LIMIT = 100
CURRENT_SLIDE_CANDIDATE_LIMIT = 100
CONFLICT_CANDIDATE_LIMIT = 20
REBUILD_FETCH_SIZE = 256

# These constants are intentionally centralized and are returned in the
# ranking trace rather than hidden in UI code.
SEMANTIC_WEIGHT = 0.55
LEXICAL_WEIGHT = 0.35
LEXICAL_SCORE_CEILING = 3.25
EXACT_PHRASE_BOOST = 0.35
EXACT_NUMBER_BOOST = 0.55
# A presentation copy wins a currency duplicate only after both candidates have
# an exact lexical number match; this keeps a supporting semantic near-match
# from displacing the source the presenter is most likely asking about.
PRESENTATION_CURRENCY_TIE_BOOST = 0.05
CURRENT_SLIDE_BOOST = 0.15
ADJACENT_SLIDE_BOOST = 0.07
WINDOW_SLIDE_BOOST = 0.03
USER_KNOWLEDGE_BOOST = 0.08
PREFERRED_KNOWLEDGE_BOOST = 0.22


@dataclass
class _RankCandidate:
    record: ChunkRecord
    lexical: LexicalCandidate | None = None
    semantic_score: float | None = None
    final_score: float = 0.0
    semantic_component: float = 0.0
    lexical_component: float = 0.0
    slide_boost: float = 0.0
    user_knowledge_boost: float = 0.0


class HybridRetrievalService:
    """Compose the M1 lexical path with a project-local NumPy index."""

    def __init__(
        self,
        storage: StorageManager,
        embedding_adapter: EmbeddingAdapter,
        event_sink: EventSink | None = None,
    ) -> None:
        self._storage = storage
        self._embedding_adapter = embedding_adapter
        self._event_sink = event_sink
        self._matrix_cache: dict[str, tuple[str, tuple[int, int, int], np.ndarray[Any, Any]]] = {}
        self._mapping_count_cache: dict[tuple[str, str, int], int] = {}

    def health(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return index/model state without exposing local paths or source text."""
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        adapter_health = self._embedding_adapter.health()
        with self._storage.project_database(project_id) as connection:
            active = self._active_generation(connection)
            current_chunk_count = self._current_chunk_count(connection, project_id)
            current_knowledge_item_count = self._current_knowledge_item_count(
                connection, project_id
            )
            current_indexable_entity_count = current_chunk_count + current_knowledge_item_count
            indexed_count = (
                self._cached_current_mapping_count(
                    connection,
                    project_id,
                    str(active["id"]),
                    current_indexable_entity_count,
                )
                if active is not None
                else 0
            )
            matrix_error: CoreDomainError | None = None
            mismatch_reasons: list[str] = []
            if active is not None and adapter_health.status == "ready":
                mismatch_reasons = self._identity_mismatch_reasons(active, adapter_health)
                if not mismatch_reasons:
                    try:
                        matrix = self._load_generation(project_id, active)
                        self._validate_mapping_bounds(
                            connection, str(active["id"]), matrix.shape[0]
                        )
                    except CoreDomainError as error:
                        matrix_error = error

            coverage = (
                indexed_count / current_indexable_entity_count
                if current_indexable_entity_count
                else (1.0 if active is not None else 0.0)
            )
            if adapter_health.status != "ready":
                status = "model_unavailable"
                stale_reason = adapter_health.error_code
            elif active is None:
                status = "not_built"
                stale_reason = None
            elif mismatch_reasons:
                status = "stale"
                stale_reason = "; ".join(mismatch_reasons)
            elif matrix_error is not None:
                status = "corrupt"
                stale_reason = matrix_error.code
            elif coverage < 1.0:
                status = "partial"
                stale_reason = "active generation does not cover every current project entity"
            else:
                status = "ready"
                stale_reason = None

            result = self._health_result(
                project_id,
                status=status,
                adapter_health=adapter_health,
                active=active,
                current_chunk_count=current_chunk_count,
                current_knowledge_item_count=current_knowledge_item_count,
                current_indexable_entity_count=current_indexable_entity_count,
                indexed_count=indexed_count,
                coverage=coverage,
                stale_reason=stale_reason,
            )
        self._cleanup_orphan_files(project_id)
        return result

    def rebuild(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build and atomically activate one compact project-local generation."""
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        generation_id = str(uuid.uuid4())
        staging_relative = f"embeddings/.staging-{generation_id}.npy"
        final_relative = f"embeddings/vectors-{generation_id}.npy"
        staging_path: Path | None = None
        final_path: Path | None = None
        activated = False
        try:
            self._emit_progress(
                project_id,
                "model_load",
                0,
                1,
                "started",
                model_id=self._embedding_adapter.model_id,
                generation_id=generation_id,
            )
            adapter_health = self._embedding_adapter.health()
            if adapter_health.status != "ready" or adapter_health.dimension is None:
                code = adapter_health.error_code or "EMBEDDING_MODEL_UNAVAILABLE"
                raise CoreDomainError(
                    code,
                    "The local embedding model is not available for indexing.",
                    details={},
                )
            dimension = adapter_health.dimension
            model_fingerprint = adapter_health.model_fingerprint
            if not model_fingerprint:
                raise CoreDomainError(
                    "EMBEDDING_MODEL_INVALID",
                    "The local embedding model has no artifact fingerprint.",
                )
            self._emit_progress(
                project_id,
                "model_load",
                1,
                1,
                "complete",
                model_id=adapter_health.model_id,
                generation_id=generation_id,
            )

            self._storage.paths.safe_embeddings_directory(project_id, create=True)
            staging_path = self._storage.paths.embedding_matrix_path(
                project_id, staging_relative, require_exists=False
            )
            final_path = self._storage.paths.embedding_matrix_path(
                project_id, final_relative, require_exists=False
            )
            with self._storage.project_database(project_id) as connection:
                current_indexable_entity_count = self._current_indexable_entity_count(
                    connection, project_id
                )
                active = self._active_generation(connection)
                old_matrix: np.ndarray[Any, Any] | None = None
                reusable: dict[str, tuple[str, int]] = {}
                if active is not None and not self._identity_mismatch_reasons(
                    active, adapter_health
                ):
                    try:
                        old_matrix = self._load_generation(project_id, active)
                        self._validate_mapping_bounds(
                            connection, str(active["id"]), old_matrix.shape[0]
                        )
                        old_rows = connection.execute(
                            """
                            SELECT ev.entity_type, ev.entity_id, ev.content_sha256, ev.row_index
                            FROM embedding_vectors AS ev
                            WHERE ev.generation_id = ? AND ev.project_id = ?
                            """,
                            (str(active["id"]), project_id),
                        ).fetchall()
                        reusable = {
                            f"{row['entity_type']}:{row['entity_id']}": (
                                str(row["content_sha256"]),
                                int(row["row_index"]),
                            )
                            for row in old_rows
                        }
                    except CoreDomainError:
                        old_matrix = None
                        reusable = {}

                self._emit_progress(
                    project_id,
                    "scan",
                    0,
                    current_indexable_entity_count,
                    "started",
                    model_id=adapter_health.model_id,
                    generation_id=generation_id,
                )
                staging_matrix = NumpyEmbeddingIndex.create_staging_matrix(
                    staging_path,
                    rows=current_indexable_entity_count,
                    dimension=dimension,
                )
                vector_rows: list[tuple[Any, ...]] = []
                reused_count = 0
                embedded_count = 0
                cursor = connection.execute(
                    """
                    SELECT c.id AS entity_id, 'chunk' AS entity_type, c.text AS entity_text,
                           'document' AS source_class
                    FROM chunks AS c
                    JOIN source_units AS su ON su.id = c.source_unit_id
                    JOIN documents AS d ON d.id = su.document_id
                    WHERE d.project_id = ? AND d.parse_status = 'ready'
                    UNION ALL
                    SELECT k.id AS entity_id, 'knowledge_item' AS entity_type,
                           k.text AS entity_text, 'user_knowledge' AS source_class
                    FROM knowledge_items AS k
                    WHERE k.project_id = ?
                      AND EXISTS (
                          SELECT 1 FROM knowledge_evidence AS ke
                          WHERE ke.knowledge_item_id = k.id
                            AND ke.provenance_type = 'user_statement'
                      )
                    ORDER BY entity_type, entity_id
                    """,
                    (project_id, project_id),
                )
                row_index = 0
                while True:
                    rows = cursor.fetchmany(REBUILD_FETCH_SIZE)
                    if not rows:
                        break
                    missing: list[tuple[int, str, str, str]] = []
                    for row in rows:
                        entity_id = str(row["entity_id"])
                        entity_type = str(row["entity_type"])
                        entity_text = str(row["entity_text"])
                        source_class = str(row["source_class"])
                        content_sha256 = _content_sha256(entity_text)
                        old = reusable.get(f"{entity_type}:{entity_id}")
                        if (
                            old is not None
                            and old[0] == content_sha256
                            and old_matrix is not None
                            and 0 <= old[1] < old_matrix.shape[0]
                        ):
                            staging_matrix[row_index] = old_matrix[old[1]]
                            reused_count += 1
                        else:
                            missing.append((row_index, entity_id, entity_text, content_sha256))
                        vector_rows.append(
                            (
                                generation_id,
                                entity_id,
                                entity_type,
                                entity_id,
                                project_id,
                                source_class,
                                row_index,
                                content_sha256,
                            )
                        )
                        row_index += 1

                    if missing:
                        encoded = list(
                            self._embedding_adapter.embed_documents(
                                (item[2] for item in missing),
                                batch_size=EMBEDDING_BATCH_SIZE,
                            )
                        )
                        if len(encoded) != len(missing):
                            raise CoreDomainError(
                                "EMBEDDING_MODEL_INVALID",
                                "The embedding adapter returned an incomplete batch.",
                            )
                        for (target, _, _, _), vector in zip(missing, encoded, strict=True):
                            staging_matrix[target] = normalize_vector(
                                vector,
                                dimension=dimension,
                            )
                            embedded_count += 1
                    self._emit_progress(
                        project_id,
                        "reuse" if not missing else "embed",
                        row_index,
                        current_indexable_entity_count,
                        "complete" if row_index == current_indexable_entity_count else "running",
                        model_id=adapter_health.model_id,
                        generation_id=generation_id,
                    )

                NumpyEmbeddingIndex.flush_and_fsync(staging_matrix, staging_path)
                del staging_matrix
                os.replace(staging_path, final_path)
                staging_path = None

                self._emit_progress(
                    project_id,
                    "persist",
                    0,
                    len(vector_rows),
                    "started",
                    model_id=adapter_health.model_id,
                    generation_id=generation_id,
                )
                self._activate_generation(
                    connection,
                    generation_id=generation_id,
                    adapter_health=adapter_health,
                    model_fingerprint=model_fingerprint,
                    dimension=dimension,
                    final_relative=final_relative,
                    matrix_row_count=current_indexable_entity_count,
                    vector_rows=vector_rows,
                )
                activated = True
                old_matrix = None

            # The old generation can be unlinked only after the activation
            # transaction commits. Release any read-only mmap before cleanup;
            # this is required for reliable replacement/deletion on Windows.
            self._evict_matrix_cache(project_id)
            self._cleanup_orphan_files(project_id)
            coverage = 1.0
            self._emit_progress(
                project_id,
                "activate",
                1,
                1,
                "complete",
                model_id=adapter_health.model_id,
                generation_id=generation_id,
            )
            self._emit(
                "project.index_ready",
                {
                    "project_id": project_id,
                    "index_kind": "hybrid",
                    "generation_id": generation_id,
                    "model_id": adapter_health.model_id,
                    "dimension": dimension,
                    "matrix_row_count": current_indexable_entity_count,
                    "indexed_count": current_indexable_entity_count,
                    "coverage": coverage,
                    "status": "ready",
                },
            )
            self._emit_progress(
                project_id,
                "complete",
                1,
                1,
                "complete",
                model_id=adapter_health.model_id,
                generation_id=generation_id,
            )
            return {
                "project_id": project_id,
                "status": "ready",
                "generation_id": generation_id,
                "model_id": adapter_health.model_id,
                "model_fingerprint": model_fingerprint,
                "dimension": dimension,
                "matrix_row_count": current_indexable_entity_count,
                "indexed_count": current_indexable_entity_count,
                "coverage": coverage,
                "reused_count": reused_count,
                "embedded_count": embedded_count,
            }
        except CoreDomainError as error:
            self._emit_progress(
                project_id,
                "complete",
                0,
                1,
                "error",
                model_id=self._embedding_adapter.model_id,
                generation_id=generation_id,
                error_code=error.code,
            )
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            rebuild_error = CoreDomainError(
                "RETRIEVAL_REBUILD_FAILED",
                "The semantic index could not be rebuilt; the previous generation remains active.",
                retryable=True,
                details={},
            )
            self._emit_progress(
                project_id,
                "complete",
                0,
                1,
                "error",
                model_id=self._embedding_adapter.model_id,
                generation_id=generation_id,
                error_code=rebuild_error.code,
            )
            raise rebuild_error from exc
        finally:
            if not activated:
                _remove_file_quietly(final_path)
            _remove_file_quietly(staging_path)

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run bounded hybrid retrieval with lexical fallback on semantic failure."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "query",
                "limit",
                "document_ids",
                "source_types",
                "current_slide",
                "slide_window",
                "usage",
                "allow_private",
            },
        )
        project_id = self._project_id(params)
        query, query_tokens, query_set, phrase = validate_query(params.get("query"))
        limit = _bounded_integer(params, "limit", default=10, minimum=1, maximum=MAX_RESULTS)
        filters, current_slide, slide_window = _parse_filters(params, project_id)
        started = monotonic()

        with self._storage.project_database(project_id) as connection:
            lexical_candidates = self._lexical_candidates(
                connection,
                filters,
                query_tokens,
                query_set,
                phrase,
            )
            active = self._active_generation(connection)
            current_chunk_count = self._current_chunk_count(connection, project_id)
            current_knowledge_item_count = self._current_knowledge_item_count(
                connection, project_id
            )
            current_indexable_entity_count = current_chunk_count + current_knowledge_item_count
            indexed_count = (
                self._cached_current_mapping_count(
                    connection,
                    project_id,
                    str(active["id"]),
                    current_indexable_entity_count,
                )
                if active is not None
                else 0
            )
            semantic_status = "not_built"
            semantic_reason: str | None = None
            adapter_health: EmbeddingHealth | None = None
            semantic_scores: dict[str, float] = {}
            semantic_info: dict[str, Any] = {
                "status": semantic_status,
                "coverage": (
                    indexed_count / current_indexable_entity_count
                    if current_indexable_entity_count
                    else (1.0 if active is not None else 0.0)
                ),
                "adapter_id": getattr(self._embedding_adapter, "adapter_id", None),
                "model_id": (
                    active["model_id"] if active is not None else self._embedding_adapter.model_id
                ),
                "model_fingerprint": active["model_fingerprint"] if active is not None else None,
                "dimension": (
                    int(active["dimension"])
                    if active is not None
                    else self._embedding_adapter.dimension
                ),
                "model_loaded": False,
                "generation_id": active["id"] if active is not None else None,
                "matrix_row_count": int(active["matrix_row_count"]) if active is not None else 0,
            }

            if active is not None:
                adapter_health = self._embedding_adapter.health()
                semantic_info.update(
                    {
                        "adapter_id": adapter_health.adapter_id,
                        "model_id": adapter_health.model_id,
                        "model_fingerprint": adapter_health.model_fingerprint,
                        "dimension": adapter_health.dimension,
                        "model_loaded": adapter_health.model_loaded,
                    }
                )
                if adapter_health.status != "ready":
                    semantic_status = "model_unavailable"
                    semantic_reason = adapter_health.error_code
                else:
                    mismatch_reasons = self._identity_mismatch_reasons(active, adapter_health)
                    if mismatch_reasons:
                        semantic_status = "stale"
                        semantic_reason = "; ".join(mismatch_reasons)
                    else:
                        try:
                            matrix = self._load_generation(project_id, active)
                            self._validate_mapping_bounds(
                                connection, str(active["id"]), matrix.shape[0]
                            )
                            matrix_rows = int(matrix.shape[0])
                            unfiltered = (
                                not filters.document_ids
                                and not filters.source_types
                                and filters.usage == "all"
                                and filters.allow_private
                            )
                            if unfiltered and indexed_count == matrix_rows:
                                # Every active matrix row has a current,
                                # project-owned mapping, so NumPy can search
                                # the compact matrix without a 50k-row mask.
                                eligible_rows = None
                            else:
                                eligible_rows = self._eligible_row_indices(
                                    connection,
                                    filters,
                                    active,
                                    current_only=indexed_count < matrix_rows,
                                )
                            query_vector = self._embedding_adapter.embed_query(query)
                            for row_index, score in NumpyEmbeddingIndex.cosine_search(
                                matrix,
                                query_vector,
                                eligible_rows=eligible_rows,
                                limit=SEMANTIC_CANDIDATE_LIMIT,
                            ):
                                semantic_scores[str(row_index)] = score
                            semantic_status = (
                                "partial" if semantic_info["coverage"] < 1.0 else "ready"
                            )
                        except CoreDomainError as error:
                            semantic_status = (
                                "corrupt"
                                if error.code
                                in {"RETRIEVAL_INDEX_CORRUPT", "EMBEDDING_PATH_UNSAFE"}
                                else "model_unavailable"
                            )
                            semantic_reason = error.code

            semantic_info["status"] = semantic_status
            semantic_info["stale_reason"] = semantic_reason

            rank_candidates: dict[str, _RankCandidate] = {}
            for candidate in lexical_candidates:
                rank_candidates[candidate.record.chunk_id] = _RankCandidate(
                    record=candidate.record,
                    lexical=candidate,
                )

            if semantic_scores and active is not None:
                semantic_rows = self._rows_for_semantic_candidates(
                    connection,
                    str(active["id"]),
                    [int(row_index) for row_index in semantic_scores],
                    filters,
                )
                for row_index, record in semantic_rows:
                    rank_candidate = rank_candidates.setdefault(
                        record.chunk_id,
                        _RankCandidate(record=record),
                    )
                    rank_candidate.semantic_score = semantic_scores.get(str(row_index), 0.0)

            if current_slide is not None:
                for record in self._current_slide_candidates(
                    connection,
                    filters,
                    current_slide,
                    slide_window,
                ):
                    rank_candidates.setdefault(record.chunk_id, _RankCandidate(record=record))

            ranked = self._rank_candidates(
                rank_candidates.values(),
                query,
                current_slide=current_slide,
                slide_window=slide_window,
            )
            debug_items = [self._debug_item(candidate) for candidate in ranked]
            conflicts = detect_conflicts(
                query,
                debug_items[:CONFLICT_CANDIDATE_LIMIT],
            )
            hits: list[dict[str, Any]] = []
            for rank, item in enumerate(debug_items[:limit], start=1):
                evidence = item["evidence"]
                evidence["rank"] = rank
                hits.append(
                    {
                        "evidence": evidence,
                        "scores": item["scores"],
                        "reasons": item["reasons"],
                    }
                )

        mode = (
            "semantic_partial"
            if semantic_status == "partial"
            else "hybrid"
            if semantic_status == "ready"
            else "lexical_fallback"
        )
        return {
            "project_id": project_id,
            "query": query,
            "mode": mode,
            "latency_ms": round(max(0.0, (monotonic() - started) * 1000), 3),
            "semantic": semantic_info,
            "hits": hits,
            "conflicts": conflicts,
        }

    def close(self) -> None:
        """Drop mmap handles and release model state at core shutdown."""
        for project_id in tuple(self._matrix_cache):
            self._evict_matrix_cache(project_id)
        self._embedding_adapter.close()

    def evict_project(self, project_id: str) -> None:
        """Release one project's cached matrix before its vault is deleted."""
        normalized_project_id = normalize_project_id(project_id)
        self._evict_matrix_cache(normalized_project_id)
        self.invalidate_project_mappings(normalized_project_id)

    def invalidate_project_mappings(self, project_id: str) -> None:
        """Forget cached validity counts after a source or indexable-row mutation."""
        normalized_project_id = normalize_project_id(project_id)
        self._mapping_count_cache = {
            key: value
            for key, value in self._mapping_count_cache.items()
            if key[0] != normalized_project_id
        }

    def _activate_generation(
        self,
        connection: sqlite3.Connection,
        *,
        generation_id: str,
        adapter_health: EmbeddingHealth,
        model_fingerprint: str,
        dimension: int,
        final_relative: str,
        matrix_row_count: int,
        vector_rows: list[tuple[Any, ...]],
    ) -> None:
        """Commit one compact generation while preserving the old one on failure."""
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO embedding_generations (
                    id, adapter_id, model_id, model_fingerprint, dimension,
                    matrix_relative_path, matrix_row_count, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    generation_id,
                    adapter_health.adapter_id,
                    adapter_health.model_id,
                    model_fingerprint,
                    dimension,
                    final_relative,
                    matrix_row_count,
                    _utc_now(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO embedding_vectors (
                    generation_id, vector_id, entity_type, entity_id, project_id,
                    source_class, row_index, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                vector_rows,
            )
            connection.execute("UPDATE embedding_generations SET is_active = 0")
            connection.execute(
                "UPDATE embedding_generations SET is_active = 1 WHERE id = ?",
                (generation_id,),
            )
            connection.execute("UPDATE chunks SET embedding_key = NULL")
            connection.execute(
                """
                UPDATE chunks
                SET embedding_key = ? || ':' || id
                WHERE id IN (
                    SELECT entity_id FROM embedding_vectors
                    WHERE generation_id = ? AND entity_type = 'chunk'
                )
                """,
                (generation_id, generation_id),
            )
            # Inactive rows are disposable metadata. Delete them only after
            # the new generation is active; FK cascade removes their mappings.
            connection.execute("DELETE FROM embedding_generations WHERE is_active = 0")
            self._commit_generation_transaction(connection)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _commit_generation_transaction(connection: sqlite3.Connection) -> None:
        """Keep the commit seam deterministic for rollback regression coverage."""
        connection.commit()

    def _lexical_candidates(
        self,
        connection: sqlite3.Connection,
        filters: RetrievalFilters,
        query_tokens: list[str],
        query_set: set[str],
        phrase: str,
    ) -> list[LexicalCandidate]:
        return bounded_lexical_candidates(
            connection,
            filters,
            query_tokens,
            query_set,
            phrase,
            limit=LEXICAL_CANDIDATE_LIMIT,
        )

    def _rank_candidates(
        self,
        candidates: Iterable[_RankCandidate],
        query: str,
        *,
        current_slide: int | None,
        slide_window: int,
    ) -> list[_RankCandidate]:
        scored: list[tuple[float, tuple[Any, ...], _RankCandidate]] = []
        query_has_currency = any(symbol in query for symbol in "$€£")
        for candidate in candidates:
            lexical = candidate.lexical
            semantic_component = (
                max(0.0, min(1.0, float(candidate.semantic_score)))
                if candidate.semantic_score is not None
                else 0.0
            )
            lexical_raw = lexical.raw_score if lexical is not None else 0.0
            lexical_component = min(lexical_raw / LEXICAL_SCORE_CEILING, 1.0)
            slide_boost = _slide_boost(candidate.record, current_slide, slide_window)
            final = SEMANTIC_WEIGHT * semantic_component + LEXICAL_WEIGHT * lexical_component
            if lexical is not None and lexical.exact_phrase:
                final += EXACT_PHRASE_BOOST
            if lexical is not None and lexical.exact_number:
                final += EXACT_NUMBER_BOOST
                if query_has_currency and candidate.record.source_type == "pptx":
                    final += PRESENTATION_CURRENCY_TIE_BOOST
            user_knowledge_boost = 0.0
            if candidate.record.entity_type == "knowledge_item" and (
                lexical is not None or candidate.semantic_score is not None
            ):
                user_knowledge_boost += USER_KNOWLEDGE_BOOST
                if candidate.record.preferred:
                    user_knowledge_boost += PREFERRED_KNOWLEDGE_BOOST
            final += user_knowledge_boost
            final += slide_boost
            tie_breaker = (
                -int(lexical is not None and lexical.exact_number),
                -int(lexical is not None and lexical.exact_phrase),
                -int(query_has_currency and candidate.record.source_type == "pptx"),
                -int(
                    candidate.record.entity_type == "knowledge_item" and candidate.record.preferred
                ),
                -int(candidate.record.entity_type == "knowledge_item"),
                candidate.record.original_name.casefold(),
                candidate.record.unit_type,
                candidate.record.ordinal if candidate.record.ordinal is not None else 2**31,
                candidate.record.chunk_index,
                candidate.record.chunk_id,
            )
            candidate.final_score = final
            candidate.semantic_component = semantic_component
            candidate.lexical_component = lexical_component
            candidate.slide_boost = slide_boost
            candidate.user_knowledge_boost = user_knowledge_boost
            scored.append((final, tie_breaker, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [candidate for _, _, candidate in scored]

    def _debug_item(self, candidate: _RankCandidate) -> dict[str, Any]:
        record = candidate.record
        final = candidate.final_score
        lexical = candidate.lexical
        reasons: list[str] = []
        if lexical is not None and lexical.exact_number:
            reasons.append("exact_number")
        elif lexical is not None and lexical.exact_phrase:
            reasons.append("exact_phrase")
        elif lexical is not None:
            reasons.append("lexical")
        if candidate.semantic_score is not None:
            reasons.append("semantic")
        if record.entity_type == "knowledge_item":
            reasons.append("user_knowledge")
            if record.preferred and candidate.user_knowledge_boost > USER_KNOWLEDGE_BOOST:
                reasons.append("preferred_user_explanation")
        slide_boost = candidate.slide_boost
        if slide_boost == CURRENT_SLIDE_BOOST:
            reasons.append("current_slide")
        elif slide_boost > 0.0:
            reasons.append("adjacent_slide")
        evidence = Evidence(
            evidence_id=record.entity_id or record.chunk_id,
            source_type=record.source_type
            if record.entity_type == "knowledge_item"
            else "document",
            source_id=record.source_id or record.document_id,
            source_unit_id=record.source_unit_id,
            label=(
                "Your Teach explanation"
                if record.entity_type == "knowledge_item"
                else provenance_label(record.original_name, record.unit_type, record.ordinal)
            ),
            text=record.chunk_text,
            rank=0,
            score=final,
            fact_safe=True,
        ).to_dict()
        if record.entity_type == "knowledge_item":
            evidence["knowledge_item_id"] = record.knowledge_item_id or record.entity_id
            evidence["preferred"] = record.preferred
            evidence["private"] = record.private
            evidence["use_live"] = record.use_live
            evidence["use_rehearsal"] = record.use_rehearsal
        return {
            "evidence": evidence,
            "scores": {
                "semantic": round(candidate.semantic_component, 6),
                "lexical": round(candidate.lexical_component, 6),
                "lexical_raw": round(lexical.raw_score if lexical is not None else 0.0, 6),
                "slide_boost": round(slide_boost, 6),
                "user_knowledge_boost": round(candidate.user_knowledge_boost, 6),
                "final": round(final, 6),
            },
            "reasons": reasons,
        }

    def _load_generation(
        self, project_id: str, generation: sqlite3.Row | Any
    ) -> np.ndarray[Any, Any]:
        relative_path = str(generation["matrix_relative_path"])
        try:
            path = self._storage.paths.embedding_matrix_path(
                project_id,
                relative_path,
                require_exists=True,
            )
            stat = path.stat()
        except CoreDomainError:
            self._evict_matrix_cache(project_id)
            raise
        except OSError as exc:
            self._evict_matrix_cache(project_id)
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix is unavailable.",
            ) from exc
        signature = (int(stat.st_size), int(stat.st_mtime_ns), int(generation["dimension"]))
        cached = self._matrix_cache.get(project_id)
        if cached is not None and cached[0] == str(generation["id"]) and cached[1] == signature:
            return cached[2]
        try:
            matrix = NumpyEmbeddingIndex.load_matrix(
                path,
                expected_rows=int(generation["matrix_row_count"]),
                expected_dimension=int(generation["dimension"]),
            )
        except CoreDomainError:
            self._evict_matrix_cache(project_id)
            raise
        self._matrix_cache[project_id] = (str(generation["id"]), signature, matrix)
        return matrix

    def _evict_matrix_cache(self, project_id: str) -> None:
        """Drop one cached matrix and explicitly close any underlying mmap."""
        cached = self._matrix_cache.pop(project_id, None)
        if cached is None:
            return
        matrix = cached[2]
        if isinstance(matrix, np.memmap):
            mmap_handle = getattr(matrix, "_mmap", None)
            if mmap_handle is not None:
                try:
                    mmap_handle.close()
                except (BufferError, OSError, ValueError):
                    # The mapping may already have been closed by NumPy or a
                    # prior cleanup path. The cache entry is still retired.
                    pass

    @staticmethod
    def _active_generation(connection: sqlite3.Connection) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT * FROM embedding_generations WHERE is_active = 1"
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _current_chunk_count(connection: sqlite3.Connection, project_id: str) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunks AS c
            JOIN source_units AS su ON su.id = c.source_unit_id
            JOIN documents AS d ON d.id = su.document_id
            WHERE d.project_id = ? AND d.parse_status = 'ready'
            """,
            (project_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    @staticmethod
    def _current_mapping_count(
        connection: sqlite3.Connection,
        project_id: str,
        generation_id: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM embedding_vectors AS ev
            WHERE ev.generation_id = ? AND ev.project_id = ?
              AND (
                  ev.entity_type = 'chunk' AND EXISTS (
                      SELECT 1
                      FROM chunks AS c
                      JOIN source_units AS su ON su.id = c.source_unit_id
                      JOIN documents AS d ON d.id = su.document_id
                      WHERE c.id = ev.entity_id
                        AND d.project_id = ?
                        AND d.parse_status = 'ready'
                  )
                  OR ev.entity_type = 'knowledge_item' AND EXISTS (
                      SELECT 1
                      FROM knowledge_items AS k
                      WHERE k.id = ev.entity_id
                        AND k.project_id = ?
                        AND EXISTS (
                            SELECT 1
                            FROM knowledge_evidence AS ke
                            WHERE ke.knowledge_item_id = k.id
                              AND ke.provenance_type = 'user_statement'
                        )
                  )
              )
            """,
            (generation_id, project_id, project_id, project_id),
        ).fetchone()
        return int(row["count"]) if row else 0

    def _cached_current_mapping_count(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        generation_id: str,
        current_indexable_entity_count: int,
    ) -> int:
        """Reuse a validated mapping count until the current entity set changes."""
        cache_key = (project_id, generation_id, current_indexable_entity_count)
        cached = self._mapping_count_cache.get(cache_key)
        if cached is not None:
            return cached
        count = self._current_mapping_count(connection, project_id, generation_id)
        self._mapping_count_cache[cache_key] = count
        return count

    @staticmethod
    def _current_knowledge_item_count(connection: sqlite3.Connection, project_id: str) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM knowledge_items AS k
            WHERE k.project_id = ?
              AND EXISTS (
                  SELECT 1 FROM knowledge_evidence AS ke
                  WHERE ke.knowledge_item_id = k.id
                    AND ke.provenance_type = 'user_statement'
              )
            """,
            (project_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    @classmethod
    def _current_indexable_entity_count(
        cls, connection: sqlite3.Connection, project_id: str
    ) -> int:
        return cls._current_chunk_count(connection, project_id) + cls._current_knowledge_item_count(
            connection, project_id
        )

    @staticmethod
    def _validate_mapping_bounds(
        connection: sqlite3.Connection,
        generation_id: str,
        matrix_rows: int,
    ) -> None:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count, COUNT(DISTINCT row_index) AS distinct_count,
                   MIN(row_index) AS minimum, MAX(row_index) AS maximum
            FROM embedding_vectors
            WHERE generation_id = ?
            """,
            (generation_id,),
        ).fetchone()
        if row is None:
            return
        count = int(row["count"])
        minimum = row["minimum"]
        maximum = row["maximum"]
        if (
            int(row["distinct_count"]) != count
            or (minimum is not None and int(minimum) < 0)
            or (maximum is not None and int(maximum) >= matrix_rows)
        ):
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding metadata has an invalid row mapping.",
            )

    @staticmethod
    def _identity_mismatch_reasons(
        generation: sqlite3.Row | Any,
        adapter_health: EmbeddingHealth,
    ) -> list[str]:
        reasons: list[str] = []
        if generation["adapter_id"] != adapter_health.adapter_id:
            reasons.append("adapter_id mismatch")
        if generation["model_id"] != adapter_health.model_id:
            reasons.append("model_id mismatch")
        if generation["model_fingerprint"] != adapter_health.model_fingerprint:
            reasons.append("model_fingerprint mismatch")
        if generation["dimension"] != adapter_health.dimension:
            reasons.append("dimension mismatch")
        return reasons

    def _eligible_row_indices(
        self,
        connection: sqlite3.Connection,
        filters: RetrievalFilters,
        generation: sqlite3.Row | Any,
        *,
        current_only: bool,
    ) -> np.ndarray[Any, Any]:
        values: list[int] = []
        generation_id = str(generation["id"])
        if current_only or filters.document_ids or filters.source_types:
            chunk_clauses = [
                "ev.generation_id = ?",
                "ev.entity_type = 'chunk'",
                "ev.project_id = ?",
                "d.project_id = ?",
                "d.parse_status = 'ready'",
            ]
            chunk_parameters: list[Any] = [
                generation_id,
                filters.project_id,
                filters.project_id,
            ]
            _append_filter_clauses(chunk_clauses, chunk_parameters, filters, table_alias="d")
            chunk_rows = connection.execute(
                """
                SELECT ev.row_index
                FROM embedding_vectors AS ev
                JOIN chunks AS c ON c.id = ev.entity_id
                JOIN source_units AS su ON su.id = c.source_unit_id
                JOIN documents AS d ON d.id = su.document_id
                WHERE """
                + " AND ".join(chunk_clauses)
                + " ORDER BY ev.row_index",
                chunk_parameters,
            ).fetchall()
        else:
            # With no document/source filters, generation metadata already
            # identifies document rows; do not join through the document
            # hierarchy merely to prove that fact.
            chunk_rows = connection.execute(
                """
                SELECT ev.row_index
                FROM embedding_vectors AS ev
                WHERE ev.generation_id = ?
                  AND ev.entity_type = 'chunk'
                  AND ev.project_id = ?
                ORDER BY ev.row_index
                """,
                (generation_id, filters.project_id),
            ).fetchall()
        values.extend(int(row["row_index"]) for row in chunk_rows)

        if not filters.document_ids and not filters.source_types:
            knowledge_clauses = [
                "ev.generation_id = ?",
                "ev.entity_type = 'knowledge_item'",
                "ev.project_id = ?",
            ]
            knowledge_parameters: list[Any] = [
                generation_id,
                filters.project_id,
            ]
            needs_knowledge_join = (
                current_only or not filters.allow_private or filters.usage != "all"
            )
            if needs_knowledge_join:
                knowledge_clauses.extend(
                    [
                        "k.project_id = ?",
                        "EXISTS ("
                        "SELECT 1 FROM knowledge_evidence AS ke "
                        "WHERE ke.knowledge_item_id = k.id "
                        "AND ke.provenance_type = 'user_statement'"
                        ")",
                    ]
                )
                knowledge_parameters.append(filters.project_id)
                if not filters.allow_private:
                    knowledge_clauses.append("k.private = 0")
                if filters.usage == "live":
                    knowledge_clauses.append("k.use_live = 1")
                elif filters.usage == "rehearsal":
                    knowledge_clauses.append("k.use_rehearsal = 1")
                knowledge_sql = (
                    """
                    SELECT ev.row_index
                    FROM embedding_vectors AS ev
                    JOIN knowledge_items AS k ON k.id = ev.entity_id
                    WHERE """
                    + " AND ".join(knowledge_clauses)
                    + " ORDER BY ev.row_index"
                )
            else:
                knowledge_sql = (
                    """
                    SELECT ev.row_index
                    FROM embedding_vectors AS ev
                    WHERE """
                    + " AND ".join(knowledge_clauses)
                    + " ORDER BY ev.row_index"
                )
            knowledge_rows = connection.execute(knowledge_sql, knowledge_parameters).fetchall()
            values.extend(int(row["row_index"]) for row in knowledge_rows)
        values.sort()
        return np.asarray(values, dtype=np.int64)

    @staticmethod
    def _rows_for_semantic_candidates(
        connection: sqlite3.Connection,
        generation_id: str,
        row_indices: list[int],
        filters: RetrievalFilters,
    ) -> list[tuple[int, ChunkRecord]]:
        if not row_indices:
            return []
        placeholders = ", ".join("?" for _ in row_indices)
        clauses = [
            "ev.generation_id = ?",
            "ev.entity_type = 'chunk'",
            "ev.row_index IN (" + placeholders + ")",
            "ev.project_id = ?",
            "d.project_id = ?",
            "d.parse_status = 'ready'",
        ]
        parameters: list[Any] = [
            generation_id,
            *row_indices,
            filters.project_id,
            filters.project_id,
        ]
        _append_filter_clauses(clauses, parameters, filters, table_alias="d")
        rows = connection.execute(
            """
            SELECT ev.row_index AS vector_row,
                   c.id AS chunk_id, c.text AS chunk_text, c.lexical_text AS lexical_text,
                   c.chunk_index AS chunk_index, su.id AS source_unit_id,
                   su.unit_type AS unit_type, su.ordinal AS ordinal,
                   d.id AS document_id, d.original_name AS original_name,
                   d.mime_type AS mime_type
            FROM embedding_vectors AS ev
            JOIN chunks AS c ON c.id = ev.entity_id
            JOIN source_units AS su ON su.id = c.source_unit_id
            JOIN documents AS d ON d.id = su.document_id
             WHERE """
            + " AND ".join(clauses),
            parameters,
        ).fetchall()
        results = [(int(row["vector_row"]), _record_from_row(row)) for row in rows]
        if not filters.document_ids and not filters.source_types:
            knowledge_clauses = [
                "ev.generation_id = ?",
                "ev.entity_type = 'knowledge_item'",
                "ev.row_index IN (" + placeholders + ")",
                "ev.project_id = ?",
                "k.project_id = ?",
                "EXISTS ("
                "SELECT 1 FROM knowledge_evidence AS ke "
                "WHERE ke.knowledge_item_id = k.id "
                "AND ke.provenance_type = 'user_statement'"
                ")",
            ]
            knowledge_parameters: list[Any] = [
                generation_id,
                *row_indices,
                filters.project_id,
                filters.project_id,
            ]
            if not filters.allow_private:
                knowledge_clauses.append("k.private = 0")
            if filters.usage == "live":
                knowledge_clauses.append("k.use_live = 1")
            elif filters.usage == "rehearsal":
                knowledge_clauses.append("k.use_rehearsal = 1")
            knowledge_rows = connection.execute(
                """
                SELECT ev.row_index AS vector_row,
                       k.id AS chunk_id, k.text AS chunk_text, k.text AS lexical_text,
                       0 AS chunk_index, NULL AS source_unit_id,
                       'knowledge_item' AS unit_type, NULL AS ordinal,
                       k.project_id AS document_id, 'Your Teach explanation' AS original_name,
                       'user_knowledge' AS mime_type, 'knowledge_item' AS entity_type,
                       'user_knowledge' AS source_class, k.id AS knowledge_item_id,
                       k.private AS private, k.preferred AS preferred,
                       k.use_live AS use_live, k.use_rehearsal AS use_rehearsal,
                       (
                           SELECT ke.provenance_id FROM knowledge_evidence AS ke
                           WHERE ke.knowledge_item_id = k.id
                             AND ke.provenance_type = 'user_statement'
                           ORDER BY ke.provenance_id LIMIT 1
                       ) AS user_statement_id
                FROM embedding_vectors AS ev
                JOIN knowledge_items AS k ON k.id = ev.entity_id
                WHERE """
                + " AND ".join(knowledge_clauses),
                knowledge_parameters,
            ).fetchall()
            results.extend(
                (int(row["vector_row"]), _record_from_row(row)) for row in knowledge_rows
            )
        return results

    @staticmethod
    def _current_slide_candidates(
        connection: sqlite3.Connection,
        filters: RetrievalFilters,
        current_slide: int,
        slide_window: int,
    ) -> list[ChunkRecord]:
        clauses = [
            "d.project_id = ?",
            "d.parse_status = 'ready'",
            "su.unit_type = 'slide'",
            "su.ordinal BETWEEN ? AND ?",
        ]
        parameters: list[Any] = [
            filters.project_id,
            max(1, current_slide - slide_window),
            current_slide + slide_window,
        ]
        _append_filter_clauses(clauses, parameters, filters, table_alias="d")
        rows = connection.execute(
            """
            SELECT c.id AS chunk_id, c.text AS chunk_text, c.lexical_text AS lexical_text,
                   c.chunk_index AS chunk_index, su.id AS source_unit_id,
                   su.unit_type AS unit_type, su.ordinal AS ordinal,
                   d.id AS document_id, d.original_name AS original_name,
                   d.mime_type AS mime_type
            FROM chunks AS c
            JOIN source_units AS su ON su.id = c.source_unit_id
            JOIN documents AS d ON d.id = su.document_id
            WHERE """
            + " AND ".join(clauses)
            + " ORDER BY ABS(su.ordinal - ?), d.original_name COLLATE NOCASE, "
            + "c.chunk_index, c.id LIMIT ?",
            [*parameters, current_slide, CURRENT_SLIDE_CANDIDATE_LIMIT],
        ).fetchall()
        return [_record_from_row(row) for row in rows]

    def _health_result(
        self,
        project_id: str,
        *,
        status: str,
        adapter_health: EmbeddingHealth,
        active: sqlite3.Row | Any | None,
        current_chunk_count: int,
        current_knowledge_item_count: int,
        current_indexable_entity_count: int,
        indexed_count: int,
        coverage: float,
        stale_reason: str | None,
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "status": status,
            "model_available": adapter_health.status == "ready",
            "model_loaded": adapter_health.model_loaded,
            "adapter_id": adapter_health.adapter_id,
            "model_id": adapter_health.model_id,
            "model_fingerprint": adapter_health.model_fingerprint,
            "dimension": adapter_health.dimension,
            "model_load_ms": adapter_health.model_load_ms,
            "active_generation_id": str(active["id"]) if active is not None else None,
            "matrix_row_count": int(active["matrix_row_count"]) if active is not None else 0,
            "current_indexed_mappings": indexed_count,
            "current_project_chunk_count": current_chunk_count,
            "current_knowledge_item_count": current_knowledge_item_count,
            "current_indexable_entity_count": current_indexable_entity_count,
            "semantic_coverage": round(coverage, 6),
            "stale_reason": stale_reason,
            "index_model_id": str(active["model_id"]) if active is not None else None,
            "index_model_fingerprint": (
                str(active["model_fingerprint"]) if active is not None else None
            ),
            "index_dimension": int(active["dimension"]) if active is not None else None,
        }

    def _project_id(self, params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    def _emit_progress(
        self,
        project_id: str,
        stage: str,
        completed: int,
        total: int,
        status: str,
        *,
        model_id: str,
        generation_id: str,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "project_id": project_id,
            "stage": stage,
            "completed": max(0, completed),
            "total": max(0, total),
            "status": status,
            "model_id": model_id,
            "generation_id": generation_id,
        }
        if error_code is not None:
            payload["error_code"] = error_code
        self._emit("project.index_progress", payload)

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _cleanup_orphan_files(self, project_id: str) -> None:
        try:
            embedding_directory = self._storage.paths.safe_embeddings_directory(project_id)
            with self._storage.project_database(project_id) as connection:
                active = connection.execute(
                    "SELECT matrix_relative_path FROM embedding_generations WHERE is_active = 1"
                ).fetchone()
                # Repair databases created by the pre-retirement M2 build as
                # well as keeping the invariant for all future operations.
                connection.execute("DELETE FROM embedding_generations WHERE is_active = 0")
                connection.commit()
            active_relative = str(active["matrix_relative_path"]) if active is not None else None
            orphan_paths = [
                path
                for path in embedding_directory.iterdir()
                if path.is_file()
                and not path.is_symlink()
                and (path.name.startswith("vectors-") or path.name.startswith(".staging-"))
                and f"embeddings/{path.name}" != active_relative
            ]
            if orphan_paths:
                self._evict_matrix_cache(project_id)
            for path in orphan_paths:
                _remove_file_quietly(path)
        except (CoreDomainError, OSError, sqlite3.Error):
            return


def _parse_filters(
    params: dict[str, Any],
    project_id: str,
) -> tuple[RetrievalFilters, int | None, int]:
    document_ids_value = params.get("document_ids", [])
    if not isinstance(document_ids_value, list) or len(document_ids_value) > MAX_DOCUMENT_IDS:
        raise invalid_request(
            f"document_ids must be a list of at most {MAX_DOCUMENT_IDS} UUIDs.",
            field="document_ids",
        )
    document_ids: list[str] = []
    for value in document_ids_value:
        if not isinstance(value, str):
            raise invalid_request("document_ids must contain UUIDs.", field="document_ids")
        try:
            normalized = str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request("document_ids must contain UUIDs.", field="document_ids") from exc
        if normalized not in document_ids:
            document_ids.append(normalized)

    source_types_value = params.get("source_types", [])
    if not isinstance(source_types_value, list):
        raise invalid_request("source_types must be a list.", field="source_types")
    source_types: list[str] = []
    for value in source_types_value:
        if not isinstance(value, str) or value not in SOURCE_TYPE_MIME:
            raise invalid_request(
                "source_types contains an unsupported type.",
                field="source_types",
            )
        if value not in source_types:
            source_types.append(value)

    current_slide_value = params.get("current_slide")
    if current_slide_value is None:
        current_slide = None
    else:
        current_slide = _validated_integer(current_slide_value, "current_slide", 1, MAX_SLIDE)
    default_window = 1 if current_slide is not None else 0
    slide_window = _bounded_integer(
        params,
        "slide_window",
        default=default_window,
        minimum=0,
        maximum=MAX_SLIDE_WINDOW,
    )
    usage = params.get("usage", "all")
    if not isinstance(usage, str) or usage not in {"all", "rehearsal", "live"}:
        raise invalid_request("usage must be all, rehearsal, or live.", field="usage")
    allow_private = params.get("allow_private", True)
    if not isinstance(allow_private, bool):
        raise invalid_request("allow_private must be a boolean.", field="allow_private")
    return (
        RetrievalFilters(
            project_id=project_id,
            document_ids=tuple(document_ids),
            source_types=tuple(source_types),
            usage=usage,
            allow_private=allow_private,
        ),
        current_slide,
        slide_window,
    )


def _append_filter_clauses(
    clauses: list[str],
    parameters: list[Any],
    filters: RetrievalFilters,
    *,
    table_alias: str,
) -> None:
    if filters.document_ids:
        placeholders = ", ".join("?" for _ in filters.document_ids)
        clauses.append(f"{table_alias}.id IN ({placeholders})")
        parameters.extend(filters.document_ids)
    if filters.source_types:
        mime_types = [SOURCE_TYPE_MIME[source_type] for source_type in filters.source_types]
        placeholders = ", ".join("?" for _ in mime_types)
        clauses.append(f"{table_alias}.mime_type IN ({placeholders})")
        parameters.extend(mime_types)


def _slide_boost(record: ChunkRecord, current_slide: int | None, slide_window: int) -> float:
    if (
        current_slide is None
        or record.source_type != "pptx"
        or record.unit_type != "slide"
        or record.ordinal is None
    ):
        return 0.0
    distance = abs(record.ordinal - current_slide)
    if distance == 0:
        return CURRENT_SLIDE_BOOST
    if distance == 1 and slide_window >= 1:
        return ADJACENT_SLIDE_BOOST
    if 1 < distance <= slide_window:
        return WINDOW_SLIDE_BOOST
    return 0.0


def _bounded_integer(
    params: dict[str, Any],
    field: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    return _validated_integer(params.get(field, default), field, minimum, maximum)


def _validated_integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise invalid_request(f"{field} must be between {minimum} and {maximum}.", field=field)
    return int(value)


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _remove_file_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists() and path.is_file() and not path.is_symlink():
            path.unlink()
    except OSError:
        return
