"""Immutable presentation lineage and revision metadata."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import PurePosixPath
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.revision_identity import original_presentation_revision_id
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 100
MAX_REVISION_NUMBER = 2**53 - 1


def record_original_revision(connection: sqlite3.Connection, document_id: str) -> str:
    """Register the imported snapshot as immutable revision one, idempotently."""
    row = connection.execute(
        """
        SELECT id, kind, local_snapshot_path, sha256, byte_size, imported_at
        FROM documents WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    if row is None or row["kind"] != "presentation":
        raise CoreDomainError(
            "PRESENTATION_REVISION_SOURCE_INVALID",
            "The original presentation revision cannot be registered.",
        )
    existing = connection.execute(
        """
        SELECT h.revision_id
        FROM presentations p
        LEFT JOIN presentation_revision_heads h ON h.presentation_id = p.id
        WHERE p.id = ?
        """,
        (document_id,),
    ).fetchone()
    if existing is not None:
        revision_id = existing["revision_id"]
        if not isinstance(revision_id, str) or not revision_id:
            raise CoreDomainError(
                "PRESENTATION_REVISION_STATE_INVALID",
                "The presentation revision history is incomplete.",
            )
        return revision_id

    relative_path = row["local_snapshot_path"]
    digest = row["sha256"]
    byte_size = row["byte_size"]
    created_at = row["imported_at"]
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or not isinstance(digest, str)
        or not _SHA256.fullmatch(digest)
        or isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or byte_size <= 0
        or not isinstance(created_at, str)
        or not created_at
    ):
        raise CoreDomainError(
            "PRESENTATION_REVISION_SOURCE_INVALID",
            "The original presentation revision metadata is invalid.",
        )

    revision_id = original_presentation_revision_id(document_id, digest)
    connection.execute(
        "INSERT INTO presentations (id, created_at) VALUES (?, ?)",
        (document_id, created_at),
    )
    connection.execute(
        """
        INSERT INTO presentation_revisions (
            id, presentation_id, parent_revision_id, revision_number,
            revision_kind, local_snapshot_path, sha256, byte_size, created_at
        ) VALUES (?, ?, NULL, 1, 'original', ?, ?, ?, ?)
        """,
        (revision_id, document_id, relative_path, digest, byte_size, created_at),
    )
    connection.execute(
        "INSERT INTO presentation_revision_heads (presentation_id, revision_id) VALUES (?, ?)",
        (document_id, revision_id),
    )
    return revision_id


