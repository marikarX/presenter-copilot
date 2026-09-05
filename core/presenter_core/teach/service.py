"""M3 Teach orchestration with durable provenance and bounded provider calls."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Callable
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionResult, ProviderExecutionService
from presenter_core.providers.models import (
    KNOWLEDGE_KINDS,
    ProviderError,
    ReasoningProvider,
    ReasoningRequest,
    validate_provider_output,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.session.service import SessionService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

MAX_TEACH_TEXT_CHARS = 4_000
MAX_KNOWLEDGE_TEXT_CHARS = 1_500
_VOICE_IN_PROGRESS = object()
_VOICE_FAILED = object()
_VOICE_MISSING = object()

EventSink = Callable[[str, dict[str, Any]], None]
VoiceCaptureActive = Callable[[str, str, str | None], bool]
VoiceCaptureStart = Callable[[dict[str, Any], bool], dict[str, Any]]
VoiceCaptureStop = Callable[[dict[str, Any]], dict[str, Any]]


class TeachService:
    """Keep provider suggestions provisional until the user explicitly confirms."""

    def __init__(
        self,
        storage: StorageManager,
        sessions: SessionService,
        retrieval: HybridRetrievalService,
        providers: ProviderService,
        context_builder: ProviderContextBuilder,
        event_sink: EventSink | None = None,
        *,
        provider_execution: ProviderExecutionService | None = None,
        voice_capture_active: VoiceCaptureActive | None = None,
    ) -> None:
        self._storage = storage
        self._sessions = sessions
        self._retrieval = retrieval
        self._providers = providers
        self._context_builder = context_builder
        self._router = ReasoningRouter()
        self._event_sink = event_sink
        self._provider_execution = provider_execution or ProviderExecutionService(
            storage,
            providers,
            event_sink=event_sink,
        )
        self._voice_capture_active = voice_capture_active or (
            lambda _project_id, _session_id, _capture_id: False
        )
        self._voice_guard = threading.RLock()
        self._voice_submission_guard = threading.RLock()
        self._voice_submissions: dict[str, object] = {}
        self._last_voice_submission: dict[tuple[str, str], dict[str, Any]] = {}

    def next_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        session = self._active_teach_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            pending = connection.execute(
                "SELECT id FROM teach_candidates WHERE session_id = ? AND status = 'pending'",
                (session_id,),
            ).fetchone()
            if pending is not None:
                raise CoreDomainError(
                    "TEACH_CANDIDATE_PENDING",
                    "Confirm or reject the current Teach candidate before asking another question.",
                )
            if session["teach_state"] in {"candidate_ready", "awaiting_user"}:
                raise CoreDomainError(
                    "TEACH_ANSWER_PENDING",
                    "Submit and resolve the current Teach answer before asking another question.",
                )
            if session["teach_state"] != "ready_for_prompt":
                raise CoreDomainError(
                    "TEACH_STATE_INVALID",
                    "Teach cannot ask a question from the current session state.",
                    details={"state": session["teach_state"]},
                )
            self._clear_last_voice_submission(project_id, session_id)

        project = self._project_row(project_id)
        effective_privacy_mode = str(project["privacy_mode"])
        provider, health = self._provider_and_health()
        route = self._router.decide(
            task_type="teach_question",
            privacy_mode=effective_privacy_mode,
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )
        focus = "decision_rationale"
        reasoning_status: dict[str, Any] = {"route": route.route.value, "reason": route.reason}
        question: str
        manifest: dict[str, Any] | None = None
        if (
            route.route in {ReasoningRoute.LOCAL_REASONING, ReasoningRoute.REMOTE_REASONING}
            and provider is not None
        ):
            try:
                request, manifest = self._context_builder.build(
                    project_id=project_id,
                    task_type="teach_question",
                    question=None,
                    user_input=None,
                    privacy_mode=effective_privacy_mode,
                    style_policy=str(session["style_policy"]),
                    current_slide=session["current_slide_start"],
                    provider_id=provider.id,
                    allow_private=not provider.leaves_machine,
                )
                execution = self._run_provider(
                    project_id=project_id,
                    session_id=session_id,
                    privacy_mode=effective_privacy_mode,
                    provider=provider,
                    request=request,
                    manifest=manifest,
                )
                provider_result = execution.result
                manifest = execution.context_manifest
                output = validate_provider_output("teach_question", provider_result.output)
                question = str(output["question"])
                focus = str(output["focus"])
                reasoning_status.update(
                    {
                        "provider_id": provider.id,
                        "model_id": provider.model_id,
                        "status": "ready",
                    }
                )
            except ProviderError as error:
                reasoning_status.update(
                    {
                        "route": ReasoningRoute.RETRIEVAL_ONLY.value,
                        "status": "fallback",
                        "provider_error": self._safe_provider_error(error),
                    }
                )
                question, focus = self._fallback_question(project_id)
                route = self._retrieval_only_decision(route, error.code)
        else:
            question, focus = self._fallback_question(project_id)
        utterance_id = self._persist_coach_prompt(
            project_id,
            session_id,
            question,
        )
        self._emit(
            "teach.prompt",
            {
                "project_id": project_id,
                "session_id": session_id,
                "utterance_id": utterance_id,
                "question": question,
                "focus": focus,
                "route": route.route.value,
            },
        )
        result = self._prompt_result(
            session,
            utterance_id,
            question,
            "awaiting_user",
            route=route.route.value,
            focus=focus,
        )
        result["reasoning"] = reasoning_status
        if manifest is not None:
            result["context_manifest"] = manifest
        return result

    def voice_start(
        self, params: dict[str, Any], start_capture: VoiceCaptureStart
    ) -> dict[str, Any]:
        """Start one transient Teach-owned capture without changing Teach state."""
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "local_only", "keep_local"},
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        local_only = params.get("local_only", params.get("keep_local", False))
        if not isinstance(local_only, bool):
            raise invalid_request("local_only must be a boolean.", field="local_only")
        with self._voice_guard:
            session = self._active_teach_session(project_id, session_id)
            self._require_state(session, "awaiting_user")
            if self._voice_capture_active(project_id, session_id, None):
                raise CoreDomainError(
                    "TEACH_VOICE_CAPTURE_ACTIVE",
                    "A Teach microphone capture is already active for this session.",
                    retryable=True,
                )
            capture = start_capture(
                {"project_id": project_id, "session_id": session_id},
                local_only,
            )
        return {
            "project_id": project_id,
            "session_id": session_id,
            "state": str(session["teach_state"]),
            "capture_state": "running",
            "asr_status": capture,
        }

    def voice_stop(
        self,
        params: dict[str, Any],
        stop_capture: VoiceCaptureStop,
        cancel_capture: VoiceCaptureStop | None = None,
    ) -> dict[str, Any]:
        """Stop one capture; ASR supplies the normal Teach submission result."""
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        release_after_state_change = cancel_capture or stop_capture
        with self._voice_guard:
            try:
                session = self._active_teach_session(project_id, session_id)
            except CoreDomainError as error:
                if self._voice_capture_active(project_id, session_id, None):
                    release_after_state_change({"project_id": project_id, "session_id": session_id})
                    raise CoreDomainError(
                        "TEACH_STATE_CHANGED_DURING_CAPTURE",
                        "The Teach session changed before voice finalization completed.",
                    ) from error
                raise
            cached = self._cached_last_voice_submission(project_id, session_id)
            capture_active = self._voice_capture_active(project_id, session_id, None)
            if cached is not None:
                if capture_active:
                    capture = stop_capture({"project_id": project_id, "session_id": session_id})
                    submission = capture.get("submission")
                    if isinstance(submission, dict):
                        return self._voice_stop_result(project_id, session_id, submission)
                return self._voice_stop_result(
                    project_id,
                    session_id,
                    cached,
                    idempotent=True,
                )
            if not capture_active:
                if session["teach_state"] != "awaiting_user":
                    raise CoreDomainError(
                        "TEACH_STATE_CHANGED_DURING_CAPTURE",
                        "The Teach session changed before voice finalization completed.",
                    )
                raise CoreDomainError(
                    "TEACH_VOICE_NOT_ACTIVE",
                    "No Teach microphone capture is active for this session.",
                    retryable=True,
                )
            if session["teach_state"] != "awaiting_user":
                release_after_state_change({"project_id": project_id, "session_id": session_id})
                raise CoreDomainError(
                    "TEACH_STATE_CHANGED_DURING_CAPTURE",
                    "The Teach session changed before voice finalization completed.",
                )
            capture = stop_capture({"project_id": project_id, "session_id": session_id})
            submission = capture.get("submission")
            if isinstance(submission, dict):
                return self._voice_stop_result(project_id, session_id, submission)
            cached = self._cached_last_voice_submission(project_id, session_id)
            if cached is not None:
                return self._voice_stop_result(
                    project_id,
                    session_id,
                    cached,
                    idempotent=True,
                )
            return {
                "project_id": project_id,
                "session_id": session_id,
                "state": str(session["teach_state"]),
                "capture_state": "stopped",
                "submission": None,
            }

    def voice_cancel(
        self, params: dict[str, Any], cancel_capture: VoiceCaptureStop
    ) -> dict[str, Any]:
        """Discard transient speech and leave an unanswered Teach prompt intact."""
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        with self._voice_guard:
            try:
                session = self._active_teach_session(project_id, session_id)
            except CoreDomainError as error:
                if self._voice_capture_active(project_id, session_id, None):
                    cancel_capture({"project_id": project_id, "session_id": session_id})
                    raise CoreDomainError(
                        "TEACH_STATE_CHANGED_DURING_CAPTURE",
                        "The Teach session changed before voice cancellation completed.",
                    ) from error
                raise
            cached = self._has_last_voice_submission(project_id, session_id)
            capture_active = self._voice_capture_active(project_id, session_id, None)
            if cached:
                if capture_active:
                    cancel_capture({"project_id": project_id, "session_id": session_id})
                raise CoreDomainError(
                    "TEACH_VOICE_SUBMISSION_ALREADY_FINALIZED",
                    "The Teach voice answer has already been finalized.",
                )
            if not capture_active:
                if session["teach_state"] != "awaiting_user":
                    raise CoreDomainError(
                        "TEACH_STATE_CHANGED_DURING_CAPTURE",
                        "The Teach session changed before voice cancellation completed.",
                    )
                raise CoreDomainError(
                    "TEACH_VOICE_NOT_ACTIVE",
                    "No Teach microphone capture is active for this session.",
                    retryable=True,
                )
            if session["teach_state"] != "awaiting_user":
                cancel_capture({"project_id": project_id, "session_id": session_id})
                raise CoreDomainError(
                    "TEACH_STATE_CHANGED_DURING_CAPTURE",
                    "The Teach session changed before voice cancellation completed.",
                )
            cancel_capture({"project_id": project_id, "session_id": session_id})
            return {
                "project_id": project_id,
                "session_id": session_id,
                "state": "awaiting_user",
                "capture_state": "stopped",
                "cancelled": True,
            }

    def submit_voice_transcript(
        self,
        project_id: str,
        session_id: str,
        capture_id: str,
        text: str,
        *,
        local_only: bool,
    ) -> dict[str, Any]:
        """Submit exactly one final transcript through the typed Teach path."""
        if not isinstance(capture_id, str) or not capture_id:
            raise CoreDomainError(
                "TEACH_VOICE_SUBMISSION_FAILED", "The voice capture identity is invalid."
            )
        if not isinstance(local_only, bool):
            raise CoreDomainError(
                "TEACH_VOICE_SUBMISSION_FAILED", "The voice privacy flag is invalid."
            )
        with self._voice_submission_guard:
            existing = self._voice_submissions.get(capture_id, _VOICE_MISSING)
            if existing is not _VOICE_MISSING:
                raise CoreDomainError(
                    "TEACH_VOICE_SUBMISSION_ALREADY_FINALIZED",
                    "This Teach voice capture has already been finalized.",
                )
            self._voice_submissions[capture_id] = _VOICE_IN_PROGRESS
        try:
            if not isinstance(text, str) or not text.strip():
                raise CoreDomainError(
                    "TEACH_VOICE_EMPTY_TRANSCRIPT",
                    "The local ASR final did not contain an answer.",
                    retryable=True,
                )
            result = self.submit_text(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "text": text,
                    "local_only": local_only,
                },
                voice_capture_id=capture_id,
            )
        except CoreDomainError as error:
            if error.code in {
                "TEACH_STATE_INVALID",
                "TEACH_ANSWER_PENDING",
                "SESSION_NOT_ACTIVE",
                "SESSION_NOT_FOUND",
            }:
                error = CoreDomainError(
                    "TEACH_STATE_CHANGED_DURING_CAPTURE",
                    "The Teach session changed before voice finalization completed.",
                )
            with self._voice_submission_guard:
                self._voice_submissions[capture_id] = _VOICE_FAILED
                self._trim_voice_submissions()
            raise error
        except Exception as error:
            with self._voice_submission_guard:
                self._voice_submissions[capture_id] = _VOICE_FAILED
                self._trim_voice_submissions()
            raise CoreDomainError(
                "TEACH_VOICE_SUBMISSION_FAILED",
                "The finalized Teach answer could not be submitted.",
                retryable=False,
            ) from error

        with self._voice_submission_guard:
            self._voice_submissions[capture_id] = dict(result)
            self._trim_voice_submissions()
            self._last_voice_submission[(project_id, session_id)] = dict(result)
        try:
            self._emit(
                "teach.voice_finalized",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "state": result.get("state", "candidate_ready"),
                    "source_utterance_id": result.get("source_utterance_id"),
                    "candidate_id": (
                        result["candidate"].get("id")
                        if isinstance(result.get("candidate"), dict)
                        else None
                    ),
                },
            )
        except Exception:
            # A UI event sink failure must not make a committed answer
            # retryable or permit a second user utterance.
            pass
        return dict(result)

    def submit_text(
        self, params: dict[str, Any], *, voice_capture_id: str | None = None
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "text", "local_only", "keep_local"},
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        text = self._bounded_text(params.get("text"), "text", MAX_TEACH_TEXT_CHARS)
        local_only = params.get("local_only", params.get("keep_local", False))
        if not isinstance(local_only, bool):
            raise invalid_request("local_only must be a boolean.", field="local_only")
        (
            session,
            project,
            effective_privacy_mode,
            source_utterance_id,
            created_at,
            current_prompt,
        ) = self._prepare_text_submission(
            project_id,
            session_id,
            text,
            voice_capture_id,
        )

        provider, health = self._provider_and_health()
        route = self._router.decide(
            task_type="teach_candidate",
            privacy_mode=effective_privacy_mode,
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
            local_only_submission=local_only,
        )
        response: dict[str, Any] = {
            "project_id": project_id,
            "session_id": session_id,
            "source_utterance_id": source_utterance_id,
            "state": "candidate_ready",
            "candidate": None,
            "direct_save_available": True,
            "route": route.route.value,
            "local_only": local_only,
        }
        if current_prompt is not None:
            response["prompt_utterance_id"] = current_prompt["id"]

        if (
            route.route
            in {
                ReasoningRoute.LOCAL_REASONING,
                ReasoningRoute.REMOTE_REASONING,
            }
            and provider is not None
        ):
            manifest: dict[str, Any] | None = None
            try:
                request, manifest = self._context_builder.build(
                    project_id=project_id,
                    task_type="teach_candidate",
                    question=str(current_prompt["text"]) if current_prompt is not None else None,
                    user_input=text,
                    privacy_mode=effective_privacy_mode,
                    style_policy=str(session["style_policy"]),
                    current_slide=session["current_slide_start"],
                    provider_id=provider.id,
                    allow_private=not provider.leaves_machine,
                )
                execution = self._run_provider(
                    project_id=project_id,
                    session_id=session_id,
                    privacy_mode=effective_privacy_mode,
                    provider=provider,
                    request=request,
                    manifest=manifest,
                )
                result = execution.result
                manifest = execution.context_manifest
                output = validate_provider_output("teach_candidate", result.output)
                candidate_id = str(uuid.uuid4())
                with self._storage.project_database(project_id) as connection:
                    connection.execute(
                        """
                        INSERT INTO teach_candidates (
                            id, session_id, source_utterance_id, proposed_kind,
                            proposed_text, provider_run_id, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            candidate_id,
                            session_id,
                            source_utterance_id,
                            output["kind"],
                            output["text"],
                            execution.provider_run_id,
                            created_at,
                        ),
                    )
                    connection.execute(
                        "UPDATE sessions SET teach_state = 'candidate_ready' WHERE id = ?",
                        (session_id,),
                    )
                    connection.commit()
                response["candidate"] = {
                    "id": candidate_id,
                    "source_utterance_id": source_utterance_id,
                    "proposed_kind": output["kind"],
                    "proposed_text": output["text"],
                    "follow_up_question": output["follow_up_question"],
                    "provisional": True,
                    "created_by": "ai_suggestion",
                }
                response["reasoning"] = {
                    "route": route.route.value,
                    "provider_id": provider.id,
                    "model_id": provider.model_id,
                    "status": "ready",
                }
                response["context_manifest"] = manifest
                self._emit(
                    "teach.knowledge_candidate",
                    {
                        "project_id": project_id,
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "source_utterance_id": source_utterance_id,
                        "proposed_kind": output["kind"],
                        "provisional": True,
                    },
                )
                return response
            except ProviderError as error:
                response["reasoning"] = {
                    "route": ReasoningRoute.RETRIEVAL_ONLY.value,
                    "status": "fallback",
                    "provider_error": self._safe_provider_error(error),
                }
        else:
            response["reasoning"] = {
                "route": route.route.value,
                "status": "direct_save_only",
                "reason": route.reason,
            }
        return response

    def discard_answer(self, params: dict[str, Any]) -> dict[str, Any]:
        """Discard only the current direct-answer decision without deleting history."""
        reject_unknown_fields(params, {"project_id", "session_id", "source_utterance_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        source_utterance_id = self._uuid_param(params, "source_utterance_id")
        session = self._active_teach_session(project_id, session_id)
        self._require_state(session, "candidate_ready")
        with self._storage.project_database(project_id) as connection:
            pending_candidate = connection.execute(
                "SELECT id FROM teach_candidates "
                "WHERE session_id = ? AND status = 'pending' LIMIT 1",
                (session_id,),
            ).fetchone()
            if pending_candidate is not None:
                raise CoreDomainError(
                    "TEACH_CANDIDATE_PENDING",
                    "Reject the current Teach candidate before discarding an answer.",
                )
            current_answer = self._current_pending_user_utterance(connection, session_id)
            if current_answer is None or str(current_answer["id"]) != source_utterance_id:
                raise CoreDomainError(
                    "TEACH_SOURCE_INVALID",
                    "The discarded answer must be the current pending Teach answer.",
                )
            transitioned = connection.execute(
                """
                UPDATE sessions
                SET teach_state = 'ready_for_prompt'
                WHERE id = ? AND project_id = ? AND teach_state = 'candidate_ready'
                """,
                (session_id, project_id),
            )
            if transitioned.rowcount != 1:
                connection.rollback()
                raise CoreDomainError(
                    "TEACH_STATE_INVALID",
                    "The Teach answer arrived after the session state changed.",
                )
            connection.commit()
        self._clear_last_voice_submission(project_id, session_id)
        return {
            "project_id": project_id,
            "session_id": session_id,
            "source_utterance_id": source_utterance_id,
            "discarded": True,
            "state": "ready_for_prompt",
        }

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return only the bounded, recoverable state of one active Teach session."""
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        session = self._active_teach_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            prompt = connection.execute(
                """
                SELECT id, text
                FROM utterances
                WHERE session_id = ? AND actor = 'ai_coach'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            pending_answer = connection.execute(
                """
                SELECT id, text
                FROM utterances
                WHERE session_id = ? AND actor = 'user'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            candidate = connection.execute(
                """
                SELECT * FROM teach_candidates
                WHERE session_id = ? AND status = 'pending'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            state = str(session["teach_state"])
            prompt_result = (
                {"utterance_id": str(prompt["id"]), "text": str(prompt["text"])}
                if state in {"awaiting_user", "candidate_ready"} and prompt is not None
                else None
            )
            pending_result = (
                {
                    "source_utterance_id": str(pending_answer["id"]),
                    "text": str(pending_answer["text"]),
                }
                if state == "candidate_ready" and pending_answer is not None
                else None
            )
            candidate_result = (
                self._candidate_dict(candidate)
                if state == "candidate_ready" and candidate is not None
                else None
            )
        return {
            "session_id": session_id,
            "state": state,
            "prompt": prompt_result,
            "pending_answer": pending_result,
            "candidate": candidate_result,
        }

    def confirm_knowledge_item(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "session_id",
                "candidate_id",
                "source_utterance_id",
                "text",
                "kind",
                "preferred",
                "private",
                "use_live",
                "use_rehearsal",
            },
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        session = self._active_teach_session(project_id, session_id)
        self._require_state(session, "candidate_ready")
        candidate_id = self._optional_uuid(params.get("candidate_id"), "candidate_id")
        source_utterance_id = self._optional_uuid(
            params.get("source_utterance_id"), "source_utterance_id"
        )
        preferred = self._flag(params, "preferred", False)
        private = self._flag(params, "private", False)
        use_live = self._flag(params, "use_live", True)
        use_rehearsal = self._flag(params, "use_rehearsal", True)
        with self._storage.project_database(project_id) as connection:
            candidate: sqlite3.Row | None = None
            if candidate_id is None:
                pending_candidate = connection.execute(
                    "SELECT id FROM teach_candidates "
                    "WHERE session_id = ? AND status = 'pending' LIMIT 1",
                    (session_id,),
                ).fetchone()
                if pending_candidate is not None:
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_PENDING",
                        "Confirm the current Teach candidate by id before saving an answer.",
                    )
            if candidate_id is not None:
                candidate = connection.execute(
                    """
                    SELECT tc.*, u.actor, u.session_id AS utterance_session_id
                    FROM teach_candidates AS tc
                    JOIN utterances AS u ON u.id = tc.source_utterance_id
                    WHERE tc.id = ? AND tc.session_id = ? AND u.session_id = ?
                    """,
                    (candidate_id, session_id, session_id),
                ).fetchone()
                if candidate is None:
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_NOT_FOUND",
                        "The Teach candidate was not found in this session.",
                    )
                if candidate["status"] != "pending":
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_NOT_PENDING",
                        "The Teach candidate has already been decided.",
                    )
                if candidate["actor"] != "user":
                    raise CoreDomainError(
                        "TEACH_SOURCE_INVALID",
                        "Only a user utterance can support confirmed knowledge.",
                    )
                candidate_source_id = str(candidate["source_utterance_id"])
                if source_utterance_id is not None and source_utterance_id != candidate_source_id:
                    raise CoreDomainError(
                        "TEACH_SOURCE_INVALID",
                        "The confirmation source must match the current Teach candidate.",
                    )
                source_utterance_id = candidate_source_id
            if source_utterance_id is None:
                source = connection.execute(
                    """
                    SELECT id, actor, session_id, text FROM utterances
                    WHERE session_id = ? AND actor = 'user'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            else:
                source = connection.execute(
                    "SELECT id, actor, session_id, text FROM utterances WHERE id = ?",
                    (source_utterance_id,),
                ).fetchone()
            if source is None or source["session_id"] != session_id or source["actor"] != "user":
                raise CoreDomainError(
                    "TEACH_SOURCE_INVALID",
                    "The confirmation source must be a user utterance in this Teach session.",
                )
            current_answer = self._current_pending_user_utterance(connection, session_id)
            if current_answer is None or str(current_answer["id"]) != str(source["id"]):
                raise CoreDomainError(
                    "TEACH_SOURCE_INVALID",
                    "The confirmation source must be the current pending Teach answer.",
                )
            final_text = params.get("text")
            if final_text is None and candidate is not None:
                final_text = candidate["proposed_text"]
            if final_text is None:
                final_text = source["text"]
            final_text = self._bounded_text(final_text, "text", MAX_KNOWLEDGE_TEXT_CHARS)
            kind = params.get(
                "kind", candidate["proposed_kind"] if candidate is not None else "rationale"
            )
            if not isinstance(kind, str) or kind not in KNOWLEDGE_KINDS:
                raise invalid_request("kind is not supported.", field="kind")
            now = utc_now()
            statement_id = str(uuid.uuid4())
            existing_statement = connection.execute(
                """
                SELECT id FROM user_statements
                WHERE project_id = ? AND source_utterance_id = ? AND text = ?
                ORDER BY created_at LIMIT 1
                """,
                (project_id, source["id"], source["text"]),
            ).fetchone()
            if existing_statement is not None:
                statement_id = str(existing_statement["id"])
            else:
                connection.execute(
                    """
                    INSERT INTO user_statements
                        (id, project_id, origin_session_id, source_utterance_id, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (statement_id, project_id, session_id, source["id"], source["text"], now),
                )
            knowledge_id = str(uuid.uuid4())
            created_by = "ai_suggested_user_confirmed" if candidate is not None else "user"
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    id, project_id, kind, text, use_live, use_rehearsal,
                    preferred, private, created_by, origin_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_id,
                    project_id,
                    kind,
                    final_text,
                    int(use_live),
                    int(use_rehearsal),
                    int(preferred),
                    int(private),
                    created_by,
                    session_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_evidence (knowledge_item_id, provenance_type, provenance_id)
                VALUES (?, 'user_statement', ?)
                """,
                (knowledge_id, statement_id),
            )
            if candidate is not None:
                connection.execute(
                    """
                    UPDATE teach_candidates
                    SET status = 'confirmed', knowledge_item_id = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (knowledge_id, candidate_id),
                )
            connection.execute(
                "UPDATE sessions SET teach_state = 'ready_for_prompt' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
            knowledge = self._knowledge_dict(connection, knowledge_id)
            statement = connection.execute(
                "SELECT * FROM user_statements WHERE id = ?", (statement_id,)
            ).fetchone()
            assert statement is not None
            statement_dict = self._statement_dict(statement)
        self._clear_last_voice_submission(project_id, session_id)

        semantic_sync = self._synchronize_semantic_index(project_id)
        self._emit(
            "project.index_ready",
            {
                "project_id": project_id,
                "index_kind": "knowledge_item",
                "knowledge_item_id": knowledge_id,
                "status": semantic_sync["status"],
            },
        )
        return {
            "knowledge_item": knowledge,
            "user_statement": statement_dict,
            "semantic_sync": semantic_sync,
            "state": "ready_for_prompt",
        }

    def reject_knowledge_item(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "candidate_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        session = self._active_teach_session(project_id, session_id)
        self._require_state(session, "candidate_ready")
        candidate_id = self._uuid_param(params, "candidate_id")
        with self._storage.project_database(project_id) as connection:
            candidate = connection.execute(
                "SELECT * FROM teach_candidates WHERE id = ? AND session_id = ?",
                (candidate_id, session_id),
            ).fetchone()
            if candidate is None:
                raise CoreDomainError(
                    "TEACH_CANDIDATE_NOT_FOUND", "The Teach candidate was not found."
                )
            if candidate["status"] != "pending":
                raise CoreDomainError(
                    "TEACH_CANDIDATE_NOT_PENDING", "The Teach candidate has already been decided."
                )
            connection.execute(
                "UPDATE teach_candidates SET status = 'rejected' WHERE id = ?",
                (candidate_id,),
            )
            connection.execute(
                "UPDATE sessions SET teach_state = 'ready_for_prompt' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        self._clear_last_voice_submission(project_id, session_id)
        return {
            "project_id": project_id,
            "session_id": session_id,
            "candidate_id": candidate_id,
            "rejected": True,
            "state": "ready_for_prompt",
        }

    def _run_provider(
        self,
        *,
        project_id: str,
        session_id: str,
        privacy_mode: str,
        provider: ReasoningProvider,
        request: ReasoningRequest,
        manifest: dict[str, Any],
    ) -> ProviderExecutionResult:
        """Delegate every Teach provider call to the shared execution boundary."""
        del privacy_mode, manifest
        return self._provider_execution.execute(
            project_id=project_id,
            session_id=session_id,
            provider=provider,
            request=request,
        )

    def _synchronize_semantic_index(self, project_id: str) -> dict[str, Any]:
        # Confirmation changes the current mapping set only if a rebuild
        # succeeds. Invalidate first so a failed rebuild cannot reuse the old
        # generation's count after the entity set returns to a prior size.
        self._retrieval.invalidate_project_mappings(project_id)
        with self._storage.project_database(project_id) as connection:
            active = connection.execute(
                "SELECT id FROM embedding_generations WHERE is_active = 1"
            ).fetchone()
        if active is None:
            return {"status": "not_built", "embedded_count": 0, "reused_count": 0}
        try:
            rebuilt = self._retrieval.rebuild({"project_id": project_id})
            return {
                "status": "ready",
                "embedded_count": rebuilt["embedded_count"],
                "reused_count": rebuilt["reused_count"],
                "generation_id": rebuilt["generation_id"],
            }
        except CoreDomainError as error:
            return {"status": "partial", "error_code": error.code}
        except Exception:
            # The confirmed KnowledgeItem is already durable. An unexpected
            # local model/index failure must not turn confirmation into a
            # failed save; the next explicit rebuild can repair the index.
            return {"status": "partial", "error_code": "INDEX_SYNC_FAILED"}

    def _prepare_text_submission(
        self,
        project_id: str,
        session_id: str,
        text: str,
        voice_capture_id: str | None,
    ) -> tuple[sqlite3.Row, sqlite3.Row, str, str, str, sqlite3.Row]:
        """Atomically authorize and persist the single normal Teach answer."""
        with self._voice_guard:
            capture_active = self._voice_capture_active(project_id, session_id, None)
            if voice_capture_id is None and capture_active:
                raise CoreDomainError(
                    "TEACH_VOICE_CAPTURE_ACTIVE",
                    "Stop or cancel the active Teach microphone capture before typing an answer.",
                    retryable=True,
                )
            if voice_capture_id is not None and not self._voice_capture_active(
                project_id, session_id, voice_capture_id
            ):
                raise CoreDomainError(
                    "TEACH_STATE_CHANGED_DURING_CAPTURE",
                    "The Teach voice capture is no longer active.",
                )
            session = self._active_teach_session(project_id, session_id)
            self._require_state(session, "awaiting_user")
            project = self._project_row(project_id)
            source_utterance_id = str(uuid.uuid4())
            created_at = utc_now()
            with self._storage.project_database(project_id) as connection:
                current_prompt = connection.execute(
                    """
                    SELECT id, text FROM utterances
                    WHERE session_id = ? AND actor = 'ai_coach'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
                if current_prompt is None:
                    raise CoreDomainError(
                        "TEACH_STATE_INVALID",
                        "The current Teach answer has no active prompt.",
                    )
                connection.execute(
                    """
                    INSERT INTO utterances (id, session_id, actor, text, created_at, is_final)
                    VALUES (?, ?, 'user', ?, ?, 1)
                    """,
                    (source_utterance_id, session_id, text, created_at),
                )
                transitioned = connection.execute(
                    """
                    UPDATE sessions
                    SET teach_state = 'candidate_ready'
                    WHERE id = ? AND project_id = ? AND teach_state = 'awaiting_user'
                    """,
                    (session_id, project_id),
                )
                if transitioned.rowcount != 1:
                    connection.rollback()
                    raise CoreDomainError(
                        "TEACH_STATE_INVALID",
                        "The Teach answer arrived after the session state changed.",
                    )
                connection.commit()
            return (
                session,
                project,
                str(project["privacy_mode"]),
                source_utterance_id,
                created_at,
                cast(sqlite3.Row, current_prompt),
            )

    def _voice_stop_result(
        self,
        project_id: str,
        session_id: str,
        submission: dict[str, Any],
        *,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "project_id": project_id,
            "session_id": session_id,
            "state": str(submission.get("state", "candidate_ready")),
            "capture_state": "stopped",
            "submission": dict(submission),
        }
        try:
            state = self.get_state({"project_id": project_id, "session_id": session_id})
            pending = state.get("pending_answer")
            if isinstance(pending, dict) and isinstance(pending.get("text"), str):
                result["answer_text"] = pending["text"]
        except CoreDomainError:
            pass
        if idempotent:
            result["idempotent"] = True
        return result

    def _trim_voice_submissions(self) -> None:
        while len(self._voice_submissions) > 64:
            oldest = next(iter(self._voice_submissions))
            del self._voice_submissions[oldest]

    def _cached_last_voice_submission(
        self, project_id: str, session_id: str
    ) -> dict[str, Any] | None:
        with self._voice_submission_guard:
            cached = self._last_voice_submission.get((project_id, session_id))
            return dict(cached) if cached is not None else None

    def _has_last_voice_submission(self, project_id: str, session_id: str) -> bool:
        with self._voice_submission_guard:
            return (project_id, session_id) in self._last_voice_submission

    def _clear_last_voice_submission(self, project_id: str, session_id: str) -> None:
        with self._voice_submission_guard:
            self._last_voice_submission.pop((project_id, session_id), None)

    def _active_teach_session(self, project_id: str, session_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")
        if row["mode"] != "teach":
            raise CoreDomainError("MODE_NOT_IMPLEMENTED", "Only Teach sessions are supported.")
        if row["status"] != "active":
            raise CoreDomainError(
                "SESSION_NOT_ACTIVE", "Teach actions require an active Teach session."
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _require_state(session: sqlite3.Row, expected: str) -> None:
        """Enforce Teach transitions in core, independently of renderer controls."""
        state = str(session["teach_state"])
        if state == expected:
            return
        if expected in {"awaiting_user", "candidate_ready"} and state == "candidate_ready":
            raise CoreDomainError(
                "TEACH_ANSWER_PENDING",
                "Resolve the current Teach answer before submitting another one.",
                details={"state": state, "expected": expected},
            )
        raise CoreDomainError(
            "TEACH_STATE_INVALID",
            "The Teach action is not valid in the current session state.",
            details={"state": state, "expected": expected},
        )

    @staticmethod
    def _current_pending_user_utterance(
        connection: sqlite3.Connection, session_id: str
    ) -> sqlite3.Row | None:
        """Return the latest user answer, which is the only direct-save source allowed."""
        row = connection.execute(
            """
            SELECT id, actor, session_id, text
            FROM utterances
            WHERE session_id = ? AND actor = 'user'
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _candidate_dict(candidate: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(candidate["id"]),
            "source_utterance_id": str(candidate["source_utterance_id"]),
            "proposed_kind": str(candidate["proposed_kind"]),
            "proposed_text": str(candidate["proposed_text"]),
            "follow_up_question": None,
            "provisional": True,
            "created_by": "ai_suggestion",
        }

    def _project_row(self, project_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return cast(sqlite3.Row, row)

    def _provider_and_health(self) -> tuple[ReasoningProvider | None, Any | None]:
        return self._providers.current_provider_and_health()

    def _fallback_question(self, project_id: str) -> tuple[str, str]:
        retrieval = self._retrieval.query(
            {
                "project_id": project_id,
                "query": "rejected option decision rationale tradeoff risk assumption",
                "limit": 6,
                "usage": "rehearsal",
                "allow_private": True,
            }
        )
        conflicts = retrieval.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            conflict = conflicts[0]
            if isinstance(conflict, dict) and isinstance(conflict.get("subject"), str):
                return (
                    f"The sources disagree about {conflict['subject']}. Which value or context "
                    "is current for this project?",
                    "exact_fact_conflict",
                )
        hits = retrieval.get("hits")
        if isinstance(hits, list) and hits:
            evidence = hits[0].get("evidence") if isinstance(hits[0], dict) else None
            label = evidence.get("label") if isinstance(evidence, dict) else None
            if isinstance(label, str):
                return (
                    f"What made the option described in {label} a poor fit for this project?",
                    "decision_rationale",
                )
        return ("What decision or tradeoff behind this project should I remember?", "tradeoff")

    @staticmethod
    def _retrieval_only_decision(decision: Any, reason: str) -> Any:
        del decision
        from presenter_core.providers.router import RouteDecision

        return RouteDecision(ReasoningRoute.RETRIEVAL_ONLY, reason, None)

    def _persist_coach_prompt(self, project_id: str, session_id: str, question: str) -> str:
        utterance_id = str(uuid.uuid4())
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                "INSERT INTO utterances "
                "(id, session_id, actor, text, created_at, is_final) "
                "VALUES (?, ?, 'ai_coach', ?, ?, 1)",
                (utterance_id, session_id, question, utc_now()),
            )
            connection.execute(
                "UPDATE sessions SET teach_state = 'awaiting_user' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        return utterance_id

    @staticmethod
    def _prompt_result(
        session: sqlite3.Row,
        utterance_id: str,
        question: str,
        state: str,
        *,
        route: str,
        focus: str,
    ) -> dict[str, Any]:
        return {
            "project_id": session["project_id"],
            "session_id": session["id"],
            "state": state,
            "utterance_id": utterance_id,
            "question": question,
            "focus": focus,
            "route": route,
        }

    @staticmethod
    def _knowledge_dict(connection: sqlite3.Connection, knowledge_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (knowledge_id,)
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "KNOWLEDGE_NOT_FOUND", "The project knowledge item was not found."
            )
        evidence = connection.execute(
            "SELECT provenance_type, provenance_id FROM knowledge_evidence "
            "WHERE knowledge_item_id = ?",
            (knowledge_id,),
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
                for item in evidence
            ],
        }

    @staticmethod
    def _statement_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "origin_session_id": row["origin_session_id"],
            "source_utterance_id": row["source_utterance_id"],
            "text": row["text"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _safe_provider_error(error: ProviderError) -> dict[str, Any]:
        return {"code": error.code, "retryable": error.retryable}

    @staticmethod
    def _bounded_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise invalid_request(f"{field} must be a bounded non-empty string.", field=field)
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise invalid_request(f"{field} contains unsupported control characters.", field=field)
        return value.strip()

    @staticmethod
    def _flag(params: dict[str, Any], field: str, default: bool) -> bool:
        value = params.get(field, default)
        if not isinstance(value, bool):
            raise invalid_request(f"{field} must be a boolean.", field=field)
        return value

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
        return TeachService._normalize_uuid(value, field)

    @staticmethod
    def _optional_uuid(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        return TeachService._normalize_uuid(value, field)

    @staticmethod
    def _normalize_uuid(value: str, field: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)
