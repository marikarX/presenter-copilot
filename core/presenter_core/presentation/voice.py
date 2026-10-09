"""Transient, review-only voice instructions for Presentation Workspace."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_FINAL_UTTERANCE_CHARS
from presenter_core.presentation.rewrite import MAX_REWRITE_SOURCE_CHARS
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.storage.paths import normalize_project_id


class _WorkspaceASR(Protocol):
    def start(self, params: dict[str, Any], *, owner_mode: str) -> dict[str, Any]: ...

    def stop(self, params: dict[str, Any], *, expected_mode: str) -> dict[str, Any]: ...

    def cancel(self, params: dict[str, Any], *, expected_mode: str) -> dict[str, Any]: ...

    def active_owner_details(self) -> tuple[str, str, str, str] | None: ...


@dataclass(frozen=True)
class _VoiceContext:
    project_id: str
    document_id: str | None
    revision_id: str | None
    slide_number: int | None
    object_id: str | None
    capture_id: str
    intent: str = "rewrite"
    scope: str = "slide"


class PresentationWorkspaceVoiceService:
    """Own an ASR capture only long enough to review one grounded edit instruction."""

    OWNER_MODE = "presentation_workspace"

    def __init__(self, sources: PresentationWorkspaceSourceService) -> None:
        self._sources = sources
        self._asr: _WorkspaceASR | None = None
        self._lock = threading.RLock()
        self._captures: dict[str, _VoiceContext] = {}

    def attach_asr(self, asr: _WorkspaceASR) -> None:
        with self._lock:
            if self._asr is not None:
                raise RuntimeError("Workspace voice ASR is already attached.")
            self._asr = asr

    def validate_asr_session(
        self, project_id: str, capture_id: str, owner_mode: str | None
    ) -> dict[str, Any]:
        with self._lock:
            context = self._captures.get(capture_id)
        if owner_mode != self.OWNER_MODE or context is None or context.project_id != project_id:
            raise CoreDomainError(
                "ASR_SESSION_INVALID",
                "The selected Workspace action does not own microphone capture.",
            )
        return {"mode": self.OWNER_MODE}

    def start(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_number",
                "object_id",
                "intent",
                "scope",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        intent, scope = params.get("intent", "rewrite"), params.get("scope", "slide")
        if intent not in ("rewrite", "edit_plan", "outline") or scope not in ("slide", "deck"):
            raise invalid_request("Choose a supported voice intent and scope.")
        if intent == "outline" and (
            scope != "deck"
            or {"document_id", "revision_id", "slide_number", "object_id"}.intersection(params)
        ):
            raise invalid_request("Outline dictation belongs to the project, before deck creation.")
        document_id = (
            self._uuid_field(params.get("document_id"), "document_id")
            if intent != "outline"
            else None
        )
        revision_id = (
            self._uuid_field(params.get("revision_id"), "revision_id")
            if intent != "outline"
            else None
        )
        if intent == "rewrite" and scope != "slide":
            raise invalid_request("Selected-text dictation requires slide scope.")
        if intent == "edit_plan" and "object_id" in params:
            raise invalid_request("General edit dictation does not select a text object.")
        object_id = (
            self._uuid_field(params.get("object_id"), "object_id") if intent == "rewrite" else None
        )
        slide_number = params.get("slide_number") if intent != "outline" else None
        if intent != "outline" and (
            isinstance(slide_number, bool)
            or not isinstance(slide_number, int)
            or not 1 <= slide_number <= 5_000
        ):
            raise invalid_request("slide_number must be between 1 and 5000.", field="slide_number")

        with self._lock:
            if self._captures:
                raise CoreDomainError(
                    "ASR_ALREADY_RUNNING",
                    "Only one microphone capture may be active at a time.",
                    retryable=True,
                )
            asr = self._asr
        if asr is None:
            raise CoreDomainError("ASR_CAPTURE_FAILED", "Workspace voice capture is not available.")

        context = _VoiceContext(
            project_id=project_id,
            document_id=document_id,
            revision_id=revision_id,
            slide_number=slide_number,
            object_id=object_id,
            capture_id=str(uuid.uuid4()),
            intent=intent,
            scope=scope,
        )
        self._assert_selection_current(context)
        with self._lock:
            if self._captures:
                raise CoreDomainError(
                    "ASR_ALREADY_RUNNING",
                    "Only one microphone capture may be active at a time.",
                    retryable=True,
                )
            self._captures[context.capture_id] = context
        try:
            asr.start(
                {"project_id": project_id, "session_id": context.capture_id},
                owner_mode=self.OWNER_MODE,
            )
        except Exception:
            with self._lock:
                self._captures.pop(context.capture_id, None)
            raise
        return {
            "project_id": project_id,
            "capture_id": context.capture_id,
            "document_id": document_id,
            "revision_id": revision_id,
            "capture_state": "running",
        }

    def stop(self, params: dict[str, Any]) -> dict[str, Any]:
        context, asr = self._owned_context(params)
        asr_params = {"project_id": context.project_id, "session_id": context.capture_id}
        try:
            self._assert_selection_current(context)
        except CoreDomainError:
            self._cancel_context(context, asr)
            raise

        try:
            result = asr.stop(asr_params, expected_mode=self.OWNER_MODE)
        except CoreDomainError:
            self._forget_if_not_active(context, asr)
            raise

        try:
            transcript = result.get("transcript")
            if not isinstance(transcript, str) or len(transcript) > MAX_FINAL_UTTERANCE_CHARS:
                raise CoreDomainError(
                    "ASR_TRANSCRIBE_FAILED",
                    "The local transcript could not be returned safely.",
                )
            self._assert_selection_current(context)
        except CoreDomainError:
            with self._lock:
                self._captures.pop(context.capture_id, None)
            raise
        with self._lock:
            self._captures.pop(context.capture_id, None)
        return {
            "project_id": context.project_id,
            "capture_id": context.capture_id,
            "document_id": context.document_id,
            "revision_id": context.revision_id,
            "slide_number": context.slide_number,
            "object_id": context.object_id,
            "intent": context.intent,
            "scope": context.scope,
            "transcript": transcript,
            "recognition_review": result["recognition_review"],
            "stopped": True,
            "cancelled": False,
        }

    def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "capture_id"})
        project_id = self._project_id(params.get("project_id"))
        capture_id = self._uuid_field(params.get("capture_id"), "capture_id")
        with self._lock:
            context = self._captures.get(capture_id)
            asr = self._asr
        if context is None:
            if asr is None:
                result = {"cancelled": False}
            else:
                owner = asr.active_owner_details()
                if owner is not None:
                    if owner[:3] != (project_id, capture_id, self.OWNER_MODE):
                        raise CoreDomainError(
                            "ASR_SESSION_INVALID",
                            "The requested capture does not own the active microphone.",
                        )
                    result = asr.cancel(
                        {"project_id": project_id, "session_id": capture_id},
                        expected_mode=self.OWNER_MODE,
                    )
                else:
                    result = {"cancelled": False}
            return {
                "project_id": project_id,
                "capture_id": capture_id,
                "stopped": True,
                "cancelled": bool(result.get("cancelled", False)),
            }
        if context.project_id != project_id:
            raise CoreDomainError(
                "ASR_SESSION_INVALID", "The requested capture does not belong to this project."
            )
        if asr is None:
            raise CoreDomainError("ASR_CAPTURE_FAILED", "Workspace voice capture is unavailable.")
        result = self._cancel_context(context, asr)
        return {
            "project_id": context.project_id,
            "capture_id": context.capture_id,
            "stopped": True,
            "cancelled": bool(result.get("cancelled", True)),
        }

    def cancel_for_project(self, project_id: str) -> None:
        self._cancel_matching(project_id=project_id)

    def cancel_for_source(self, project_id: str, document_id: str) -> None:
        self._cancel_matching(project_id=project_id, document_id=document_id)

    def cancel_all(self) -> None:
        self._cancel_matching()

    def _cancel_matching(
        self, *, project_id: str | None = None, document_id: str | None = None
    ) -> None:
        with self._lock:
            contexts = tuple(self._captures.values())
            asr = self._asr
        matching = [
            context
            for context in contexts
            if (project_id is None or context.project_id == project_id)
            and (document_id is None or context.document_id == document_id)
        ]
        if not matching:
            return
        if asr is None:
            raise CoreDomainError("ASR_CAPTURE_FAILED", "Workspace voice cleanup is unavailable.")
        for context in matching:
            self._cancel_context(context, asr)

    def _cancel_context(self, context: _VoiceContext, asr: _WorkspaceASR) -> dict[str, Any]:
        try:
            result = asr.cancel(
                {"project_id": context.project_id, "session_id": context.capture_id},
                expected_mode=self.OWNER_MODE,
            )
        except CoreDomainError:
            self._forget_if_not_active(context, asr)
            raise
        with self._lock:
            self._captures.pop(context.capture_id, None)
        return result

    def _owned_context(self, params: dict[str, Any]) -> tuple[_VoiceContext, _WorkspaceASR]:
        reject_unknown_fields(params, {"project_id", "capture_id"})
        project_id = self._project_id(params.get("project_id"))
        capture_id = self._uuid_field(params.get("capture_id"), "capture_id")
        with self._lock:
            context = self._captures.get(capture_id)
            asr = self._asr
        if context is None or context.project_id != project_id:
            raise CoreDomainError(
                "ASR_SESSION_INVALID", "The requested capture does not belong to this project."
            )
        if asr is None:
            raise CoreDomainError("ASR_CAPTURE_FAILED", "Workspace voice capture is unavailable.")
        return context, asr

    def _assert_selection_current(self, context: _VoiceContext) -> None:
        if context.intent == "outline":
            with self._sources._storage.project_database(context.project_id) as connection:
                project = connection.execute(
                    "SELECT id FROM project WHERE id = ?", (context.project_id,)
                ).fetchone()
            if project is None:
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            return
        selected = self._sources.list_text_targets(
            {
                "project_id": context.project_id,
                "document_id": context.document_id,
                "revision_id": context.revision_id,
                "slide_number": context.slide_number,
            }
        )
        # The bounded source reader verifies the exact current head and slide.
        # General plans do not require a replaceable text object: blank slides,
        # object edits, notes and deck-wide requests use the same capture owner.
        if context.intent == "edit_plan":
            return
        targets = selected.get("targets")
        target = (
            next(
                (
                    item
                    for item in targets
                    if isinstance(item, dict) and item.get("object_id") == context.object_id
                ),
                None,
            )
            if isinstance(targets, list)
            else None
        )
        current_text = target.get("current_text") if target is not None else None
        if (
            target is None
            or not (
                target.get("single_run_editable") is True
                or target.get("uniform_run_editable") is True
            )
            or not isinstance(current_text, str)
            or not current_text.strip()
            or len(current_text) > MAX_REWRITE_SOURCE_CHARS
            or "\n" in current_text
            or "\r" in current_text
        ):
            raise CoreDomainError(
                "PRESENTATION_REWRITE_TARGET_UNSUPPORTED",
                "Select a supported text shape before dictating a rewrite instruction.",
            )

    def _forget_if_not_active(self, context: _VoiceContext, asr: _WorkspaceASR) -> None:
        owner = asr.active_owner_details()
        if owner is None or owner[:3] != (
            context.project_id,
            context.capture_id,
            self.OWNER_MODE,
        ):
            with self._lock:
                self._captures.pop(context.capture_id, None)

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _uuid_field(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 64:
            raise invalid_request(f"{field} must be a valid UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a valid UUID.", field=field) from error


__all__ = [
    "PresentationWorkspaceVoiceService",
]
