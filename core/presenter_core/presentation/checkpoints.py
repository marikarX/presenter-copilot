"""Project-local labels on immutable revisions; no package or head mutation."""

from __future__ import annotations

import uuid
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager


class PresentationCheckpointService:
    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    @staticmethod
    def _id(value: Any) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise invalid_request("Provide a valid checkpoint identity.") from None

    def _scope(self, params: dict[str, Any]) -> tuple[str, str]:
        return normalize_project_id(self._id(params.get("project_id"))), self._id(
            params.get("document_id")
        )

    @staticmethod
    def _head(connection: Any, project: str, document: str) -> str:
        row = connection.execute(
            "SELECT h.revision_id FROM documents d JOIN presentation_revision_heads h "
            "ON h.presentation_id = d.id WHERE d.id = ? AND d.project_id = ? "
            "AND d.kind = 'presentation'",
            (document, project),
        ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Presentation was not found.")
        return str(row["revision_id"])

    @staticmethod
    def _token(connection: Any, document: str, revision: str) -> str | None:
        row = connection.execute(
            "SELECT record_token FROM presentation_revision_checkpoints "
            "WHERE presentation_id = ? AND revision_id = ?",
            (document, revision),
        ).fetchone()
        return str(row["record_token"]) if row else None

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id"})
        project, document = self._scope(params)
        with self._storage.project_database(project) as connection:
            head = self._head(connection, project, document)
            rows = connection.execute(
                "SELECT c.*, r.revision_number, r.sha256 FROM presentation_revision_checkpoints c "
                "JOIN presentation_revisions r ON r.id = c.revision_id "
                "WHERE c.presentation_id = ? AND c.name IS NOT NULL "
                "ORDER BY r.revision_number DESC",
                (document,),
            ).fetchall()
            return {
                "current_revision_id": head,
                "current_record_token": self._token(connection, document, head),
                "items": [dict(row) for row in rows],
            }

    def save(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "expected_token", "name", "note"},
        )
        project, document = self._scope(params)
        revision = self._id(params.get("expected_revision_id"))
        name, note = params.get("name"), params.get("note")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 80
            or any(ord(c) < 32 for c in name)
        ):
            raise invalid_request("Use a checkpoint name of 1-80 characters on one line.")
        if (
            not isinstance(note, str)
            or len(note) > 500
            or any(ord(c) < 32 and c not in "\n\r\t" for c in note)
        ):
            raise invalid_request("Use a checkpoint note of up to 500 characters.")
        self._write(project, document, revision, params, name.strip(), note, current=True)
        return self.list({"project_id": project, "document_id": document})

    def clear(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "revision_id", "expected_token"}
        )
        project, document = self._scope(params)
        revision = self._id(params.get("revision_id"))
        if params.get("expected_token") is None:
            raise invalid_request("Choose an existing checkpoint to remove.")
        self._write(project, document, revision, params, None, "", current=False)
        return self.list({"project_id": project, "document_id": document})

    def _write(
        self,
        project: str,
        document: str,
        revision: str,
        params: dict[str, Any],
        name: str | None,
        note: str,
        *,
        current: bool,
    ) -> None:
        if "expected_token" not in params:
            raise invalid_request("Provide the checkpoint record token.")
        expected = params["expected_token"]
        if expected is not None:
            expected = self._id(expected)
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            head = self._head(connection, project, document)
            if current and head != revision:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_CONFLICT",
                    "The current revision changed. Reload the presentation.",
                )
            if self._token(connection, document, revision) != expected:
                raise CoreDomainError(
                    "PRESENTATION_CHECKPOINT_CONFLICT",
                    "The checkpoint changed. Reload checkpoints before saving or removing it.",
                )
            original = connection.execute(
                "SELECT name FROM presentation_revision_checkpoints "
                "WHERE revision_id = ? AND presentation_id = ?",
                (revision, document),
            ).fetchone()
            if name is not None and (original is None or original["name"] is None):
                count = connection.execute(
                    "SELECT COUNT(*) FROM presentation_revision_checkpoints "
                    "WHERE presentation_id = ? AND name IS NOT NULL",
                    (document,),
                ).fetchone()[0]
                if count >= 100:
                    raise invalid_request("Remove a checkpoint before saving more than 100 labels.")
            connection.execute(
                "INSERT INTO presentation_revision_checkpoints VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(revision_id) DO UPDATE SET record_token=excluded.record_token, "
                "name=excluded.name, note=excluded.note, updated_at=excluded.updated_at",
                (revision, document, str(uuid.uuid4()), name, note, utc_now()),
            )
            connection.commit()
