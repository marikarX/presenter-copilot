"""Session lifecycle and deletion semantics."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import PRIVACY_MODES, STYLE_POLICIES, utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

SESSION_MODES = frozenset({"teach", "challenge", "run", "live_assist"})
SESSION_STATUSES = frozenset({"active", "completed", "aborted", "error"})
TEACH_STATES = frozenset(
    {"ready_for_prompt", "prompted", "awaiting_user", "candidate_ready", "completed"}
)


class SessionService:
    """Own project-local session rows; cascading child data stays in SQLite."""

    def __init__(
        self,
        storage: StorageManager,
        style_context: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._storage = storage
        self._style_context = style_context

    def start(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "mode",
                "style_policy",
                "privacy_mode",
                "provider_id",
                "current_slide_start",
            },
        )
        project_id = self._project_id(params)
        mode = params.get("mode", "teach")
        if not isinstance(mode, str) or mode not in SESSION_MODES:
            raise invalid_request("mode is not supported.", field="mode")
        if mode != "teach":
            raise CoreDomainError(
                "MODE_NOT_IMPLEMENTED",
                "Only Teach sessions are implemented in Milestone 3.",
                details={"mode": mode},
            )
        with self._storage.project_database(project_id) as connection:
            project = connection.execute(
                "SELECT * FROM project WHERE id = ?", (project_id,)
            ).fetchone()
            if project is None:
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            style_policy = params.get("style_policy")
            if style_policy is None:
                style_policy = (
                    self._style_context(project_id).get("policy")
                    if self._style_context is not None
                    else project["default_style_policy"]
                )
            privacy_mode = params.get("privacy_mode", project["privacy_mode"])
            self._validate_enum(style_policy, STYLE_POLICIES, "style_policy")
            self._validate_enum(privacy_mode, PRIVACY_MODES, "privacy_mode")
            provider_id = params.get("provider_id")
            if provider_id is not None and (
                not isinstance(provider_id, str) or not provider_id.strip()
            ):
                raise invalid_request("provider_id must be a string.", field="provider_id")
            current_slide_start = params.get("current_slide_start")
            if current_slide_start is not None and (
                isinstance(current_slide_start, bool)
                or not isinstance(current_slide_start, int)
                or current_slide_start < 1
            ):
                raise invalid_request(
                    "current_slide_start must be a positive integer.", field="current_slide_start"
                )
            session_id = str(uuid.uuid4())
            started_at = utc_now()
            connection.execute(
                """
                INSERT INTO sessions (
                    id, project_id, mode, started_at, ended_at, style_policy,
                    privacy_mode, provider_id, current_slide_start, status, teach_state
                ) VALUES (?, ?, 'teach', ?, NULL, ?, ?, ?, ?, 'active', 'ready_for_prompt')
                """,
                (
                    session_id,
                    project_id,
                    started_at,
                    style_policy,
                    privacy_mode,
                    provider_id.strip() if isinstance(provider_id, str) else None,
                    current_slide_start,
                ),
            )
            connection.commit()
            row = self._session_row(connection, project_id, session_id)
            return {"session": self._session_dict(connection, row)}

    def stop(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "status"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        requested_status = params.get("status", "completed")
        if requested_status not in {"completed", "aborted", "error"}:
            raise invalid_request("status is not a stoppable session status.", field="status")
        with self._storage.project_database(project_id) as connection:
            row = self._session_row(connection, project_id, session_id)
            if row["status"] == "active":
                pending = connection.execute(
                    "SELECT 1 FROM teach_candidates "
                    "WHERE session_id = ? AND status = 'pending' LIMIT 1",
                    (session_id,),
                ).fetchone()
                if pending is not None:
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_PENDING",
                        "Confirm or reject the current Teach candidate before ending the session.",
                    )
                if row["teach_state"] == "candidate_ready":
                    raise CoreDomainError(
                        "TEACH_ANSWER_PENDING",
                        "Save or discard the current Teach answer before ending the session.",
                    )
                ended_at = utc_now()
                connection.execute(
                    """
                    UPDATE sessions
                    SET ended_at = ?, status = ?, teach_state = 'completed'
                    WHERE id = ? AND project_id = ?
                    """,
                    (ended_at, requested_status, session_id, project_id),
                )
                connection.commit()
            row = self._session_row(connection, project_id, session_id)
            return {"session": self._session_dict(connection, row)}

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        with self._storage.project_database(project_id) as connection:
            row = self._session_row(connection, project_id, session_id)
            return {"session": self._session_dict(connection, row)}

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                "SELECT * FROM sessions WHERE project_id = ? ORDER BY started_at DESC, id DESC",
                (project_id,),
            ).fetchall()
            return {"sessions": [self._session_dict(connection, row) for row in rows]}

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        with self._storage.project_database(project_id) as connection:
            self._session_row(connection, project_id, session_id)
            # Confirmed knowledge points at a durable UserStatement snapshot,
            # but old session/utterance provenance is detached before cascade.
            connection.execute(
                """
                UPDATE user_statements
                SET origin_session_id = NULL, source_utterance_id = NULL
                WHERE project_id = ? AND (
                    origin_session_id = ? OR source_utterance_id IN (
                        SELECT id FROM utterances WHERE session_id = ?
                    )
                )
                """,
                (project_id, session_id, session_id),
            )
            connection.execute(
                """
                UPDATE knowledge_items
                SET origin_session_id = NULL
                WHERE project_id = ? AND origin_session_id = ?
                """,
                (project_id, session_id),
            )
            cursor = connection.execute(
                "DELETE FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            )
            connection.commit()
            # Approved global style evidence remains user-owned after a
            # session delete, but it must not retain a dangling session
            # provenance identifier.
            with self._storage.app_database() as app_connection:
                app_connection.execute(
                    """
                    UPDATE speaker_evidence
                    SET origin_session_id = NULL
                    WHERE origin_project_id = ? AND origin_session_id = ?
                    """,
                    (project_id, session_id),
                )
                app_connection.commit()
            return {
                "project_id": project_id,
                "session_id": session_id,
                "deleted": cursor.rowcount == 1,
            }

    @staticmethod
    def _session_row(
        connection: sqlite3.Connection, project_id: str, session_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _session_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        counts = {
            "utterances": "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
            "pending_candidates": "SELECT COUNT(*) FROM teach_candidates "
            "WHERE session_id = ? AND status = 'pending'",
            "provider_runs": "SELECT COUNT(*) FROM provider_runs WHERE session_id = ?",
        }
        result: dict[str, Any] = {
            "id": row["id"],
            "project_id": row["project_id"],
            "mode": row["mode"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "style_policy": row["style_policy"],
            "privacy_mode": row["privacy_mode"],
            "provider_id": row["provider_id"],
            "current_slide_start": row["current_slide_start"],
            "status": row["status"],
            "teach_state": row["teach_state"],
        }
        for key, sql in counts.items():
            value = connection.execute(sql, (row["id"],)).fetchone()
            result[key] = int(value[0]) if value else 0
        return result

    @staticmethod
    def _validate_enum(value: Any, allowed: frozenset[str], field: str) -> None:
        if not isinstance(value, str) or value not in allowed:
            raise invalid_request(f"{field} is not supported.", field=field)

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
