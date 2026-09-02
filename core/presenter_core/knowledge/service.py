"""Management API for confirmed project knowledge."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager


class KnowledgeService:
    """Keep KnowledgeItems editable through explicit user-controlled flag APIs."""

    def __init__(
        self,
        storage: StorageManager,
        after_delete: Callable[[str], dict[str, Any]] | None = None,
        after_mapping_delete: Callable[[str], None] | None = None,
        before_delete: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> None:
        self._storage = storage
        self._after_delete = after_delete
        self._after_mapping_delete = after_mapping_delete
        self._before_delete = before_delete

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "usage"})
        project_id = self._project_id(params)
        usage = params.get("usage", "all")
        if usage not in {"all", "live", "rehearsal"}:
            raise invalid_request("usage must be all, live, or rehearsal.", field="usage")
        with self._storage.project_database(project_id) as connection:
            clauses = ["ki.project_id = ?"]
            parameters: list[Any] = [project_id]
            if usage == "live":
                clauses.append("ki.use_live = 1")
            elif usage == "rehearsal":
                clauses.append("ki.use_rehearsal = 1")
            rows = connection.execute(
                "SELECT * FROM knowledge_items AS ki WHERE "
                + " AND ".join(clauses)
                + " ORDER BY ki.updated_at DESC, ki.id DESC",
                parameters,
            ).fetchall()
            return {"knowledge_items": [self._knowledge_dict(connection, row) for row in rows]}

    def update_flags(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "knowledge_item_id",
                "preferred",
                "private",
                "use_live",
                "use_rehearsal",
            },
        )
        project_id = self._project_id(params)
        item_id = self._uuid_param(params, "knowledge_item_id")
        if not any(
            field in params for field in ("preferred", "private", "use_live", "use_rehearsal")
        ):
            raise invalid_request("At least one knowledge flag is required.")
        values: dict[str, bool] = {}
        for field in ("preferred", "private", "use_live", "use_rehearsal"):
            if field in params:
                value = params[field]
                if not isinstance(value, bool):
                    raise invalid_request(f"{field} must be a boolean.", field=field)
                values[field] = value
        with self._storage.project_database(project_id) as connection:
            self._knowledge_row(connection, project_id, item_id)
            assignments: list[str] = []
            parameters: list[Any] = []
            for field, value in values.items():
                assignments.append(f"{field} = ?")
                parameters.append(int(value))
            from presenter_core.project.service import utc_now

            assignments.append("updated_at = ?")
            parameters.extend([utc_now(), item_id, project_id])
            connection.execute(
                "UPDATE knowledge_items SET "
                + ", ".join(assignments)
                + " WHERE id = ? AND project_id = ?",
                parameters,
            )
            connection.commit()
            updated = self._knowledge_row(connection, project_id, item_id)
            return {"knowledge_item": self._knowledge_dict(connection, updated)}

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "knowledge_item_id"})
        project_id = self._project_id(params)
        item_id = self._uuid_param(params, "knowledge_item_id")
        with self._storage.project_database(project_id) as connection:
            self._knowledge_row(connection, project_id, item_id)
            # embedding_vectors is intentionally polymorphic, so this explicit
            # cleanup is the authoritative KnowledgeItem delete hook.
            if self._before_delete is not None:
                self._before_delete(connection, item_id)
            connection.execute(
                "DELETE FROM embedding_vectors "
                "WHERE entity_type = 'knowledge_item' AND entity_id = ?",
                (item_id,),
            )
            cursor = connection.execute(
                "DELETE FROM knowledge_items WHERE id = ? AND project_id = ?",
                (item_id, project_id),
            )
            connection.commit()
        if cursor.rowcount == 1 and self._after_mapping_delete is not None:
            self._after_mapping_delete(project_id)
        semantic_sync = (
            self._after_delete(project_id)
            if self._after_delete is not None
            else {"status": "not_requested"}
        )
        return {
            "project_id": project_id,
            "knowledge_item_id": item_id,
            "deleted": cursor.rowcount == 1,
            "semantic_sync": semantic_sync,
        }

    @staticmethod
    def _knowledge_row(
        connection: sqlite3.Connection, project_id: str, item_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ? AND project_id = ?",
            (item_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "KNOWLEDGE_NOT_FOUND", "The project knowledge item was not found."
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _knowledge_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        evidence_rows = connection.execute(
            "SELECT provenance_type, provenance_id FROM knowledge_evidence "
            "WHERE knowledge_item_id = ? ORDER BY provenance_type, provenance_id",
            (row["id"],),
        ).fetchall()
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "kind": row["kind"],
            "text": row["text"],
            "use_live": bool(row["use_live"]),
            "use_rehearsal": bool(row["use_rehearsal"]),
            "preferred": bool(row["preferred"]),
            "private": bool(row["private"]),
            "created_by": row["created_by"],
            "origin_session_id": row["origin_session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": [
                {"provenance_type": item["provenance_type"], "provenance_id": item["provenance_id"]}
                for item in evidence_rows
            ],
        }

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _uuid_param(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error
