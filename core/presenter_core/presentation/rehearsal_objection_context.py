"""Original slide ownership and complete, actor-preserving recorded speech windows."""

import json
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_FINAL_UTTERANCE_CHARS, MAX_RUN_UTTERANCES_PER_SESSION
from presenter_core.presentation.claims import digest
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import PRIVACY_MODES
from presenter_core.providers.context import (
    APPLICATION_POLICY,
    MAX_TOTAL_CONTEXT_CHARS,
    MAX_TRUSTED_CONTENT_OVERHEAD_CHARS,
)
from presenter_core.providers.models import ReasoningRequest
from presenter_core.providers.rehearsal_objection_schema import (
    OUTPUT_SCHEMA,
    TASK_INSTRUCTION,
    TASK_TYPE,
)

SOURCE_FIELDS = (
    "document_id",
    "session_id",
    "source_revision_id",
    "source_sha256",
    "slide_id",
    "source_slide_number",
)


def objection_request(
    source: dict[str, Any], speech: list[dict[str, Any]], privacy: str
) -> ReasoningRequest:
    return ReasoningRequest(
        task_type=TASK_TYPE,
        question="Review possible concerns and answers in this recorded speech window only.",
        user_input=None,
        current_slide_summary=json.dumps(
            {"source": source, "recorded_speech": speech}, ensure_ascii=False
        ),
        evidence=(),
        preferred_user_explanations=(),
        speaker_evidence=(),
        style_context={},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode=privacy,
        output_schema=OUTPUT_SCHEMA,
        latency_budget_ms=30000,
        application_policy=APPLICATION_POLICY,
        task_instruction=TASK_INSTRUCTION,
        source_ids=(source["document_id"],),
        presentation_revision_ids=(source["source_revision_id"],),
        rehearsal_session_ids=(source["session_id"],),
    )


def objection_context_size(request: ReasoningRequest) -> int:
    return (
        len(request.serialized_input())
        + len(APPLICATION_POLICY)
        + len(TASK_INSTRUCTION)
        + MAX_TRUSTED_CONTENT_OVERHEAD_CHARS
    )


