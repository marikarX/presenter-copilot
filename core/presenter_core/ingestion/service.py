"""Project-local source snapshot, parsing, chunk persistence, and previews."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .chunking import chunk_text
from .models import Evidence, ParsedSourceUnit
from .parsers.base import SourceParser
from .parsers.registry import parser_for
from .security import (
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_SOURCE_UNITS,
    preflight_source,
    source_type_for_path,
)

EventSink = Callable[[str, dict[str, Any]], None]
MAX_FILENAME_LENGTH = 120
MAX_PREVIEW_UNITS = 25
MAX_PREVIEW_TEXT_CHARS = 12_000
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")

MIME_TYPES = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "markdown": "text/markdown",
}


class IngestionService:
    """Own the import lifecycle but never parse an external file in place."""

    def __init__(self, storage: StorageManager, event_sink: EventSink | None = None) -> None:
        self._storage = storage
        self._event_sink = event_sink

    def import_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "path", "kind"})
        project_id = self._project_id(params)
        external_path = self._external_path(params)
        source_type = source_type_for_path(external_path)
        kind = self._kind(params, source_type)
        parser = parser_for(source_type)
        source_directory = self._storage.paths.safe_sources_directory(project_id, create=True)

        size_bytes = preflight_source(external_path, source_type)
        sha256 = _sha256_file(external_path)
        with self._storage.project_database(project_id) as connection:
            duplicate = connection.execute(
                "SELECT id FROM documents WHERE project_id = ? AND sha256 = ?",
                (project_id, sha256),
            ).fetchone()
            if duplicate is not None:
                raise CoreDomainError(
                    "SOURCE_DUPLICATE",
                    "This source is already imported in the project.",
                    details={
                        "duplicate": True,
                        "existing_document_id": duplicate["id"],
                    },
                )

        document_id = str(uuid.uuid4())
        original_name = external_path.name
        snapshot_name = _snapshot_filename(document_id, original_name)
        snapshot = source_directory / snapshot_name
        relative_snapshot = f"sources/{snapshot_name}"
        self._emit_progress(project_id, document_id, "snapshot", 0, 1, "started")
        try:
            _copy_atomically(external_path, snapshot, max_bytes=size_bytes)
            self._storage.paths.snapshot_path(project_id, relative_snapshot, require_exists=True)
            if _sha256_file(snapshot) != sha256:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_FAILED",
                    "The selected source changed while it was being copied.",
                    retryable=True,
                    details={},
                )
            # The copied file, rather than the user-selected path, is the
            # security subject for the parser that follows.
            preflight_source(snapshot, source_type)
        except CoreDomainError:
            _remove_snapshot(snapshot)
            raise
        except OSError as exc:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED",
                "The source could not be copied into the project vault.",
                retryable=True,
                details={},
            ) from exc
        self._emit_progress(project_id, document_id, "snapshot", 1, 1, "complete")

        imported_at = utc_now()
        try:
            with self._storage.project_database(project_id) as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, project_id, kind, original_name, local_snapshot_path,
                        source_uri, sha256, mime_type, parser_id, imported_at,
                        parse_status, parse_error_code, parse_error_message,
                        byte_size, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                    """,
                    (
                        document_id,
                        project_id,
                        kind,
                        original_name,
                        relative_snapshot,
                        sha256,
                        MIME_TYPES[source_type],
                        parser.parser_id,
                        imported_at,
                        size_bytes,
                        json.dumps(
                            {
                                "source_type": source_type,
                                "parser": parser.parser_id,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
                connection.commit()
        except Exception:
            _remove_snapshot(snapshot)
            raise

        self._emit_progress(project_id, document_id, "parse", 0, 1, "started")
        try:
            parsed_units = self._parse_snapshot(snapshot, source_type, parser=parser)
            self._validate_parsed_units(parsed_units)
        except CoreDomainError as error:
            self._mark_document_error(project_id, document_id, error.code, error.message)
            self._emit_error(project_id, document_id, error.code, "parse")
            raise
        self._emit_progress(project_id, document_id, "parse", 1, 1, "complete")

        unit_rows, chunk_rows = self._build_rows(document_id, parsed_units)
        self._emit_progress(
            project_id, document_id, "chunk", len(unit_rows), len(unit_rows), "complete"
        )
        self._persist_parsed_content(project_id, document_id, unit_rows, chunk_rows)
        self._emit_progress(
            project_id,
            document_id,
            "persist",
            len(unit_rows) + len(chunk_rows),
            len(unit_rows) + len(chunk_rows),
            "complete",
        )
        self._emit_index_events(project_id, document_id, len(chunk_rows))

        with self._storage.project_database(project_id) as connection:
            document = self._document_row(connection, document_id)
            return {
                "document": self._document_dict(document, connection),
                "duplicate": False,
                "source_units_count": len(unit_rows),
                "chunks_count": len(chunk_rows),
                "status": "ready",
            }

    def list_sources(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY imported_at DESC, id DESC"
            ).fetchall()
            return {"sources": [self._document_dict(row, connection) for row in rows]}

    def preview_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "offset", "limit"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        offset = self._bounded_integer(params, "offset", default=0, minimum=0, maximum=100_000)
        limit = self._bounded_integer(
            params,
            "limit",
            default=MAX_PREVIEW_UNITS,
            minimum=1,
            maximum=MAX_PREVIEW_UNITS,
        )
        with self._storage.project_database(project_id) as connection:
            document = self._document_row(connection, document_id)
            total_row = connection.execute(
                "SELECT COUNT(*) AS count FROM source_units WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            total = int(total_row["count"]) if total_row else 0
            units = connection.execute(
                """
                SELECT * FROM source_units
                WHERE document_id = ?
                ORDER BY ordinal IS NULL, ordinal, id
                LIMIT ? OFFSET ?
                """,
                (document_id, limit, offset),
            ).fetchall()
            previews = [self._unit_preview(document, row) for row in units]
            return {
                "document": self._document_dict(document, connection),
                "units": previews,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(previews) < total,
            }

    def delete_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        with self._storage.project_database(project_id) as connection:
            document = self._document_row(connection, document_id)
        try:
            if document["local_snapshot_path"]:
                snapshot = self._storage.paths.snapshot_path(
                    project_id,
                    document["local_snapshot_path"],
                )
                # Filesystem cleanup intentionally precedes the DB commit. If
                # the DB operation fails, the retained document row makes a
                # retry able to finish the cleanup even though the snapshot
                # is already absent.
                _remove_snapshot(snapshot)
            self._delete_document_record(project_id, document_id)
        except CoreDomainError as error:
            if error.code == "SOURCE_DELETE_FAILED":
                raise
            raise CoreDomainError(
                "SOURCE_DELETE_FAILED",
                "The source could not be deleted; retry to complete cleanup.",
                retryable=True,
                details={"cause_code": error.code},
            ) from error
        except (OSError, sqlite3.Error) as error:
            raise CoreDomainError(
                "SOURCE_DELETE_FAILED",
                "The source could not be deleted; retry to complete cleanup.",
                retryable=True,
                details={"cause_code": type(error).__name__},
            ) from error
        except Exception as error:
            raise CoreDomainError(
                "SOURCE_DELETE_FAILED",
                "The source could not be deleted; retry to complete cleanup.",
                retryable=True,
                details={},
            ) from error
        return {"project_id": project_id, "document_id": document_id, "deleted": True}

    def _delete_document_record(self, project_id: str, document_id: str) -> None:
        with self._storage.project_database(project_id) as connection:
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                raise CoreDomainError(
                    "SOURCE_DELETE_FAILED",
                    "The source record could not be deleted.",
                    retryable=True,
                    details={},
                )
            connection.commit()

    def reindex_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        with self._storage.project_database(project_id) as connection:
            document = self._document_row(connection, document_id)
        source_type = _source_type_from_mime(document["mime_type"])
        parser = parser_for(source_type)
        self._emit_progress(project_id, document_id, "parse", 0, 1, "started")
        try:
            relative_path = document["local_snapshot_path"]
            if not relative_path:
                raise CoreDomainError("SOURCE_REINDEX_FAILED", "The source has no stored snapshot.")
            snapshot = self._storage.paths.snapshot_path(
                project_id, relative_path, require_exists=True
            )
            preflight_source(snapshot, source_type)
            snapshot_sha256 = _sha256_file(snapshot)
            if snapshot_sha256 != document["sha256"]:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored source snapshot no longer matches its imported hash.",
                    details={},
                )
            parsed_units = self._parse_snapshot(snapshot, source_type, parser=parser)
            self._validate_parsed_units(parsed_units)
        except CoreDomainError as error:
            raise CoreDomainError(
                "SOURCE_REINDEX_FAILED",
                "The stored source could not be re-indexed; previous parsed content was retained.",
                retryable=False,
                details={"cause_code": error.code},
            ) from error
        self._emit_progress(project_id, document_id, "parse", 1, 1, "complete")

        unit_rows, chunk_rows = self._build_rows(document_id, parsed_units)
        self._emit_progress(
            project_id, document_id, "chunk", len(unit_rows), len(unit_rows), "complete"
        )
        try:
            with self._storage.project_database(project_id) as connection:
                reusable_vectors = self._capture_active_vectors(connection, document_id)
                connection.execute("DELETE FROM source_units WHERE document_id = ?", (document_id,))
                self._insert_rows(connection, unit_rows, chunk_rows)
                self._restore_reusable_vectors(connection, reusable_vectors, chunk_rows)
                connection.execute(
                    """
                    UPDATE documents
                    SET parse_status = 'ready', parse_error_code = NULL,
                        parse_error_message = NULL, parser_id = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        parser.parser_id,
                        _parser_metadata(document["metadata_json"], source_type, parser.parser_id),
                        document_id,
                    ),
                )
                connection.commit()
                document = self._document_row(connection, document_id)
                result_document = self._document_dict(document, connection)
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "SOURCE_REINDEX_FAILED",
                "The stored source could not be re-indexed; previous parsed content was retained.",
                retryable=True,
                details={},
            ) from exc
        self._emit_index_events(project_id, document_id, len(chunk_rows))
        return {
            "document": result_document,
            "source_units_count": len(unit_rows),
            "chunks_count": len(chunk_rows),
            "status": "ready",
        }

    def _parse_snapshot(
        self,
        snapshot: Path,
        source_type: str,
        *,
        parser: SourceParser | None = None,
    ) -> list[ParsedSourceUnit]:
        # Keep the security check immediately adjacent to parser consumption;
        # callers may also preflight earlier for clearer lifecycle stages.
        preflight_source(snapshot, source_type)
        parser = parser or parser_for(source_type)
        return parser.parse(snapshot)

    def _validate_parsed_units(self, units: list[ParsedSourceUnit]) -> None:
        if len(units) > MAX_SOURCE_UNITS:
            raise CoreDomainError(
                "SOURCE_PARSE_FAILED",
                "The source contains too many structural units.",
                details={"max_units": MAX_SOURCE_UNITS},
            )
        total_text = 0
        for unit in units:
            if unit.unit_type not in {"slide", "page", "section"}:
                raise CoreDomainError(
                    "SOURCE_PARSE_FAILED", "The parser returned an unsupported unit type."
                )
            if not isinstance(unit.text, str) or not isinstance(unit.metadata, dict):
                raise CoreDomainError(
                    "SOURCE_PARSE_FAILED", "The parser returned invalid source data."
                )
            if unit.search_text is not None and not isinstance(unit.search_text, str):
                raise CoreDomainError(
                    "SOURCE_PARSE_FAILED", "The parser returned invalid source data."
                )
            total_text += len(unit.index_text)
            if total_text > MAX_EXTRACTED_TEXT_CHARS:
                raise CoreDomainError(
                    "SOURCE_PARSE_FAILED",
                    "The extracted source text exceeds the import limit.",
                    details={"max_text_chars": MAX_EXTRACTED_TEXT_CHARS},
                )

    def _build_rows(
        self,
        document_id: str,
        units: list[ParsedSourceUnit],
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        unit_rows: list[tuple[Any, ...]] = []
        chunk_rows: list[tuple[Any, ...]] = []
        now = utc_now()
        for structural_index, unit in enumerate(units):
            unit_id = _source_unit_id(document_id, unit, structural_index)
            unit_rows.append(
                (
                    unit_id,
                    document_id,
                    unit.unit_type,
                    unit.ordinal,
                    unit.title,
                    None,
                    None,
                    None,
                    unit.text,
                    json.dumps(
                        unit.metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                )
            )
            for chunk in chunk_text(unit.index_text):
                chunk_rows.append(
                    (
                        _chunk_id(unit_id, chunk.chunk_index, chunk.text),
                        unit_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.token_count,
                        None,
                        chunk.lexical_text,
                        now,
                    )
                )
        return unit_rows, chunk_rows

    def _persist_parsed_content(
        self,
        project_id: str,
        document_id: str,
        unit_rows: list[tuple[Any, ...]],
        chunk_rows: list[tuple[Any, ...]],
    ) -> None:
        try:
            with self._storage.project_database(project_id) as connection:
                self._insert_rows(connection, unit_rows, chunk_rows)
                connection.execute(
                    """
                    UPDATE documents
                    SET parse_status = 'ready', parse_error_code = NULL,
                        parse_error_message = NULL
                    WHERE id = ?
                    """,
                    (document_id,),
                )
                connection.commit()
        except Exception as exc:
            self._mark_document_error(
                project_id, document_id, "SOURCE_PERSIST_FAILED", "Source persistence failed."
            )
            raise CoreDomainError(
                "SOURCE_PERSIST_FAILED",
                "The parsed source could not be persisted.",
                retryable=True,
                details={},
            ) from exc

    @staticmethod
    def _insert_rows(
        connection: Any,
        unit_rows: list[tuple[Any, ...]],
        chunk_rows: list[tuple[Any, ...]],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms,
                end_ms, speaker_label, text, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            unit_rows,
        )
        connection.executemany(
            """
            INSERT INTO chunks (
                id, source_unit_id, chunk_index, text, token_count,
                embedding_key, lexical_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chunk_rows,
        )

    def _mark_document_error(
        self,
        project_id: str,
        document_id: str,
        code: str,
        message: str,
    ) -> None:
        try:
            with self._storage.project_database(project_id) as connection:
                connection.execute(
                    """
                    DELETE FROM embedding_vectors
                    WHERE entity_type = 'chunk'
                      AND entity_id IN (
                          SELECT c.id
                          FROM chunks AS c
                          JOIN source_units AS su ON su.id = c.source_unit_id
                          WHERE su.document_id = ?
                      )
                    """,
                    (document_id,),
                )
                connection.execute(
                    """
                    UPDATE chunks
                    SET embedding_key = NULL
                    WHERE source_unit_id IN (
                        SELECT id FROM source_units WHERE document_id = ?
                    )
                    """,
                    (document_id,),
                )
                connection.execute(
                    """
                    UPDATE documents
                    SET parse_status = 'error', parse_error_code = ?, parse_error_message = ?
                    WHERE id = ?
                    """,
                    (code, message, document_id),
                )
                connection.commit()
        except Exception:
            # The original structured error is more useful to the caller than
            # a secondary failure while recording an already-failed parse.
            pass

    @staticmethod
    def _capture_active_vectors(connection: Any, document_id: str) -> list[tuple[Any, ...]]:
        """Capture active vector metadata before re-index cascades delete old chunks."""
        rows = cast(
            list[sqlite3.Row],
            connection.execute(
                """
            SELECT ev.generation_id, ev.vector_id, ev.entity_type, ev.entity_id,
                   ev.project_id, ev.source_class, ev.row_index, ev.content_sha256
            FROM embedding_vectors AS ev
            JOIN embedding_generations AS eg ON eg.id = ev.generation_id
            JOIN chunks AS c ON c.id = ev.entity_id
            JOIN source_units AS su ON su.id = c.source_unit_id
            WHERE eg.is_active = 1 AND ev.entity_type = 'chunk' AND su.document_id = ?
            ORDER BY ev.row_index
            """,
                (document_id,),
            ).fetchall(),
        )
        return [tuple(row) for row in rows]

    @staticmethod
    def _restore_reusable_vectors(
        connection: Any,
        reusable_vectors: list[tuple[Any, ...]],
        chunk_rows: list[tuple[Any, ...]],
    ) -> None:
        """Restore only unchanged active mappings after a successful re-index."""
        if not reusable_vectors or not chunk_rows:
            return
        current_hashes = {
            str(row[0]): hashlib.sha256(str(row[3]).encode("utf-8")).hexdigest()
            for row in chunk_rows
        }
        reusable = [
            tuple(row)
            for row in reusable_vectors
            if str(row[3]) in current_hashes and str(row[7]) == current_hashes[str(row[3])]
        ]
        if not reusable:
            return
        connection.executemany(
            """
            INSERT INTO embedding_vectors (
                generation_id, vector_id, entity_type, entity_id,
                project_id, source_class, row_index, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            reusable,
        )
        connection.executemany(
            "UPDATE chunks SET embedding_key = ? WHERE id = ?",
            [(f"{row[0]}:{row[3]}", row[3]) for row in reusable],
        )

    def _emit_progress(
        self,
        project_id: str,
        document_id: str,
        stage: str,
        completed: int,
        total: int,
        status: str,
    ) -> None:
        self._emit(
            "source.import_progress",
            {
                "project_id": project_id,
                "document_id": document_id,
                "stage": stage,
                "completed": max(0, completed),
                "total": max(0, total),
                "status": status,
            },
        )

    def _emit_index_events(self, project_id: str, document_id: str, chunk_count: int) -> None:
        self._emit_progress(project_id, document_id, "index", chunk_count, chunk_count, "complete")
        self._emit(
            "project.index_progress",
            {
                "project_id": project_id,
                "document_id": document_id,
                "stage": "lexical",
                "completed": chunk_count,
                "total": chunk_count,
                "status": "complete",
            },
        )
        self._emit(
            "project.index_ready",
            {
                "project_id": project_id,
                "document_id": document_id,
                "index_kind": "lexical",
                "chunk_count": chunk_count,
            },
        )
        self._emit_progress(project_id, document_id, "complete", 1, 1, "complete")

    def _emit_error(self, project_id: str, document_id: str, code: str, stage: str) -> None:
        self._emit(
            "source.import_error",
            {
                "project_id": project_id,
                "document_id": document_id,
                "stage": stage,
                "code": code,
            },
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    @staticmethod
    def _document_row(connection: Any, document_id: str) -> Any:
        row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        return row

    def _document_dict(self, row: Any, connection: Any) -> dict[str, Any]:
        units_row = connection.execute(
            "SELECT COUNT(*) AS count FROM source_units WHERE document_id = ?", (row["id"],)
        ).fetchone()
        chunks_row = connection.execute(
            """
            SELECT COUNT(*) AS count FROM chunks
            WHERE source_unit_id IN (SELECT id FROM source_units WHERE document_id = ?)
            """,
            (row["id"],),
        ).fetchone()
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        result: dict[str, Any] = {
            "id": row["id"],
            "project_id": row["project_id"],
            "kind": row["kind"],
            "original_name": row["original_name"],
            "source_type": _source_type_from_mime(row["mime_type"]),
            "mime_type": row["mime_type"],
            "parser_id": row["parser_id"],
            "sha256": row["sha256"],
            "imported_at": row["imported_at"],
            "parse_status": row["parse_status"],
            "byte_size": row["byte_size"],
            "source_units_count": int(units_row["count"]) if units_row else 0,
            "chunks_count": int(chunks_row["count"]) if chunks_row else 0,
            "snapshot_name": Path(row["local_snapshot_path"]).name
            if row["local_snapshot_path"]
            else None,
        }
        if row["parse_error_code"]:
            result["parse_error"] = {
                "code": row["parse_error_code"],
                "message": row["parse_error_message"] or "The source could not be parsed.",
            }
        result["metadata"] = metadata
        return result

    def _unit_preview(self, document: Any, row: Any) -> dict[str, Any]:
        text = row["text"]
        excerpt = text[:MAX_PREVIEW_TEXT_CHARS]
        title = row["title"]
        title_excerpt = title[:MAX_PREVIEW_TEXT_CHARS] if isinstance(title, str) else title
        metadata: dict[str, Any]
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata.get("notes"), str):
            metadata["notes"] = metadata["notes"][:MAX_PREVIEW_TEXT_CHARS]
        evidence = self.evidence_for_unit(document, row, excerpt)
        return {
            "id": row["id"],
            "unit_type": row["unit_type"],
            "ordinal": row["ordinal"],
            "title": title_excerpt,
            "title_truncated": isinstance(title, str) and len(title) > len(title_excerpt),
            "text": excerpt,
            "text_truncated": len(text) > len(excerpt),
            "metadata": metadata,
            "provenance": evidence.to_dict(),
        }

    @staticmethod
    def evidence_for_unit(document: Any, unit: Any, text: str) -> Evidence:
        label = provenance_label(document["original_name"], unit["unit_type"], unit["ordinal"])
        return Evidence(
            evidence_id=unit["id"],
            source_type="document",
            source_id=document["id"],
            source_unit_id=unit["id"],
            label=label,
            text=text,
            fact_safe=True,
        )

    def _project_id(self, params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _document_id(params: dict[str, Any]) -> str:
        value = params.get("document_id")
        if not isinstance(value, str):
            raise invalid_request("document_id must be a UUID.", field="document_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request("document_id must be a UUID.", field="document_id") from exc

    @staticmethod
    def _external_path(params: dict[str, Any]) -> Path:
        value = params.get("path")
        if not isinstance(value, str) or not value or "\x00" in value:
            raise invalid_request("path must be a readable file path.", field="path")
        try:
            path = Path(value).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected source cannot be read."
            ) from exc
        if not path.is_file():
            raise CoreDomainError("SOURCE_SNAPSHOT_FAILED", "The selected source cannot be read.")
        return path

    @staticmethod
    def _kind(params: dict[str, Any], source_type: str) -> str:
        default = "presentation" if source_type == "pptx" else "supporting"
        value = params.get("kind", default)
        if not isinstance(value, str) or value not in {
            "presentation",
            "supporting",
            "transcript",
            "note",
        }:
            raise invalid_request("kind is not supported.", field="kind")
        return value

    @staticmethod
    def _bounded_integer(
        params: dict[str, Any],
        field: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = params.get(field, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise invalid_request(f"{field} must be between {minimum} and {maximum}.", field=field)
        return int(value)


def provenance_label(original_name: str, unit_type: str, ordinal: int | None) -> str:
    """Build the one canonical human-readable source label."""
    name = Path(original_name).name
    if unit_type == "slide":
        location = f"slide {ordinal}" if ordinal is not None else "slide"
    elif unit_type == "page":
        location = f"p.{ordinal}" if ordinal is not None else "page"
    elif unit_type == "section":
        location = f"section {ordinal}" if ordinal is not None else "section"
    else:
        location = unit_type
    return f"{name} {location}"


def _source_unit_id(document_id: str, unit: ParsedSourceUnit, structural_index: int) -> str:
    """Derive a stable unit identity from document structure, not wall time."""
    ordinal = "" if unit.ordinal is None else str(unit.ordinal)
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"presenter-copilot:source-unit:{document_id}:{structural_index}:"
            f"{unit.unit_type}:{ordinal}",
        )
    )


def _chunk_id(source_unit_id: str, chunk_index: int, text: str) -> str:
    """Derive a stable chunk identity while changing it when content changes."""
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"presenter-copilot:chunk:{source_unit_id}:{chunk_index}:{fingerprint}",
        )
    )


def _parser_metadata(metadata_json: Any, source_type: str, parser_id: str) -> str:
    """Synchronize persisted parser identity without retaining malformed JSON."""
    try:
        metadata = json.loads(metadata_json)
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["source_type"] = source_type
    metadata["parser"] = parser_id
    return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise CoreDomainError(
            "SOURCE_SNAPSHOT_FAILED", "The selected source cannot be read."
        ) from exc
    return digest.hexdigest()


def _snapshot_filename(document_id: str, original_name: str) -> str:
    base_name = original_name.replace("\\", "/").split("/")[-1]
    safe_name = _SAFE_FILENAME_RE.sub("_", base_name).strip(" .")
    if not safe_name:
        safe_name = "source"
    safe_name = re.sub(r"\.{2,}", ".", safe_name)
    safe_name = safe_name[:MAX_FILENAME_LENGTH].rstrip(" .") or "source"
    return f"{document_id}-{safe_name}"


def _copy_atomically(source: Path, destination: Path, *, max_bytes: int) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with source.open("rb") as source_handle, temporary.open("xb") as temporary_handle:
            copied = 0
            while block := source_handle.read(1024 * 1024):
                copied += len(block)
                if copied > max_bytes:
                    raise CoreDomainError(
                        "SOURCE_TOO_LARGE",
                        "The source exceeded its validated import size while being copied.",
                        details={"max_bytes": max_bytes},
                    )
                temporary_handle.write(block)
            temporary_handle.flush()
            os.fsync(temporary_handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        _remove_snapshot(temporary)
        raise


def _remove_snapshot(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        raise CoreDomainError(
            "SOURCE_SNAPSHOT_FAILED",
            "The project snapshot could not be cleaned up.",
            retryable=True,
            details={},
        ) from exc


def _source_type_from_mime(mime_type: str) -> str:
    for source_type, mime in MIME_TYPES.items():
        if mime == mime_type:
            return source_type
    raise CoreDomainError("SOURCE_TYPE_UNSUPPORTED", "The stored source type is not supported.")
