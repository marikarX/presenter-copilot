"""Verified recorded-speech windows for explicit semantic rehearsal review."""

import json
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_FINAL_UTTERANCE_CHARS, MAX_RUN_UTTERANCES_PER_SESSION
from presenter_core.presentation.claims import digest
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.providers.context import (
    APPLICATION_POLICY,
    MAX_TOTAL_CONTEXT_CHARS,
    MAX_TRUSTED_CONTENT_OVERHEAD_CHARS,
)
from presenter_core.providers.models import ReasoningRequest
from presenter_core.providers.rehearsal_coverage_schema import (
    OUTPUT_SCHEMA,
    TASK_INSTRUCTION,
    TASK_TYPE,
)


def coverage_request(
    scope: dict[str, Any], point: dict[str, Any], speech: list[dict[str, Any]], privacy: str
) -> ReasoningRequest:
    return ReasoningRequest(
        task_type=TASK_TYPE,
        question="Review this selected message against this recorded speech window only.",
        user_input=None,
        current_slide_summary=json.dumps(
            {"source": scope, "selected_message": point, "recorded_speech": speech},
            ensure_ascii=False,
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
        source_ids=(scope["document_id"],),
        presentation_revision_ids=(scope["source_revision_id"],),
        rehearsal_session_ids=(scope["session_id"],),
    )


def coverage_context_size(request: ReasoningRequest) -> int:
    return (
        len(request.serialized_input())
        + len(APPLICATION_POLICY)
        + len(TASK_INSTRUCTION)
        + MAX_TRUSTED_CONTENT_OVERHEAD_CHARS
    )


class RehearsalSemanticContext:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "session_id",
                "slide_id",
                "object_id",
                "quote",
                "offset",
                "limit",
            },
        )
        s = self._semantics
        session_id = s._uuid_field(params.get("session_id"), "session_id")
        slide_id = s._uuid_field(params.get("slide_id"), "slide_id")
        object_id = s._uuid_field(params.get("object_id"), "object_id")
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if type(offset) is not int or not 0 <= offset <= MAX_RUN_UTTERANCES_PER_SESSION:
            raise invalid_request("Choose a valid speech-window offset.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise invalid_request("Choose between 1 and 20 speech windows per page.")
        scope = {
            "project_id": params.get("project_id"),
            "document_id": params.get("document_id"),
            "revision_id": params.get("expected_revision_id"),
        }
        project, document, revision, current = s._workspace_sources.read_revision_inventory(scope)
        with s._storage.project_database(project) as connection:
            session = connection.execute(
                "SELECT s.presentation_revision_id, p.privacy_mode "
                "FROM sessions s JOIN presentation_revisions r ON r.id=s.presentation_revision_id "
                "JOIN project p ON p.id=s.project_id "
                "WHERE s.id=? AND s.project_id=? AND s.mode='run' "
                "AND s.status!='active' AND r.presentation_id=?",
                (session_id, project, document),
            ).fetchone()
            if session is None:
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
        source_revision = str(session["presentation_revision_id"])
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
        targets = cast(
            list[dict[str, Any]],
            source.text_targets(source_slide.ordinal, limit=len(source_slide.objects))[
                "semantic_targets"
            ],
        )
        matches = [t for t in targets if t["object_id"] == object_id]
        if len(matches) != 1:
            raise invalid_request(
                "Choose one represented native object from the rehearsal snapshot."
            )
        target = matches[0]
        text = target["decision_text"]
        quote = params.get("quote", text)
        if (
            not isinstance(quote, str)
            or not quote.strip()
            or len(quote) > 2000
            or text.find(quote) < 0
            or text.find(quote, text.find(quote) + 1) >= 0
        ):
            raise invalid_request("Choose an exact unique message span of at most 2000 characters.")
        point = {
            "object_id": object_id,
            "quote": quote,
            "source_kind": target["source_kind"],
            "object_sha256": digest(text),
            "quote_sha256": digest(quote),
        }
        native_scope = {
            "document_id": document,
            "session_id": session_id,
            "source_revision_id": source_revision,
            "source_sha256": source.source_sha256,
            "slide_id": slide_id,
            "source_slide_number": source_slide.ordinal,
        }
        speech: list[dict[str, Any]] = []
        unmapped = excluded_actors = 0
        source_ordinals = {slide.ordinal for slide in source.slides}
        for row in rows:
            ordinal = row["slide_ordinal"]
            if ordinal is not None and (type(ordinal) is not int or not 1 <= ordinal <= 5000):
                raise invalid_request("The recording contains an invalid slide observation.")
            if ordinal not in source_ordinals:
                unmapped += 1
            if row["actor"] != "user":
                excluded_actors += 1
                continue
            if ordinal != source_slide.ordinal:
                continue
            spoken = row["text"]
            if (
                not isinstance(spoken, str)
                or not spoken.strip()
                or len(spoken) > MAX_FINAL_UTTERANCE_CHARS
            ):
                raise invalid_request("The recorded utterance is invalid or exceeds its bound.")
            for key in ("start_ms", "end_ms"):
                if row[key] is not None and (type(row[key]) is not int or row[key] < 0):
                    raise invalid_request("The recording contains invalid timing.")
            if (
                row["start_ms"] is not None
                and row["end_ms"] is not None
                and row["end_ms"] < row["start_ms"]
            ):
                raise invalid_request("The recording ends before it starts.")
            speech.append(
                {
                    "utterance_id": s._uuid_field(row["id"], "utterance_id"),
                    "text": spoken,
                    "sha256": digest(spoken),
                    "actor": "user",
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                }
            )
        windows: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        privacy = str(session["privacy_mode"])

        def size(items: list[dict[str, Any]]) -> int:
            return coverage_context_size(coverage_request(native_scope, point, items, privacy))

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
                raise invalid_request(
                    "This escaped utterance cannot fit one semantic review request."
                )
            pending.append(utterance)
        flush()
        fingerprint = digest(
            json.dumps(
                {"source": native_scope, "point": point, "speech": speech},
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        current_slide = next(
            (slide for slide in current.slides if slide.slide_id == slide_id), None
        )
        current_targets = (
            cast(
                list[dict[str, Any]],
                current.text_targets(current_slide.ordinal, limit=len(current_slide.objects))[
                    "semantic_targets"
                ],
            )
            if current_slide
            else []
        )
        present = next((t for t in current_targets if t["object_id"] == object_id), None)
        status = (
            "missing"
            if present is None
            else "unchanged"
            if present["source_kind"] == point["source_kind"]
            and digest(present["decision_text"]) == point["object_sha256"]
            else "changed"
        )
        with s._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
        return {
            **native_scope,
            "revision_id": revision,
            "point": point,
            "current_slide_number": current_slide.ordinal if current_slide else None,
            "current_span_status": status,
            "context_sha256": fingerprint,
            "total_utterances": len(speech),
            "total_windows": len(windows),
            "unmapped_session_utterances": unmapped,
            "excluded_actor_utterances": excluded_actors,
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