class RehearsalObjectionContext:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def prepare(
        self, params: dict[str, Any], *, window_privacy_mode: str | None = None
    ) -> dict[str, Any]:
        # Historical reconstruction only: this never grants authority to invoke
        # a provider with an old policy. Public selection fields remain unchanged.
        if window_privacy_mode is not None and window_privacy_mode not in PRIVACY_MODES:
            raise invalid_request("The recorded window privacy mode is invalid.")
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "session_id",
                "slide_id",
                "offset",
                "limit",
            },
        )
        s = self._semantics
        session_id = s._uuid_field(params.get("session_id"), "session_id")
        slide_id = s._uuid_field(params.get("slide_id"), "slide_id")
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if type(offset) is not int or not 0 <= offset <= MAX_RUN_UTTERANCES_PER_SESSION:
            raise invalid_request("Choose a valid objection-window offset.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise invalid_request("Choose between 1 and 20 objection windows per page.")
        scope = {
            "project_id": params.get("project_id"),
            "document_id": params.get("document_id"),
            "revision_id": params.get("expected_revision_id"),
        }
        project, document, revision, current = s._workspace_sources.read_revision_inventory(scope)

        def recording() -> tuple[dict[str, Any], list[dict[str, Any]]]:
            with s._storage.project_database(project) as connection:
                owner = connection.execute(
                    "SELECT s.presentation_revision_id,s.status,p.privacy_mode "
                    "FROM sessions s JOIN presentation_revisions r "
                    "ON r.id=s.presentation_revision_id "
                    "JOIN project p ON p.id=s.project_id WHERE s.id=? AND s.project_id=? "
                    "AND s.mode='run' AND s.status!='active' AND r.presentation_id=?",
                    (session_id, project, document),
                ).fetchone()
                if owner is None:
                    raise CoreDomainError(
                        "REHEARSAL_ANALYSIS_UNAVAILABLE",
                        "Choose an ended Run bound to this presentation.",
                    )
                rows = connection.execute(
                    "SELECT id,text,actor,start_ms,end_ms,slide_ordinal FROM utterances "
                    "WHERE session_id=? AND is_final=1 "
                    "ORDER BY COALESCE(start_ms,2147483647),id LIMIT ?",
                    (session_id, MAX_RUN_UTTERANCES_PER_SESSION + 1),
                ).fetchall()
            if len(rows) > MAX_RUN_UTTERANCES_PER_SESSION:
                raise invalid_request("The recording exceeds its utterance limit.")
            return dict(owner), [dict(row) for row in rows]

        owner, rows = recording()
        source_revision = str(owner["presentation_revision_id"])
        source = (
            current
            if source_revision == revision
            else s._workspace_sources.read_revision_inventory(
                {**scope, "revision_id": source_revision}, current_only=False
            )[-1]
        )
        source_slide = next((slide for slide in source.slides if slide.slide_id == slide_id), None)
        if source_slide is None:
            raise invalid_request("The selected slide is not in this rehearsal snapshot.")
        native_scope = {
            "document_id": document,
            "session_id": session_id,
            "source_revision_id": source_revision,
            "source_sha256": source.source_sha256,
            "slide_id": slide_id,
            "source_slide_number": source_slide.ordinal,
        }
        speech: list[dict[str, Any]] = []
        unmapped = 0
        actors: dict[str, int] = {}
        ordinals = {slide.ordinal for slide in source.slides}
        for row in rows:
            ordinal = row["slide_ordinal"]
            if ordinal is not None and (type(ordinal) is not int or not 1 <= ordinal <= 5000):
                raise invalid_request("The recording contains an invalid slide observation.")
            if ordinal not in ordinals:
                unmapped += 1
            if ordinal != source_slide.ordinal:
                continue
            actor, text = row["actor"], row["text"]
            if actor not in {"user", "audience_profile", "ai_coach", "unknown_audience"}:
                raise invalid_request("The recording contains an invalid actor label.")
            if (
                not isinstance(text, str)
                or not text.strip()
                or "\x00" in text
                or len(text) > MAX_FINAL_UTTERANCE_CHARS
            ):
                raise invalid_request("The recorded utterance is invalid or exceeds its bound.")
            for field in ("start_ms", "end_ms"):
                if row[field] is not None and (type(row[field]) is not int or row[field] < 0):
                    raise invalid_request("The recording contains invalid timing.")
            if (
                row["start_ms"] is not None
                and row["end_ms"] is not None
                and row["end_ms"] < row["start_ms"]
            ):
                raise invalid_request("The recording ends before it starts.")
            actors[actor] = actors.get(actor, 0) + 1
            speech.append(
                {
                    "utterance_id": s._uuid_field(row["id"], "utterance_id"),
                    "text": text,
                    "sha256": digest(text),
                    "actor": actor,
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                }
            )
        windows: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []

        def size(items: list[dict[str, Any]]) -> int:
            return objection_context_size(
                objection_request(native_scope, items, window_privacy_mode or owner["privacy_mode"])
            )

        def flush() -> None:
            if pending:
                windows.append(
                    {
                        "index": len(windows),
                        "utterances": list(pending),
                        "serialized_context_chars": size(pending),
                    }
                )
                pending.clear()

        for utterance in speech:
            if len(pending) >= 4 or size([*pending, utterance]) > MAX_TOTAL_CONTEXT_CHARS:
                flush()
            if size([utterance]) > MAX_TOTAL_CONTEXT_CHARS:
                raise invalid_request("This escaped utterance cannot fit one objection request.")
            pending.append(utterance)
        flush()
        with s._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
        if recording() != (owner, rows):
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED",
                "The recording changed while preparing objection review.",
                retryable=True,
            )
        current_slide = next(
            (slide for slide in current.slides if slide.slide_id == slide_id), None
        )
        return {
            **native_scope,
            "revision_id": revision,
            "current_slide_number": current_slide.ordinal if current_slide else None,
            "context_sha256": digest(
                json.dumps(
                    {"source": native_scope, "speech": speech}, sort_keys=True, ensure_ascii=False
                )
            ),
            "recording_sha256": digest(
                json.dumps(
                    {
                        "session": [session_id, project, source_revision, "run", owner["status"]],
                        "speech": [
                            [
                                row[key]
                                for key in (
                                    "id",
                                    "text",
                                    "actor",
                                    "start_ms",
                                    "end_ms",
                                    "slide_ordinal",
                                )
                            ]
                            for row in rows
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
            "total_utterances": len(speech),
            "total_windows": len(windows),
            "actor_counts": actors,
            "unmapped_session_utterances": unmapped,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(windows),
            "windows": windows[offset : offset + limit],
            "requires_user_review": True,
            "has_recorded_speech": bool(windows),
            "recording_completeness": "unknown",
            "speaker_identity_verified": False,
            "asr_accuracy_verified": False,
        }