class PresentationRevisionService:
    """Read history and clean managed revision files with Core-owned paths."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def list_revisions(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "limit", "before_revision_number"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        limit = params.get("limit", DEFAULT_HISTORY_LIMIT)
        before_revision_number = params.get("before_revision_number")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_HISTORY_LIMIT
        ):
            raise invalid_request(
                f"limit must be between 1 and {MAX_HISTORY_LIMIT}.", field="limit"
            )
        if before_revision_number is not None and (
            isinstance(before_revision_number, bool)
            or not isinstance(before_revision_number, int)
            or not 2 <= before_revision_number <= MAX_REVISION_NUMBER
        ):
            raise invalid_request(
                "before_revision_number must be at least 2.",
                field="before_revision_number",
            )
        with self._storage.project_database(project_id) as connection:
            document = connection.execute(
                "SELECT kind FROM documents WHERE id = ? AND project_id = ?",
                (document_id, project_id),
            ).fetchone()
            if document is None:
                raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
            if document["kind"] != "presentation":
                raise CoreDomainError(
                    "PRESENTATION_REVISION_SOURCE_INVALID",
                    "Revision history is available for imported presentations only.",
                )
            lineage = connection.execute(
                """
                SELECT p.id, h.revision_id
                FROM presentations p
                LEFT JOIN presentation_revision_heads h ON h.presentation_id = p.id
                WHERE p.id = ?
                """,
                (document_id,),
            ).fetchone()
            if lineage is None or not isinstance(lineage["revision_id"], str):
                raise CoreDomainError(
                    "PRESENTATION_REVISION_STATE_INVALID",
                    "The presentation revision history is unavailable.",
                )
            rows = connection.execute(
                """
                SELECT id, parent_revision_id, revision_number, revision_kind,
                       sha256, byte_size, created_at
                FROM presentation_revisions
                WHERE presentation_id = ? AND (? IS NULL OR revision_number < ?)
                ORDER BY revision_number DESC, id
                LIMIT ?
                """,
                (
                    document_id,
                    before_revision_number,
                    before_revision_number,
                    limit + 1,
                ),
            ).fetchall()
            transaction_rows = connection.execute(
                "SELECT revision_id, baseline_revision_id, operation_metadata_json "
                "FROM presentation_edit_transactions WHERE presentation_id = ? "
                f"AND revision_id IN ({','.join('?' for _ in rows) or 'NULL'})",
                (document_id, *(row["id"] for row in rows)),
            ).fetchall()
            transactions = {
                row["revision_id"]: {
                    "baseline_revision_id": row["baseline_revision_id"],
                    "operations": json.loads(row["operation_metadata_json"]),
                }
                for row in transaction_rows
            }

        has_more = len(rows) > limit
        page = rows[:limit]

        return {
            "presentation_id": document_id,
            "current_revision_id": lineage["revision_id"],
            "has_more": has_more,
            "next_before_revision_number": (
                int(page[-1]["revision_number"]) if has_more and page else None
            ),
            "revisions": [
                {
                    "revision_id": row["id"],
                    "parent_revision_id": row["parent_revision_id"],
                    "revision_number": int(row["revision_number"]),
                    "revision_kind": row["revision_kind"],
                    "sha256": row["sha256"],
                    "byte_size": int(row["byte_size"]),
                    "created_at": row["created_at"],
                    "is_current": row["id"] == lineage["revision_id"],
                    **(
                        {"edit_transaction": transactions[row["id"]]}
                        if row["id"] in transactions
                        else {}
                    ),
                }
                for row in page
            ],
        }

    def before_source_delete(self, project_id: str, document_id: str) -> None:
        """Remove only app-named non-original snapshots before source deletion."""
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.local_snapshot_path, d.local_snapshot_path AS original_path
                FROM presentation_revisions r
                JOIN documents d ON d.id = r.presentation_id
                WHERE r.presentation_id = ? AND d.project_id = ?
                """,
                (document_id, project_id),
            ).fetchall()
        for row in rows:
            relative_path = row["local_snapshot_path"]
            if relative_path == row["original_path"]:
                continue
            expected_name = f"revision-{row['id']}.pptx"
            if (
                not isinstance(relative_path, str)
                or PurePosixPath(relative_path).name != expected_name
            ):
                raise CoreDomainError(
                    "PRESENTATION_REVISION_PATH_INVALID",
                    "A managed presentation revision path is invalid.",
                )
            snapshot = self._storage.paths.snapshot_path(project_id, relative_path)
            try:
                snapshot.unlink(missing_ok=True)
            except OSError as error:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_DELETE_FAILED",
                    "A presentation revision could not be removed; retry is safe.",
                    retryable=True,
                ) from error

    def assert_source_deletable(self, project_id: str, document_id: str) -> None:
        """Keep active rehearsal sessions bound until they have ended."""
        with self._storage.project_database(project_id) as connection:
            active = connection.execute(
                """
                SELECT 1
                FROM sessions AS s
                JOIN presentation_revisions AS r ON r.id = s.presentation_revision_id
                WHERE r.presentation_id = ? AND s.status = 'active'
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        if active is not None:
            raise CoreDomainError(
                "PRESENTATION_SESSION_ACTIVE",
                "End the active session using this presentation before deleting it.",
                retryable=True,
            )

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _document_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("document_id must be a UUID.", field="document_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request("document_id must be a UUID.", field="document_id") from error
