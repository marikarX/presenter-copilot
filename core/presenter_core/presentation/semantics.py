"""Revision-scoped, user-confirmed semantic presentation labels."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

SLIDE_PURPOSES = frozenset(
    {
        "opening",
        "problem",
        "recommendation",
        "evidence",
        "plan",
        "risk",
        "transition",
        "summary",
        "appendix",
        "unclear",
    }
)


class PresentationSemanticService:
    """Persist only explicit user-confirmed semantics for immutable revisions."""

    def __init__(
        self,
        storage: StorageManager,
        workspace_sources: PresentationWorkspaceSourceService,
    ) -> None:
        self._storage = storage
        self._workspace_sources = workspace_sources

    def list_slide_purposes(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "revision_id"})
        project_id = self._project_id(params.get("project_id"))
        document_id = self._uuid_field(params.get("document_id"), "document_id")
        revision_id = self._uuid_field(params.get("revision_id"), "revision_id")

        with self._storage.project_database(project_id) as connection:
            self._require_current_presentation(connection, project_id, document_id, revision_id)
            rows = connection.execute(
                """
                SELECT slide_id, purpose, provenance, created_at, updated_at
                FROM presentation_slide_purposes
                WHERE presentation_id = ? AND revision_id = ?
                ORDER BY slide_id
                """,
                (document_id, revision_id),
            ).fetchall()

        return {
            "revision_id": revision_id,
            "items": [
                {
                    "slide_id": str(row["slide_id"]),
                    "revision_id": revision_id,
                    "purpose": str(row["purpose"]),
                    "provenance": str(row["provenance"]),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                }
                for row in rows
            ],
        }

    def save_slide_purpose(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_id",
                "slide_number",
                "purpose",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._uuid_field(params.get("document_id"), "document_id")
        revision_id = self._uuid_field(params.get("revision_id"), "revision_id")
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        slide_number = self._slide_number(params.get("slide_number"))
        purpose = params.get("purpose")
        if not isinstance(purpose, str) or purpose not in SLIDE_PURPOSES:
            raise invalid_request("purpose is not a supported slide label.", field="purpose")

        selection = self._workspace_sources.list_text_targets(
            {
                "project_id": project_id,
                "document_id": document_id,
                "revision_id": revision_id,
                "slide_number": slide_number,
            }
        )
        if selection.get("slide_id") != slide_id:
            raise CoreDomainError(
                "PRESENTATION_SEMANTIC_SLIDE_MISMATCH",
                "The selected slide changed. Refresh the workspace and try again.",
                retryable=True,
            )

        now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_current_presentation(connection, project_id, document_id, revision_id)
            connection.execute(
                """
                INSERT INTO presentation_slide_purposes (
                    presentation_id, revision_id, slide_id, purpose, provenance,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'user_confirmed', ?, ?)
                ON CONFLICT (presentation_id, revision_id, slide_id) DO UPDATE SET
                    purpose = excluded.purpose,
                    provenance = excluded.provenance,
                    updated_at = excluded.updated_at
                """,
                (document_id, revision_id, slide_id, purpose, now, now),
            )
            saved = connection.execute(
                """
                SELECT created_at FROM presentation_slide_purposes
                WHERE presentation_id = ? AND revision_id = ? AND slide_id = ?
                """,
                (document_id, revision_id, slide_id),
            ).fetchone()
            if saved is None:
                raise CoreDomainError(
                    "PRESENTATION_SEMANTIC_STATE_INVALID",
                    "The slide purpose could not be verified after saving.",
                )
            connection.commit()

        return {
            "revision_id": revision_id,
            "slide_id": slide_id,
            "purpose": purpose,
            "provenance": "user_confirmed",
            "created_at": str(saved["created_at"]),
            "updated_at": now,
        }

    @staticmethod
    def _require_current_presentation(
        connection: sqlite3.Connection,
        project_id: str,
        document_id: str,
        revision_id: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT d.kind, d.mime_type, d.parse_status, h.revision_id
            FROM documents d
            LEFT JOIN presentation_revision_heads h ON h.presentation_id = d.id
            WHERE d.id = ? AND d.project_id = ?
            """,
            (document_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        if row["kind"] != "presentation" or row["mime_type"] != (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ):
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "Slide purposes are available for imported PPTX presentations only.",
            )
        if row["parse_status"] != "ready":
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_NOT_READY",
                "The presentation is not ready for semantic labels.",
                retryable=True,
            )
        if row["revision_id"] != revision_id:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The current presentation revision changed. Refresh and try again.",
                retryable=True,
            )

    @staticmethod
    def _project_id(value: object) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _uuid_field(value: object, field: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 64:
            raise invalid_request(f"{field} must be a valid UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a valid UUID.", field=field) from error

    @staticmethod
    def _slide_number(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5_000:
            raise invalid_request("slide_number must be between 1 and 5000.", field="slide_number")
        return value
