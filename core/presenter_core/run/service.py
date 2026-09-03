"""Durable Run-mode state built on the existing session and retrieval seams."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from time import monotonic
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import (
    MAX_DEBRIEF_UTTERANCES,
    MAX_FINAL_UTTERANCE_CHARS,
    MAX_RUN_MARKER_NOTE_CHARS,
    MAX_RUN_MARKERS_PER_SESSION,
    MAX_RUN_SESSION_DURATION_MS,
    MAX_RUN_TIMELINE_PAGE_SIZE,
    MAX_RUN_TRANSCRIPT_PAGE_SIZE,
    MAX_RUN_UTTERANCES_PER_SESSION,
)
from presenter_core.presentation.service import SlideStateService
from presenter_core.project.service import utc_now
from presenter_core.retrieval.conflicts import detect_conflicts, extract_fact_values
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.session.service import SessionService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

EventSink = Callable[[str, dict[str, Any]], None]
ASRStop = Callable[[dict[str, Any]], dict[str, Any]]
ASROwner = Callable[[], tuple[str, str] | None]

DEBRIEF_ALGORITHM_VERSION = "m6-deterministic-v1"
MARKER_TYPES = frozenset({"question", "weak_point", "note"})
_NUMERIC_OR_FACTUAL_PATTERN = re.compile(
    r"(?:\b(?:rto|cost|price|percent|percentage|year|years|minute|minutes|hour|hours|sla|availability)\b|\d|[$€£%])",
    re.IGNORECASE,
)


class RunService:
    """Coordinate Run cleanup and own its bounded durable read/write APIs."""

    def __init__(
        self,
        storage: StorageManager,
        sessions: SessionService,
        presentation: SlideStateService,
        retrieval: HybridRetrievalService,
        *,
        asr_stop: ASRStop,
        asr_owner: ASROwner | None = None,
        event_sink: EventSink | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._storage = storage
        self._sessions = sessions
        self._presentation = presentation
        self._retrieval = retrieval
        self._asr_stop = asr_stop
        self._asr_owner = asr_owner
        self._event_sink = event_sink
        self._clock = clock

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink

    def start(self, project_id: str, session_id: str) -> dict[str, Any]:
        """Initialize slide tracking after the canonical session row commits."""
        return self._presentation.start_run(project_id, session_id)

    def stop_project_runs(self, params: dict[str, Any]) -> None:
        """Release active Run resources before the project vault is deleted."""
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
                "SELECT id FROM sessions WHERE mode = 'run' AND status = 'active' "
                "ORDER BY started_at, id LIMIT ?",
                (MAX_RUN_UTTERANCES_PER_SESSION,),
            ).fetchall()
        stopped_sessions = {str(row["id"]) for row in rows}
        for row in rows:
            self.stop(
                {
                    "project_id": project_id,
                    "session_id": str(row["id"]),
                    "status": "aborted",
                }
            )
        owner = self._current_asr_owner()
        if owner is not None and owner[0] == project_id and owner[1] not in stopped_sessions:
            # A stale/terminal session row must not hide a still-owned ASR
            # resource from project deletion.  Run.stop performs the retryable
            # resource cleanup before any project filesystem operation.
            self.stop({"project_id": owner[0], "session_id": owner[1], "status": "aborted"})

    def stop_active_runs(self, *, status: str = "aborted") -> None:
        """Flush every active Run before a normal core shutdown."""
        if status not in {"completed", "aborted", "error"}:
            raise ValueError("status must be a stoppable session status")
        active_sessions: set[tuple[str, str]] = set()
        first_error: CoreDomainError | None = None
        for app_row in self._storage.list_app_rows():
            project_id = str(app_row["id"])
            with self._storage.project_database(project_id) as connection:
                rows = connection.execute(
                    "SELECT id FROM sessions WHERE mode = 'run' AND status = 'active' "
                    "ORDER BY started_at, id LIMIT ?",
                    (MAX_RUN_UTTERANCES_PER_SESSION,),
                ).fetchall()
            for row in rows:
                owner = (project_id, str(row["id"]))
                active_sessions.add(owner)
                try:
                    self.stop(
                        {
                            "project_id": owner[0],
                            "session_id": owner[1],
                            "status": status,
                        }
                    )
                except CoreDomainError as error:
                    first_error = first_error or error
        asr_owner = self._current_asr_owner()
        if asr_owner is not None and asr_owner not in active_sessions:
            try:
                self.stop(
                    {
                        "project_id": asr_owner[0],
                        "session_id": asr_owner[1],
                        "status": status,
                    }
                )
            except CoreDomainError as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    def stop(self, params: dict[str, Any]) -> dict[str, Any]:
        """Flush local ASR and slide state before completing the Run session."""
        reject_unknown_fields(params, {"project_id", "session_id", "status"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        requested_status = params.get("status", "completed")
        if requested_status not in {"completed", "aborted", "error"}:
            raise invalid_request("status is not a stoppable session status.", field="status")
        session = self._session(project_id, session_id)
        if session["mode"] != "run":
            return self._sessions.stop(params)
        if session["status"] != "active":
            if self._current_asr_owner() == (project_id, session_id):
                # A resource owner is authoritative for cleanup even if a
                # previous process wrote a terminal session status too early.
                self._asr_stop({"project_id": project_id, "session_id": session_id})
                self._presentation.stop_run(project_id, session_id)
            result: dict[str, Any] = {"session": self._session_dict(project_id, session_id)}
            debrief = self.get_debrief({"project_id": project_id, "session_id": session_id})
            result["debrief"] = debrief.get("debrief")
            return result

        # ASR owns the first irreversible shutdown boundary.  If it cannot
        # flush/finalize and terminate, do not stop the watcher or mutate the
        # canonical session status; the caller can safely retry this method.
        try:
            self._asr_stop({"project_id": project_id, "session_id": session_id})
        except CoreDomainError:
            raise
        except Exception as error:
            raise CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The active Run could not release its local ASR resources; retry is safe.",
                retryable=True,
            ) from error

        # The watcher is independent of microphone capture and is released
        # only after the final ASR boundary has completed successfully.
        self._presentation.stop_run(project_id, session_id)

        stopped = self._sessions.stop(
            {"project_id": project_id, "session_id": session_id, "status": requested_status}
        )
        result = {"session": stopped["session"]}
        if requested_status == "completed":
            try:
                result["debrief"] = self.generate_debrief(
                    {"project_id": project_id, "session_id": session_id}
                )["debrief"]
            except CoreDomainError as error:
                result["debrief_error_code"] = error.code
        else:
            result["debrief"] = None
        return result

    def persist_final_utterance(
        self,
        project_id: str,
        session_id: str,
        utterance_id: str,
        text: str,
        start_ms: int,
        end_ms: int,
        confidence: float | None,
        slide_hint: int | None,
    ) -> int | None:
        """Commit one final utterance and return its start-slide snapshot."""
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        try:
            utterance_id = str(uuid.UUID(utterance_id))
        except ValueError as exc:
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED", "The ASR utterance id is invalid."
            ) from exc
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.strip()) > MAX_FINAL_UTTERANCE_CHARS
        ):
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED",
                "The final ASR utterance is empty or exceeds the safe bound.",
            )
        if (
            isinstance(start_ms, bool)
            or isinstance(end_ms, bool)
            or not isinstance(start_ms, int)
            or not isinstance(end_ms, int)
            or start_ms < 0
            or end_ms < start_ms
        ):
            raise CoreDomainError("ASR_TRANSCRIBE_FAILED", "The ASR timestamps are invalid.")
        if confidence is not None and (
            not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0
        ):
            confidence = None
        with self._storage.project_database(project_id) as connection:
            session = connection.execute(
                "SELECT status, mode, started_at FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
            if session is None or session["mode"] != "run" or session["status"] != "active":
                raise CoreDomainError(
                    "ASR_SESSION_INVALID",
                    "Final ASR text requires an active Run session.",
                )
            existing = connection.execute(
                "SELECT slide_ordinal, text FROM utterances WHERE id = ? AND session_id = ?",
                (utterance_id, session_id),
            ).fetchone()
            if existing is not None:
                if existing["text"] != text.strip():
                    raise CoreDomainError(
                        "ASR_TRANSCRIBE_FAILED", "The ASR utterance id was reused."
                    )
                return (
                    int(existing["slide_ordinal"])
                    if existing["slide_ordinal"] is not None
                    else None
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id = ? AND is_final = 1",
                (session_id,),
            ).fetchone()
            if count is not None and int(count[0]) >= MAX_RUN_UTTERANCES_PER_SESSION:
                raise CoreDomainError(
                    "ASR_SESSION_LIMIT_REACHED",
                    "The Run transcript reached its safety bound.",
                )
            previous = connection.execute(
                "SELECT end_ms FROM utterances WHERE session_id = ? AND is_final = 1 "
                "ORDER BY COALESCE(end_ms, 0) DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if (
                previous is not None
                and previous["end_ms"] is not None
                and start_ms < int(previous["end_ms"])
            ):
                raise CoreDomainError(
                    "ASR_TRANSCRIBE_FAILED",
                    "ASR timestamps must be monotonic within a Run session.",
                )
            presentation_slide = self._presentation.current_slide(project_id, session_id)
            slide_ordinal = self._valid_slide_hint(slide_hint, presentation_slide)
            connection.execute(
                """
                INSERT INTO utterances (
                    id, session_id, actor, text, created_at, start_ms, end_ms,
                    asr_confidence, slide_ordinal, is_final
                ) VALUES (?, ?, 'user', ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    utterance_id,
                    session_id,
                    text.strip(),
                    utc_now(),
                    start_ms,
                    end_ms,
                    float(confidence) if confidence is not None else None,
                    slide_ordinal,
                ),
            )
            connection.commit()
            return slide_ordinal

    def mark_event(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "marker_type", "timestamp_ms", "slide_ordinal", "note"},
        )
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._require_active_run(project_id, session_id)
        marker_type = params.get("marker_type")
        if not isinstance(marker_type, str) or marker_type not in MARKER_TYPES:
            raise invalid_request("marker_type is not supported.", field="marker_type")
        note = params.get("note")
        if note is not None and (
            not isinstance(note, str) or len(note) > MAX_RUN_MARKER_NOTE_CHARS
        ):
            raise invalid_request("note exceeds the safe marker bound.", field="note")
        timestamp_ms = params.get("timestamp_ms")
        if timestamp_ms is None:
            timestamp_ms = self._elapsed_ms(project_id, session_id)
        if (
            isinstance(timestamp_ms, bool)
            or not isinstance(timestamp_ms, int)
            or timestamp_ms < 0
            or timestamp_ms > MAX_RUN_SESSION_DURATION_MS
        ):
            raise invalid_request("timestamp_ms is outside the Run bounds.", field="timestamp_ms")
        requested_slide = params.get("slide_ordinal")
        current_slide = self._presentation.current_slide(project_id, session_id)
        if requested_slide is not None and (
            isinstance(requested_slide, bool)
            or not isinstance(requested_slide, int)
            or requested_slide < 1
        ):
            raise invalid_request(
                "slide_ordinal must be a positive integer.", field="slide_ordinal"
            )
        slide_ordinal = requested_slide if requested_slide is not None else current_slide
        with self._storage.project_database(project_id) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM run_markers WHERE session_id = ?", (session_id,)
            ).fetchone()
            if count is not None and int(count[0]) >= MAX_RUN_MARKERS_PER_SESSION:
                raise CoreDomainError(
                    "RUN_SESSION_LIMIT_REACHED",
                    "The Run marker timeline reached its safety bound.",
                )
            marker_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO run_markers
                    (id, session_id, marker_type, timestamp_ms, slide_ordinal, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (marker_id, session_id, marker_type, timestamp_ms, slide_ordinal, note, utc_now()),
            )
            connection.commit()
        return {
            "marker": {
                "id": marker_id,
                "session_id": session_id,
                "marker_type": marker_type,
                "timestamp_ms": timestamp_ms,
                "slide_ordinal": slide_ordinal,
                "note": note,
            }
        }

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        session = self._session(project_id, session_id)
        if session["mode"] != "run":
            raise CoreDomainError(
                "SESSION_MODE_INVALID", "The selected session is not a Run session."
            )
        presentation = self._presentation.status(
            {"project_id": project_id, "session_id": session_id}
        )
        with self._storage.project_database(project_id) as connection:
            transcript_count = self._count(connection, "utterances", session_id, "is_final = 1")
            timeline_count = self._count(connection, "slide_state_events", session_id)
            marker_count = self._count(connection, "run_markers", session_id)
            debrief = connection.execute(
                "SELECT 1 FROM run_debriefs WHERE session_id = ?", (session_id,)
            ).fetchone()
        return {
            "project_id": project_id,
            "session_id": session_id,
            "mode": "run",
            "status": session["status"],
            "started_at": session["started_at"],
            "ended_at": session["ended_at"],
            "duration_ms": self._duration_ms(session),
            "current_slide": presentation["current_slide"],
            "slide_count": presentation["slide_count"],
            "presentation_mode": presentation["mode"],
            "presentation_reason": presentation["reason"],
            "tracking": presentation["tracking"],
            "transcript_count": transcript_count,
            "timeline_count": timeline_count,
            "marker_count": marker_count,
            "debrief_available": debrief is not None,
        }

    def list_transcript(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "limit", "offset"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._require_run_scope(project_id, session_id)
        limit, offset = self._page(params, MAX_RUN_TRANSCRIPT_PAGE_SIZE)
        with self._storage.project_database(project_id) as connection:
            total = self._count(connection, "utterances", session_id, "is_final = 1")
            rows = connection.execute(
                """
                SELECT id, text, start_ms, end_ms, asr_confidence, slide_ordinal
                FROM utterances
                WHERE session_id = ? AND is_final = 1
                ORDER BY COALESCE(start_ms, 2147483647), id
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()
        return {
            "project_id": project_id,
            "session_id": session_id,
            "utterances": [
                {
                    "utterance_id": row["id"],
                    "text": row["text"],
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                    "confidence": row["asr_confidence"],
                    "slide_ordinal": row["slide_ordinal"],
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(rows) < total,
        }

    def list_timeline(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "limit", "offset"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._require_run_scope(project_id, session_id)
        limit, offset = self._page(params, MAX_RUN_TIMELINE_PAGE_SIZE)
        with self._storage.project_database(project_id) as connection:
            slide_rows = connection.execute(
                """
                SELECT id, session_id, slide_ordinal, timestamp_ms, source, created_at
                FROM slide_state_events WHERE session_id = ?
                ORDER BY timestamp_ms, id
                """,
                (session_id,),
            ).fetchall()
            marker_rows = connection.execute(
                """
                SELECT id, marker_type, timestamp_ms, slide_ordinal, note, created_at
                FROM run_markers WHERE session_id = ?
                ORDER BY timestamp_ms, id
                """,
                (session_id,),
            ).fetchall()
            slide_total = self._count(connection, "slide_state_events", session_id)
            marker_total = self._count(connection, "run_markers", session_id)
        all_slide_events = [self._slide_dict(row) for row in slide_rows]
        all_markers = [self._marker_dict(row, session_id) for row in marker_rows]
        all_events = [{"kind": "slide", **event} for event in all_slide_events] + [
            {"kind": "marker", **marker} for marker in all_markers
        ]
        all_events.sort(key=lambda item: (int(item["timestamp_ms"]), str(item["id"])))
        page = all_events[offset : offset + limit]
        slide_events = [event for event in page if event["kind"] == "slide"]
        markers = [event for event in page if event["kind"] == "marker"]
        return {
            "project_id": project_id,
            "session_id": session_id,
            "slide_events": slide_events,
            "markers": markers,
            "timeline": page,
            "limit": limit,
            "offset": offset,
            "total": slide_total + marker_total,
            "has_more": offset + len(page) < slide_total + marker_total,
        }

    def get_debrief(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._require_run_scope(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT * FROM run_debriefs WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return {"project_id": project_id, "session_id": session_id, "debrief": None}
        try:
            debrief = json.loads(row["debrief_json"])
        except json.JSONDecodeError as exc:
            raise CoreDomainError(
                "RUN_DEBRIEF_CORRUPT", "The persisted Run debrief is invalid."
            ) from exc
        return {
            "project_id": project_id,
            "session_id": session_id,
            "debrief": debrief,
            "algorithm_version": row["algorithm_version"],
            "transcript_fingerprint": row["transcript_fingerprint"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def generate_debrief(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        session = self._require_run_scope(project_id, session_id)
        if session["status"] == "active":
            raise CoreDomainError(
                "RUN_SESSION_ACTIVE",
                "A Run debrief is available only after the session stops.",
            )
        self._emit_progress(session_id, "load", 0, 1)
        with self._storage.project_database(project_id) as connection:
            utterances = connection.execute(
                """
                SELECT id, text, start_ms, end_ms, asr_confidence, slide_ordinal
                FROM utterances WHERE session_id = ? AND is_final = 1
                ORDER BY COALESCE(start_ms, 2147483647), id LIMIT ?
                """,
                (session_id, MAX_DEBRIEF_UTTERANCES + 1),
            ).fetchall()
            if len(utterances) > MAX_DEBRIEF_UTTERANCES:
                raise CoreDomainError(
                    "RUN_DEBRIEF_LIMIT_REACHED",
                    "The Run debrief input exceeded its bounded utterance limit.",
                )
            slides = connection.execute(
                "SELECT id, slide_ordinal, timestamp_ms, source FROM slide_state_events "
                "WHERE session_id = ? ORDER BY timestamp_ms, id",
                (session_id,),
            ).fetchall()
            markers = connection.execute(
                "SELECT id, marker_type, timestamp_ms, slide_ordinal, note FROM run_markers "
                "WHERE session_id = ? ORDER BY timestamp_ms, id",
                (session_id,),
            ).fetchall()
            existing = connection.execute(
                "SELECT * FROM run_debriefs WHERE session_id = ?", (session_id,)
            ).fetchone()
        fingerprint = self._fingerprint(utterances, slides, markers)
        if existing is not None and existing["transcript_fingerprint"] == fingerprint:
            current = self.get_debrief({"project_id": project_id, "session_id": session_id})
            current["reused"] = True
            return current

        self._emit_progress(session_id, "analyze", 0, max(1, len(utterances)))
        slide_summaries = self._slide_summaries(utterances)
        long_segments = self._long_segments(utterances)
        marked = [self._marker_dict(row, session_id) for row in markers]
        evidence_reviews: list[dict[str, Any]] = []
        best_explanations: list[dict[str, Any]] = []
        for index, row in enumerate(utterances):
            self._emit_progress(session_id, "retrieve", index, len(utterances))
            query_result = self._retrieve_for_debrief(project_id, row)
            hits = query_result.get("hits", [])
            conflicts = query_result.get("conflicts", [])
            if not isinstance(hits, list):
                hits = []
            if not isinstance(conflicts, list):
                conflicts = []
            claim_text = str(row["text"])
            fact_support = self._fact_support(claim_text, hits, conflicts)
            if fact_support is not None:
                conflicts = fact_support["conflicts"]
                evidence = [self._safe_evidence_ref(hit) for hit in hits[:3]]
                if fact_support["status"] == "supported":
                    explanation_evidence = fact_support["supporting_evidence"]
                else:
                    # Retrieval context is not evidence for an exact value
                    # unless the canonical fact-safe check below accepted it.
                    explanation_evidence = []
                if fact_support["status"] != "supported":
                    evidence_reviews.append(
                        {
                            "utterance_id": row["id"],
                            "slide_ordinal": row["slide_ordinal"],
                            "excerpt": claim_text[:320],
                            "status": fact_support["status"],
                            "evidence": evidence,
                            "supporting_evidence": fact_support["supporting_evidence"],
                            "not_supporting_evidence": fact_support["not_supporting_evidence"],
                            "conflicts": self._safe_conflicts(conflicts),
                        }
                    )
            else:
                evidence = [self._safe_evidence_ref(hit) for hit in hits[:3]]
                explanation_evidence = evidence
                if _NUMERIC_OR_FACTUAL_PATTERN.search(claim_text) and not evidence:
                    evidence_reviews.append(
                        {
                            "utterance_id": row["id"],
                            "slide_ordinal": row["slide_ordinal"],
                            "excerpt": claim_text[:320],
                            "status": "needs_evidence_review",
                            "evidence": evidence,
                            "conflicts": self._safe_conflicts(conflicts),
                        }
                    )
            word_count = len(str(row["text"]).split())
            if 8 <= word_count <= 100 and len(best_explanations) < 8:
                explanation: dict[str, Any] = {
                    "utterance_id": row["id"],
                    "slide_ordinal": row["slide_ordinal"],
                    "excerpt": claim_text[:320],
                    "evidence": explanation_evidence,
                }
                if fact_support is not None:
                    explanation["fact_support"] = {
                        key: value for key, value in fact_support.items() if key != "conflicts"
                    }
                best_explanations.append(explanation)
        self._emit_progress(session_id, "analyze", len(utterances), len(utterances))
        recommendations = self._recommended_questions(marked, evidence_reviews, long_segments)
        total_words = sum(len(str(row["text"]).split()) for row in utterances)
        debrief: dict[str, Any] = {
            "algorithm_version": DEBRIEF_ALGORITHM_VERSION,
            "session": {
                "session_id": session_id,
                "duration_ms": self._duration_ms(session),
                "word_count": total_words,
                "utterance_count": len(utterances),
            },
            "per_slide": slide_summaries,
            "markers": marked[:MAX_RUN_MARKERS_PER_SESSION],
            "long_segments": long_segments,
            "evidence_review_candidates": evidence_reviews[:100],
            "best_explanation_candidates": best_explanations,
            "recommended_challenge_questions": recommendations,
        }
        serialized = json.dumps(debrief, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        self._emit_progress(session_id, "persist", 0, 1)
        timestamp = utc_now()
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                INSERT INTO run_debriefs
                    (
                        session_id,
                        algorithm_version,
                        transcript_fingerprint,
                        debrief_json,
                        created_at,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    algorithm_version = excluded.algorithm_version,
                    transcript_fingerprint = excluded.transcript_fingerprint,
                    debrief_json = excluded.debrief_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    DEBRIEF_ALGORITHM_VERSION,
                    fingerprint,
                    serialized,
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
        self._emit_progress(session_id, "complete", 1, 1)
        result = self.get_debrief({"project_id": project_id, "session_id": session_id})
        result["reused"] = False
        return result

    def close(self) -> None:
        return

    def _retrieve_for_debrief(self, project_id: str, row: sqlite3.Row) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {
                "project_id": project_id,
                "query": str(row["text"])[:MAX_FINAL_UTTERANCE_CHARS],
                "limit": 3,
                "allow_private": True,
                "usage": "rehearsal",
            }
            if row["slide_ordinal"] is not None:
                params["current_slide"] = int(row["slide_ordinal"])
            return self._retrieval.query(params)
        except Exception:
            return {"hits": [], "conflicts": []}

    @staticmethod
    def _safe_evidence_ref(hit: Any) -> dict[str, Any]:
        evidence = hit.get("evidence", {}) if isinstance(hit, dict) else {}
        return {
            "evidence_id": evidence.get("evidence_id"),
            "label": evidence.get("label"),
            "source_type": evidence.get("source_type"),
            "source_id": evidence.get("source_id"),
            "source_unit_id": evidence.get("source_unit_id"),
            "knowledge_item_id": evidence.get("knowledge_item_id"),
            "fact_safe": evidence.get("fact_safe") is True,
            "use_rehearsal": evidence.get("use_rehearsal"),
        }

    @classmethod
    def _fact_support(
        cls,
        query: str,
        hits: list[Any],
        conflicts: list[Any],
    ) -> dict[str, Any] | None:
        """Classify exact-value support without promoting semantic similarity."""
        query_values = extract_fact_values(query)
        if not query_values:
            return None
        if not conflicts:
            conflicts = detect_conflicts(
                query,
                [hit for hit in hits if isinstance(hit, dict)],
                require_query_number_match=False,
            )
        query_value_set = {value.normalized_value for value in query_values}
        supporting_hits: list[Any] = []
        rejected_hits: list[Any] = []
        supported_values: set[str] = set()
        for hit in hits:
            evidence = hit.get("evidence") if isinstance(hit, dict) else None
            if not isinstance(evidence, Mapping):
                continue
            values = {
                value.normalized_value
                for value in extract_fact_values(str(evidence.get("text", "")))
            }
            if evidence.get("fact_safe") is True and query_value_set.intersection(values):
                supporting_hits.append(hit)
                supported_values.update(query_value_set.intersection(values))
            else:
                rejected_hits.append(hit)
        supporting_evidence = [cls._safe_evidence_ref(hit) for hit in supporting_hits[:3]]
        not_supporting_evidence = [cls._safe_evidence_ref(hit) for hit in rejected_hits[:3]]
        if conflicts:
            status = "conflict_review"
            supporting_evidence = []
        elif supported_values >= query_value_set:
            status = "supported"
        else:
            status = "needs_evidence_review"
        return {
            "status": status,
            "claim_values": sorted(query_value_set),
            "supporting_evidence": supporting_evidence,
            "not_supporting_evidence": not_supporting_evidence,
            "conflicts": conflicts,
        }

    @staticmethod
    def _safe_conflicts(conflicts: Any) -> list[dict[str, Any]]:
        if not isinstance(conflicts, list):
            return []
        result: list[dict[str, Any]] = []
        for conflict in conflicts[:5]:
            if not isinstance(conflict, dict):
                continue
            result.append(
                {
                    "subject": str(conflict.get("subject", ""))[:160],
                    "values": [
                        {"normalized_value": str(value.get("normalized_value", ""))[:120]}
                        for value in conflict.get("values", [])[:5]
                        if isinstance(value, dict)
                    ],
                }
            )
        return result

    @staticmethod
    def _slide_summaries(utterances: list[sqlite3.Row]) -> list[dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in utterances:
            slide = int(row["slide_ordinal"]) if row["slide_ordinal"] is not None else 0
            summary = grouped.setdefault(
                slide,
                {
                    "slide_ordinal": slide if slide > 0 else None,
                    "speaking_time_ms": 0,
                    "word_count": 0,
                    "utterance_count": 0,
                },
            )
            start = int(row["start_ms"] or 0)
            end = int(row["end_ms"] or start)
            summary["speaking_time_ms"] += max(0, end - start)
            summary["word_count"] += len(str(row["text"]).split())
            summary["utterance_count"] += 1
        return [grouped[key] for key in sorted(grouped)]

    @staticmethod
    def _long_segments(utterances: list[sqlite3.Row]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        candidates = sorted(
            utterances,
            key=lambda row: (len(str(row["text"]).split()), str(row["id"])),
            reverse=True,
        )
        for row in candidates:
            words = len(str(row["text"]).split())
            duration = max(0, int(row["end_ms"] or 0) - int(row["start_ms"] or 0))
            if words < 55 and duration < 20_000:
                continue
            result.append(
                {
                    "utterance_id": row["id"],
                    "slide_ordinal": row["slide_ordinal"],
                    "duration_ms": duration,
                    "word_count": words,
                    "excerpt": str(row["text"])[:320],
                }
            )
            if len(result) >= 12:
                break
        return result

    @staticmethod
    def _recommended_questions(
        markers: list[dict[str, Any]],
        evidence_reviews: list[dict[str, Any]],
        long_segments: list[dict[str, Any]],
    ) -> list[str]:
        questions: list[str] = []
        for marker in markers:
            marker_type = marker["marker_type"]
            slide = marker.get("slide_ordinal")
            location = f" on slide {slide}" if slide else ""
            note = str(marker.get("note") or "").strip()
            if marker_type == "question":
                text = f"How would you answer the marked question{location}?"
            elif marker_type == "weak_point":
                text = f"How would you strengthen this weak point{location}?"
            else:
                text = f"What should you clarify about this note{location}?"
            if note:
                text += f" Focus: {note[:160]}"
            if text not in questions:
                questions.append(text)
        for candidate in evidence_reviews:
            text = f"What evidence supports this claim: {candidate['excerpt'][:180]}?"
            if text not in questions:
                questions.append(text)
        for segment in long_segments:
            slide_label = segment.get("slide_ordinal") or "the current slide"
            text = f"Can you explain the key point more concisely from slide {slide_label}?"
            if text not in questions:
                questions.append(text)
        return questions[:12]

    def _require_active_run(self, project_id: str, session_id: str) -> sqlite3.Row:
        session = self._require_run_scope(project_id, session_id)
        if session["status"] != "active":
            raise CoreDomainError(
                "SESSION_NOT_ACTIVE", "Run actions require an active Run session."
            )
        return session

    def _require_run_scope(self, project_id: str, session_id: str) -> sqlite3.Row:
        session = self._session(project_id, session_id)
        if session["mode"] != "run":
            raise CoreDomainError(
                "SESSION_MODE_INVALID", "The selected session is not a Run session."
            )
        return session

    def _session(self, project_id: str, session_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")
        return cast(sqlite3.Row, row)

    def _session_dict(self, project_id: str, session_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._sessions.get({"project_id": project_id, "session_id": session_id})["session"],
        )

    def _elapsed_ms(self, project_id: str, session_id: str) -> int:
        session = self._session(project_id, session_id)
        return min(MAX_RUN_SESSION_DURATION_MS, self._duration_ms(session, now=True))

    def _duration_ms(self, session: sqlite3.Row, *, now: bool = False) -> int:
        started = self._parse_timestamp(session["started_at"])
        ended = self._parse_timestamp(session["ended_at"]) if session["ended_at"] else None
        if now or ended is None:
            ended = datetime.now(UTC)
        return min(
            MAX_RUN_SESSION_DURATION_MS, max(0, int((ended - started).total_seconds() * 1_000))
        )

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return datetime.now(UTC)

    @staticmethod
    def _count(
        connection: sqlite3.Connection, table: str, session_id: str, where: str | None = None
    ) -> int:
        if table not in {"utterances", "slide_state_events", "run_markers"}:
            raise ValueError("unexpected Run table")
        clause = f" AND {where}" if where else ""
        row = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ?{clause}", (session_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _page(params: dict[str, Any], maximum: int) -> tuple[int, int]:
        limit = params.get("limit", min(50, maximum))
        offset = params.get("offset", 0)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
            raise invalid_request(f"limit must be between 1 and {maximum}.", field="limit")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise invalid_request("offset must be a non-negative integer.", field="offset")
        return limit, offset

    @staticmethod
    def _valid_slide_hint(slide_hint: int | None, fallback: int | None) -> int | None:
        if isinstance(slide_hint, int) and not isinstance(slide_hint, bool) and slide_hint >= 1:
            return slide_hint
        return fallback if isinstance(fallback, int) and fallback >= 1 else None

    @staticmethod
    def _slide_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"] if "session_id" in row.keys() else None,
            "slide_ordinal": row["slide_ordinal"],
            "timestamp_ms": row["timestamp_ms"],
            "source": row["source"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _marker_dict(row: sqlite3.Row, session_id: str) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": session_id,
            "marker_type": row["marker_type"],
            "timestamp_ms": row["timestamp_ms"],
            "slide_ordinal": row["slide_ordinal"],
            "note": row["note"],
            "created_at": row["created_at"] if "created_at" in row.keys() else None,
        }

    @staticmethod
    def _fingerprint(
        utterances: list[sqlite3.Row], slides: list[sqlite3.Row], markers: list[sqlite3.Row]
    ) -> str:
        payload = {
            "algorithm_version": DEBRIEF_ALGORITHM_VERSION,
            "utterances": [
                [row["id"], row["text"], row["start_ms"], row["end_ms"], row["slide_ordinal"]]
                for row in utterances
            ],
            "slides": [
                [row["id"], row["slide_ordinal"], row["timestamp_ms"], row["source"]]
                for row in slides
            ],
            "markers": [
                [
                    row["id"],
                    row["marker_type"],
                    row["timestamp_ms"],
                    row["slide_ordinal"],
                    row["note"],
                ]
                for row in markers
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()

    def _emit_progress(self, session_id: str, phase: str, completed: int, total: int) -> None:
        self._emit(
            "run.debrief_progress",
            {"session_id": session_id, "phase": phase, "completed": completed, "total": total},
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _current_asr_owner(self) -> tuple[str, str] | None:
        if self._asr_owner is None:
            return None
        return self._asr_owner()

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
        except ValueError as exc:
            raise invalid_request("session_id must be a UUID.", field="session_id") from exc
