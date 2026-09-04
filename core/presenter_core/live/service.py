"""Bounded push-to-assist orchestration for Live Assist sessions.

The live path deliberately keeps speech, retrieval, provider routing, and cue
storage inside the core process. Electron receives only bounded cue events and
never receives audio, provider credentials, or a generic HUD-to-core channel.
"""

from __future__ import annotations

import builtins
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, cast

from presenter_core.asr.service import ASRService
from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import (
    MAX_CUE_EVIDENCE,
    MAX_CUE_LINE_CHARS,
    MAX_CUE_LINES,
    MAX_CUE_OFFSET,
    MAX_CUE_SOURCE_EXCERPT_CHARS,
    MAX_CUE_TEXT_CHARS,
    MAX_EXPLICIT_QUESTION_CHARS,
    MAX_LIVE_CUES_PER_SESSION,
    MAX_LIVE_QUERY_CHARS,
    MAX_LIVE_QUERY_UTTERANCES,
    MAX_LIVE_QUESTION_CHARS,
    MAX_LIVE_RECENT_WINDOW_MS,
    MAX_LIVE_RETRIEVAL_QUERY_CHARS,
)
from presenter_core.presentation.service import SlideStateService
from presenter_core.project.service import utc_now
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import (
    LIVE_CUE_TYPES,
    ProviderError,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.retrieval.conflicts import extract_fact_values
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.session.service import SessionService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

EventSink = Callable[[str, dict[str, Any]], None]

_FACT_QUERY_RE = re.compile(
    r"\b(?:how much|how many|rto|sla|cost|price|percent|percentage|target|number|"
    r"duration|time|availability|latency|budget)\b|[$€£%]|\d",
    re.IGNORECASE,
)


class _AssistCancelled(Exception):
    """Internal marker for a logically cancelled background request."""


@dataclass
class _AssistState:
    assist_id: str
    project_id: str
    session_id: str
    generation: int
    question: str
    question_origin: str
    trigger: str
    cancelled: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None


class CueService:
    """Own the v7 cue rows and bounded provenance projections."""

    def __init__(self, storage: StorageManager, sessions: SessionService) -> None:
        self._storage = storage
        self._sessions = sessions

    def save(
        self,
        *,
        project_id: str,
        session_id: str,
        cue_id: str,
        assist_id: str,
        cue_type: str,
        lines: list[str] | tuple[str, ...],
        state: str,
        route: str,
        evidence: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        provider_run_id: str | None = None,
    ) -> dict[str, Any]:
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        cue_id = self._uuid(cue_id, "cue_id")
        assist_id = self._uuid(assist_id, "assist_id")
        normalized_lines = self._lines(lines)
        if cue_type not in LIVE_CUE_TYPES:
            raise CoreDomainError("ASSIST_OUTPUT_INVALID", "The cue type is not supported.")
        if state not in {"partial", "final"}:
            raise CoreDomainError("ASSIST_OUTPUT_INVALID", "The cue state is not supported.")
        if route not in {"retrieval_only", "local_reasoning", "remote_reasoning"}:
            raise CoreDomainError("ASSIST_OUTPUT_INVALID", "The cue route is not supported.")
        provider_run_id = (
            self._uuid(provider_run_id, "provider_run_id") if provider_run_id is not None else None
        )
        normalized_evidence = self._evidence_rows(evidence)
        if not normalized_evidence:
            raise CoreDomainError(
                "ASSIST_CONTEXT_STALE", "No current source evidence is available for the cue."
            )

        with self._storage.project_database(project_id) as connection:
            session = connection.execute(
                "SELECT mode, status FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
            if session is None or session["mode"] != "live_assist":
                raise CoreDomainError(
                    "CUE_SESSION_INVALID", "The cue session is not a Live Assist session."
                )
            if state == "partial" and session["status"] != "active":
                raise CoreDomainError(
                    "ASSIST_CANCELLED", "The Live Assist session is no longer active."
                )
            normalized_evidence = self._current_evidence(
                connection, normalized_evidence, project_id
            )
            if not normalized_evidence or not any(
                item["available"] for item in normalized_evidence
            ):
                raise CoreDomainError(
                    "ASSIST_CONTEXT_STALE",
                    "The cue evidence is no longer live-eligible.",
                )
            existing = connection.execute(
                "SELECT id, created_at FROM cues WHERE session_id = ? AND assist_id = ?",
                (session_id, assist_id),
            ).fetchone()
            if existing is None:
                count = connection.execute(
                    "SELECT COUNT(*) FROM cues WHERE session_id = ?", (session_id,)
                ).fetchone()
                if count is not None and int(count[0]) >= MAX_LIVE_CUES_PER_SESSION:
                    raise CoreDomainError(
                        "CUE_LIMIT_REACHED", "The Live Assist cue history reached its safety bound."
                    )
                cue_id_to_write = cue_id
                created_at = utc_now()
                connection.execute(
                    """
                    INSERT INTO cues (
                        id, session_id, assist_id, cue_type, text, state, route,
                        provider_run_id, created_at, displayed_at, dismissed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        cue_id_to_write,
                        session_id,
                        assist_id,
                        cue_type,
                        "\n".join(normalized_lines),
                        state,
                        route,
                        provider_run_id,
                        created_at,
                    ),
                )
            else:
                cue_id_to_write = str(existing["id"])
                connection.execute(
                    """
                    UPDATE cues
                    SET cue_type = ?, text = ?, state = ?, route = ?, provider_run_id = ?,
                        dismissed_at = NULL
                    WHERE id = ? AND session_id = ?
                    """,
                    (
                        cue_type,
                        "\n".join(normalized_lines),
                        state,
                        route,
                        provider_run_id,
                        cue_id_to_write,
                        session_id,
                    ),
                )
                connection.execute("DELETE FROM cue_evidence WHERE cue_id = ?", (cue_id_to_write,))
            connection.executemany(
                """
                INSERT INTO cue_evidence (
                    cue_id, evidence_id, source_type, source_id, source_unit_id,
                    knowledge_item_id, label_snapshot, rank, available
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        cue_id_to_write,
                        item["evidence_id"],
                        item["source_type"],
                        item["source_id"],
                        item.get("source_unit_id"),
                        item.get("knowledge_item_id"),
                        item["label_snapshot"],
                        item["rank"],
                        item["available"],
                    )
                    for item in normalized_evidence
                ],
            )
            connection.commit()
            return self._cue_dict(connection, cue_id_to_write, project_id)

    def discard_partial(self, project_id: str, session_id: str, assist_id: str) -> None:
        """Remove only an incomplete cue left by cancelled background work."""
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        assist_id = self._uuid(assist_id, "assist_id")
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                "DELETE FROM cues WHERE session_id = ? AND assist_id = ? AND state = 'partial'",
                (session_id, assist_id),
            )
            connection.commit()

    def mark_displayed(self, project_id: str, session_id: str, cue_id: str) -> None:
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        cue_id = self._uuid(cue_id, "cue_id")
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                "UPDATE cues SET displayed_at = COALESCE(displayed_at, ?) "
                "WHERE id = ? AND session_id = ?",
                (utc_now(), cue_id, session_id),
            )
            connection.commit()

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "session_id", "limit", "offset", "include_dismissed"}
        )
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._require_live_session(project_id, session_id, active=False)
        limit = self._bounded_limit(params.get("limit", 20))
        offset = self._bounded_offset(params.get("offset", 0))
        include_dismissed = params.get("include_dismissed", False)
        if not isinstance(include_dismissed, bool):
            raise invalid_request("include_dismissed must be a boolean.", field="include_dismissed")
        with self._storage.project_database(project_id) as connection:
            where = "session_id = ?"
            filter_values: list[Any] = [session_id]
            if not include_dismissed:
                where += " AND dismissed_at IS NULL"
            total_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM cues WHERE {where}", filter_values
            ).fetchone()
            total = int(total_row["count"]) if total_row is not None else 0
            rows = connection.execute(
                f"SELECT id FROM cues WHERE {where} "
                "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*filter_values, limit, offset],
            ).fetchall()
            return {
                "project_id": project_id,
                "session_id": session_id,
                "cues": [self._cue_dict(connection, str(row["id"]), project_id) for row in rows],
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": offset + len(rows) < total,
            }

    def dismiss(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "cue_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        cue_id = self._uuid(params.get("cue_id"), "cue_id")
        self._require_live_session(project_id, session_id, active=False)
        with self._storage.project_database(project_id) as connection:
            cursor = connection.execute(
                "UPDATE cues SET dismissed_at = COALESCE(dismissed_at, ?) "
                "WHERE id = ? AND session_id = ?",
                (utc_now(), cue_id, session_id),
            )
            if cursor.rowcount != 1:
                raise CoreDomainError("CUE_NOT_FOUND", "The cue was not found in this session.")
            connection.commit()
            return {"cue": self._cue_dict(connection, cue_id, project_id), "dismissed": True}

    def expand_sources(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "cue_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        cue_id = self._uuid(params.get("cue_id"), "cue_id")
        self._require_live_session(project_id, session_id, active=False)
        with self._storage.project_database(project_id) as connection:
            cue = connection.execute(
                "SELECT id FROM cues WHERE id = ? AND session_id = ?",
                (cue_id, session_id),
            ).fetchone()
            if cue is None:
                raise CoreDomainError("CUE_NOT_FOUND", "The cue was not found in this session.")
            rows = connection.execute(
                "SELECT * FROM cue_evidence WHERE cue_id = ? ORDER BY rank, evidence_id LIMIT ?",
                (cue_id, MAX_CUE_EVIDENCE),
            ).fetchall()
            sources = [self._expand_evidence(connection, row, project_id) for row in rows]
            # Source deletion/re-indexing is intentionally represented as
            # unavailable evidence rather than silently rewriting history.
            for source in sources:
                connection.execute(
                    "UPDATE cue_evidence SET available = ? WHERE cue_id = ? AND evidence_id = ?",
                    (int(bool(source["available"])), cue_id, source["evidence_id"]),
                )
            connection.commit()
            return {
                "project_id": project_id,
                "session_id": session_id,
                "cue": self._cue_dict(connection, cue_id, project_id),
                "sources": sources,
            }

    def before_source_delete(self, connection: sqlite3.Connection, document_id: str) -> None:
        connection.execute(
            """
            UPDATE cue_evidence
            SET available = 0
            WHERE source_id = ? OR source_unit_id IN (
                SELECT id FROM source_units WHERE document_id = ?
            )
            """,
            (document_id, document_id),
        )

    def after_source_reindex(
        self, connection: sqlite3.Connection, document_id: str, previous_unit_ids: set[str]
    ) -> None:
        if previous_unit_ids:
            placeholders = ", ".join("?" for _ in previous_unit_ids)
            connection.execute(
                f"UPDATE cue_evidence SET available = 0 WHERE source_unit_id IN ({placeholders})",
                tuple(sorted(previous_unit_ids)),
            )
        connection.execute(
            "UPDATE cue_evidence SET available = 0 WHERE source_id = ? "
            "AND source_unit_id IS NOT NULL AND source_unit_id NOT IN "
            "(SELECT id FROM source_units WHERE document_id = ?)",
            (document_id, document_id),
        )

    def before_knowledge_delete(
        self, connection: sqlite3.Connection, knowledge_item_id: str
    ) -> None:
        connection.execute(
            "UPDATE cue_evidence SET available = 0 WHERE knowledge_item_id = ? OR evidence_id = ?",
            (knowledge_item_id, knowledge_item_id),
        )

    def current_evidence(
        self, project_id: str, evidence: builtins.list[dict[str, Any]]
    ) -> builtins.list[dict[str, Any]]:
        """Re-read current source/knowledge availability before a cue claims it."""
        project_id = self._project_id(project_id)
        normalized = self._evidence_rows(evidence)
        with self._storage.project_database(project_id) as connection:
            return self._current_evidence(connection, normalized, project_id)

    def _cue_dict(
        self, connection: sqlite3.Connection, cue_id: str, project_id: str
    ) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM cues WHERE id = ?", (cue_id,)).fetchone()
        if row is None:
            raise CoreDomainError("CUE_NOT_FOUND", "The cue was not found.")
        evidence = [
            {
                "evidence_id": str(item["evidence_id"]),
                "source_type": str(item["source_type"]),
                "source_id": str(item["source_id"]),
                "source_unit_id": item["source_unit_id"],
                "knowledge_item_id": item["knowledge_item_id"],
                "label": str(item["label_snapshot"]),
                "rank": int(item["rank"]),
                "available": bool(item["available"]),
            }
            for item in connection.execute(
                "SELECT * FROM cue_evidence WHERE cue_id = ? ORDER BY rank, evidence_id LIMIT ?",
                (cue_id, MAX_CUE_EVIDENCE),
            ).fetchall()
        ]
        text = str(row["text"])
        return {
            "id": str(row["id"]),
            "project_id": project_id,
            "session_id": str(row["session_id"]),
            "assist_id": str(row["assist_id"]),
            "cue_type": str(row["cue_type"]),
            "text": text[:MAX_CUE_TEXT_CHARS],
            "lines": text.splitlines()[:MAX_CUE_LINES],
            "state": str(row["state"]),
            "route": str(row["route"]),
            "provider_run_id": row["provider_run_id"],
            "created_at": str(row["created_at"]),
            "displayed_at": row["displayed_at"],
            "dismissed_at": row["dismissed_at"],
            "evidence": evidence,
        }

    def _expand_evidence(
        self, connection: sqlite3.Connection, row: sqlite3.Row, project_id: str
    ) -> dict[str, Any]:
        source_type = str(row["source_type"])
        source_id = str(row["source_id"])
        source_unit_id = row["source_unit_id"]
        knowledge_item_id = row["knowledge_item_id"]
        label = str(row["label_snapshot"])
        excerpt: str | None = None
        # Re-index/delete hooks deliberately persist unavailable=0. That
        # historical invalidation is monotonic; only rows still marked
        # available may be revalidated against current source state.
        available = bool(row["available"])
        source_name: str | None = None
        pointer: dict[str, Any] = {
            "source_type": source_type,
            "source_id": source_id,
            "source_unit_id": source_unit_id,
            "knowledge_item_id": knowledge_item_id,
        }
        if available and source_type == "user_statement":
            item = connection.execute(
                "SELECT text, private, use_live FROM knowledge_items "
                "WHERE id = ? AND project_id = ?",
                (knowledge_item_id or source_id, project_id),
            ).fetchone()
            if item is not None:
                excerpt = " ".join(str(item["text"]).split())[:MAX_CUE_SOURCE_EXCERPT_CHARS]
                available = bool(item["use_live"])
        elif available:
            unit = (
                connection.execute(
                    """
                SELECT su.text, d.original_name, d.parse_status
                FROM source_units AS su
                JOIN documents AS d ON d.id = su.document_id
                WHERE su.id = ? AND d.project_id = ?
                """,
                    (source_unit_id, project_id),
                ).fetchone()
                if source_unit_id
                else None
            )
            if unit is not None and str(unit["parse_status"]) == "ready":
                source_name = str(unit["original_name"])
                excerpt = " ".join(str(unit["text"]).split())[:MAX_CUE_SOURCE_EXCERPT_CHARS]
                available = True
            elif source_unit_id is None:
                document = connection.execute(
                    "SELECT original_name, parse_status FROM documents "
                    "WHERE id = ? AND project_id = ?",
                    (source_id, project_id),
                ).fetchone()
                if document is not None:
                    source_name = str(document["original_name"])
                    available = str(document["parse_status"]) == "ready"
        return {
            "evidence_id": str(row["evidence_id"]),
            "label": label,
            "source_name": source_name,
            "pointer": pointer,
            "excerpt": excerpt,
            "available": available,
            "rank": int(row["rank"]),
        }

    @staticmethod
    def _current_evidence(
        connection: sqlite3.Connection,
        evidence: builtins.list[dict[str, Any]],
        project_id: str,
    ) -> builtins.list[dict[str, Any]]:
        current: builtins.list[dict[str, Any]] = []
        for item in evidence:
            available = bool(item.get("available", True))
            source_unit_id = item.get("source_unit_id")
            if available and item["source_type"] == "user_statement":
                knowledge = connection.execute(
                    "SELECT use_live FROM knowledge_items WHERE id = ? AND project_id = ?",
                    (item.get("knowledge_item_id"), project_id),
                ).fetchone()
                available = knowledge is not None and bool(knowledge["use_live"])
            elif available:
                unit = (
                    connection.execute(
                        """
                    SELECT 1
                    FROM source_units AS su
                    JOIN documents AS d ON d.id = su.document_id
                    WHERE su.id = ? AND d.project_id = ? AND d.parse_status = 'ready'
                    """,
                        (source_unit_id, project_id),
                    ).fetchone()
                    if source_unit_id
                    else None
                )
                if source_unit_id is not None:
                    available = unit is not None
                else:
                    document = connection.execute(
                        "SELECT 1 FROM documents WHERE id = ? AND project_id = ? "
                        "AND parse_status = 'ready'",
                        (item["source_id"], project_id),
                    ).fetchone()
                    available = document is not None
            current.append({**item, "available": int(available)})
        return current

    def _require_live_session(self, project_id: str, session_id: str, *, active: bool) -> None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT mode, status FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row is None or row["mode"] != "live_assist":
            raise CoreDomainError(
                "CUE_SESSION_INVALID", "The cue session is not a Live Assist session."
            )
        if active and row["status"] != "active":
            raise CoreDomainError(
                "ASSIST_SESSION_INVALID", "The Live Assist session is not active."
            )

    @staticmethod
    def _evidence_rows(
        evidence: builtins.list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> builtins.list[dict[str, Any]]:
        rows: builtins.list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(evidence[:MAX_CUE_EVIDENCE]):
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("evidence_id")
            source_type = item.get("source_type")
            source_id = item.get("source_id")
            label = item.get("label") or item.get("label_snapshot")
            if (
                not isinstance(evidence_id, str)
                or not evidence_id
                or evidence_id in seen
                or not isinstance(source_type, str)
                or source_type not in {"document", "transcript", "user_statement"}
                or not isinstance(source_id, str)
                or not source_id
                or not isinstance(label, str)
                or not label.strip()
                or len(label) > 300
            ):
                continue
            seen.add(evidence_id)
            normalized: dict[str, Any] = {
                "evidence_id": evidence_id[:120],
                "source_type": source_type[:80],
                "source_id": source_id[:120],
                "source_unit_id": item.get("source_unit_id")
                if isinstance(item.get("source_unit_id"), str)
                else None,
                "knowledge_item_id": item.get("knowledge_item_id")
                if isinstance(item.get("knowledge_item_id"), str)
                else None,
                "label_snapshot": label[:300],
                "rank": max(0, int(item.get("rank", index + 1)))
                if isinstance(item.get("rank", index + 1), int)
                and not isinstance(item.get("rank", index + 1), bool)
                else index + 1,
                "available": int(bool(item.get("available", True))),
            }
            # These fields are intentionally transient: they let the live
            # assist path preserve canonical grounding and privacy flags while
            # CueService persists only the bounded provenance columns above.
            if isinstance(item.get("text"), str):
                normalized["text"] = item["text"][:MAX_CUE_SOURCE_EXCERPT_CHARS]
            for key in ("fact_safe", "private", "preferred", "use_live", "use_rehearsal"):
                if isinstance(item.get(key), bool):
                    normalized[key] = item[key]
            rows.append(normalized)
        return rows

    @staticmethod
    def _lines(value: builtins.list[str] | tuple[str, ...]) -> builtins.list[str]:
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_CUE_LINES:
            raise CoreDomainError("ASSIST_OUTPUT_INVALID", "A cue must contain one to three lines.")
        result: list[str] = []
        for line in value:
            if (
                not isinstance(line, str)
                or not line.strip()
                or len(line.strip()) > MAX_CUE_LINE_CHARS
                or "\n" in line
                or "\r" in line
            ):
                raise CoreDomainError("ASSIST_OUTPUT_INVALID", "A cue line exceeds its safe bound.")
            result.append(line.strip())
        if len("\n".join(result)) > MAX_CUE_TEXT_CHARS:
            raise CoreDomainError("ASSIST_OUTPUT_INVALID", "The cue exceeds its safe text bound.")
        return result

    @staticmethod
    def _bounded_limit(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
            raise invalid_request("limit must be an integer between 1 and 50.", field="limit")
        return int(value)

    @staticmethod
    def _bounded_offset(value: Any) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= MAX_CUE_OFFSET
        ):
            raise invalid_request(
                f"offset must be an integer between 0 and {MAX_CUE_OFFSET}.", field="offset"
            )
        return int(value)

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _session_id(value: Any) -> str:
        return CueService._uuid(value, "session_id")

    @staticmethod
    def _uuid(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error


class AssistService:
    """Run one bounded asynchronous push-to-assist operation at a time per session."""

    def __init__(
        self,
        storage: StorageManager,
        sessions: SessionService,
        asr: ASRService,
        presentation: SlideStateService,
        retrieval: HybridRetrievalService,
        providers: ProviderService,
        context_builder: ProviderContextBuilder,
        *,
        event_sink: EventSink | None = None,
        clock: Callable[[], float] = monotonic,
        provider_execution: ProviderExecutionService | None = None,
    ) -> None:
        self._storage = storage
        self._sessions = sessions
        self._asr = asr
        self._presentation = presentation
        self._retrieval = retrieval
        self._providers = providers
        self._context_builder = context_builder
        self._event_sink = event_sink
        self._clock = clock
        self._router = ReasoningRouter()
        self._provider_execution = provider_execution or ProviderExecutionService(
            storage,
            providers,
            event_sink=event_sink,
        )
        self._cue = CueService(storage, sessions)
        self._lock = threading.RLock()
        self._states: dict[str, _AssistState] = {}
        self._generations: dict[tuple[str, str], int] = {}
        self._closed = False

    @property
    def cues(self) -> CueService:
        return self._cue

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink

    def request(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "question", "text", "trigger"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._sessions.validate_active_live_assist(project_id, session_id)
        if "question" in params and "text" in params:
            raise invalid_request(
                "Provide question once; text is only a compatibility alias.", field="question"
            )
        explicit = params.get("question", params.get("text"))
        trigger = params.get("trigger", "hotkey")
        if trigger not in {"hotkey", "button", "typed"}:
            raise invalid_request("trigger must be hotkey, button, or typed.", field="trigger")
        if explicit is not None and (
            not isinstance(explicit, str)
            or not explicit.strip()
            or len(explicit.strip()) > MAX_EXPLICIT_QUESTION_CHARS
        ):
            raise invalid_request(
                "question must be a non-empty bounded question.", field="question"
            )
        question: str | None = None
        if isinstance(explicit, str):
            question = self._clean_text(explicit)
            origin = "typed"
        else:
            question, origin = self._assemble_live_question(project_id, session_id)
        if not question:
            raise CoreDomainError(
                "ASSIST_CONTEXT_INSUFFICIENT",
                "Push-to-assist needs a current audience question or typed prompt.",
            )
        assist_id = str(uuid.uuid4())
        key = (project_id, session_id)
        with self._lock:
            if self._closed:
                raise CoreDomainError("ASSIST_SESSION_INVALID", "Live Assist is shut down.")
            generation = self._generations.get(key, 0) + 1
            self._generations[key] = generation
            for state in self._states.values():
                if (state.project_id, state.session_id) == key:
                    state.cancelled.set()
                    self._cue.discard_partial(state.project_id, state.session_id, state.assist_id)
            state = _AssistState(
                assist_id=assist_id,
                project_id=project_id,
                session_id=session_id,
                generation=generation,
                question=question,
                question_origin=origin,
                trigger=str(trigger),
            )
            worker = threading.Thread(
                target=self._run,
                args=(state,),
                name="presenter-copilot-live-assist",
                daemon=True,
            )
            state.worker = worker
            self._states[assist_id] = state
            current_slide = self._presentation.current_slide(project_id, session_id)
        self._emit(
            "assist.started",
            {
                "assist_id": assist_id,
                "session_id": session_id,
                "question_origin": origin,
                "trigger": str(trigger),
                "question_chars": len(question),
                "started_at": utc_now(),
                "current_slide": current_slide,
            },
        )
        worker.start()
        return {
            "assist_id": assist_id,
            "project_id": project_id,
            "session_id": session_id,
            "status": "started",
            "question_origin": origin,
        }

    def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "assist_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        assist_id = CueService._uuid(params.get("assist_id"), "assist_id")
        with self._lock:
            state = self._states.get(assist_id)
            if state is None or (state.project_id, state.session_id) != (project_id, session_id):
                raise CoreDomainError("CUE_NOT_FOUND", "The assist request was not found.")
            state.cancelled.set()
            self._cue.discard_partial(state.project_id, state.session_id, state.assist_id)
        self._emit(
            "cue.error",
            {
                "assist_id": assist_id,
                "session_id": session_id,
                "code": "ASSIST_CANCELLED",
                "message": "The Live Assist request was cancelled.",
                "retryable": True,
            },
        )
        return {"assist_id": assist_id, "cancelled": True}

    def stop_session(
        self, project_id: str, session_id: str, *, status: str = "aborted"
    ) -> dict[str, Any]:
        """Logically cancel assist work, release ASR/presentation, then stop the row."""
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        if status not in {"completed", "aborted", "error"}:
            raise invalid_request("status is not a stoppable session status.", field="status")
        with self._lock:
            for state in self._states.values():
                if (state.project_id, state.session_id) == (project_id, session_id):
                    state.cancelled.set()
                    self._cue.discard_partial(state.project_id, state.session_id, state.assist_id)
        try:
            self._asr.stop({"project_id": project_id, "session_id": session_id})
        except CoreDomainError as error:
            if error.code not in {"ASR_SESSION_INVALID"}:
                raise CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The active Live Assist microphone could not be released; retry is safe.",
                    retryable=True,
                    details={"cause_code": error.code},
                ) from error
        self._presentation.stop_run(project_id, session_id)
        return self._sessions.stop(
            {"project_id": project_id, "session_id": session_id, "status": status}
        )

    def stop_active_sessions(self, *, status: str = "aborted") -> None:
        if status not in {"completed", "aborted", "error"}:
            raise ValueError("status must be a stoppable session status")
        targets: set[tuple[str, str]] = set()
        for app_row in self._storage.list_app_rows():
            project_id = str(app_row["id"])
            with self._storage.project_database(project_id) as connection:
                rows = connection.execute(
                    "SELECT id FROM sessions WHERE mode = 'live_assist' AND status = 'active' "
                    "ORDER BY started_at, id LIMIT ?",
                    (MAX_LIVE_CUES_PER_SESSION,),
                ).fetchall()
            for row in rows:
                targets.add((project_id, str(row["id"])))
        owner = self._asr.active_owner()
        if owner is not None:
            with self._storage.project_database(owner[0]) as connection:
                row = connection.execute(
                    "SELECT mode FROM sessions WHERE id = ? AND project_id = ?",
                    (owner[1], owner[0]),
                ).fetchone()
            if row is not None and row["mode"] == "live_assist":
                targets.add(owner)
        first_error: CoreDomainError | None = None
        for project_id, session_id in sorted(targets):
            try:
                self.stop_session(project_id, session_id, status=status)
            except CoreDomainError as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    def stop_project_sessions(self, params: dict[str, Any]) -> None:
        """Release only one project's Live Assist resources before deletion."""
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params.get("project_id"))
        try:
            self._storage.app_row(project_id)
        except CoreDomainError as error:
            if error.code == "PROJECT_NOT_FOUND":
                return
            raise
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                "SELECT id FROM sessions WHERE mode = 'live_assist' AND status = 'active' "
                "ORDER BY started_at, id LIMIT ?",
                (MAX_LIVE_CUES_PER_SESSION,),
            ).fetchall()
        stopped = {str(row["id"]) for row in rows}
        for row in rows:
            self.stop_session(project_id, str(row["id"]), status="aborted")
        owner = self._asr.active_owner()
        if owner is not None and owner[0] == project_id and owner[1] not in stopped:
            with self._storage.project_database(project_id) as connection:
                row = connection.execute(
                    "SELECT mode FROM sessions WHERE id = ? AND project_id = ?",
                    (owner[1], project_id),
                ).fetchone()
            if row is not None and row["mode"] == "live_assist":
                self.stop_session(project_id, owner[1], status="aborted")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for state in self._states.values():
                state.cancelled.set()
                self._cue.discard_partial(state.project_id, state.session_id, state.assist_id)

    def _run(self, state: _AssistState) -> None:
        started = self._clock()
        cue_id = str(uuid.uuid4())
        provider_run_id: str | None = None
        try:
            self._ensure_current(state)
            current_slide = self._presentation.current_slide(state.project_id, state.session_id)
            retrieval_started = self._clock()
            retrieval_result = self._retrieval.query(
                {
                    "project_id": state.project_id,
                    "query": state.question[:MAX_LIVE_RETRIEVAL_QUERY_CHARS],
                    "limit": MAX_CUE_EVIDENCE,
                    "usage": "live",
                    "allow_private": True,
                    **(
                        {"current_slide": current_slide, "slide_window": 1}
                        if current_slide is not None
                        else {}
                    ),
                }
            )
            hits = [item for item in retrieval_result.get("hits", []) if isinstance(item, dict)]
            evidence = [
                item["evidence"]
                for item in hits
                if isinstance(item.get("evidence"), dict)
                and isinstance(item["evidence"].get("evidence_id"), str)
            ]
            evidence = [
                item
                for item in self._cue.current_evidence(state.project_id, evidence)
                if item["available"]
            ]
            retrieval_ms = max(0, int((self._clock() - retrieval_started) * 1000))
            conflicts = [
                item for item in retrieval_result.get("conflicts", []) if isinstance(item, dict)
            ][:3]
            self._ensure_current(state)
            self._emit(
                "assist.retrieval_ready",
                {
                    "assist_id": state.assist_id,
                    "session_id": state.session_id,
                    "hit_count": len(evidence),
                    "evidence_count": len(evidence),
                    "conflict_count": len(conflicts),
                    "retrieval_mode": "live",
                    "latency_ms": max(0, int((self._clock() - started) * 1000)),
                    "retrieval_latency_ms": retrieval_ms,
                    "current_slide": current_slide,
                },
            )
            if not evidence:
                raise CoreDomainError(
                    "ASSIST_CONTEXT_INSUFFICIENT",
                    "No live-eligible project evidence matched the question.",
                )
            partial = self._save_partial(state, cue_id, evidence, started)
            self._emit(
                "cue.partial",
                self._cue_event(partial, state, started, retrieval_ms, degraded=False),
            )

            project = self._project_row(state.project_id)
            provider, health = self._providers.current_provider_and_health()
            decision = self._router.decide(
                task_type="live_cue",
                privacy_mode=str(project["privacy_mode"]),
                remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
                provider=provider,
                provider_health=health,
            )
            fast = self._retrieval_fast_path(
                state.question, evidence, conflicts, decision.route, started, cue_id, state
            )
            if fast is not None:
                self._emit(
                    "cue.ready",
                    self._cue_event(fast, state, started, retrieval_ms, degraded=False),
                )
                return
            if decision.route == ReasoningRoute.RETRIEVAL_ONLY:
                fallback = self._retrieval_pointer_cue(
                    state, cue_id, evidence, conflicts, started, reason=decision.reason
                )
                self._emit(
                    "cue.ready",
                    self._cue_event(fallback, state, started, retrieval_ms, degraded=True),
                )
                return
            if provider is None:
                raise CoreDomainError(
                    "ASSIST_PROVIDER_UNAVAILABLE",
                    "No reasoning provider is available for Live Assist.",
                    retryable=True,
                )

            reasoning_started = self._clock()
            safe_for_provider = evidence[:MAX_CUE_EVIDENCE]
            request, manifest = self._context_builder.build(
                project_id=state.project_id,
                task_type="live_cue",
                question=state.question,
                user_input=None,
                privacy_mode=str(project["privacy_mode"]),
                style_policy=str(project["default_style_policy"]),
                current_slide=current_slide,
                provider_id=provider.id,
                allow_private=True,
                include_private_in_provider=provider.locality == "local",
                retrieval_usage="live",
                additional_grounding_evidence=safe_for_provider,
            )
            self._ensure_current(state)

            def before_provider(run_id: str, actual_manifest: dict[str, Any]) -> None:
                self._emit(
                    "assist.reasoning_started",
                    {
                        "assist_id": state.assist_id,
                        "session_id": state.session_id,
                        "provider_id": provider.id,
                        "route": decision.route.value,
                        "latency_ms": max(0, int((self._clock() - started) * 1000)),
                        "provider_run_id": run_id,
                        "context_manifest": self._bounded_manifest(actual_manifest),
                    },
                )

            execution = self._provider_execution.execute(
                project_id=state.project_id,
                session_id=state.session_id,
                provider=provider,
                request=request,
                cancellation_check=lambda: not self._is_current(state),
                output_validator=lambda output: self._validate_live_output_for_execution(
                    output, request, state.project_id
                ),
                before_provider=before_provider,
            )
            provider_run_id = execution.provider_run_id
            result = execution.result
            self._ensure_current(state)
            output = result.output
            output_ids = set(str(item) for item in output.get("evidence_ids", []))
            supplied_ids = {
                str(item.get("evidence_id"))
                for item in request.grounding_evidence
                if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
            }
            if not output_ids or not output_ids.issubset(supplied_ids):
                raise ProviderError(
                    "ASSIST_OUTPUT_INVALID",
                    "The Live Assist provider cited evidence outside its bounded context.",
                )
            selected = [
                item
                for item in request.grounding_evidence
                if isinstance(item, dict) and str(item.get("evidence_id")) in output_ids
            ]
            selected = [
                item
                for item in self._cue.current_evidence(state.project_id, selected)
                if item["available"]
            ]
            if not selected:
                raise ProviderError(
                    "ASSIST_OUTPUT_INVALID",
                    "The Live Assist provider did not cite supplied evidence.",
                )
            if self._has_unsupported_fact(output["lines"], selected):
                raise ProviderError(
                    "ASSIST_OUTPUT_INVALID",
                    "The Live Assist provider introduced an unsupported exact fact.",
                )
            final = self._cue.save(
                project_id=state.project_id,
                session_id=state.session_id,
                cue_id=cue_id,
                assist_id=state.assist_id,
                cue_type=str(output["cue_type"]),
                lines=self._with_source_pointer(list(output["lines"]), selected),
                state="final",
                route=decision.route.value,
                evidence=selected,
                provider_run_id=provider_run_id,
            )
            self._emit(
                "cue.ready",
                {
                    **self._cue_event(final, state, started, retrieval_ms, degraded=False),
                    "reasoning_latency_ms": max(0, int((self._clock() - reasoning_started) * 1000)),
                },
            )
        except _AssistCancelled:
            return
        except ProviderError as error:
            if error.code == "PROVIDER_CANCELLED":
                return
            self._emit_error(
                state,
                CoreDomainError(
                    "ASSIST_PROVIDER_FAILED",
                    "The provider did not return a usable Live Assist cue.",
                    retryable=error.retryable,
                    details={"cause_code": error.code},
                ),
            )
            try:
                if self._is_current(state):
                    self._ensure_current(state)
                    fallback_hits = self._retrieval.query(
                        {
                            "project_id": state.project_id,
                            "query": state.question[:MAX_LIVE_RETRIEVAL_QUERY_CHARS],
                            "limit": MAX_CUE_EVIDENCE,
                            "usage": "live",
                            "allow_private": True,
                        }
                    ).get("hits", [])
                    fallback_evidence = [
                        item
                        for item in fallback_hits
                        if isinstance(item, dict) and isinstance(item.get("evidence"), dict)
                    ]
                    fallback_evidence = [
                        item
                        for item in self._cue.current_evidence(
                            state.project_id,
                            [item["evidence"] for item in fallback_evidence],
                        )
                        if item["available"]
                    ]
                    if not fallback_evidence:
                        raise CoreDomainError(
                            "ASSIST_CONTEXT_STALE",
                            "The retrieval fallback is no longer live-eligible.",
                        )
                    fallback = self._retrieval_pointer_cue(
                        state,
                        cue_id,
                        fallback_evidence,
                        [],
                        started,
                        reason="provider_failed",
                    )
                    self._emit(
                        "cue.ready",
                        self._cue_event(fallback, state, started, 0, degraded=True),
                    )
            except Exception:
                pass
        except CoreDomainError as error:
            if error.code == "ASSIST_CANCELLED":
                return
            if error.code in {"ASSIST_CONTEXT_INSUFFICIENT", "ASSIST_RETRIEVAL_FAILED"}:
                self._emit_error(state, error)
            else:
                self._emit_error(
                    state,
                    CoreDomainError(
                        "ASSIST_PROVIDER_FAILED",
                        "Live Assist could not complete its bounded reasoning step.",
                        retryable=True,
                        details={"cause_code": error.code},
                    ),
                )
        except Exception:
            self._emit_error(
                state,
                CoreDomainError(
                    "ASSIST_RETRIEVAL_FAILED",
                    "Live Assist could not complete its bounded retrieval step.",
                    retryable=True,
                ),
            )
        finally:
            self._cue.discard_partial(state.project_id, state.session_id, state.assist_id)
            with self._lock:
                self._states.pop(state.assist_id, None)

    def _save_partial(
        self, state: _AssistState, cue_id: str, evidence: list[dict[str, Any]], started: float
    ) -> dict[str, Any]:
        label = self._evidence_label(evidence[0])
        with self._lock:
            self._ensure_current(state)
            return self._cue.save(
                project_id=state.project_id,
                session_id=state.session_id,
                cue_id=cue_id,
                assist_id=state.assist_id,
                cue_type="source_pointer",
                lines=[f"Checking {label}."[:MAX_CUE_LINE_CHARS]],
                state="partial",
                route="retrieval_only",
                evidence=evidence,
            )

    @staticmethod
    def _has_unsupported_fact(lines: list[str], evidence: list[dict[str, Any]]) -> bool:
        supported = {
            fact.normalized_value
            for item in evidence
            for fact in extract_fact_values(str(item.get("text") or ""))
        }
        produced = extract_fact_values(" ".join(lines))
        return any(fact.normalized_value not in supported for fact in produced)

    @staticmethod
    def _with_source_pointer(lines: list[str], evidence: list[dict[str, Any]]) -> list[str]:
        result = list(lines[:2])
        if evidence:
            label = AssistService._evidence_label(evidence[0])
            result.append(AssistService._one_line(f"Source: {label}", MAX_CUE_LINE_CHARS))
        return result[:MAX_CUE_LINES]

    @staticmethod
    def _evidence_label(item: Mapping[str, Any], default: str = "project source") -> str:
        label = item.get("label") or item.get("label_snapshot")
        return label.strip() if isinstance(label, str) and label.strip() else default

    def _retrieval_fast_path(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        route: ReasoningRoute,
        started: float,
        cue_id: str,
        state: _AssistState,
    ) -> dict[str, Any] | None:
        if conflicts:
            conflict = conflicts[0]
            subject = str(conflict.get("subject") or "the requested fact")
            ids = {
                str(evidence_id)
                for value in conflict.get("values", [])
                if isinstance(value, dict)
                for evidence_id in value.get("evidence_ids", [])
                if isinstance(evidence_id, str)
            }
            selected = [item for item in evidence if str(item.get("evidence_id")) in ids]
            if not selected:
                selected = evidence[:2]
            return self._cue.save(
                project_id=state.project_id,
                session_id=state.session_id,
                cue_id=cue_id,
                assist_id=state.assist_id,
                cue_type="warning",
                lines=[
                    f"Sources conflict on {subject}."[:MAX_CUE_LINE_CHARS],
                    "Check the cited sources before answering."[:MAX_CUE_LINE_CHARS],
                ],
                state="final",
                route="retrieval_only",
                evidence=selected,
            )
        preferred = self._preferred_live_evidence(question, evidence, route)
        if preferred is not None:
            wording = self._one_line(str(preferred.get("text") or ""), MAX_CUE_LINE_CHARS)
            if wording:
                return self._cue.save(
                    project_id=state.project_id,
                    session_id=state.session_id,
                    cue_id=cue_id,
                    assist_id=state.assist_id,
                    cue_type="reminder",
                    lines=self._with_source_pointer([wording], [preferred]),
                    state="final",
                    route="retrieval_only",
                    evidence=[preferred],
                )
        if not self._is_exact_fact_question(question):
            return None
        safe = [item for item in evidence if item.get("fact_safe") is True]
        if not safe:
            return None
        item = safe[0]
        label = self._evidence_label(item, default="Project source")
        excerpt = self._one_line(str(item.get("text") or ""), MAX_CUE_LINE_CHARS)
        line = self._one_line(f"{label}: {excerpt}", MAX_CUE_LINE_CHARS)
        return self._cue.save(
            project_id=state.project_id,
            session_id=state.session_id,
            cue_id=cue_id,
            assist_id=state.assist_id,
            cue_type="fact",
            lines=[line],
            state="final",
            route="retrieval_only",
            evidence=[item],
        )

    @staticmethod
    def _preferred_live_evidence(
        question: str,
        evidence: list[dict[str, Any]],
        route: ReasoningRoute,
    ) -> dict[str, Any] | None:
        if route == ReasoningRoute.REMOTE_REASONING:
            # A private item may be retrieved locally but must not bypass the
            # remote-context boundary merely because it is preferred.
            eligible = [
                item
                for item in evidence
                if not (item.get("private") is True and item.get("source_type") == "user_statement")
            ]
        else:
            eligible = evidence
        question_values = {fact.normalized_value for fact in extract_fact_values(question)}
        for item in eligible:
            if (
                item.get("source_type") != "user_statement"
                or item.get("preferred") is not True
                or item.get("use_live") is not True
            ):
                continue
            text = str(item.get("text") or "")
            if not text:
                continue
            if question_values:
                item_values = {fact.normalized_value for fact in extract_fact_values(text)}
                if not question_values.intersection(item_values):
                    continue
            return item
        return None

    def _retrieval_pointer_cue(
        self,
        state: _AssistState,
        cue_id: str,
        raw_evidence: list[dict[str, Any]] | list[Any],
        conflicts: list[dict[str, Any]],
        started: float,
        *,
        reason: str,
    ) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        for item in raw_evidence[:MAX_CUE_EVIDENCE]:
            candidate = item.get("evidence") if isinstance(item, dict) else None
            if isinstance(candidate, dict):
                evidence.append(candidate)
            elif isinstance(item, dict) and isinstance(item.get("evidence_id"), str):
                evidence.append(item)
        if not evidence:
            raise CoreDomainError("ASSIST_CONTEXT_INSUFFICIENT", "No source pointer is available.")
        label = self._evidence_label(evidence[0])
        if conflicts:
            lines = ["Sources conflict; verify before answering.", f"Source: {label}"]
            cue_type = "warning"
        else:
            lines = ["Start with the cited source.", f"Source: {label}"]
            cue_type = "source_pointer"
        return self._cue.save(
            project_id=state.project_id,
            session_id=state.session_id,
            cue_id=cue_id,
            assist_id=state.assist_id,
            cue_type=cue_type,
            lines=[self._one_line(line, MAX_CUE_LINE_CHARS) for line in lines],
            state="final",
            route="retrieval_only",
            evidence=evidence,
        )

    def _validate_live_output_for_execution(
        self,
        output: dict[str, Any],
        request: Any,
        project_id: str,
    ) -> dict[str, Any]:
        """Run Live's canonical-evidence checks before ProviderRun success."""
        output_ids = {str(item) for item in output.get("evidence_ids", [])}
        supplied_ids = {
            str(item.get("evidence_id"))
            for item in request.grounding_evidence
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        }
        if not output_ids or not output_ids.issubset(supplied_ids):
            raise ProviderError(
                "ASSIST_OUTPUT_INVALID",
                "The Live Assist provider cited evidence outside its bounded context.",
            )
        selected = [
            item
            for item in request.grounding_evidence
            if isinstance(item, dict) and str(item.get("evidence_id")) in output_ids
        ]
        selected = [
            item for item in self._cue.current_evidence(project_id, selected) if item["available"]
        ]
        if not selected:
            raise ProviderError(
                "ASSIST_OUTPUT_INVALID",
                "The Live Assist provider did not cite supplied evidence.",
            )
        if self._has_unsupported_fact(output["lines"], selected):
            raise ProviderError(
                "ASSIST_OUTPUT_INVALID",
                "The Live Assist provider introduced an unsupported exact fact.",
            )
        return output

    def _emit_error(self, state: _AssistState, error: CoreDomainError) -> None:
        if not self._is_current(state):
            return
        self._emit(
            "cue.error",
            {
                "assist_id": state.assist_id,
                "session_id": state.session_id,
                "code": error.code,
                "error_code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "latency_ms": 0,
            },
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _cue_event(
        self,
        cue: dict[str, Any],
        state: _AssistState,
        started: float,
        retrieval_ms: int,
        *,
        degraded: bool,
    ) -> dict[str, Any]:
        evidence = [
            {
                "evidence_id": item["evidence_id"],
                "label": item["label"],
                "available": item["available"],
                "rank": item["rank"],
            }
            for item in cue.get("evidence", [])[:MAX_CUE_EVIDENCE]
        ]
        return {
            "assist_id": state.assist_id,
            "session_id": state.session_id,
            "cue_id": cue["id"],
            "cue_type": cue["cue_type"],
            "state": cue["state"],
            "route": cue["route"],
            "lines": list(cue["lines"]),
            "text": "\n".join(cue["lines"]),
            "evidence": evidence,
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "provider_run_id": cue.get("provider_run_id"),
            "degraded": degraded,
            "latency_ms": max(0, int((self._clock() - started) * 1000)),
            "retrieval_latency_ms": retrieval_ms,
        }

    def _ensure_current(self, state: _AssistState) -> None:
        if not self._is_current(state):
            raise _AssistCancelled
        try:
            self._sessions.validate_active_live_assist(state.project_id, state.session_id)
        except CoreDomainError as error:
            if error.code in {"SESSION_NOT_FOUND", "SESSION_NOT_ACTIVE", "SESSION_MODE_INVALID"}:
                raise _AssistCancelled from error
            raise

    def _is_current(self, state: _AssistState) -> bool:
        with self._lock:
            current = self._states.get(state.assist_id)
            return (
                not self._closed
                and current is state
                and not state.cancelled.is_set()
                and self._generations.get((state.project_id, state.session_id)) == state.generation
            )

    def _project_row(self, project_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return cast(sqlite3.Row, row)

    def _assemble_live_question(self, project_id: str, session_id: str) -> tuple[str | None, str]:
        recent = self._recent_utterances(project_id, session_id)
        partial = self._asr.latest_partial(project_id, session_id)
        pieces = [str(item["text"]) for item in reversed(recent)]
        partial_text = (
            str(partial["text"])
            if partial is not None and isinstance(partial.get("text"), str)
            else None
        )
        if partial_text and partial_text not in pieces:
            pieces.append(partial_text)
        if not pieces:
            return None, "none"
        while len(pieces) > 1 and len(" ".join(pieces)) > MAX_LIVE_QUERY_CHARS:
            pieces.pop(0)
        combined = " ".join(pieces)
        if len(combined) > MAX_LIVE_QUERY_CHARS:
            combined = combined[-MAX_LIVE_QUERY_CHARS:]
        origin = (
            "live_partial"
            if partial_text and not recent
            else "live_window"
            if partial_text
            else "live_final"
        )
        return self._clean_text(combined), origin

    def _recent_utterances(self, project_id: str, session_id: str) -> list[dict[str, Any]]:
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                """
                SELECT id, text, start_ms, end_ms, slide_ordinal
                FROM utterances
                WHERE session_id = ? AND actor = 'unknown_audience' AND is_final = 1
                ORDER BY COALESCE(end_ms, start_ms, 0) DESC, id DESC
                LIMIT ?
                """,
                (session_id, MAX_LIVE_QUERY_UTTERANCES),
            ).fetchall()
        latest_time = self._utterance_time(rows[0]) if rows else None
        result: list[dict[str, Any]] = []
        for row in rows:
            timestamp = self._utterance_time(row)
            if (
                latest_time is not None
                and timestamp is not None
                and latest_time - timestamp > MAX_LIVE_RECENT_WINDOW_MS
            ):
                continue
            result.append(
                {
                    "utterance_id": str(row["id"]),
                    "text": self._one_line(str(row["text"]), 800),
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                    "slide_ordinal": row["slide_ordinal"],
                }
            )
        return result

    @staticmethod
    def _utterance_time(row: sqlite3.Row) -> int | None:
        value = row["end_ms"] if row["end_ms"] is not None else row["start_ms"]
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _is_exact_fact_question(question: str) -> bool:
        return bool(_FACT_QUERY_RE.search(question))

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())[:MAX_LIVE_QUESTION_CHARS].strip()

    @staticmethod
    def _one_line(value: str, maximum: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= maximum:
            return normalized
        return normalized[: max(1, maximum - 1)].rstrip() + "…"

    @staticmethod
    def _bounded_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "provider_content_boundary",
            "provider_id",
            "task_type",
            "privacy_mode",
            "classes_sent",
            "source_ids",
            "knowledge_item_ids",
            "speaker_evidence_ids",
            "audience_profile_ids",
            "audience_observation_ids",
            "prior_question_count",
            "raw_audio_sent",
            "full_document_sent",
            "full_corpus_sent",
            "private_items_sent",
            "bounded_context_chars",
        }
        result: dict[str, Any] = {}
        for key in allowed:
            value = manifest.get(key)
            if isinstance(value, list):
                result[key] = [str(item)[:120] for item in value[:8]]
            elif isinstance(value, (str, bool, int)) or value is None:
                result[key] = value
        return result

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _session_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("session_id must be a UUID.", field="session_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request("session_id must be a UUID.", field="session_id") from error

    def wait_for_idle(self, timeout_seconds: float = 5.0) -> bool:
        """Wait for currently registered workers, primarily for deterministic tests."""
        deadline = monotonic() + max(0.0, timeout_seconds)
        while True:
            with self._lock:
                workers = [state.worker for state in self._states.values()]
            alive = [worker for worker in workers if worker is not None and worker.is_alive()]
            if not alive:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            alive[0].join(timeout=min(0.05, remaining))
